"""
用户认证 API

端点：
    POST /api/v1/auth/register                — 用户注册
    POST /api/v1/auth/login                   — 用户登录，返回 JWT 令牌
    GET  /api/v1/auth/me                      — 获取当前登录用户信息
    POST /api/v1/auth/users/{id}/reset-password — 管理员重置用户密码
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.dependencies import get_current_user, require_admin
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth import RegisterRequest, LoginRequest, LoginResponse, UserInfo, PasswordResetRequest

router = APIRouter()


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    用户注册

    新用户默认角色为 WORKER（一线人员），状态为 PENDING（待审核）。
    注册后需等待管理员审核通过方可登录。
    用户名重复时返回 409 冲突错误。
    """
    # 检查用户名是否已被占用
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    # 创建用户记录，密码使用 bcrypt 哈希后存储
    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),  # 不存储明文密码
        name=req.name,
        employee_id=req.employee_id,
        team=req.team,
        role=UserRole.WORKER,         # 固定为一线人员角色
        status=UserStatus.PENDING,    # 需管理员审核后激活
    )
    db.add(user)
    await db.commit()
    return {"message": "注册成功，请等待管理员审核"}


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    用户登录

    验证用户名和密码，返回 JWT 访问令牌。
    令牌包含用户 ID 和角色信息，有效期 8 小时（由配置控制）。
    登录失败条件：
        - 用户名或密码错误 → 401
        - 账号尚未审核通过 → 403
        - 账号已被禁用 → 403
    """
    # 按用户名查找用户
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    # 验证密码（使用固定错误信息防止用户名枚举攻击）
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    # 检查账号状态
    if user.status == UserStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号尚未通过审核")
    if user.status == UserStatus.DISABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    # 签发 JWT 令牌，载荷包含用户 ID（sub）和角色（role）
    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})

    return LoginResponse(
        access_token=token,
        user=UserInfo.model_validate(user),  # ORM 对象 → Pydantic 模型
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息

    依赖 get_current_user 解析 JWT 令牌并查询数据库。
    可用于：前端页面刷新后恢复用户状态、验证令牌有效性。
    """
    return UserInfo.model_validate(user)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    req: PasswordResetRequest,
    admin: User = Depends(require_admin),   # 仅管理员可操作
    db: AsyncSession = Depends(get_db),
):
    """
    管理员重置用户密码

    仅管理员角色可调用（require_admin 依赖校验）。
    用户忘记密码时联系管理员，管理员使用此接口重置。
    用户下次登录时使用新密码。
    """
    # 查找目标用户
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 更新密码哈希
    target_user.hashed_password = hash_password(req.new_password)
    await db.commit()
    return {"message": "密码已重置"}
