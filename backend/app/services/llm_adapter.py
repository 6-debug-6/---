"""
LLM 大模型适配层

设计思想：
    通过统一的抽象接口隔离不同大模型提供商的 API 差异。
    业务代码只依赖 ModelAdapter 接口，不直接调用具体模型。
    新增模型只需实现 Adapter 并注册到 ModelRouter。

模型分工：
    - DeepSeek: 文本主力模型，用于对话生成、意图重写、实体抽取
      优点：价格便宜，文本理解能力强；缺点：不支持图片输入
    - 千问 VL: 视觉模型，用于故障图片分析、PDF 图片描述生成
      优点：支持图文联合理解；缺点：价格较高

路由策略：
    - 纯文本请求 → DeepSeek
    - 含图片请求 → 千问 VL
    - 图片分析   → 千问 VL
    - 实体抽取   → DeepSeek（离线批量，成本优先）

扩展方式：
    新增模型（如本地部署的 Llama）只需：
    1. 实现 ModelAdapter 的三个抽象方法
    2. 在 ModelRouter 中添加对应的属性和路由逻辑
"""
from abc import ABC, abstractmethod
from typing import Optional
import httpx

from app.core.config import get_settings

settings = get_settings()


# ==================== 抽象接口 ====================

class ModelAdapter(ABC):
    """
    大模型适配器抽象基类

    定义三个核心能力的接口：
    - chat:             文本对话（所有模型必须支持）
    - analyze_image:    图片分析（视觉模型支持，纯文本模型抛出 NotImplementedError）
    - extract_entities: 实体抽取（从文本中提取知识图谱三元组）

    子类只需实现这三个方法，业务代码通过 ModelRouter 调用，
    无需关心底层是哪个模型提供商。
    """

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """
        文本对话

        参数：
            messages: OpenAI 格式的消息列表
                [{"role": "system", "content": "..."},
                 {"role": "user", "content": "..."}]
            **kwargs: 额外参数（temperature, max_tokens 等）

        返回：模型生成的文本回复
        """
        pass

    @abstractmethod
    async def analyze_image(self, image_url: str, prompt: str) -> str:
        """
        图片分析

        参数：
            image_url: 图片地址（本地 file:// 或远程 https://）
            prompt: 分析指令（如"描述这张图片中的设备异常"）

        返回：图片描述文本
        """
        pass

    @abstractmethod
    async def extract_entities(self, text: str) -> list[dict]:
        """
        实体关系抽取

        从文本中提取（主体, 关系, 客体）三元组，用于构建知识图谱。

        参数：
            text: 待抽取的文本

        返回：三元组列表
            [{"subject": "发动机", "relation": "可能发生", "object": "冒黑烟"}, ...]
        """
        pass


# ==================== DeepSeek 适配器 ====================

class DeepSeekAdapter(ModelAdapter):
    """
    DeepSeek 文本模型适配器

    调用 DeepSeek API（兼容 OpenAI 格式）。
    模型名称由配置 DEEPSEEK_MODEL 决定，默认 deepseek-chat。
    temperature 默认 0.3（工业场景需要稳定的输出，不宜过高）。
    """

    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        # 去掉尾部斜杠避免 URL 中出现双斜杠
        self.api_base = settings.DEEPSEEK_API_BASE.rstrip("/")
        self.model = settings.DEEPSEEK_MODEL

    async def _request(self, messages: list[dict], **kwargs) -> dict:
        """
        发送请求到 DeepSeek API

        DeepSeek API 兼容 OpenAI Chat Completions 格式：
        POST {api_base}/v1/chat/completions

        60 秒超时：大模型生成可能需要较长时间。
        """
        url = f"{self.api_base}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),     # 低温度保证专业场景回答稳定
            "max_tokens": kwargs.get("max_tokens", 4096),      # 单次回复最大长度
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()    # HTTP 错误直接抛出异常
            return resp.json()

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """文本对话：从 API 响应中提取 message.content"""
        data = await self._request(messages, **kwargs)
        return data["choices"][0]["message"]["content"]

    async def analyze_image(self, image_url: str, prompt: str) -> str:
        """
        DeepSeek 不支持图片分析
        调用此方法会抛出 NotImplementedError，上层代码应捕获并提示用户
        """
        raise NotImplementedError("DeepSeek 不支持图片分析，请使用千问 VL")

    async def extract_entities(self, text: str) -> list[dict]:
        """
        从文本中提取知识图谱三元组

        使用 System Prompt 引导 DeepSeek 输出纯 JSON 数组格式。
        temperature=0.1（极低）以保证输出格式稳定。
        解析失败时返回空列表（不阻塞知识入库流程）。
        """
        messages = [
            {"role": "system", "content": (
                "你是一个知识图谱构建助手。"
                "从以下文本中抽取设备和故障相关的实体及关系，以JSON数组格式返回。"
                "每个元素包含: subject, relation, object。"
                "只返回JSON数组，不要其他内容。"
            )},
            {"role": "user", "content": text},
        ]
        response = await self.chat(messages, temperature=0.1)
        import json
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # 模型输出可能包含 JSON 外的文本，解析失败时静默返回空
            return []


