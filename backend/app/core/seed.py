"""
数据库种子数据脚本

系统首次部署时运行此脚本，自动创建：
1. 默认管理员账号（admin / admin123）
2. 默认大模型配置（DeepSeek API）

运行方式：
    python -m app.core.seed

设计说明：
- 操作幂等：多次运行不会重复创建（检查已有数据后跳过）
- flush() 刷新 SQL 以获取 admin.id，用于后续关联模型配置
"""
from app.core.database import async_session, init_db
from app.models.user import User, UserRole, UserStatus
from app.models.audit import ModelConfig
from app.core.security import hash_password
import asyncio


async def seed():
    """
    执行种子数据初始化

    流程：
    1. 调用 init_db() 确保所有表已创建
    2. 检查是否已存在 admin 用户（幂等性保证）
    3. 创建管理员账号（角色=admin, 状态=active）
    4. 创建默认的 DeepSeek 模型配置
    """
    # 首先确保数据库表结构存在
    await init_db()

    async with async_session() as db:
        from sqlalchemy import select

        # ===== 幂等性检查 =====
        # 如果已存在 admin 用户，说明种子数据已初始化过，直接跳过
        existing = await db.execute(select(User).where(User.username == "admin"))
        if existing.scalar_one_or_none():
            print("管理员账号已存在，跳过种子数据")
            return

        # ===== 创建默认管理员 =====
        # 使用 bcrypt 哈希存储密码，不保存明文
        # admin 角色拥有全部管理端权限
        admin = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            name="系统管理员",
            employee_id="ADMIN001",
            team="信息部",
            role=UserRole.ADMIN,        # 管理员角色
            status=UserStatus.ACTIVE,   # 直接激活，无需审核
        )
        db.add(admin)
        # flush 将对象同步到数据库（未提交），获取自增的 id
        await db.flush()

        # ===== 创建默认大模型配置 =====
        # 系统需要至少一个模型配置才能正常使用 AI 功能
        # api_key 留空，部署时由管理员在管理端配置
        model_cfg = ModelConfig(
            model_name="deepseek-chat",         # 使用 DeepSeek 对话模型
            model_type="cloud",                 # 云端 API 接入方式
            api_base="https://api.deepseek.com",
            api_key="",                         # 需在管理端配置实际 API Key
            is_active=True,                     # 设为当前激活的模型
            parameters={
                "temperature": 0.3,             # 生成温度：较低以提高专业场景准确性
                "max_tokens": 4096,             # 单次回复最大长度
                "top_k": 5,                     # 检索召回文档数
            },
            updated_by=admin.id,                # 关联操作人
        )
        db.add(model_cfg)

        # ===== 提交事务 =====
        # 两条记录在同一个事务中提交，保证原子性
        await db.commit()
        print("种子数据创建完成: admin / admin123")


if __name__ == "__main__":
    # 顶层入口：创建事件循环并运行种子函数
    asyncio.run(seed())
