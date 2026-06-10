"""
客服工单模型

工单制客服系统（非实时聊天）：
- 用户在 AI 无法解决问题时提交工单
- 管理员/专家回复工单
- 已解决的工单可沉淀为知识条目

工单状态流转：
    PENDING → PROCESSING → REPLIED → RESOLVED → CLOSED
    (待处理)  (处理中)    (已回复)  (已解决)   (已关闭)

Ticket:  工单主表
TicketReply: 工单回复记录
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class TicketStatus(str, enum.Enum):
    """
    工单状态枚举

    正常流转: PENDING → PROCESSING → REPLIED → RESOLVED → CLOSED
    已解决的工单 7 天后自动关闭
    """
    PENDING = "pending"         # 待处理：用户刚提交，等待管理员接管
    PROCESSING = "processing"   # 处理中：管理员已接管，正在调查研究
    REPLIED = "replied"         # 已回复：管理员已给出答复，等待用户确认
    RESOLVED = "resolved"       # 已解决：用户确认问题已解决
    CLOSED = "closed"           # 已关闭：超过 7 天自动关闭或管理员手动关闭


class Ticket(Base):
    """
    客服工单主表

    记录用户提交的支持请求。每个工单有唯一工单号（ticket_no），
    格式如 TK-20250610-0001（日期+序号），方便追踪和引用。
    """
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 工单唯一编号，格式 TK-YYYYMMDD-NNNN
    ticket_no = Column(String(30), unique=True, nullable=False, index=True)
    # 问题标题：简明扼要描述问题
    title = Column(String(300), nullable=False)
    # 问题详细描述：富文本，可包含图片
    description = Column(Text, nullable=False)
    # 辅助图片路径列表
    images = Column(JSON, default=list)
    # 提交人工单的用户 ID
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # 指派处理人：管理员可将工单分配给特定专家
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # 工单当前状态
    status = Column(Enum(TicketStatus), default=TicketStatus.PENDING)
    # 创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # 最后更新时间
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TicketReply(Base):
    """
    工单回复记录表

    一条工单可有多条回复，形成问答链。
    每次管理员回复后工单状态变为 REPLIED，等待用户确认。
    每条回复可携带附件（截图、手册片段等）。
    """
    __tablename__ = "ticket_replies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 所属工单 ID
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    # 回复人 ID（管理员或专家）
    replier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # 回复内容（支持富文本）
    content = Column(Text, nullable=False)
    # 附件文件路径列表
    attachments = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
