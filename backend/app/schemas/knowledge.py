"""
知识库模块的 Pydantic 数据模型

定义知识条目相关请求/响应的数据结构。

核心模型：
    KnowledgeCreate      — 创建知识条目的请求体
    KnowledgeUpdate      — 更新知识条目的请求体（所有字段可选 + 修改说明）
    KnowledgeListItem    — 列表项（轻量，不含正文，用于列表页）
    KnowledgeDetail      — 详情（含正文、版本列表，用于详情页）
    VersionItem          — 版本项
    KnowledgeListResponse — 分页列表响应
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class KnowledgeCreate(BaseModel):
    """创建知识条目请求体"""
    title: str = Field(..., min_length=1, max_length=300, description="知识标题")
    content: str = Field(..., min_length=1, description="正文内容（富文本）")
    summary: str = ""                                               # 摘要（列表页展示）
    source: str = "manual"                                          # 来源：manual/pdf_import/user_upload/ticket
    source_ref: str = ""                                            # 来源引用（手册名+版本或工单号）
    device_models: list[str] = Field(default_factory=list)          # 关联设备型号列表
    fault_tags: list[str] = Field(default_factory=list)             # 故障分类标签列表
    maintenance_level: str = ""                                     # 检修等级：日常/定修/大修
    is_procedure: bool = False                                      # 是否包含作业指引步骤
    procedure_data: Optional[list[dict]] = None                     # 结构化步骤数据


class KnowledgeUpdate(BaseModel):
    """
    更新知识条目请求体

    所有字段均为 Optional：仅传入需要修改的字段。
    change_summary 为必填的修改说明，用于版本记录。
    """
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    device_models: Optional[list[str]] = None
    fault_tags: Optional[list[str]] = None
    maintenance_level: Optional[str] = None
    is_procedure: Optional[bool] = None
    procedure_data: Optional[list[dict]] = None
    change_summary: str = ""  # 修改说明（写入版本历史，非空时建议填写）


class KnowledgeListItem(BaseModel):
    """
    知识条目列表项（轻量，用于列表页和搜索结果）

    不包含 content 正文（减少数据传输量），
    前端点击条目后通过详情接口获取完整内容。
    """
    id: int
    title: str
    summary: str
    source: str              # 来源类型
    source_ref: str          # 来源引用
    device_models: list[str]  # 关联设备型号
    fault_tags: list[str]     # 故障分类标签
    maintenance_level: str    # 检修等级
    is_procedure: bool        # 是否作业指引
    status: str               # 发布状态
    current_version: str      # 当前版本号
    author_id: Optional[int]  # 作者 ID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True  # 支持从 SQLAlchemy ORM 对象自动转换


class VersionItem(BaseModel):
    """版本记录项"""
    id: int
    version: str             # 版本号字符串：V1.0, V1.1, V2.0
    version_num: int         # 版本序号（整数）
    change_summary: str      # 本次修改的说明
    editor_id: Optional[int] # 编辑者 ID
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class KnowledgeDetail(BaseModel):
    """
    知识条目详情（含完整内容和版本历史）

    用于详情页展示，包含所有字段。
    versions 列表按版本号降序排列（最新在前）。
    """
    id: int
    title: str
    content: str                              # 完整正文（富文本）
    summary: str
    source: str
    source_ref: str
    device_models: list[str]
    fault_tags: list[str]
    maintenance_level: str
    is_procedure: bool
    procedure_data: Optional[list[dict]]      # 步骤化数据（若 is_procedure=True）
    status: str
    current_version: str
    author_id: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    versions: list["VersionItem"] = []        # 历史版本列表

    class Config:
        from_attributes = True


class KnowledgeListResponse(BaseModel):
    """分页列表响应"""
    items: list[KnowledgeListItem]  # 当前页条目列表
    total: int                      # 符合条件的总条目数（用于前端分页器）
    page: int                       # 当前页码
    page_size: int                  # 每页条数
