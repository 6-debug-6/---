"""
对话与消息模型

Conversation: 对话会话 — 用户的一次 AI 对话
Message:     对话消息 — 会话中的每一条消息（用户提问或 AI 回复）

对话功能支持：
- 多轮对话上下文管理（最近 10 轮送入 Prompt）
- 跨对话隔离：不同会话互不影响
- 作业中调起对话：携带当前步骤和设备上下文
- 反馈收集：用户可标记 AI 回复质量，修正内容用于模型优化

消息角色：
    user      — 用户发送的消息
    assistant — AI 生成的回复
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class Conversation(Base):
    """
    对话会话表

    每个会话记录用户与 AI 的一次完整对话。
    用户可同时拥有多个并行会话（不同故障/设备的对话分开）。
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 会话所属用户
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # 会话标题：默认"新对话"，首条用户消息后自动更新
    title = Column(String(200), default="新对话")
    # 对话背景上下文：从作业指引中调起时携带
    context_device_model = Column(String(100), default="")   # 关联设备型号
    context_task_step = Column(String(200), default="")      # 关联作业步骤描述
    context_task_id = Column(Integer, nullable=True)          # 关联作业任务 ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Message(Base):
    """
    对话消息表

    存储会话中的每条消息，包含用户问题和 AI 回复。
    structured_reply 将 AI 的自然语言回复解析为结构化数据，
    前端可用此数据渲染更有层次感的回复卡片。
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 所属会话 ID
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    # 消息发送者角色：user（用户） 或 assistant（AI）
    role = Column(String(20), nullable=False)
    # 消息正文内容
    content = Column(Text, nullable=False)
    # AI 回复的结构化数据：{"analysis": "", "causes": [], "solutions": [], "sources": []}
    # 仅 assistant 角色的消息有此字段
    structured_reply = Column(JSON, default=None)
    # 用户反馈标记：useful / partial / useless
    # 仅 assistant 角色的消息可被反馈
    feedback = Column(String(20), default="")
    # 用户提交的修正内容（当反馈为 useless 或 partial 时填写）
    feedback_comment = Column(Text, default="")
    # 消息中包含的图片路径列表
    image_urls = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
