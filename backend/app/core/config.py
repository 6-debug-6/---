"""
系统全局配置管理

使用 pydantic-settings 实现：
- 从 .env 文件读取环境变量
- 提供类型校验和默认值
- 通过 lru_cache 缓存的工厂函数获取单例配置

所有可配置项在此集中定义，便于管理和文档化。
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """
    应用配置类
    每个属性对应一个配置项，可以从 .env 文件或环境变量中读取
    属性名自动映射为全大写的环境变量名
    """

    # ==================== 应用基础配置 ====================
    APP_NAME: str = "设备检修知识检索与作业系统"  # 应用显示名称
    APP_VERSION: str = "0.1.0"                    # 当前版本号
    DEBUG: bool = True                            # 调试模式（控制日志和错误详情输出）
    SECRET_KEY: str = "change-this-to-a-random-secret-key"  # JWT 签名密钥，生产环境必须更换
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480        # JWT 令牌有效期（分钟），默认 8 小时

    # ==================== 数据库配置 ====================
    # 开发阶段使用 SQLite + aiosqlite（异步驱动）
    # 生产环境切换为 PostgreSQL: postgresql+asyncpg://user:pass@host/db
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # ==================== ChromaDB 向量数据库 ====================
    # 持久化目录，存储向量索引和元数据
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    # ==================== 文件存储 ====================
    UPLOAD_DIR: str = "./data/uploads"            # 上传文件存放根目录
    MAX_UPLOAD_SIZE_MB: int = 50                  # 单文件最大上传大小（MB）

    # ==================== DeepSeek 大模型配置 ====================
    # 文本主力模型，用于：对话生成、意图重写、实体抽取
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ==================== 千问 VL 视觉模型配置 ====================
    # 用于：故障图片分析、PDF 图片描述生成、图文联合理解
    QWEN_API_KEY: str = ""
    QWEN_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_VL_MODEL: str = "qwen-vl-max"

    # ==================== Embedding 嵌入模型 ====================
    # 本地部署的文本向量化模型，用于知识片段向量化和语义检索
    # BGE-Small: 轻量高效的中文 Embedding 模型，CPU 即可运行
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DEVICE: str = "cpu"                 # 推理设备：cpu 或 cuda

    # ==================== CORS 跨域配置 ====================
    # 开发阶段允许 Vite 前端开发服务器跨域访问
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    class Config:
        # 启用 .env 文件读取，字段名自动匹配环境变量
        env_file = ".env"
        # 环境变量名大小写敏感（必须全大写）
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置单例
    lru_cache 装饰器确保 Settings 对象只创建一次
    后续调用直接返回缓存的实例，避免重复读取 .env 文件
    """
    return Settings()
