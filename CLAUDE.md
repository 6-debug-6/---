# 设备检修知识检索与作业系统

基于多模态大模型技术的工业设备检修知识检索与作业辅助系统。

## 技术栈

| 层 | 技术 | 备注 |
|---|------|------|
| 前端 | Vue 3 + Vite | PC Web 端，响应式适配平板 |
| 后端 | FastAPI (Python 3.10+) | REST API |
| LLM 编排 | LangChain | 模型调用、检索链路编排 |
| 大模型 | DeepSeek / 千问 API | 支持本地部署或云端接入 |
| 向量数据库 | ChromaDB | 需验证 LoongArch 兼容性 |
| 关系数据库 | PostgreSQL 或 SQLite | SQLite 用于轻量/开发 |
| 文件存储 | 本地文件系统 或 MinIO | |

## 运行环境

- **强制性**: LoongArch 架构 + 银河麒麟高级服务器版 V10
- 开发阶段可在 Windows/macOS 上进行，部署时迁移至目标环境

## 目录结构（规划）

```
.
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/           # API 路由
│   │   ├── core/          # 配置、安全、依赖
│   │   ├── models/        # 数据库模型
│   │   ├── schemas/       # Pydantic 模型
│   │   ├── services/      # 业务逻辑（LLM、检索、知识库）
│   │   └── main.py        # 入口
│   ├── tests/
│   └── requirements.txt
├── frontend/               # Vue 3 前端
│   ├── src/
│   │   ├── views/         # 页面
│   │   ├── components/    # 通用组件
│   │   ├── api/           # API 调用封装
│   │   ├── router/        # 路由
│   │   └── stores/        # Pinia 状态管理
│   └── package.json
├── docs/                   # 文档
├── requirements.md         # 需求规格说明书
└── CLAUDE.md
```

## 编码约定

- Python: 遵循 PEP 8，使用 type hints
- Vue: Composition API + `<script setup>` 语法
- 所有 API 端点使用 `/api/v1/` 前缀
- Git 提交信息使用中文，格式: `类型: 简要描述`
- 后端环境通过 `.env` 文件配置，不硬编码密钥

## 关键约束

- 系统必须可完整部署在 LoongArch + 麒麟 V10 上
- 优先选择有 LoongArch 兼容性的依赖库
- 大模型调用支持配置切换（DeepSeek / 千问 / 本地模型）
- 用户角色：一线人员、知识管理员、专家，需权限隔离
