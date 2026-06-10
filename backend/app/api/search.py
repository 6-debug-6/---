"""
知识检索 API：多模态搜索

端点：
    POST /api/v1/search        — 多模态检索（文本 + 图片 + 设备型号联合查询）
    POST /api/v1/images/analyze — 单独图片故障分析

检索流程：
    1. 意图重写：LLM 将口语化查询改写为精准检索词
    2. 图片分析：千问 VL 提取图片中的故障特征描述
    3. 向量检索：在 ChromaDB 中做语义相似度搜索
    4. 关键词补充：数据库模糊匹配补充结果
    5. 融合排序：按得分降序返回，标注匹配类型

降级策略：
    - 向量库不可用 → 降级为数据库关键词搜索
    - LLM 不可用 → 跳过意图重写，直接使用原始查询
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.knowledge import KnowledgeEntry, KnowledgeStatus
from app.services.vector_store import vector_store
from app.services.llm_adapter import model_router
from app.schemas.knowledge import KnowledgeListItem

router = APIRouter()


@router.post("/search")
async def search_knowledge(
    query: str = Form(""),
    device_model: str = Form(""),
    image: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not query and not image:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入搜索内容或上传图片")

    image_description = ""
    # 若有图片，调用视觉模型提取描述
    if image:
        # 保存临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            content = await image.read()
            tmp.write(content)
            tmp_path = tmp.name

        image_description = await model_router.analyze_image(
            image_url=f"file://{tmp_path}",
            prompt="请详细描述这张图片中设备的状态，特别是任何异常、损坏、磨损的迹象。用中文回答，不超过200字。",
        )
        import os
        os.unlink(tmp_path)

    # 意图重写：将口语化查询改写为更精准的检索 Query
    search_query = query
    if query:
        try:
            rewritten = await model_router.chat([
                {"role": "system", "content": "将用户输入的故障描述改写为一个简洁的知识检索查询词。只输出改写后的词，不要加其他内容。"},
                {"role": "user", "content": query},
            ], has_image=False, temperature=0.1)
            search_query = rewritten.strip()[:200]
        except Exception:
            pass  # LLM 不可用时使用原始查询

    # 组合查询文本
    combined_query = search_query
    if image_description:
        combined_query = f"{search_query} {image_description}"

    # 向量检索
    vector_results = []
    try:
        vector_results = vector_store.search(combined_query, top_k=10)
    except Exception:
        pass  # 向量库不可用时降级为数据库搜索

    # 数据库精确搜索（关键词匹配）
    db_ids = [int(r["id"].split("_")[0]) for r in vector_results if r["id"].split("_")[0].isdigit()]
    db_ids = list(set(db_ids))  # 去重

    # 从数据库获取完整信息
    result_items = []
    seen_ids = set()

    # 先返回向量搜索匹配的
    if db_ids:
        query_stmt = select(KnowledgeEntry).where(
            KnowledgeEntry.id.in_(db_ids),
            KnowledgeEntry.status == KnowledgeStatus.PUBLISHED,
        )
        if device_model:
            query_stmt = query_stmt.where(KnowledgeEntry.device_models.contains([device_model]))
        db_result = await db.execute(query_stmt)
        for entry in db_result.scalars().all():
            if entry.id not in seen_ids:
                seen_ids.add(entry.id)
                item = KnowledgeListItem.model_validate(entry)
                result_items.append({"item": item.model_dump(), "match_type": "语义匹配", "score": 0.85})

    # 补充关键词搜索结果
    if query:
        keyword_stmt = select(KnowledgeEntry).where(
            (KnowledgeEntry.title.contains(query)) |
            (KnowledgeEntry.content.contains(query)) |
            (KnowledgeEntry.summary.contains(query)),
            KnowledgeEntry.status == KnowledgeStatus.PUBLISHED,
        )
        if device_model:
            keyword_stmt = keyword_stmt.where(KnowledgeEntry.device_models.contains([device_model]))
        keyword_stmt = keyword_stmt.limit(10)
        keyword_result = await db.execute(keyword_stmt)
        for entry in keyword_result.scalars().all():
            if entry.id not in seen_ids:
                seen_ids.add(entry.id)
                item = KnowledgeListItem.model_validate(entry)
                result_items.append({"item": item.model_dump(), "match_type": "关键词匹配", "score": 0.6})

    # 视觉匹配标记
    if image_description and result_items:
        for r in result_items[:3]:
            r["match_type"] = f"视觉匹配+{r['match_type']}"

    # 按得分排序
    result_items.sort(key=lambda x: x["score"], reverse=True)

    return {
        "results": result_items,
        "total": len(result_items),
        "query_rewritten": search_query if search_query != query else None,
        "image_description": image_description or None,
    }


@router.post("/images/analyze")
async def analyze_image(
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """单独对图片进行故障特征分析"""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        content = await image.read()
        tmp.write(content)
        tmp_path = tmp.name

    description = await model_router.analyze_image(
        image_url=f"file://{tmp_path}",
        prompt="分析这张设备故障图片，描述：1. 可见的异常迹象 2. 可能的故障类型 3. 建议的检修方向。用中文回答。",
    )
    import os
    os.unlink(tmp_path)
    return {"description": description}
