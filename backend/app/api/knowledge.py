"""
知识库 CRUD API

端点：
    GET    /api/v1/knowledge/                          — 分页列表（支持关键词/来源/设备/故障标签筛选）
    GET    /api/v1/knowledge/{id}                      — 条目详情（含版本历史）
    POST   /api/v1/knowledge/                          — 创建条目（仅管理员）
    PUT    /api/v1/knowledge/{id}                      — 编辑条目（自动版本递增，仅管理员）
    PUT    /api/v1/knowledge/{id}/archive              — 归档条目（不删除，仅管理员）
    GET    /api/v1/knowledge/{id}/versions             — 版本历史列表
    POST   /api/v1/knowledge/{id}/versions/{v_id}/rollback — 回滚版本（仅管理员）

权限：
    - 列表和详情：需登录即可访问
    - 创建、编辑、归档、回滚：仅管理员（require_admin 依赖）
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.knowledge import KnowledgeEntry, KnowledgeVersion, KnowledgeStatus, KnowledgeSource
from app.schemas.knowledge import (
    KnowledgeCreate, KnowledgeUpdate, KnowledgeListItem, KnowledgeDetail,
    KnowledgeListResponse, VersionItem,
)

router = APIRouter()


@router.get("/", response_model=KnowledgeListResponse)
async def list_knowledge(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索关键词"),
    source: str = Query(""),
    device_model: str = Query(""),
    fault_tag: str = Query(""),
    status: str = Query("published"),
    db: AsyncSession = Depends(get_db),
):
    query = select(KnowledgeEntry)
    count_query = select(func.count(KnowledgeEntry.id))

    # 筛选
    if status and status != "all":
        query = query.where(KnowledgeEntry.status == status)
        count_query = count_query.where(KnowledgeEntry.status == status)
    if source:
        query = query.where(KnowledgeEntry.source == source)
        count_query = count_query.where(KnowledgeEntry.source == source)
    if keyword:
        like_term = f"%{keyword}%"
        query = query.where(
            (KnowledgeEntry.title.ilike(like_term)) |
            (KnowledgeEntry.summary.ilike(like_term))
        )
        count_query = count_query.where(
            (KnowledgeEntry.title.ilike(like_term)) |
            (KnowledgeEntry.summary.ilike(like_term))
        )

    # 总数
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.order_by(KnowledgeEntry.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    entries = result.scalars().all()

    # 如果是设备型号筛选，在 Python 里过滤（JSON 字段）
    filtered = []
    for e in entries:
        if device_model and device_model not in (e.device_models or []):
            continue
        if fault_tag and fault_tag not in (e.fault_tags or []):
            continue
        filtered.append(e)

    return KnowledgeListResponse(
        items=[KnowledgeListItem.model_validate(e) for e in filtered],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{entry_id}", response_model=KnowledgeDetail)
async def get_knowledge(entry_id: int, db: AsyncSession = Depends(get_db)):
    """
    获取知识条目详情

    使用 selectinload 预加载 versions 关系，避免在会话外访问导致的懒加载错误。
    返回的 versions 按版本号降序排列（最新版本在最前）。
    """
    result = await db.execute(
        select(KnowledgeEntry)
        .options(selectinload(KnowledgeEntry.versions))
        .where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    detail = KnowledgeDetail.model_validate(entry)
    detail.versions = [
        VersionItem.model_validate(v)
        for v in sorted(entry.versions, key=lambda v: v.version_num, reverse=True)
    ]
    return detail


@router.post("/")
async def create_knowledge(
    req: KnowledgeCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    创建知识条目（仅管理员）

    流程：
    1. 创建 KnowledgeEntry 记录
    2. flush 获取自增 ID
    3. 创建 KnowledgeVersion 初始版本（V1.0）
    4. 提交事务

    两个操作在同一事务中，保证原子性。
    """
    entry = KnowledgeEntry(
        title=req.title,
        content=req.content,
        summary=req.summary,
        source=KnowledgeSource(req.source),
        source_ref=req.source_ref,
        device_models=req.device_models,
        fault_tags=req.fault_tags,
        maintenance_level=req.maintenance_level,
        is_procedure=req.is_procedure,
        procedure_data=req.procedure_data,
        author_id=user.id,
        current_version="V1.0",
    )
    db.add(entry)
    await db.flush()

    # 创建初始版本
    version = KnowledgeVersion(
        entry_id=entry.id,
        version="V1.0",
        version_num=1,
        content=req.content,
        change_summary="初始版本",
        editor_id=user.id,
    )
    db.add(version)
    await db.commit()
    return {"id": entry.id, "message": "知识条目已创建"}


