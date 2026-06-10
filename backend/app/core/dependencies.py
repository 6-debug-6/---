"""
FastAPI 依赖注入：认证与授权

提供三个层级的依赖函数，用于保护 API 端点：

1. get_current_user   — 解析 JWT，返回当前登录用户（所有需登录的接口使用）
2. require_role       — 基于角色的访问控制（如 require_role(ADMIN, EXPERT)）
3. require_admin      — 管理员专用权限检查

使用示例：
    @app.get("/protected")
    async def protected_route(user: User = Depends(get_current_user)):
        ...

    @app.delete("/admin/action")
    async def admin_action(user: User = Depends(require_admin)):
        ...
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User, UserRole, UserStatus

# HTTP Bearer 认证方案：从请求头 Authorization: Bearer <token> 提取令牌
# auto_error=False 表示不自动报错，由各依赖函数自行处理
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从 JWT 令牌中获取当前登录用户

    执行流程：
    1. 从请求头提取 Bearer token
    2. 解码 JWT 令牌，获取用户 ID（载荷中的 sub 字段）
    3. 从数据库查询用户记录
    4. 校验用户状态（ACTIVE 才允许访问）

    可能抛出的异常：
        401: 令牌无效、用户不存在
        403: 账号未审核通过或已被禁用
    """
    # Step 1: 提取令牌字符串
    token = credentials.credentials

    # Step 2: 解码验证 JWT
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    # Step 3: 获取用户 ID（JWT 中 sub 字段存储用户 ID 的字符串形式）
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    # Step 4: 数据库查询用户
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    # Step 5: 校验用户状态
    # PENDING: 注册后等待管理员审核 → 不允许登录
    # DISABLED: 被管理员禁用 → 不允许访问
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号未激活或已被禁用")

    return user


def require_role(*roles: UserRole):
    """
    基于角色的权限检查工厂函数

    用法：
        require_role(UserRole.ADMIN)              → 仅管理员
        require_role(UserRole.ADMIN, UserRole.EXPERT) → 管理员或专家

    返回一个 FastAPI 依赖函数，在 get_current_user 验证通过后
    额外检查用户角色是否在允许列表中。
    """
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user
    return role_checker


def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    管理员权限检查（require_role 的便捷版本）
    仅 UserRole.ADMIN 角色的用户可以访问
    """
    if user.role not in (UserRole.ADMIN,):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
