"""
审计与辅助业务模型

包含：
- AuditLog:          操作审计日志（不可篡改的操作记录）
- TaskRecord:        作业指引任务（用户执行检修流程的实例）
- ProcedureTemplate: 检修流程模板（管理员配置的步骤化模板）
- DeviceModel:       设备型号（设备类型定义）
- FaultCategory:     故障分类（树形结构，用于知识标签）
- ModelConfig:       大模型配置（系统当前使用的 LLM 参数）
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class AuditLog(Base):
    """
    操作审计日志表

    记录系统中的关键操作，用于安全审计和合规追溯。
    日志为只读，不可删除或修改。
    关键操作类型：用户审核、知识条目修改、权限变更、模型配置变更、数据备份。
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 操作人 ID（匿名操作时为 null）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # 操作类型：如 user.approve, knowledge.edit, model.switch
    action = Column(String(100), nullable=False)
    # 操作对象类型：如 user, knowledge_entry, model_config
    target_type = Column(String(50), nullable=False)
    # 操作对象 ID
    target_id = Column(Integer, nullable=True)
    # 操作详情描述（人类可读的说明文字）
    detail = Column(Text, default="")
    # 操作来源 IP 地址
    ip_address = Column(String(50), default="")
    # 额外元数据（JSON 格式，存储变更前后的值等）
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TaskRecord(Base):
    """
    作业指引任务记录表

    用户从检修流程模板创建的任务实例，记录执行的每一步。
    支持暂停、恢复、交接操作。
    confirmed_steps 和 handover_chain 为 JSON 数组，记录完整的执行和交接历史。
    """
    __tablename__ = "task_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False)                # 任务名称
    device_model = Column(String(100), nullable=False)          # 检修设备型号
    maintenance_level = Column(String(20), nullable=False)      # 检修等级：日常/定修/大修
    template_id = Column(Integer, nullable=True)                 # 使用的流程模板 ID
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)    # 当前执行人
    original_assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)         # 原执行人（交接场景）
    status = Column(String(20), default="in_progress")          # 任务状态：in_progress/paused/completed
    current_step = Column(Integer, default=0)                    # 当前步骤编号（从 1 开始）
    total_steps = Column(Integer, default=0)                     # 总步骤数
    confirmed_steps = Column(JSON, default=list)                 # 已确认步骤列表 [{"step":1,"time":"...","user_id":1}]
    pause_reason = Column(String(300), default="")               # 暂停原因
    handover_note = Column(Text, default="")                     # 交接说明（富文本）
    handover_chain = Column(JSON, default=list)                  # 交接链 [{"from_user":1,"to_user":2,"time":"..."}]
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)  # 完成时间
    deadline_at = Column(DateTime(timezone=True), nullable=True)   # 预计完成时间（用于超时提醒）


class ProcedureTemplate(Base):
    """
    检修流程模板表

    管理员预先配置的标准化作业模板。
    支持模板继承（parent_id），通用模板可派生出设备专用模板。
    steps 为 JSON 数组：每个元素包含阶段名、步骤号、标题、内容、合规校验项列表。
    """
    __tablename__ = "procedure_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)              # 模板名称
    device_models = Column(JSON, default=list)               # 适用设备型号列表
    maintenance_level = Column(String(20), nullable=False)   # 检修等级
    version = Column(String(20), default="V1.0")              # 版本号
    version_num = Column(Integer, default=1)                  # 版本序号
    parent_id = Column(Integer, nullable=True)                # 父模板 ID（支持继承）
    steps = Column(JSON, default=list)                        # 步骤列表 [{
                                                               #   "phase": "准备",
                                                               #   "step_num": 1,
                                                               #   "title": "断电确认",
                                                               #   "content": "...",
                                                               #   "compliance_items": ["执行能量隔离"]
                                                               # }]
    status = Column(String(20), default="published")          # 状态：draft/published/archived
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DeviceModel(Base):
    """
    设备型号定义表

    管理员在此维护所有可检修的设备型号信息。
    知识条目通过 device_models JSON 字段与此表关联。
    有关联知识条目的设备不可删除，仅可归档。
    """
    __tablename__ = "device_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)   # 设备型号名称
    production_line = Column(String(100), default="")           # 所属产线
    category = Column(String(50), nullable=False)               # 设备分类：发动机/传动/液压/电气...
    status = Column(String(20), default="active")               # 状态：active/archived
    spec_data = Column(JSON, default=dict)                      # 技术参数（结构化 JSON）
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FaultCategory(Base):
    """
    故障分类表（树形结构）

    通过 parent_id 实现层级分类，如：
        根节点: 电气故障(id=1, parent_id=null)
        ├── 电机故障(id=2, parent_id=1)
        │   ├── 轴承过热(id=3, parent_id=2)
        │   └── 绕组短路(id=4, parent_id=2)
        └── 控制系统故障(id=5, parent_id=1)

    知识条目的 fault_tags 字段引用此表的 name 值。
    """
    __tablename__ = "fault_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)                # 分类名称
    parent_id = Column(Integer, nullable=True)                 # 父分类 ID（null 为根节点）
    level = Column(Integer, default=0)                         # 层级深度（0=根, 1=一级...）
    sort_order = Column(Integer, default=0)                    # 同级排序权重
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ModelConfig(Base):
    """
    大模型配置表

    存储系统接入的大模型配置信息。系统启动时读取 is_active=True 的配置。
    管理员可通过管理端切换激活的模型、调整参数。
    所有模型变更记录在 AuditLog 中。
    """
    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)          # 模型名称：deepseek-chat / qwen-vl-max
    model_type = Column(String(30), nullable=False)           # 模型类型：cloud（云端API）/ local（本地部署）
    api_base = Column(String(300), nullable=False)            # API 端点地址
    api_key = Column(String(300), default="")                 # API 密钥（存储为明文，需配合环境安全措施）
    is_active = Column(Boolean, default=False)                 # 是否为当前激活的模型
    parameters = Column(JSON, default=dict)                    # 模型参数：{temperature, max_tokens, top_k}
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 最后修改人
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