# ==================== 千问 VL 适配器 ====================

class QwenVLAdapter(ModelAdapter):
    """
    千问视觉模型适配器

    调用阿里云 DashScope API（兼容 OpenAI 格式）。
    支持图文混合输入：消息中可同时包含 image_url 和 text。

    千问 VL 的 API 格式与 DeepSeek 略有不同：
    - API 端点：{api_base}/chat/completions（而不是 /v1/chat/completions）
    - 消息中 content 可以是数组（多模态输入）：[{"type":"image_url",...}, {"type":"text",...}]
    """

    def __init__(self):
        self.api_key = settings.QWEN_API_KEY
        self.api_base = settings.QWEN_API_BASE.rstrip("/")
        self.model = settings.QWEN_VL_MODEL

    async def _request(self, messages: list[dict], **kwargs) -> dict:
        """发送请求到千问 API（兼容 OpenAI 格式）"""
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """文本对话（千问 VL 也支持纯文本）"""
        data = await self._request(messages, **kwargs)
        return data["choices"][0]["message"]["content"]

    async def analyze_image(self, image_url: str, prompt: str) -> str:
        """
        图片分析：发送图文混合请求

        千问 VL 支持在单条消息中同时包含图片 URL 和文本提示。
        这是视觉模型的核心能力——直接理解图片内容并生成文本描述。
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        data = await self._request(messages)
        return data["choices"][0]["message"]["content"]

    async def extract_entities(self, text: str) -> list[dict]:
        """实体抽取（与 DeepSeek 实现相同，使用纯文本模式）"""
        messages = [
            {"role": "system", "content": (
                "你是一个知识图谱构建助手。"
                "从以下文本中抽取设备和故障相关的实体及关系，以JSON数组格式返回。"
                "每个元素包含: subject, relation, object。"
                "只返回JSON数组，不要其他内容。"
            )},
            {"role": "user", "content": text},
        ]
        response = await self.chat(messages, temperature=0.1)
        import json
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return []


# ==================== 模型路由器 ====================

class ModelRouter:
    """
    模型路由器：根据请求类型智能选择模型

    使用懒加载（Lazy Initialization）：适配器实例在首次使用时才创建，
    避免启动时因为 API Key 未配置而导致初始化报错。

    路由规则：
    - 图文请求 → 千问 VL
    - 纯文本请求 → DeepSeek
    - 图片分析 → 千问 VL（强制）
    - 实体抽取 → DeepSeek（成本优先）
    """

    def __init__(self):
        # 懒加载：初始为 None，首次访问时创建实例
        self._deepseek: Optional[DeepSeekAdapter] = None
        self._qwen: Optional[QwenVLAdapter] = None

    @property
    def deepseek(self) -> DeepSeekAdapter:
        """懒加载 DeepSeek 适配器"""
        if not self._deepseek:
            self._deepseek = DeepSeekAdapter()
        return self._deepseek

    @property
    def qwen(self) -> QwenVLAdapter:
        """懒加载千问 VL 适配器"""
        if not self._qwen:
            self._qwen = QwenVLAdapter()
        return self._qwen

    async def chat(self, messages: list[dict], has_image: bool = False, **kwargs) -> str:
        """
        文本对话路由

        参数：
            messages: OpenAI 格式消息列表
            has_image: 消息中是否包含图片（True → 千问 VL, False → DeepSeek）

        注意：千问 VL 的 chat 也可以处理图片，前提是消息中已包含 image_url 块。
        如果只是纯文本但指定了 has_image=True，也会路由到千问 VL。
        """
        if has_image:
            return await self.qwen.chat(messages, **kwargs)
        return await self.deepseek.chat(messages, **kwargs)

    async def analyze_image(self, image_url: str, prompt: str) -> str:
        """图片分析（固定使用千问 VL）"""
        return await self.qwen.analyze_image(image_url, prompt)

    async def extract_entities(self, text: str) -> list[dict]:
        """实体抽取（固定使用 DeepSeek，成本更低）"""
        return await self.deepseek.extract_entities(text)


# ========== 全局路由器实例 ==========
# 整个应用共享一个路由器，内部管理多个模型适配器的生命周期
model_router = ModelRouter()
