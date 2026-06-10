"""
数据库连接管理

职责：
- 创建 SQLAlchemy 异步引擎和会话工厂
- 提供异步会话的依赖注入函数 (get_db)
- 提供开发阶段的自动建表函数 (init_db)
- 确保数据目录在启动时已存在

使用 SQLAlchemy 2.0 异步 API，通过 aiosqlite 驱动连接 SQLite。
生产环境迁移时仅需更换 DATABASE_URL 即可切换为 PostgreSQL。
"""
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

# ========== 启动时确保数据目录存在 ==========
# data/ 为所有持久化数据的根目录（SQLite 数据库文件、ChromaDB 向量索引、上传文件）
# 使用 mkdir 确保目录在首次启动时自动创建，避免 "unable to open database file" 错误
Path("data").mkdir(exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)

# ========== 创建异步数据库引擎 ==========
# echo=DEBUG 时打印 SQL 语句，方便开发调试
# async_engine 是非阻塞的，支持并发请求
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)

# 异步会话工厂：每次请求创建一个新的 AsyncSession
# expire_on_commit=False：提交后不使对象过期，允许在会话外访问已提交对象的属性
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """
    所有 ORM 模型继承自此基类
    使用 SQLAlchemy 2.0 的声明式映射风格
    """
    pass


async def get_db() -> AsyncSession:
    """
    FastAPI 依赖注入：为每个请求提供独立的数据库会话

    用法（在路由处理函数中）：
        @app.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...

    会话在请求结束后自动关闭（finally 块确保资源释放）。
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    开发阶段自动建表函数
    导入所有模型模块以注册到 Base.metadata，然后执行 CREATE TABLE
    生产环境应使用 Alembic 管理数据库迁移
    """
    async with engine.begin() as conn:
        # 导入模型模块触发 SQLAlchemy 的注册机制
        # 只有被导入的模型对应的表才会被创建
        # noqa 注释告诉 linter 不要警告"未使用的导入"
        from app.models import user, knowledge, conversation, ticket, audit  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
