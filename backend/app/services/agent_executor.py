"""
Agent 模式：多步工具调用的智能体

处理超出单次 RAG 检索能力的复杂查询，例如：
- "对比型号 A 和型号 B 的曲轴检修流程差异"
- "为什么发动机冒黑烟而不是白烟？分别是什么原因？"

Agent 执行流程（ReAct 模式）：
    1. 用户输入 → 大模型分析意图
    2. 判断是否需要工具 → 是 → 调用工具获取信息
    3. 工具结果回传 → 大模型判断是否继续调用工具
    4. 最多 3 轮工具调用 → 综合所有结果生成最终回答

与普通 RAG 的区别：
    普通 RAG：用户提问 → 检索知识 → 大模型生成 → 回答（单步）
    Agent 模式：用户提问 → (思考→调用工具→观察结果) × N → 回答（多步）

工具扩展：
    新增工具只需继承 AgentTool 并添加到 AGENT_TOOLS 列表。
"""
from typing import Optional
import json

from app.services.llm_adapter import model_router
from app.services.vector_store import vector_store


class AgentTool:
    """
    Agent 工具基类

    每个工具有一个名称（name，用于大模型识别）和描述（description，告诉大模型何时使用）。
    子类实现 execute 方法，接收参数，返回字符串结果。
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    async def execute(self, **kwargs) -> str:
        """
        执行工具调用

        参数由大模型从用户问题中提取，通过 kwargs 传入。
        返回字符串结果（通常是 JSON），大模型会基于此结果继续推理。
        """
        raise NotImplementedError


class SearchKnowledgeTool(AgentTool):
    """
    知识库检索工具

    用于在向量库中搜索与查询词相关的知识片段。
    大模型在需要查找设备故障原因、检修方案等信息时调用此工具。
    """

    def __init__(self):
        super().__init__(
            "search_knowledge",
            "在知识库中检索指定关键词，返回相关知识片段。参数: query (string)",
        )

    async def execute(self, query: str = "", **kwargs) -> str:
        # 调用向量检索，返回 Top-5 结果
        results = vector_store.search(query, top_k=5)
        # 将结果序列化为 JSON 字符串返回给大模型
        # content 截断到 300 字符避免 token 消耗过大
        return json.dumps([{
            "content": r["content"][:300],
            "source": r["metadata"].get("source_file", ""),
            "score": r["score"],
        } for r in results], ensure_ascii=False)


class SearchSimilarCaseTool(AgentTool):
    """
    相似案例检索工具

    按故障现象查找历史上报的类似案例。
    用于大模型回答"这个故障以前出现过吗？以前怎么修的？"等问题。
    """

    def __init__(self):
        super().__init__(
            "search_similar_case",
            "按故障现象查找相似历史案例。参数: symptom (string)",
        )

    async def execute(self, symptom: str = "", **kwargs) -> str:
        results = vector_store.search(symptom, top_k=5)
        return json.dumps([{
            "content": r["content"][:300],
            "source": r["metadata"].get("source_file", ""),
        } for r in results], ensure_ascii=False)


# ========== 已注册的工具列表 ==========
# 新增工具时在此添加实例即可
AGENT_TOOLS = [
    SearchKnowledgeTool(),
    SearchSimilarCaseTool(),
]


def _build_tool_descriptions() -> str:
    """
    构建工具描述的 System Prompt 片段

    告诉大模型有哪些工具可用、每个工具有什么功能、如何调用。
    格式为 TOOL_CALL: 后跟 JSON，大模型学会按此格式输出。
    """
    lines = ["你拥有以下工具可用："]
    for tool in AGENT_TOOLS:
        lines.append(f"- {tool.name}: {tool.description}")
    lines.append("")
    lines.append("当你需要检索信息时，请用以下格式调用工具：")
    lines.append('TOOL_CALL: {"tool": "工具名", "params": {"参数名": "值"}}')
    lines.append("收到 TOOL_RESULT 后继续回答用户问题。")
    return "\n".join(lines)


def _should_use_agent(query: str) -> bool:
    """
    判断用户查询是否需要 Agent 模式

    触发 Agent 的关键词：
    - 对比类：对比、区别、差异、比较、哪个更好
    - 推理类：为什么...而不是、分别、各自
    - 跨域类：多个、不同

    不含这些关键词的简单问题直接走普通 RAG 链路。
    """
    agent_keywords = ["对比", "区别", "差异", "比较", "为什么...而不是",
                       "多个", "不同", "哪个更好", "分别", "各自"]
    return any(kw in query for kw in agent_keywords)


async def execute_agent(
    user_message: str,
    conversation_history: list[dict] = None,
    context: dict = None,
) -> str:
    """
    Agent 模式主执行函数

    参数：
        user_message:       用户当前问题
        conversation_history: [{role, content}] 最近的对话历史
        context:            {device_model, task_step} 当前上下文

    返回：Agent 综合分析后的最终回答

    流程：
        1. 构建包含工具描述的 System Prompt
        2. 进入 Agent 循环（最多 3 轮）
        3. 每轮：大模型回复 → 检查是否调用工具 → 执行/返回
        4. 达到最大轮数后强制生成综合回答

    注意：
    - Agent 模式比普通 RAG 慢（多次 LLM 调用 + 工具执行），仅在需要时使用
    - 最多 3 轮工具调用防止无限循环
    """
    context = context or {}
    history = conversation_history or []

    # 构建包含工具描述的 System Prompt
    tool_descriptions = _build_tool_descriptions()
    system_prompt = f"""{tool_descriptions}

