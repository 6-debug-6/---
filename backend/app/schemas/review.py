"""
审核模块的 Pydantic 数据模型

定义案例审核相关的请求/响应结构。
审核流程：初审（管理员检查格式和分类）→ 复审（专家验证技术准确性，仅经验型知识需要）
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReviewListItem(BaseModel):
    """审核队列列表项"""
    id: int
    title: str              # 案例标题
    uploader_name: str = "" # 提交人姓名
    uploader_id: int        # 提交人 ID
    device_models: list[str]  # 关联设备型号
    fault_tags: list[str]     # 故障分类标签
    is_experience_based: bool  # 是否经验型（决定是否需要复审）
    review_status: str         # 当前审核状态
    created_at: Optional[datetime]  # 提交时间

    class Config:
        from_attributes = True


class ReviewDetail(BaseModel):
    """审核详情（含完整内容）"""
    id: int
    title: str
    content: str                       # 案例正文（富文本）
    device_models: list[str]
    fault_tags: list[str]
    is_experience_based: bool
    images: list[str]                  # 图片路径列表
    attachments: list[str]             # 附件路径列表
    uploader_name: str = ""
    uploader_id: int
    review_status: str
    review_comment: str = ""           # 当前审核意见
    reject_reason: str = ""            # 驳回原因
    initial_reviewer_id: Optional[int]  # 初审人
    expert_reviewer_id: Optional[int]   # 复审人
    linked_entry_id: Optional[int]     # 审核通过后关联的知识条目 ID
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class ReviewAction(BaseModel):
    """
    审核操作请求体

    action 可选值：
        approve          — 直接通过，自动入库
        approve_edited   — 通过含修改（content 字段包含修改后的内容）
        reject           — 驳回（reject_reason 为驳回原因）
    """
    action: str = Field(..., description="审核操作: approve / approve_edited / reject")
    content: str = ""              # 修改后的内容（approve_edited 时必填）
    review_comment: str = ""       # 审核意见
    reject_reason: str = ""        # 驳回原因（reject 时必填）


class ReviewListResponse(BaseModel):
    """分页审核队列响应"""
    items: list[ReviewListItem]
    total: int
    page: int
    page_size: int
