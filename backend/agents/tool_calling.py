"""
Tool-Calling Agent 实现
支持自主调用工具完成数据分析任务
"""
import json
import re
import time
from typing import Dict, List, Any, Optional, Tuple, Callable, Awaitable

import dashscope
from dashscope import MultiModalConversation, Generation

from backend.config import DASHSCOPE_API_KEY, DASHSCOPE_MODEL
from backend.agents.registry import ToolRegistry
from backend.agents.base import BaseAgent
from backend.tools.base import ToolResult


class ToolCallingAgent(BaseAgent):
    """
    支持工具调用的 Agent

    通过 ReAct 模式（Reason + Act）循环：
    1. 接收用户消息
    2. LLM 决定是否调用工具
    3. 执行工具（如果需要）
    4. 将工具结果反馈给 LLM
    5. 生成最终回复
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        api_key: Optional[str] = None,
        model: str = DASHSCOPE_MODEL
    ):
        """
        初始化 Agent

        :param tool_registry: 工具注册中心
        :param api_key: API 密钥
        :param model: 模型名称
        """
        self.tool_registry = tool_registry
        self.api_key = api_key or DASHSCOPE_API_KEY
        self.model = model

        if self.api_key:
            dashscope.api_key = self.api_key

    def _build_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        构建系统提示词

        :param context: 上下文信息
        :return: 系统提示词
        """
        sheets_info = context.get("sheets_info", [])

        # 构建数据描述
        sheets_desc = []
        for sheet in sheets_info:
            desc = f"- {sheet.get('file_name', '')} ({sheet.get('sheet_name', '')}): "
            desc += f"{sheet.get('row_count', 0)}行，{len(sheet.get('columns', []))}列"
            columns = sheet.get('columns', [])
            if columns:
                desc += f"\n  列：{', '.join(columns[:10])}{'...' if len(columns) > 10 else ''}"
            sheets_desc.append(desc)

        # 获取可用工具列表
        available_tools = self.tool_registry.get_all()
        tools_desc = []
        for tool in available_tools:
            tools_desc.append(f"- {tool.definition.name}: {tool.definition.description}")

        # 生成工具调用示例
        tool_examples = []
        for tool in available_tools:
            example = tool.get_usage_example()
            if example:
                tool_examples.append(f"  {tool.definition.name}: {example}")
        examples_text = chr(10).join(tool_examples) if tool_examples else "暂无示例"

        return f"""你是智能数据分析助手，可调用工具分析数据。

可用数据：{chr(10).join(sheets_desc) if sheets_desc else '暂无数据'}
可用工具：{', '.join(tools_desc) if tools_desc else '暂无'}

===== 回复格式规范（重要）=====
每次回复只能选择以下一种格式，不能同时包含两种：

1. 工具调用格式（需要调用工具时）：
```json
{{"tool_call": {{"name": "工具名", "arguments": {{"参数名": "参数值"}}}}}}
```
工具调用示例：
{examples_text}

2. 直接回复（不需要调用工具时）：
```json
{{"response": "回复内容"}}
```

注意：不能同时返回 tool_call 和 response，每次只能选择一种格式！

工作流程：
1. 用户上传文件后：确认接收，简述数据结构，询问分析需求（不要自动调用工具）
2. 用户请求分析时：先调用 analyze_data，再根据需求决定是否生成图表
3. 用户请求图表时：调用 generate_chart 或 auto_generate_charts
4. 用户明确请求生成报告（如"生成分析报告"、"生成报告"等关键词）时：立即调用 generate_dynamic_report 工具
5. 重要：即使用户是第一次请求，只要明确要求生成报告，就必须调用 generate_dynamic_report 工具生成，不能仅回复消息
6. 关键规则：当用户消息中包含"并生成报告"、"生成分析报告"、"生成报告"等明确请求时，必须在调用 analyze_data 分析数据后，紧接着调用 generate_dynamic_report 生成报告，这是强制要求

注意：
- 不要自动生成图表，仅在用户明确要求或分析需要时调用
- 支持多轮分析，可在一次对话中连续调用多个工具
- 回复要简洁专业，包含数据洞察和建议
"""

    async def run(
        self,
        user_message: str,
        context: Dict[str, Any],
        perf: Optional[Any] = None
    ) -> Tuple[str, List[ToolResult]]:
        """
        运行 Agent 循环

        :param user_message: 用户消息
        :param context: 上下文（包含 session_id, sheets_info 等）
        :param perf: 可选的性能记录器
        :return: (最终回复，工具执行结果列表)
        """
        # 初始化消息历史
        messages = [{"role": "user", "content": user_message}]
        tool_results: List[ToolResult] = []
        tool_call_history: List[str] = []  # 记录已调用的工具（防止重复循环）
        llm_call_count = 0
        tool_call_count = 0

        # 检测用户是否请求生成报告
        user_message_lower = user_message.lower()
        needs_report_generation = any(kw in user_message_lower for kw in [
            "生成报告", "生成分析报告", "并生成报告", "create report", "generate report"
        ])
        # 标记是否已调用 analyze_data（用于报告生成流程）
        analyze_data_called = False
        # 标记是否需要强制执行报告生成
        force_report_generation = needs_report_generation

        # Agent 循环 - 移除硬性次数限制，使用智能退出机制
        print(f"[TOOL_CALLING_AGENT] 开始 Agent 循环，force_report_generation={force_report_generation}")
        while True:
            # 调用 LLM
            llm_start = time.time()
            response, error = self._call_llm(messages, context)
            llm_time = time.time() - llm_start
            llm_call_count += 1

            # 记录性能
            if perf:
                perf.log(f"agent_llm_call_{llm_call_count}", llm_time)
                print(f"[PERF] LLM 调用 #{llm_call_count}: {llm_time:.3f}s")

            if error:
                return f"AI 服务错误：{error}", tool_results

            # 解析响应
            parsed = self._parse_response(response)

            # 检查是否是工具调用
            if "tool_call" in parsed:
                tool_call = parsed["tool_call"]
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                # 防止无限循环：检查是否重复调用相同的工具
                call_signature = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                if call_signature in tool_call_history:
                    messages.append({
                        "role": "user",
                        "content": f"工具 {tool_name} 已用相同参数调用过，请不要重复调用，直接总结分析结果。"
                    })
                    continue

                # 防止过多工具调用：超过 15 次后提醒 LLM 收敛
                if len(tool_results) >= 15:
                    messages.append({
                        "role": "user",
                        "content": "已执行较多工具调用，请总结当前分析结果并回复用户。"
                    })
                    continue

                tool_call_history.append(call_signature)

                # 获取工具
                tool = self.tool_registry.get(tool_name)
                if not tool:
                    # 工具不存在，反馈给 LLM
                    messages.append({
                        "role": "assistant",
                        "content": f"请求了不存在的工具：{tool_name}"
                    })
                    continue

                # 自动注入 session_id（如果参数中没有但 context 中有）
                if "session_id" not in tool_args and "session_id" in context:
                    tool_args["session_id"] = context["session_id"]

                # 执行工具
                tool_start = time.time()
                result = await tool.execute(**tool_args)
                tool_time = time.time() - tool_start
                tool_call_count += 1

                # 记录性能
                if perf:
                    perf.log(f"agent_tool_call_{tool_call_count}_{tool_name}", tool_time)
                    print(f"[PERF] 工具调用 #{tool_call_count} ({tool_name}): {tool_time:.3f}s")

                tool_results.append(result)

                # 将工具调用和结果添加到消息历史
                # 注意：DashScope MultiModalConversation 不支持 role="tool"
                # 所以使用 assistant + user 的组合来传递工具结果
                # 使用用户友好的消息，不暴露工具名和内部参数
                messages.append({
                    "role": "assistant",
                    "content": f"正在处理{self._get_action_name(tool_name)}..."
                })

                # 工具执行失败时，不将详细错误消息添加到历史，避免 LLM 复述错误
                # 而是用一个中性提示让 LLM 重试或跳过此工具
                if not result.success:
                    messages.append({
                        "role": "user",
                        "content": f"{self._get_action_name(tool_name)}执行失败，请尝试其他方法或跳过此步骤。"
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": self._get_tool_result_message(tool_name, result)
                    })

                # 跟踪 analyze_data 是否已调用
                if tool_name == "analyze_data":
                    analyze_data_called = True

                # 如果工具执行失败，继续循环让 LLM 决定下一步
                if not result.success:
                    continue

                # 检查是否已经完成了核心任务（如报告已生成），如果是则可以提前结束
                if result.data and isinstance(result.data, dict):
                    if result.data.get('report_id'):
                        # 报告已生成，可以提前结束，让 LLM 生成总结回复
                        messages.append({
                            "role": "user",
                            "content": "报告已生成，请总结分析结果并告诉用户可以进行更多分析。"
                        })
                        force_report_generation = False  # 报告已生成，不需要强制

            elif "response" in parsed:
                # 检查是否需要强制生成报告（用户明确要求但 LLM 没有调用）
                if force_report_generation and not any(
                    r.data and isinstance(r.data, dict) and r.data.get('report_id')
                    for r in tool_results
                ):
                    # 用户要求生成报告，但 LLM 只返回了普通回复
                    # 如果已经调用了 analyze_data，现在应该调用 generate_dynamic_report
                    if analyze_data_called:
                        # 强制执行报告生成工具
                        report_tool = self.tool_registry.get("generate_dynamic_report")
                        if report_tool:
                            tool_start = time.time()
                            result = await report_tool.execute(
                                session_id=context.get("session_id"),
                                user_request=user_message
                            )
                            tool_time = time.time() - tool_start
                            tool_call_count += 1

                            if perf:
                                perf.log(f"agent_tool_call_{tool_call_count}_generate_dynamic_report", tool_time)
                                print(f"[PERF] 工具调用 #{tool_call_count} (generate_dynamic_report): {tool_time:.3f}s")

                            tool_results.append(result)

                            messages.append({
                                "role": "assistant",
                                "content": "正在生成报告..."
                            })
                            messages.append({
                                "role": "user",
                                "content": self._get_tool_result_message("generate_dynamic_report", result)
                            })

                            if result.success and result.data and result.data.get('report_id'):
                                # 报告生成成功，让 LLM 生成总结回复
                                messages.append({
                                    "role": "user",
                                    "content": "报告已生成，请总结分析结果并告诉用户可以进行更多分析。"
                                })
                                # 再次调用 LLM 生成总结
                                continue

                    # 如果没有调用 analyze_data，提醒 LLM 先分析数据
                    else:
                        messages.append({
                            "role": "user",
                            "content": "用户要求生成报告，请先调用 analyze_data 分析数据，然后生成报告。"
                        })
                        continue

                # 直接回复，结束循环
                return parsed["response"], tool_results

            else:
                # 未知格式，直接返回原始响应
                return response, tool_results

    def _call_llm(
        self,
        messages: List[Dict],
        context: Dict[str, Any]
    ) -> Tuple[str, Optional[str]]:
        """
        调用 LLM

        :param messages: 消息历史
        :param context: 上下文
        :return: (响应内容，错误信息)
        """
        system_prompt = self._build_system_prompt(context)

        # 构建 API 消息格式
        api_messages = [
            {"role": "system", "content": system_prompt}
        ]

        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                content = [{"text": content}]
            elif isinstance(content, dict):
                content = [{"text": json.dumps(content)}]
            api_messages.append({"role": msg["role"], "content": content})

        # 调试日志
        print(f"[DEBUG] LLM 调用：model={self.model}, api_key={'已配置' if self.api_key else '未配置'}")

        try:
            response = MultiModalConversation.call(
                model=self.model,
                api_key=self.api_key,
                messages=api_messages,
                result_format='message',
                timeout=300  # 报告生成可能需要较长时间，设置为 5 分钟
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content

                # 处理不同类型的返回
                if isinstance(content, list):
                    text = ' '.join(
                        item.get('text', '') if isinstance(item, dict) else str(item)
                        for item in content
                    )
                    print(f"[DEBUG] LLM 调用完成：{len(text)} 字符")
                    return text, None
                elif isinstance(content, dict):
                    text = content.get('text', '')
                    print(f"[DEBUG] LLM 调用完成：{len(text)} 字符")
                    return text, None
                text = str(content) if content else ""
                print(f"[DEBUG] LLM 调用完成：{len(text)} 字符")
                return text, None

            else:
                print(f"[ERROR] LLM 调用失败：{response.code} - {response.message}")
                return "", f"API 错误：{response.code} - {response.message}"

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[ERROR] LLM 调用异常：{error_detail}")
            return "", f"异常：{type(e).__name__} - {str(e)}"

    def _parse_response(self, response: str) -> Dict:
        """
        解析 LLM 响应

        尝试从响应中提取 JSON 格式的工具调用或回复

        :param response: LLM 响应文本
        :return: 解析后的字典
        """
        if not response:
            return {"response": "抱歉，我没有收到有效的响应。"}

        try:
            # 尝试提取代码块中的 JSON
            # 匹配 ```json ... ``` 或 ``` ... ```
            code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if code_block_match:
                json_str = code_block_match.group(1)
            else:
                # 尝试提取普通 JSON（非贪婪匹配，找到第一个完整的 JSON 对象）
                json_match = re.search(r'\{.*?\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                else:
                    return {"response": self._clean_response_content(response)}

            # 尝试直接解析
            try:
                parsed = json.loads(json_str)
                if "response" in parsed:
                    parsed["response"] = self._clean_response_content(parsed["response"])
                return parsed
            except json.JSONDecodeError:
                # 如果失败，可能是多个 JSON 对象（如 {"response": "..."}, {"tool_call": {...}}）
                # 尝试分割并分别解析
                if '},' in json_str or '\n{' in json_str:
                    # 尝试用多种方式分割
                    parts = re.split(r'\}\s*,\s*\{|\}\s*\n\s*\{', json_str)
                    for i, part in enumerate(parts):
                        # 补回被分割的括号
                        if i == 0 and not part.endswith('}'):
                            part = part + '}'
                        elif i > 0 and not part.startswith('{'):
                            part = '{' + part
                        if not part.startswith('{'):
                            part = '{' + part
                        if not part.endswith('}'):
                            part = part + '}'
                        try:
                            candidate = json.loads(part)
                            # 优先返回 tool_call（工具调用优先级更高）
                            if "tool_call" in candidate:
                                return candidate
                            # 如果没有 tool_call，保留 response
                            if "response" in candidate:
                                candidate["response"] = self._clean_response_content(candidate["response"])
                                return candidate
                        except json.JSONDecodeError:
                            continue

                # 都失败则返回原始响应
                return {"response": self._clean_response_content(response)}

        except json.JSONDecodeError as e:
            print(f"JSON 解析失败：{e}，响应内容：{response[:200]}")
        except Exception as e:
            print(f"解析响应失败：{e}")

        # 无法解析时，作为普通回复（清理可能的代码块标记）
        return {"response": self._clean_response_content(response)}

    def _clean_response_content(self, content: str) -> str:
        """
        清理响应内容，移除可能的代码块标记

        :param content: 原始响应内容
        :return: 清理后的内容
        """
        if not content:
            return content

        # 移除包裹的 ```json 或 ``` 代码块标记（只移除外层）
        # 处理 ```json {...}``` 格式
        content = re.sub(r'^\s*```json\s*', '', content)
        content = re.sub(r'\s*```\s*$', '', content)
        # 处理 ``` {...}``` 格式
        content = re.sub(r'^\s*```\s*', '', content)

        return content

    def _sanitize_data_for_llm(self, data: Any, max_length: int = 5000) -> Any:
        """
        清理数据以适应 LLM 输入限制

        :param data: 原始数据
        :param max_length: 最大长度
        :return: 清理后的数据
        """
        if data is None:
            return None

        if isinstance(data, str):
            return data[:max_length]

        if isinstance(data, (int, float, bool)):
            return data

        if isinstance(data, list):
            # 截断长列表
            return [self._sanitize_data_for_llm(item, max_length // 10)
                    for item in data[:50]]

        if isinstance(data, dict):
            # 截断长字典
            return {
                k: self._sanitize_data_for_llm(v, max_length // 10)
                for k, v in list(data.items())[:20]
            }

        # 其他类型转为字符串
        return str(data)[:max_length]

    def _get_data_summary(self, data: Any, max_length: int = 500) -> str:
        """
        获取数据的简短摘要，用于传递给 LLM

        :param data: 原始数据
        :param max_length: 最大长度
        :return: 数据摘要字符串
        """
        if data is None:
            return "无数据"

        if isinstance(data, str):
            return data[:max_length]

        if isinstance(data, dict):
            # 提取关键信息
            summary_parts = []
            if "row_count" in data:
                summary_parts.append(f"行数：{data['row_count']}")
            if "column_count" in data:
                summary_parts.append(f"列数：{data['column_count']}")
            if "quality_score" in data:
                summary_parts.append(f"质量评分：{data['quality_score']}")
            if "message" in data:
                summary_parts.append(data["message"])

            if summary_parts:
                return ", ".join(summary_parts)

            # 如果没有预定义字段，返回键列表
            keys = list(data.keys())[:10]
            return f"包含字段：{', '.join(keys)}"

        if isinstance(data, list):
            return f"列表，长度：{len(data)}"

        return str(data)[:max_length]

    def _get_tool_result_message(self, tool_name: str, result: ToolResult) -> str:
        """
        将工具结果转换为用户友好的消息（不暴露内部路径、工具名等）

        :param tool_name: 工具名称
        :param result: 工具执行结果
        :return: 用户友好的消息
        """
        if not result.success:
            # 错误消息也需友好处理
            error_msg = str(result.error) if result.error else "操作失败"
            # 移除路径、函数名等内部信息
            if "session_id" in error_msg:
                error_msg = "请先上传数据文件"
            # 更精确的错误匹配：只有当错误明确提到"文件"时才返回文件相关提示
            elif "未找到数据文件" in error_msg or "找不到数据文件" in error_msg:
                error_msg = "数据文件已上传但无法读取，请检查文件格式后重试"
            elif "列" in error_msg and "不存在" in error_msg:
                error_msg = "指定的列不存在，请检查列名是否正确"
            elif "不存在" in error_msg or "未找到" in error_msg:
                # 其他"未找到"情况，返回更具体的提示
                error_msg = "操作失败，请检查数据是否存在或格式是否正确"
            return error_msg

        # 根据工具类型返回友好消息，包含更多数据洞察
        friendly_messages = {
            "analyze_data": lambda r: self._format_analyze_data_message(r),
            "generate_dynamic_report": lambda r: f"报告已生成，包含数据概览、质量评估和可视化图表，可在线查看或下载",
            "get_report": lambda r: "报告已找到",
            "update_report": lambda r: "报告已更新",
            "generate_chart": lambda r: f"已生成图表：{r.data.get('title', '数据可视化') if r.data else '数据可视化'}",
            "generate_correlation_heatmap": lambda r: "已生成变量相关性热力图，展示各数值列之间的关联程度",
            "auto_generate_charts": lambda r: f"已自动生成 {len(r.data.get('charts', [])) if r.data else 0} 个可视化图表",
            "get_column_distribution": lambda r: self._format_distribution_message(r),
            "get_column_statistics": lambda r: self._format_statistics_message(r),
        }

        handler = friendly_messages.get(tool_name)
        if handler:
            return handler(result)

        # 默认返回
        return result.message if result.message else "操作已完成"

    def _format_analyze_data_message(self, result: ToolResult) -> str:
        """格式化数据分析结果消息"""
        if not result.data:
            return "已完成数据分析"

        # 合并分析结果
        merged = result.data.get("merged_analysis", {})
        if merged:
            stats = merged.get("basic_stats", {})
            row_count = stats.get("row_count", 0)
            col_count = stats.get("column_count", 0)
            quality = stats.get("quality_score", 0)
            return f"已完成合并分析：{row_count}行 x {col_count}列，数据质量评分 {quality:.1f}/100"

        # 独立分析结果
        individual = result.data.get("individual_analyses", {})
        if individual:
            total_rows = sum(
                sheet.get("basic_stats", {}).get("row_count", 0)
                for sheet in individual.values()
            )
            return f"已完成分析，共 {len(individual)} 个数据表，总计 {total_rows} 行数据"

        return "已完成数据分析"

    def _format_distribution_message(self, result: ToolResult) -> str:
        """格式化分布分析结果消息"""
        if not result.data:
            return "已完成分布分析"

        column_name = result.data.get("column_name", "该列")
        distribution_type = result.data.get("type", "categorical")
        top_values = result.data.get("top_values", {})

        if top_values:
            top_item = list(top_values.items())[0]
            return f"列 '{column_name}' 分布分析完成，最高频值为 '{top_item[0]}' ({top_item[1]}次)"

        return f"已完成列 '{column_name}' 的分布分析"

    def _format_statistics_message(self, result: ToolResult) -> str:
        """格式化统计分析结果消息"""
        if not result.data:
            return "已完成统计分析"

        column_name = result.data.get("column_name", "该列")
        stats_type = result.data.get("type", "")

        if stats_type == "numeric":
            mean = result.data.get("mean")
            median = result.data.get("median")
            if mean is not None and median is not None:
                return f"列 '{column_name}' 统计分析：均值={mean:.2f}, 中位数={median:.2f}"
        else:
            unique_count = result.data.get("unique_count", 0)
            return f"列 '{column_name}' 统计分析：共 {unique_count} 个唯一值"

        return f"已完成列 '{column_name}' 的统计分析"

    def _get_action_name(self, tool_name: str) -> str:
        """
        将工具名映射为友好的动作名称（不暴露内部工具名）

        :param tool_name: 工具名称
        :return: 友好的动作描述
        """
        action_map = {
            "analyze_data": "数据分析",
            "generate_dynamic_report": "报告生成",
            "get_report": "获取报告",
            "update_report": "报告更新",
            "generate_chart": "图表绘制",
            "generate_correlation_heatmap": "相关性分析",
            "auto_generate_charts": "智能图表生成",
            "get_column_distribution": "分布分析",
            "get_column_statistics": "统计分析",
        }
        return action_map.get(tool_name, "处理")

    async def run_streaming(
        self,
        user_message: str,
        context: Dict[str, Any],
        text_callback: Callable[[str], Awaitable[None]],
        perf: Optional[Any] = None
    ) -> Tuple[str, List[ToolResult]]:
        """
        运行 Agent 循环（流式版本）

        :param user_message: 用户消息
        :param context: 上下文（包含 session_id, sheets_info 等）
        :param text_callback: 文本流回调函数，接收文本片段
        :param perf: 可选的性能记录器
        :return: (最终回复，工具执行结果列表)
        """
        # 初始化消息历史
        messages = [{"role": "user", "content": user_message}]
        tool_results: List[ToolResult] = []
        tool_call_history: List[str] = []
        llm_call_count = 0
        tool_call_count = 0

        # 检测用户是否请求生成报告
        user_message_lower = user_message.lower()
        needs_report_generation = any(kw in user_message_lower for kw in [
            "生成报告", "生成分析报告", "并生成报告", "create report", "generate report"
        ])
        # 标记是否已调用 analyze_data（用于报告生成流程）
        analyze_data_called = False
        # 标记是否需要强制执行报告生成
        force_report_generation = needs_report_generation

        # Agent 循环
        while True:
            # 调用 LLM（流式）
            llm_start = time.time()
            response, error = await self._call_llm_streaming(messages, context, text_callback)
            llm_time = time.time() - llm_start
            llm_call_count += 1

            # 记录性能
            if perf:
                perf.log(f"agent_llm_call_{llm_call_count}", llm_time)
                print(f"[PERF] LLM 调用 #{llm_call_count}: {llm_time:.3f}s")

            if error:
                return f"AI 服务错误：{error}", tool_results

            # 解析响应
            parsed = self._parse_response(response)

            # 检查是否是工具调用
            if "tool_call" in parsed:
                tool_call = parsed["tool_call"]
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                # 防止无限循环
                call_signature = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                if call_signature in tool_call_history:
                    messages.append({
                        "role": "user",
                        "content": f"工具 {tool_name} 已用相同参数调用过，请不要重复调用，直接总结分析结果。"
                    })
                    continue

                if len(tool_results) >= 15:
                    messages.append({
                        "role": "user",
                        "content": "已执行较多工具调用，请总结当前分析结果并回复用户。"
                    })
                    continue

                tool_call_history.append(call_signature)

                # 获取工具
                tool = self.tool_registry.get(tool_name)
                if not tool:
                    messages.append({
                        "role": "assistant",
                        "content": f"请求了不存在的工具：{tool_name}"
                    })
                    continue

                # 自动注入 session_id
                if "session_id" not in tool_args and "session_id" in context:
                    tool_args["session_id"] = context["session_id"]

                # 执行工具
                tool_start = time.time()
                result = await tool.execute(**tool_args)
                tool_time = time.time() - tool_start
                tool_call_count += 1

                # 记录性能
                if perf:
                    perf.log(f"agent_tool_call_{tool_call_count}_{tool_name}", tool_time)
                    print(f"[PERF] 工具调用 #{tool_call_count} ({tool_name}): {tool_time:.3f}s")

                tool_results.append(result)

                # 将工具调用和结果添加到消息历史
                messages.append({
                    "role": "assistant",
                    "content": f"正在处理{self._get_action_name(tool_name)}..."
                })

                # 工具执行失败时，不将详细错误消息添加到历史，避免 LLM 复述错误
                # 而是用一个中性提示让 LLM 重试或跳过此工具
                if not result.success:
                    messages.append({
                        "role": "user",
                        "content": f"{self._get_action_name(tool_name)}执行失败，请尝试其他方法或跳过此步骤。"
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": self._get_tool_result_message(tool_name, result)
                    })

                # 跟踪 analyze_data 是否已调用
                if tool_name == "analyze_data":
                    analyze_data_called = True

                if not result.success:
                    continue

                if result.data and isinstance(result.data, dict):
                    if result.data.get('report_id'):
                        messages.append({
                            "role": "user",
                            "content": "报告已生成，请总结分析结果并告诉用户可以进行更多分析。"
                        })
                        force_report_generation = False

            elif "response" in parsed:
                # 检查是否需要强制生成报告（用户明确要求但 LLM 没有调用）
                if force_report_generation and not any(
                    r.data and isinstance(r.data, dict) and r.data.get('report_id')
                    for r in tool_results
                ):
                    # 用户要求生成报告，但 LLM 只返回了普通回复
                    # 如果已经调用了 analyze_data，现在应该调用 generate_dynamic_report
                    if analyze_data_called:
                        # 强制执行报告生成工具
                        report_tool = self.tool_registry.get("generate_dynamic_report")
                        if report_tool:
                            tool_start = time.time()
                            result = await report_tool.execute(
                                session_id=context.get("session_id"),
                                user_request=user_message
                            )
                            tool_time = time.time() - tool_start
                            tool_call_count += 1

                            if perf:
                                perf.log(f"agent_tool_call_{tool_call_count}_generate_dynamic_report", tool_time)
                                print(f"[PERF] 工具调用 #{tool_call_count} (generate_dynamic_report): {tool_time:.3f}s")

                            tool_results.append(result)

                            await text_callback("\n\n正在生成报告...\n\n")
                            messages.append({
                                "role": "assistant",
                                "content": "正在生成报告..."
                            })
                            messages.append({
                                "role": "user",
                                "content": self._get_tool_result_message("generate_dynamic_report", result)
                            })

                            if result.success and result.data and result.data.get('report_id'):
                                # 报告生成成功，让 LLM 生成总结回复
                                messages.append({
                                    "role": "user",
                                    "content": "报告已生成，请总结分析结果并告诉用户可以进行更多分析。"
                                })
                                # 再次调用 LLM 生成总结
                                continue

                    # 如果没有调用 analyze_data，提醒 LLM 先分析数据
                    else:
                        messages.append({
                            "role": "user",
                            "content": "用户要求生成报告，请先调用 analyze_data 分析数据，然后生成报告。"
                        })
                        continue

                return parsed["response"], tool_results

            else:
                return response, tool_results

    async def _call_llm_streaming(
        self,
        messages: List[Dict],
        context: Dict[str, Any],
        text_callback: Callable[[str], Awaitable[None]]
    ) -> Tuple[str, Optional[str]]:
        """
        调用 LLM（流式版本）

        :param messages: 消息历史
        :param context: 上下文
        :param text_callback: 文本流回调函数
        :return: (响应内容，错误信息)
        """
        system_prompt = self._build_system_prompt(context)

        # 构建 API 消息格式
        api_messages = [
            {"role": "system", "content": system_prompt}
        ]

        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                content = [{"text": content}]
            elif isinstance(content, dict):
                content = [{"text": json.dumps(content)}]
            api_messages.append({"role": msg["role"], "content": content})

        # 调试日志
        print(f"[DEBUG] 流式调用 LLM: model={self.model}, api_key={'已配置' if self.api_key else '未配置'}")

        try:
            # 使用 MultiModalConversation API 进行流式调用
            response = MultiModalConversation.call(
                model=self.model,
                api_key=self.api_key,
                messages=api_messages,
                stream=True,  # 启用流式
                result_format='message',
                timeout=300  # 报告生成可能需要较长时间，设置为 5 分钟
            )

            full_response = ""
            chunk_count = 0
            for chunk in response:
                if chunk.status_code == 200:
                    content = chunk.output.choices[0].message.content
                    if content:
                        # 处理不同类型的内容（可能是字符串、列表或字典）
                        if isinstance(content, list):
                            text = ' '.join(
                                item.get('text', '') if isinstance(item, dict) else str(item)
                                for item in content
                            )
                        elif isinstance(content, dict):
                            text = content.get('text', '')
                        else:
                            text = str(content)

                        full_response += text
                        chunk_count += 1
                else:
                    print(f"[ERROR] 流式调用失败：{chunk.code} - {chunk.message}")
                    return "", f"API 错误：{chunk.code} - {chunk.message}"

            print(f"[DEBUG] 流式调用完成：共 {chunk_count} 个 chunk，{len(full_response)} 字符")

            # 解析完整响应，过滤工具调用标记，发送用户友好的内容
            parsed = self._parse_response(full_response)

            if "tool_call" in parsed:
                # 工具调用：发送 1 条友好消息，不暴露原始 JSON
                tool_name = parsed["tool_call"]["name"]
                # 添加换行符，让后续内容另起一行
                await text_callback(f"正在处理{self._get_action_name(tool_name)}...\n\n")
            elif "response" in parsed:
                # 最终回复：流式发送处理后的内容（移除 JSON 标记）
                response_text = self._clean_response_content(parsed["response"])
                # 逐字发送以保持流式体验
                for char in response_text:
                    await text_callback(char)
            else:
                # 未知格式：发送原始响应（清理后）
                cleaned = self._clean_response_content(full_response)
                await text_callback(cleaned)

            return full_response, None

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[ERROR] 流式调用异常：{error_detail}")
            return "", f"异常：{type(e).__name__} - {str(e)}"


class SimpleAgent(BaseAgent):
    """
    简单 Agent - 不支持工具调用，仅用于简单对话

    适用于不需要复杂工具调用的场景
    """

    def __init__(self, api_key: Optional[str] = None, model: str = DASHSCOPE_MODEL):
        self.api_key = api_key or DASHSCOPE_API_KEY
        self.model = model

        if self.api_key:
            dashscope.api_key = self.api_key

    async def run(
        self,
        user_message: str,
        context: Dict[str, Any]
    ) -> Tuple[str, List[ToolResult]]:
        """简单对话，不调用工具"""
        sheets_info = context.get("sheets_info", [])

        system_prompt = f"""你是一个数据分析助手。
可用数据：
{chr(10).join(f"- {s.get('file_name', '')} ({s.get('sheet_name', '')}): {s.get('row_count', 0)}行" for s in sheets_info)}

请回答用户的问题。"""

        messages = [{"role": "user", "content": user_message}]

        api_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                content = [{"text": content}]
            api_messages.append({"role": msg["role"], "content": content})

        try:
            response = MultiModalConversation.call(
                model=self.model,
                api_key=self.api_key,
                messages=api_messages,
                result_format='message'
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    text = ' '.join(
                        item.get('text', '') if isinstance(item, dict) else str(item)
                        for item in content
                    )
                    return text, []
                return str(content) if content else "抱歉，我无法回答。", []
            else:
                return f"API 错误：{response.code}", []

        except Exception as e:
            return f"异常：{str(e)}", []
