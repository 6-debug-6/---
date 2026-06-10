"""
向量数据库服务：ChromaDB 集成

封装 ChromaDB 的操作，管理知识片段的向量化存储和语义检索。

ChromaDB 特点：
- 轻量级嵌入式向量数据库，无需额外服务进程
- 持久化存储到磁盘，数据不丢失
- 内置多种 Embedding 函数（SentenceTransformer / OpenAI / 默认）
- 支持元数据过滤（metadata filtering）

嵌入模型选择策略：
    1. 首选：BGE-Small-ZH（BAAI/bge-small-zh-v1.5）— 中文专用，CPU 友好
    2. Fallback：all-MiniLM-L6-v2 — ChromaDB 默认模型，广泛兼容

检索返回的 score 由 distance 转换：score = 1.0 - distance
（ChromaDB 默认使用余弦距离，距离越小越相似）
"""
import os
from typing import Optional

from chromadb import PersistentClient
from chromadb.utils import embedding_functions

from app.core.config import get_settings

settings = get_settings()


class ChromaVectorStore:
    """
    ChromaDB 向量存储封装

    提供：
    - Collection 管理（按集合名隔离不同知识域）
    - 文档批量入库（自动向量化）
    - 语义检索（返回 Top-K 最相关内容）
    - 文档更新/删除（与知识条目同步）
    """

    def __init__(self):
        # 确保持久化目录存在
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)

        # PersistentClient：数据持久化到磁盘
        # 生产环境可替换为 HttpClient 连接独立 ChromaDB 服务
        self._client = PersistentClient(path=settings.CHROMA_PERSIST_DIR)

        # 初始化 Embedding 函数
        # BGE-Small-ZH：轻量级中文嵌入模型，384 维向量
        try:
            self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.EMBEDDING_MODEL_NAME,
                device=settings.EMBEDDING_DEVICE,    # cpu / cuda
            )
        except Exception:
            # Fallback: 使用 ChromaDB 内置默认嵌入函数（all-MiniLM-L6-v2）
            # 此模型支持中英文但中文效果不如 BGE
            self._ef = embedding_functions.DefaultEmbeddingFunction()

    def get_or_create_collection(self, name: str = "maintenance_knowledge"):
        """
        获取或创建向量集合

        每个集合是一个独立的向量空间，使用指定的 Embedding 函数。
        集合在首次调用时自动创建，后续调用返回已存在的集合。
        """
        return self._client.get_or_create_collection(
            name=name,
            embedding_function=self._ef,     # 嵌入函数：文本 → 向量
        )

    def add_documents(self, documents: list[dict], collection_name: str = "maintenance_knowledge"):
        """
        批量添加文档到向量库

        参数：
            documents: [{id, content, metadata}]
                - id: 文档唯一标识（用于后续更新/删除）
                - content: 纯文本内容（将被自动向量化）
                - metadata: 元信息字典（仅支持 str/int/float/bool 类型的值）

        返回：添加的文档数量

        注意：ChromaDB 的 metadata 只接受简单类型，复杂类型需转为字符串。
        """
        if not documents:
            return

        collection = self.get_or_create_collection(collection_name)

        # 拆分为 ChromaDB API 所需的三组并行列表
        ids = []
        contents = []
        metadatas = []
        for doc in documents:
            ids.append(doc["id"])
            contents.append(doc["content"])

            # ChromaDB metadata 值只能为 str/int/float/bool
            # 其他类型（list/dict/none）转为字符串
            meta = {}
            for k, v in doc.get("metadata", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                else:
                    meta[k] = str(v)
            metadatas.append(meta)

        collection.add(
            ids=ids,
            documents=contents,     # ChromaDB 自动调用 _ef 将 content 转为向量
            metadatas=metadatas,    # 元数据用于过滤和展示
        )
        return len(ids)

    def search(
        self,
        query: str,
        top_k: int = 5,
        collection_name: str = "maintenance_knowledge",
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """
        语义检索：查找与查询最相关的知识片段

        参数：
            query: 查询文本（自然语言描述）
            top_k: 返回结果数量（默认 5）
            filter_metadata: 元数据过滤条件（如按设备型号筛选）
                用法：filter_metadata={"device_model": "XX发动机"}

        返回：
            [{id, content, metadata, score}]
            score 为相关度分数（0-1，越大越相关），由距离转换而来
        """
        collection = self.get_or_create_collection(collection_name)

        # 构建过滤条件（ChromaDB where 子句）
        where_filter = None
        if filter_metadata:
            where_filter = filter_metadata

        # 执行向量相似度查询
        # ChromaDB 自动将 query 向量化，计算与库中所有文档的余弦距离
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
        )

        # 格式化返回结果
        items = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    # ChromaDB 返回的是距离（越小越相似），转为人更直观的相关度分数
                    "score": 1.0 - (results["distances"][0][i] if results["distances"] else 0),
                })
        return items

    def delete_by_ids(self, ids: list[str], collection_name: str = "maintenance_knowledge"):
        """
        按 ID 批量删除文档

        用于知识条目归档或删除时同步清理向量索引。
        """
        collection = self.get_or_create_collection(collection_name)
        collection.delete(ids=ids)

    def update_by_id(self, doc_id: str, content: str, metadata: dict, collection_name: str = "maintenance_knowledge"):
        """
        按 ID 更新单个文档的内容和元数据

        用于知识条目编辑后同步更新向量库。
        更新后会重新向量化 content。
        """
        collection = self.get_or_create_collection(collection_name)
        # metadata 值类型转换（与 add_documents 相同的规则）
        clean_meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                      for k, v in metadata.items()}
        collection.update(
            ids=[doc_id],
            documents=[content],
            metadatas=[clean_meta],
        )


# ========== 全局单例 ==========
# 整个应用共享一个 ChromaVectorStore 实例
# 避免重复创建 PersistentClient 和加载 Embedding 模型
vector_store = ChromaVectorStore()