@router.put("/{entry_id}")
async def update_knowledge(
    entry_id: int,
    req: KnowledgeUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")

    # 更新字段
    for field, value in req.model_dump(exclude_unset=True, exclude={"change_summary"}).items():
        if value is not None:
            setattr(entry, field, value)

    # 版本号递增
    old_ver = entry.current_version
    parts = old_ver.replace("V", "").split(".")
    major, minor = int(parts[0]), int(parts[1])
    new_ver = f"V{major}.{minor + 1}" if minor < 9 else f"V{major+1}.0"
    entry.current_version = new_ver

    # 保存历史版本
    version_num = 1 + await db.scalar(
        select(func.max(KnowledgeVersion.version_num)).where(KnowledgeVersion.entry_id == entry_id)
    ) or 1
    version = KnowledgeVersion(
        entry_id=entry.id,
        version=new_ver,
        version_num=version_num,
        content=entry.content,
        change_summary=req.change_summary or "",
        editor_id=user.id,
    )
    db.add(version)
    await db.commit()
    return {"message": "知识条目已更新", "version": new_ver}


@router.put("/{entry_id}/archive")
async def archive_knowledge(
    entry_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    归档知识条目（仅管理员）

    归档后状态变为 ARCHIVED，用户端不再可检索。
    数据不删除，管理员可查看和恢复。
    """
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    entry.status = KnowledgeStatus.ARCHIVED
    await db.commit()
    return {"message": "知识条目已归档"}


@router.get("/{entry_id}/versions")
async def get_versions(entry_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(KnowledgeEntry)
        .options(selectinload(KnowledgeEntry.versions))
        .where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    versions = sorted(entry.versions, key=lambda v: v.version_num, reverse=True)
    return [VersionItem.model_validate(v) for v in versions]


@router.post("/{entry_id}/versions/{version_id}/rollback")
async def rollback_version(
    entry_id: int,
    version_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    回滚到指定历史版本（仅管理员）

    回滚操作本身也会生成一个新版本记录（说明"回滚至 Vx.y"），
    确保回滚操作可被审计追溯。
    """
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")

    ver_result = await db.execute(select(KnowledgeVersion).where(
        KnowledgeVersion.id == version_id,
        KnowledgeVersion.entry_id == entry_id,
    ))
    target_ver = ver_result.scalar_one_or_none()
    if not target_ver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在")

    # 回滚：更新内容并生成新版本
    old_ver = entry.current_version
    parts = old_ver.replace("V", "").split(".")
    new_ver = f"V{int(parts[0])+1}.0"  # 回滚视为大版本变更
    entry.content = target_ver.content
    entry.current_version = new_ver

    max_ver = await db.scalar(
        select(func.max(KnowledgeVersion.version_num)).where(KnowledgeVersion.entry_id == entry_id)
    ) or 1
    new_version = KnowledgeVersion(
        entry_id=entry.id,
        version=new_ver,
        version_num=max_ver + 1,
        content=target_ver.content,
        change_summary=f"回滚至 {target_ver.version}",
        editor_id=user.id,
    )
    db.add(new_version)
    await db.commit()
    return {"message": f"已回滚至版本 {target_ver.version}", "new_version": new_ver}
