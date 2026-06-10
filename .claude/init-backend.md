---
name: init-backend
description: Initialize the FastAPI backend project structure and dependencies
---

# Backend 初始化技能

此技能用于初始化 FastAPI 后端项目结构。

## 步骤

1. 在 `backend/` 下创建目录结构：`app/`, `app/api/`, `app/core/`, `app/models/`, `app/schemas/`, `app/services/`, `tests/`
2. 创建 `backend/requirements.txt`，包含：
   - fastapi, uvicorn[standard]
   - langchain, langchain-community
   - chromadb
   - sqlalchemy, asyncpg 或 aiosqlite
   - python-multipart, python-jose[cryptography], passlib[bcrypt]
   - pydantic, pydantic-settings
   - httpx, aiofiles
3. 创建 `backend/app/main.py` FastAPI 入口
4. 创建 `backend/app/core/config.py` 配置管理（环境变量读取）
5. 初始化 `.env` 模板文件

## 注意

- 数据库驱动优先选 aiosqlite（开发）和 asyncpg（生产，需验证 LoongArch 兼容性）
- 所有依赖需能在 LoongArch 上编译或提供 wheel
