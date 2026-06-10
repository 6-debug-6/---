"""
PDF 离线解析管线

将 PDF 检修手册解析为结构化知识片段，供向量化入库。

解析流程：
    1. 页面拆分：PDF → 逐页处理
    2. 多模态提取：文本（段落切分）+ 表格（结构保留）+ 图片区域（坐标标注）
    3. 知识分片（Chunking）：按段落/表格/图片类型生成独立片段
    4. 输出文档列表：每片含内容 + 元信息，可直接送入向量库

依赖：
    - pdfplumber: 开源 PDF 解析库，支持文本、表格、图片区域提取
    - 视觉模型（千问 VL）：图片区域的描述生成在 llm_adapter 层调用

设计说明：
    - 这是一个离线（batch）处理管线，不暴露为实时 API
    - 解析结果先存入数据库（status=待校验），管理员人工校验后发布
    - 增量更新时复用此管线处理新版 PDF
"""
import os
import json
from pathlib import Path
from typing import Optional

import pdfplumber
from app.core.config import get_settings

settings = get_settings()


class PDFParser:
    """
    PDF 解析器

    逐页提取文本、表格、图片区域，并按语义拆分为知识片段（chunk）。
    每个 chunk 有明确的类型标记（text/table/image），便于后续差异化处理。
    """

    def __init__(self, filepath: str):
        self.filepath = filepath

    def parse(self) -> list[dict]:
        """
        解析 PDF 所有页面

        返回每页的结构化数据：
        {
            page: 页码,
            text: "纯文本内容",
            tables: [{headers, rows, raw}],
            image_regions: [{x0, y0, x1, y1, name}],
            chunks: [页面内拆分后的知识片段]
        }
        """
        pages = []
        with pdfplumber.open(self.filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                # 逐页提取
                page_data = {
                    "page": i + 1,
                    "text": page.extract_text() or "",           # 提取全部文本
                    "tables": self._extract_tables(page),         # 提取表格
                    "image_regions": self._extract_image_regions(page),  # 定位图片
                }
                # 将页面内容拆分为语义片段
                page_data["chunks"] = self._chunk_page(page_data)
                pages.append(page_data)
        return pages

    def _extract_tables(self, page) -> list[dict]:
        """
        提取页面中的表格

        使用 pdfplumber 的 extract_tables() 识别表格布局。
        返回结构化数据：表头列表 + 数据行列表 + 原始二维数组。
        """
        tables = []
        for t in page.extract_tables():
            if t:
                headers = t[0] if t else []       # 第一行为表头
                rows = t[1:] if len(t) > 1 else []  # 其余行为数据
                tables.append({"headers": headers, "rows": rows, "raw": t})
        return tables

    def _extract_image_regions(self, page) -> list[dict]:
        """
        检测页面中的内嵌图片区域

        pdfplumber 可识别 PDF 中的内嵌图片坐标（bbox），
        但不提取图片内容。图片内容的视觉分析需要额外工具或视觉模型。
        此处返回区域坐标供后续定位使用。
        """
        regions = []
        for img in getattr(page, "images", []):
            regions.append({
                "x0": img.get("x0"), "y0": img.get("y0"),
                "x1": img.get("x1"), "y1": img.get("y1"),
                "name": img.get("name", ""),
            })
        return regions

    def _chunk_page(self, page_data: dict) -> list[dict]:
        """
        将一页内容拆分为独立的知识片段

        拆分规则：
        - 文本：按双换行（段落边界）切分，过滤过短段落（≤20 字符）
        - 表格：每张表独立成一个 chunk，同时保留结构化数据
        - 图片：标记位置和类型，description 为空（待视觉模型填充）

        每个 chunk 包含 type 字段，后续向量化时可根据类型调整处理策略。
        """
        chunks = []
        text = page_data["text"]
        if text:
            # 按段落拆分（双换行为段落边界）
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for para in paragraphs:
                if len(para) > 20:  # 过滤过短段落（标题、页码等无意义内容）
                    chunks.append({
                        "type": "text",
                        "page": page_data["page"],
                        "content": para,
                    })

        # 表格独立成 chunk
        for table in page_data["tables"]:
            table_text = self._table_to_text(table)
            chunks.append({
                "type": "table",
                "page": page_data["page"],
                "content": table_text,
                "structured_data": table,   # 保留原始结构化数据
            })

        # 图片区域标记（描述待视觉模型填充）
        for region in page_data["image_regions"]:
            chunks.append({
                "type": "image",
                "page": page_data["page"],
                "bbox": {"x0": region["x0"], "y0": region["y0"],
                         "x1": region["x1"], "y1": region["y1"]},
                "description": "",  # 待视觉模型（千问 VL）填充
            })

        return chunks

    def _table_to_text(self, table: dict) -> str:
        """
        将表格结构转为可读文本（用于向量嵌入和检索）

        格式：表头行 + 数据行，用 | 分隔列
        这种格式保留了表格的语义信息，适合作为 Embedding 的输入。
        """
        lines = []
        if table.get("headers"):
            lines.append(" | ".join(str(h) for h in table["headers"]))
        for row in table.get("rows", []):
            lines.append(" | ".join(str(c) for c in row))
        return "\n".join(lines)

    def get_all_chunks(self, pages: list[dict]) -> list[dict]:
        """
        聚合所有页面的 chunk，并附加源文件信息

        用于将解析结果统一导出为待入库的文档列表。
        """
        all_chunks = []
        for page in pages:
            for chunk in page.get("chunks", []):
                chunk["source_file"] = os.path.basename(self.filepath)
                all_chunks.append(chunk)
        return all_chunks


async def parse_pdf_to_documents(pdf_path: str) -> list[dict]:
    """
    解析 PDF 文件为待入库的文档片段列表

    这是 PDF 解析的顶层入口函数，封装了完整的解析→分片→格式化流程。
    返回格式与 ChromaVectorStore.add_documents() 兼容：
        [{id, content, metadata: {page, type, source_file}}]

    参数：
        pdf_path: PDF 文件的绝对路径

    返回：
        可直接传入向量库的文档列表
    """
    parser = PDFParser(pdf_path)
    pages = parser.parse()          # 逐页提取
    chunks = parser.get_all_chunks(pages)  # 聚合所有片段

    documents = []
    for i, chunk in enumerate(chunks):
        doc = {
            "id": f"{os.path.basename(pdf_path)}_{i}",   # 唯一 ID：文件名_序号
            "content": chunk.get("content", ""),
            "metadata": {
                "page": chunk["page"],                     # 来源页码（便于追溯）
                "type": chunk["type"],                     # 片段类型
                "source_file": chunk.get("source_file", ""),  # 来源文件名
            },
        }
        documents.append(doc)
    return documents
