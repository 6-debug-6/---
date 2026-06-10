"""
知识库模型

核心业务模型，包含：
- KnowledgeEntry:   知识条目（主表），存储检索和展示的知识内容
- KnowledgeVersion: 版本历史（从表），每次编辑生成一条新版本记录
- CaseUpload:       用户上传案例（待审核表），审核通过后转为 KnowledgeEntry

知识来源：
    manual      — 管理员手动编写
    pdf_import  — PDF 手册批量导入
    user_upload — 一线人员上传的经验案例
    ticket      — 客服工单沉淀转化

审核流程（两级审核）：
    事实型知识：提交 → 待初审 → 管理员初审 → 通过/驳回
    经验型知识：提交 → 待初审 → 管理员初审 → 待复审 → 专家复审 → 通过/驳回
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class KnowledgeStatus(str, enum.Enum):
    """知识条目发布状态"""
    DRAFT = "draft"             # 草稿：编辑中，不对外可见
    PUBLISHED = "published"     # 已发布：用户端可检索
    ARCHIVED = "archived"       # 已归档：不可检索但数据保留


class KnowledgeSource(str, enum.Enum):
    """知识来源类型"""
    MANUAL = "manual"           # 管理员手动编写
    PDF_IMPORT = "pdf_import"   # PDF 批量导入
    USER_UPLOAD = "user_upload" # 用户上传
    TICKET = "ticket"           # 客服工单转化


class ReviewStatus(str, enum.Enum):
    """案例审核状态"""
    PENDING_INITIAL = "pending_initial"     # 待初审：管理员需检查格式和分类
    PENDING_EXPERT = "pending_expert"       # 待复审：专家需验证技术准确性（仅经验型）
    APPROVED = "approved"                   # 已通过：可自动入库
    APPROVED_WITH_EDITS = "approved_edited" # 通过含修改：管理员修改后入库
    REJECTED = "rejected"                   # 已驳回：退回提交者


class KnowledgeEntry(Base):
    """
    知识条目主表

    所有可被检索的知识数据都存储在此表中。
    内容使用 Text 类型存储富文本（支持图片、表格等 HTML 内容）。
    device_models 和 fault_tags 使用 JSON 存储数组，支持关联多个设备型号和故障分类。
    """
    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False, index=True)  # 知识标题，用于全文检索
    content = Column(Text, nullable=False)                   # 富文本正文内容
    summary = Column(Text, default="")                        # 摘要（列表页展示用）
    source = Column(Enum(KnowledgeSource), nullable=False)    # 知识来源
    source_ref = Column(String(300), default="")              # 来源引用（手册名+版本/工单号）
    device_models = Column(JSON, default=list)                # 关联设备型号列表：["XX发动机", "YY泵"]
    fault_tags = Column(JSON, default=list)                   # 故障分类标签：["电气", "过载"]
    maintenance_level = Column(String(20), default="")        # 检修等级：日常/定修/大修
    is_procedure = Column(Boolean, default=False)             # 是否包含作业指引步骤
    procedure_data = Column(JSON, default=None)               # 结构化步骤数据（JSON 格式）
    status = Column(Enum(KnowledgeStatus), default=KnowledgeStatus.PUBLISHED)  # 发布状态
    current_version = Column(String(20), default="V1.0")      # 当前版本号
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 创建者
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 一对多关系：一个知识条目有多个历史版本
    # back_populates 指向 KnowledgeVersion.entry，实现双向关联
    versions = relationship(
        "KnowledgeVersion",
        back_populates="entry",
        order_by="KnowledgeVersion.version_num.desc()"  # 按版本号降序，最新在前
    )


class KnowledgeVersion(Base):
    """
    知识版本历史表

    每次编辑 KnowledgeEntry 时自动创建一条新版本记录。
    旧版本内容保留在此表中，支持版本对比和回滚。
    version_num 是递增的整数，version 是展示用的字符串（如 V1.0, V1.1, V2.0）。
    """
    __tablename__ = "knowledge_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, ForeignKey("knowledge_entries.id"), nullable=False, index=True)
    version = Column(String(20), nullable=False)               # 版本号字符串：V1.0, V1.1, V2.0
    version_num = Column(Integer, nullable=False)               # 版本序号（整数递增，排序用）
    content = Column(Text, nullable=False)                      # 该版本完整内容快照
    change_summary = Column(String(500), default="")             # 修改说明（编辑者填写）
    editor_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 编辑者 ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 反向关联到 KnowledgeEntry
    entry = relationship("KnowledgeEntry", back_populates="versions")


class CaseUpload(Base):
    """
    用户上传案例表（待审核）

    一线人员通过客户端上传的检修经验案例，进入审核队列。
    审核流程参见文件顶部注释。
    审核通过后自动创建 KnowledgeEntry 记录。
    """
    __tablename__ = "case_uploads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False)                       # 案例标题
    content = Column(Text, nullable=False)                             # 案例正文（富文本）
    device_models = Column(JSON, default=list)                         # 关联设备型号
    fault_tags = Column(JSON, default=list)                            # 故障分类标签
    is_experience_based = Column(Boolean, default=False)               # 是否经验型（触发两级审核）
    images = Column(JSON, default=list)                                # 图片文件路径列表
    attachments = Column(JSON, default=list)                           # 附件文件路径列表
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # 上传者
    review_status = Column(Enum(ReviewStatus), default=ReviewStatus.PENDING_INITIAL)     # 审核状态
    initial_reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)          # 初审人
    expert_reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)           # 复审人
    review_comment = Column(Text, default="")                                              # 审核意见
    reject_reason = Column(String(500), default="")                                       # 驳回原因
    linked_entry_id = Column(Integer, ForeignKey("knowledge_entries.id"), nullable=True)   # 审核通过后关联的知识条目
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
