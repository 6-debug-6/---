"""
用户模型

定义系统用户的数据库表结构，包含三种角色：
- WORKER  (worker):  一线检修人员 — 使用 AI 助手、检索知识、上传经验
- ADMIN   (admin):   知识管理员 — 管理知识库、审核内容、管理用户
- EXPERT  (expert):  技术专家 — 复审经验型知识、回复客服工单

用户状态流转：
    PENDING → (管理员审核通过) → ACTIVE
    ACTIVE  → (管理员禁用)     → DISABLED
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    """
    用户角色枚举
    继承 str 使得枚举值可直接作为字符串使用，方便序列化
    """
    WORKER = "worker"       # 一线人员：基础用户，可搜索、对话、上传经验
    ADMIN = "admin"         # 知识管理员：管理知识库、审核、用户管理、系统配置
    EXPERT = "expert"       # 技术专家：复审技术内容、回答复杂工单


class UserStatus(str, enum.Enum):
    """
    用户状态枚举
    控制用户是否可以登录和使用系统
    """
    PENDING = "pending"     # 待审核：新注册用户等待管理员审批
    ACTIVE = "active"       # 正常：审核通过，可正常使用
    DISABLED = "disabled"   # 已禁用：被管理员停用，不可登录


class User(Base):
    """
    系统用户表

    存储所有用户的基本信息和认证数据。
    hashed_password 使用 bcrypt 哈希后存储，不存储明文密码。
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 登录用户名，唯一约束保证不重复
    username = Column(String(50), unique=True, nullable=False, index=True)
    # bcrypt 哈希后的密码，固定 60 字符 + 盐值前缀
    hashed_password = Column(String(255), nullable=False)
    # 用户真实姓名（界面展示用）
    name = Column(String(50), nullable=False)
    # 工号：企业内部唯一标识，注册时填写
    employee_id = Column(String(30), nullable=False)
    # 所属班组：如"检修一班"、"电气组"
    team = Column(String(100), nullable=False)
    # 角色：控制用户可访问的功能模块
    role = Column(Enum(UserRole), default=UserRole.WORKER, nullable=False)
    # 状态：控制用户是否可以登录
    status = Column(Enum(UserStatus), default=UserStatus.PENDING, nullable=False)
    # 创建时间：数据库自动填充当前时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # 更新时间：记录更新时自动刷新
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
