"""
认证与安全工具

提供：
- 密码哈希与校验（bcrypt 算法，单向不可逆）
- JWT 令牌的创建与解码（HS256 对称签名）

安全要点：
- 密码使用 bcrypt 自动加盐哈希，不存储明文
- JWT 令牌有效期 8 小时，过期需重新登录
- SECRET_KEY 在生产环境必须更换为随机字符串
"""
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt
from app.core.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    """
    对明文密码进行 bcrypt 哈希加盐处理
    bcrypt.gensalt() 自动生成随机盐值，内嵌在哈希结果中
    返回的字符串可直接存入数据库 hashed_password 字段
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    校验明文密码是否与哈希值匹配
    bcrypt.checkpw 内部从哈希值中提取盐值，对明文重新哈希后比对
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    创建 JWT 访问令牌

    参数：
        data: 载荷数据，必须包含 "sub"（subject，用户标识）
        expires_delta: 自定义过期时间，默认使用配置的 8 小时

    令牌结构：
        Header:  { "alg": "HS256", "typ": "JWT" }
        Payload: { "sub": "用户ID", "role": "admin", "exp": 过期时间戳 }
        Signature: 使用 SECRET_KEY 的 HMAC-SHA256 签名
    """
    to_encode = data.copy()
    # 计算过期时间：当前 UTC 时间 + 有效期
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    """
    解码并验证 JWT 令牌
    返回：令牌中的载荷数据字典，验证失败返回 None
    验证失败的情况：令牌过期、签名不匹配、载荷被篡改
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        return None
