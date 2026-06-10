"""
审核流程 API

端点：
    GET   /api/v1/review/               — 审核队列列表（按状态筛选）
    GET   /api/v1/review/{id}           — 审核详情（完整案例内容）
    POST  /api/v1/review/{id}/action    — 执行审核操作（通过/驳回/通过含修改）

审核机制：
    初审（管理员）：任何人都可以提交 → 管理员检查格式完整性、分类正确性
    复审（专家）：仅 is_experience_based=True 的案例需复审，验证技术准确性

通过后自动入库：
    1. 创建 KnowledgeEntry 记录（来源=user_upload）
    2. 生成初始版本 KnowledgeVersion（V1.0）
    3. 向量化知识内容 → 存入 ChromaDB
    4. 更新 CaseUpload.linked_entry_id
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_role
from app.models.user import User, UserRole
from app.models.knowledge import (
    CaseUpload, ReviewStatus, KnowledgeEntry, KnowledgeVersion,
    KnowledgeStatus, KnowledgeSource,
)
from app.schemas.review import (
    ReviewAction, ReviewListItem, ReviewDetail, ReviewListResponse,
)
from app.services.vector_store import vector_store

router = APIRouter()


@router.get("/", response_model=ReviewListResponse)
async def list_reviews(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    review_status: str = Query("pending_initial", description="审核状态筛选"),
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.EXPERT)),
    db: AsyncSession = Depends(get_db),
):
    """
    获取审核队列列表

    review_status 可选值：
        pending_initial  — 待初审（默认，管理员可见）
        pending_expert   — 待复审（专家可见，仅经验型知识进入此状态）
        approved         — 已通过
        rejected         — 已驳回

    权限：管理员和专家均可访问，但各自关注不同状态的案例。
    """
    # 基础查询
    query = select(CaseUpload)
    count_query = select(func.count(CaseUpload.id))

    # 按审核状态筛选
    if review_status:
        query = query.where(CaseUpload.review_status == review_status)
        count_query = count_query.where(CaseUpload.review_status == review_status)

    # 总数
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页排序（最新提交在前）
    query = query.order_by(CaseUpload.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    cases = result.scalars().all()

    # 构建响应（需要查询上传者姓名）
    items = []
    for case in cases:
        # 查询上传者姓名
        uploader_name = ""
        if case.uploader_id:
            user_result = await db.execute(select(User).where(User.id == case.uploader_id))
            uploader_user = user_result.scalar_one_or_none()
            if uploader_user:
                uploader_name = uploader_user.name

        items.append(ReviewListItem(
            id=case.id,
            title=case.title,
            uploader_name=uploader_name,
            uploader_id=case.uploader_id,
            device_models=case.device_models or [],
            fault_tags=case.fault_tags or [],
            is_experience_based=case.is_experience_based,
            review_status=case.review_status.value,
            created_at=case.created_at,
        ))

    return ReviewListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{case_id}", response_model=ReviewDetail)
async def get_review_detail(
    case_id: int,
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.EXPERT)),
    db: AsyncSession = Depends(get_db),
):
    """
    获取审核详情

    返回案例的完整内容（文本、图片、附件），供审核人员审阅。
    同时返回上传者姓名，方便审核人员了解提交人背景。
    """
    result = await db.execute(select(CaseUpload).where(CaseUpload.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="案例不存在")

    # 查询上传者姓名
    uploader_name = ""
    if case.uploader_id:
        user_result = await db.execute(select(User).where(User.id == case.uploader_id))
        uploader_user = user_result.scalar_one_or_none()
        if uploader_user:
            uploader_name = uploader_user.name

    return ReviewDetail(
        id=case.id,
        title=case.title,
        content=case.content,
        device_models=case.device_models or [],
        fault_tags=case.fault_tags or [],
        is_experience_based=case.is_experience_based,
        images=case.images or [],
        attachments=case.attachments or [],
        uploader_name=uploader_name,
        uploader_id=case.uploader_id,
        review_status=case.review_status.value,
        review_comment=case.review_comment or "",
        reject_reason=case.reject_reason or "",
        initial_reviewer_id=case.initial_reviewer_id,
        expert_reviewer_id=case.expert_reviewer_id,
        linked_entry_id=case.linked_entry_id,
        created_at=case.created_at,
    )


@router.post("/{case_id}/action")
async def review_action(
    case_id: int,
    req: ReviewAction,
    user: User = Depends(require_role(UserRole.ADMIN, UserRole.EXPERT)),
    db: AsyncSession = Depends(get_db),
):
    """
    执行审核操作

    操作类型：
        approve         — 通过：事实型直接入库；经验型进入待复审状态
        approve_edited  — 通过含修改：使用审核者修改后的内容入库
        reject          — 驳回：填写驳回原因，退回提交者

    两级审核逻辑：
        - 初审（管理员）：approve 经验型知识后 → 状态变为 pending_expert（待复审）
        - 复审（专家）：approve 后 → 最终入库
        - 复审权限由角色控制（管理员=初审，专家=复审）

    入库流程（最终通过时）：
        1. 创建 KnowledgeEntry 记录
        2. 生成初始版本 V1.0
        3. 向量化知识内容存入 ChromaDB
        4. 关联 CaseUpload.linked_entry_id
    """
    # 查询案例
    result = await db.execute(select(CaseUpload).where(CaseUpload.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="案例不存在")

    # 权限校验
    current_status = case.review_status
    if current_status == ReviewStatus.PENDING_INITIAL and user.role == UserRole.EXPERT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="初审应由管理员完成，专家负责复审")
    if current_status == ReviewStatus.PENDING_EXPERT and user.role == UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="复审应由专家完成")

    # 确定最终使用的内容（通过含修改时使用审核者提供的新内容）
    final_content = req.content if req.action == "approve_edited" and req.content else case.content

    if req.action == "approve":
        # ===== 通过 =====
        if case.is_experience_based and current_status == ReviewStatus.PENDING_INITIAL:
            # 经验型知识的初审：状态变为待复审，由专家进行二次审核
            case.review_status = ReviewStatus.PENDING_EXPERT
            case.review_comment = req.review_comment
            case.initial_reviewer_id = user.id
        else:
            # 事实型知识的初审 或 经验型知识的复审：直接入库
            await _approve_and_index(case, final_content, user, db)

    elif req.action == "approve_edited":
        # ===== 通过含修改 =====
        await _approve_and_index(case, final_content, user, db)

    elif req.action == "reject":
        # ===== 驳回 =====
        case.review_status = ReviewStatus.REJECTED
        case.reject_reason = req.reject_reason
        case.review_comment = req.review_comment
        if current_status == ReviewStatus.PENDING_INITIAL:
            case.initial_reviewer_id = user.id
        else:
            case.expert_reviewer_id = user.id

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的审核操作: {req.action}")

    await db.commit()
    return {"message": "审核操作已完成", "action": req.action}


async def _approve_and_index(
    case: CaseUpload,
    final_content: str,
    reviewer: User,
    db: AsyncSession,
):
    """
    审核通过后的入库流程

    1. 创建 KnowledgeEntry（来源=user_upload, 状态=published）
    2. 生成初始版本记录 V1.0
    3. 向量化后存入 ChromaDB（用于后续检索）
    4. 更新 case 的审核状态和关联知识条目 ID
    """
    # Step 1: 创建知识条目
    entry = KnowledgeEntry(
        title=case.title,
        content=final_content,
        summary=case.title,  # 摘要默认用标题
        source=KnowledgeSource.USER_UPLOAD,
        source_ref=f"案例 #{case.id}",
        device_models=case.device_models or [],
        fault_tags=case.fault_tags or [],
        is_procedure=False,
        author_id=case.uploader_id,    # 作者记为原始上传者
        current_version="V1.0",
        status=KnowledgeStatus.PUBLISHED,
    )
    db.add(entry)
    await db.flush()  # 获取 entry.id

    # Step 2: 创建初始版本
    version = KnowledgeVersion(
        entry_id=entry.id,
        version="V1.0",
        version_num=1,
        content=final_content,
        change_summary="用户上传案例审核通过",
        editor_id=reviewer.id,
    )
    db.add(version)

    # Step 3: 向量化入库
    try:
        # 生成唯一 ID（格式：upload_{case_id}）
        doc_id = f"upload_{case.id}"
        vector_store.add_documents([{
            "id": doc_id,
            "content": final_content,
            "metadata": {
                "page": 0,
                "type": "user_upload",
                "source_file": f"案例 #{case.id}: {case.title}",
                "entry_id": str(entry.id),
            },
        }])
    except Exception:
        # 向量化失败不阻塞审核流程（后续可补索引）
        pass

    # Step 4: 更新案例状态
    current_status = case.review_status
    case.review_status = ReviewStatus.APPROVED
    case.review_comment = "审核通过，已纳入知识库"
    case.linked_entry_id = entry.id

    if current_status == ReviewStatus.PENDING_INITIAL:
        case.initial_reviewer_id = reviewer.id
    else:
        case.expert_reviewer_id = reviewer.id
