"""
AI 对话 API：RAG 检索增强生成 + 会话管理

端点：
    POST  /api/v1/conversations                   — 创建新对话
    GET   /api/v1/conversations                   — 获取用户的对话列表
    GET   /api/v1/conversations/{id}              — 获取对话详情（含消息历史）
    POST  /api/v1/chat                            — 发送消息（RAG 链路）
    POST  /api/v1/conversations/{id}/feedback     — 提交反馈（对某条 AI 回复的评价）

RAG 流程（send_message）：
    1. 验证对话归属（防止越权访问）
    2. 处理图片（如有 → 千问 VL 视觉分析）
    3. 检索背景知识（向量库搜索 → 拼接为上下文）
    4. 获取对话历史（最近 10 轮）
    5. 拼装 System Prompt（模板化，注入知识上下文+历史+设备/步骤信息）
    6. 调用大模型生成回复
    7. 解析结构化回复
    8. 保存消息 → 返回

反馈收集：
    - useful/partial/useless 三个级别
    - partial 和 useless 时可填写修正内容
    - 连续两次 useless → 提示用户提交客服工单
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.services.llm_adapter import model_router
from app.services.vector_store import vector_store
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

RAG_SYSTEM_PROMPT = """你是一个设备检修专家助手。回答时按以下结构组织：
1. 问题分析（对用户描述的现象进行分析）
2. 可能原因（列出1-3个最可能的原因，按概率排序）
3. 推荐方案（针对每个原因给出具体操作步骤）
4. 参考来源（列出引用的知识来源）

当前上下文（如有）：设备型号={device_model}，当前作业步骤={task_step}
遵守合规要求：所有操作建议必须包含安全提醒。

已知相关知识（从知识库检索获得）：
{knowledge_context}

对话历史：
{history}

用户消息：{user_message}"""


class FeedbackRequest(BaseModel):
    feedback: str  # useful / partial / useless
    comment: str = ""


# ---- 会话管理 ----

@router.post("/conversations")
async def create_conversation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = Conversation(user_id=user.id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return {"id": conv.id, "title": conv.title, "created_at": str(conv.created_at)}


@router.get("/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    convs = result.scalars().all()
    return [{"id": c.id, "title": c.title, "created_at": str(c.created_at), "updated_at": str(c.updated_at)} for c in convs]


@router.get("/conversations/{conv_id}")
async def get_conversation(
    conv_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user.id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")

    msg_result = await db.execute(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    )
    messages = msg_result.scalars().all()
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "structured_reply": m.structured_reply,
                "feedback": m.feedback,
                "image_urls": m.image_urls,
                "created_at": str(m.created_at),
            }
            for m in messages
        ],
    }


# ---- 对话 ----

@router.post("/chat")
async def send_message(
    message: str = Form(...),
    conversation_id: int = Form(...),
    image: UploadFile | None = File(None),
    device_model: str = Form(""),
    task_step: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 验证对话归属
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")

    # 处理图片
    image_urls = []
    has_image = False
    if image:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            content = await image.read()
            tmp.write(content)
            tmp_path = tmp.name
        has_image = True
        image_urls.append(tmp_path)

    # 检索背景知识
    knowledge_context = ""
    try:
        search_results = vector_store.search(message, top_k=5)
        knowledge_context = "\n\n".join([
            f"[来源: {r['metadata'].get('source_file', '未知')}]\n{r['content'][:500]}"
            for r in search_results
        ])
    except Exception:
        pass

    # 构建消息历史（最近10轮）
    hist_result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.desc()).limit(20)
    )
    recent_messages = list(reversed(hist_result.scalars().all()))
    history_text = "\n".join([
        f"{'用户' if m.role == 'user' else '助手'}: {m.content[:200]}"
        for m in recent_messages
    ])

    # 构建 Prompt
    system_prompt = RAG_SYSTEM_PROMPT.format(
        device_model=device_model or "未指定",
        task_step=task_step or "无",
        knowledge_context=knowledge_context or "未找到相关知识",
        history=history_text or "无历史",
        user_message=message,
    )

    # 调用大模型
    llm_messages = [{"role": "system", "content": system_prompt}]
    if image_urls and has_image:
        # 含图片时使用千问 VL
        llm_messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"file://{image_urls[0]}"}},
                {"type": "text", "text": message},
            ],
        })
    else:
        llm_messages.append({"role": "user", "content": message})

    try:
        reply = await model_router.chat(llm_messages, has_image=has_image, temperature=0.3)
    except Exception as e:
        reply = f"AI 服务暂时不可用：{str(e)}\n请稍后重试或提交客服工单。"

    # 解析结构化回复
    structured = _parse_structured_reply(reply)

    # 保存消息
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=message,
        image_urls=[f"file://{u}" for u in image_urls] if image_urls else [],
    )
    db.add(user_msg)

    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=reply,
        structured_reply=structured,
    )
    db.add(assistant_msg)

    # 更新对话标题（首次对话用首条用户消息）
    if not recent_messages:
        conv.title = message[:50] + ("..." if len(message) > 50 else "")
    conv.updated_at = func.now()

    await db.commit()
    await db.refresh(assistant_msg)

    return {
        "id": assistant_msg.id,
        "role": "assistant",
        "content": reply,
        "structured_reply": structured,
        "conversation_id": conversation_id,
        "created_at": str(assistant_msg.created_at),
    }


@router.post("/conversations/{conv_id}/feedback")
async def submit_feedback(
    conv_id: int,
    req: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 获取最后一条 assistant 消息
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_msg = result.scalar_one_or_none()
    if not last_msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可反馈的消息")

    last_msg.feedback = req.feedback
    last_msg.feedback_comment = req.comment
    await db.commit()

    # 连续两次无用 → 提示提交工单
    useless_count = 0
    if req.feedback == "useless":
        recent_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv_id, Message.role == "assistant")
            .order_by(Message.created_at.desc())
            .limit(5)
        )
        for m in recent_result.scalars().all():
            if m.feedback == "useless":
                useless_count += 1
            else:
                break

    return {
        "message": "反馈已提交",
        "suggest_ticket": useless_count >= 2,
    }


def _parse_structured_reply(reply: str) -> dict:
    """尝试解析 AI 回复中的结构化内容"""
    result = {"analysis": "", "causes": [], "solutions": [], "sources": []}
    # 简单按段落标题解析
    current_section = ""
    for line in reply.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "问题分析" in line or "分析" in line:
            current_section = "analysis"
            continue
        if "可能原因" in line or "原因" in line:
            current_section = "causes"
            continue
        if "推荐方案" in line or "方案" in line:
            current_section = "solutions"
            continue
        if "参考来源" in line or "来源" in line:
            current_section = "sources"
            continue

        if current_section == "analysis" and not result["analysis"]:
            result["analysis"] = line
        elif current_section == "causes":
            result["causes"].append(line)
        elif current_section == "solutions":
            result["solutions"].append(line)
        elif current_section == "sources":
            result["sources"].append(line)

    result["causes"] = result["causes"][:3]
    result["solutions"] = result["solutions"][:5]
    return result
