"""
认证模块的 Pydantic 数据模型

定义请求/响应的数据结构，FastAPI 自动完成：
- 请求体验证（类型检查、长度限制等）
- 响应体序列化（Python 对象 → JSON）
- OpenAPI 文档生成（Swagger UI 中可见）
"""
from pydantic import BaseModel, Field
from typing import Optional


class RegisterRequest(BaseModel):
    """用户注册请求体"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名，2-50 字符")  # 用于登录，需唯一
    password: str = Field(..., min_length=6, max_length=100, description="密码，最少 6 字符")  # 明文，服务端哈希后存储
    name: str = Field(..., min_length=1, max_length=50, description="真实姓名")                # 界面展示用
    employee_id: str = Field(..., min_length=1, max_length=30, description="工号")              # 企业内部唯一标识
    team: str = Field(..., min_length=1, max_length=100, description="所属班组")               # 如"检修一班"


class LoginRequest(BaseModel):
    """用户登录请求体"""
    username: str   # 用户名
    password: str   # 密码（明文传输，建议生产环境启用 HTTPS）


class LoginResponse(BaseModel):
    """登录成功响应体：返回 JWT 令牌和用户信息"""
    access_token: str                # JWT 访问令牌，后续请求通过 Authorization: Bearer <token> 携带
    token_type: str = "bearer"       # 令牌类型，固定为 bearer
    user: "UserInfo"                 # 当前用户基本信息，前端存入 Pinia store


class UserInfo(BaseModel):
    """
    用户信息（公开字段）
    注意：不包含 hashed_password 等敏感字段
    """
    id: int           # 用户 ID
    username: str     # 用户名
    name: str         # 真实姓名
    employee_id: str  # 工号
    team: str         # 所属班组
    role: str         # 角色：worker/admin/expert
    status: str       # 状态：pending/active/disabled

    class Config:
        # from_attributes=True 允许从 SQLAlchemy ORM 对象直接转换
        from_attributes = True


class PasswordResetRequest(BaseModel):
    """管理员重置用户密码请求体"""
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码，最少 6 字符")