你是一个设备检修专家。用户当前问题可能涉及多步信息检索。
当前上下文：设备型号={context.get('device_model', '未指定')}

请先分析用户问题，判断需要使用哪些工具，然后依次调用工具获取信息，最后综合所有结果给出完整回答。"""

    # 构建初始消息列表
    messages = [{"role": "system", "content": system_prompt}]

    # 添加最近 6 轮对话历史（保持上下文，但不过长）
    for h in history[-6:]:
        messages.append({
            "role": h.get("role", "user"),
            "content": h.get("content", "")[:200]  # 截断过长历史
        })

    # 添加当前用户问题
    messages.append({"role": "user", "content": user_message})

    # ===== Agent 循环 =====
    max_iterations = 3  # 最多 3 轮工具调用
    for i in range(max_iterations):
        # 大模型推理当前状态
        response = await model_router.chat(messages, temperature=0.3)

        # 检查大模型是否决定调用工具
        if "TOOL_CALL:" in response:
            # 提取 TOOL_CALL 行
            tool_call_line = [l for l in response.split("\n") if "TOOL_CALL:" in l][0]
            tool_json_str = tool_call_line.split("TOOL_CALL:")[1].strip()

            try:
                # 解析工具调用 JSON
                tool_call = json.loads(tool_json_str)
                tool_name = tool_call.get("tool", "")
                params = tool_call.get("params", {})

                # 匹配并执行工具
                tool_result = ""
                for tool in AGENT_TOOLS:
                    if tool.name == tool_name:
                        tool_result = await tool.execute(**params)
                        break

                if not tool_result:
                    tool_result = f"工具 {tool_name} 未找到"

                # 将工具调用和结果追加到对话历史
                # assistant 消息记录工具调用请求
                messages.append({"role": "assistant", "content": response})
                # user 消息携带 TOOL_RESULT（模拟用户返回工具结果）
                messages.append({"role": "user", "content": f"TOOL_RESULT: {tool_result}"})

            except (json.JSONDecodeError, IndexError):
                # 工具调用格式无法解析，返回当前已有回答
                return response
        else:
            # 大模型不再需要工具，直接返回最终回答
            return response

    # 达到最大轮数后，强制生成综合回答
    messages.append({
        "role": "user",
        "content": "请基于以上所有 TOOL_RESULT 的信息，给出一个综合性的完整回答。"
    })
    final_response = await model_router.chat(messages, temperature=0.3)
    return final_response


def is_agent_query(query: str) -> bool:
    """
    判断用户查询是否应走 Agent 模式

    用于 API 层的路由决策：
    - True  → 调用 execute_agent() 走多步推理
    - False → 走普通 RAG 单步回答
    """
    return _should_use_agent(query)
