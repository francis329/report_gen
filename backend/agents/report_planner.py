"""
报告规划器
根据用户意图和数据特征，智能生成报告结构
"""
import json
from typing import Dict, List, Any, Optional

from backend.models.report import ReportPlan, ChapterPlan, ChartSpec
from backend.services.session_manager import SessionManager
from backend.config import DASHSCOPE_API_KEY, DASHSCOPE_MODEL


class ReportPlanner:
    """
    报告规划器

    核心职责：
    1. 解析用户意图
    2. 探索数据结构
    3. 智能生成报告结构（章节名称、内容、维度完全动态，不是固定模板）
    """

    def __init__(self, session_manager: SessionManager, api_key: Optional[str] = None):
        self.session_manager = session_manager
        self.api_key = api_key or DASHSCOPE_API_KEY
        self.model = DASHSCOPE_MODEL

    async def plan(self, session_id: str, user_request: str) -> ReportPlan:
        """
        生成报告规划

        :param session_id: 会话 ID
        :param user_request: 用户请求（如"分析主被叫失败原因"）
        :return: ReportPlan
        """
        print(f"[REPORT_PLANNER] 开始生成报告规划，session_id: {session_id}")
        print(f"[REPORT_PLANNER] 用户请求：{user_request}")

        # 1. 获取数据 schema
        data_schema = self._get_data_schema(session_id)
        print(f"[REPORT_PLANNER] 获取到数据 schema: {len(data_schema)} 个数据表")

        # 2. 尝试从缓存获取
        from backend.utils.cache import report_plan_cache
        cached_plan_data = report_plan_cache.get(user_request, data_schema)
        if cached_plan_data:
            print(f"[缓存命中] 报告规划")
            return self._rebuild_plan_from_cache(cached_plan_data)

        # 3. 缓存未命中，执行完整流程
        intent = await self._parse_intent(user_request, data_schema)
        print(f"[REPORT_PLANNER] 意图解析完成：{intent.get('theme', '未知主题')}")
        plan = await self._generate_plan(user_request, intent, data_schema)
        print(f"[REPORT_PLANNER] 报告规划生成完成，共 {len(plan.chapters)} 个章节")

        # 4. 存储规划到缓存
        report_plan_cache.set(user_request, data_schema, {
            'title': plan.title,
            'theme': plan.theme,
            'user_intent': plan.user_intent,
            'chapters': [
                {
                    'id': ch.id, 'title': ch.title, 'description': ch.description,
                    'dimensions': ch.dimensions, 'analysis_guidance': ch.analysis_guidance
                }
                for ch in plan.chapters
            ],
            'required_fields': plan.required_fields,
            'suggested_charts': [
                {
                    'chapter_id': c.chapter_id, 'chart_type': c.chart_type,
                    'data_query': c.data_query, 'title': c.title,
                    'element_key_field': c.element_key_field
                }
                for c in plan.suggested_charts
            ]
        })

        # 5. 存储规划到会话
        self.session_manager.store_report_plan(session_id, plan)
        return plan

    def _rebuild_plan_from_cache(self, cached_data: Dict) -> ReportPlan:
        """从缓存数据重建 ReportPlan 对象"""
        chapters = [
            ChapterPlan(
                id=ch['id'], title=ch['title'], description=ch['description'],
                dimensions=ch['dimensions'], analysis_guidance=ch['analysis_guidance']
            )
            for ch in cached_data['chapters']
        ]
        suggested_charts = [
            ChartSpec(
                chapter_id=c['chapter_id'], chart_type=c['chart_type'],
                data_query=c['data_query'], title=c['title'],
                element_key_field=c['element_key_field']
            )
            for c in cached_data['suggested_charts']
        ]
        return ReportPlan(
            title=cached_data['title'],
            theme=cached_data['theme'],
            user_intent=cached_data['user_intent'],
            chapters=chapters,
            required_fields=cached_data['required_fields'],
            suggested_charts=suggested_charts
        )

    def _get_data_schema(self, session_id: str) -> Dict:
        """获取数据结构信息"""
        print(f"[REPORT_PLANNER] _get_data_schema: 开始获取文件列表，session_id: {session_id}")
        files = self.session_manager.get_files(session_id)
        print(f"[REPORT_PLANNER] _get_data_schema: 获取到 {len(files)} 个文件")
        if not files:
            print(f"[REPORT_PLANNER] _get_data_schema: 错误 - 会话中没有数据文件")
            raise ValueError("会话中没有数据文件")

        schema = []
        for f in files:
            print(f"[REPORT_PLANNER] _get_data_schema: 尝试获取文件 ID: {f.id}, 文件名：{f.filename if hasattr(f, 'filename') else 'N/A'}")
            file_data = self.session_manager.get_file_data(session_id, f.id)
            print(f"[REPORT_PLANNER] _get_data_schema: 文件数据获取结果：{'成功' if file_data else '失败'}")
            if file_data:
                print(f"[REPORT_PLANNER] _get_data_schema: Sheet 数量：{len(file_data)}")
                df = list(file_data.values())[0]
                schema.append({
                    "file_name": f.filename if hasattr(f, "filename") else f.name,
                    "columns": df.columns.tolist(),
                    "dtypes": {col: str(df[col].dtype) for col in df.columns},
                    "sample_values": {
                        col: str(df[col].dropna().iloc[0]) if len(df) > 0 and df[col].notna().any() else "N/A"
                        for col in df.columns[:5]
                    }
                })
            else:
                print(f"[REPORT_PLANNER] _get_data_schema: 警告 - 文件 {f.id} 数据为空")

        if not schema:
            print(f"[REPORT_PLANNER] _get_data_schema: 错误 - 所有文件数据都为空")
            raise ValueError("无法获取任何文件数据")

        print(f"[REPORT_PLANNER] _get_data_schema: 成功获取 {len(schema)} 个数据表结构")
        return schema

    async def _parse_intent(self, user_request: str, data_schema: Dict) -> Dict:
        """
        解析用户意图

        提取：
        - 分析主题
        - 关注的关键指标
        - 期望的分析维度
        """
        print(f"[REPORT_PLANNER] _parse_intent: 开始解析用户意图")
        prompt = f"""分析用户需求，提取关键信息。返回 JSON：

用户请求：{user_request}
数据字段：{json.dumps(data_schema, ensure_ascii=False)}

{{
    "theme": "分析主题",
    "key_metrics": ["指标 1", "指标 2"],
    "focus_dimensions": ["维度 1", "维度 2"],
    "user_intent_summary": "一句话总结"
}}"""
        response = await self._call_llm(prompt)
        print(f"[REPORT_PLANNER] _parse_intent: LLM 响应长度：{len(response) if response else 0}")

        try:
            intent = json.loads(response)
            print(f"[REPORT_PLANNER] _parse_intent: JSON 解析成功")
            return intent
        except json.JSONDecodeError as e:
            # 如果解析失败，返回默认结构
            print(f"[REPORT_PLANNER] _parse_intent: JSON 解析失败：{e}")
            print(f"[REPORT_PLANNER] _parse_intent: 原始响应：{response[:500] if response else '空'}")
            return {
                "theme": "数据分析",
                "key_metrics": [],
                "focus_dimensions": [],
                "user_intent_summary": user_request
            }

    async def _generate_plan(
        self,
        user_request: str,
        intent: Dict,
        data_schema: Dict
    ) -> ReportPlan:
        """
        智能生成报告结构

        关键：不是组合固定模块，而是让 LLM 创造报告结构
        """
        print(f"[REPORT_PLANNER] _generate_plan: 开始生成报告结构")
        prompt = f"""你是智能报告生成助手。根据用户需求和数据特征，创造有针对性的分析报告。

【需求】{user_request}
【主题】{intent['theme']}
【指标】{', '.join(intent.get('key_metrics', []) or ['未明确'])}
【维度】{', '.join(intent.get('focus_dimensions', []) or ['未明确'])}
【数据】{json.dumps(data_schema, ensure_ascii=False)}

【要求】
1. 章节数 3-5 个，标题具体（如"呼叫数据总览"而非"数据概览"）
2. 每章指定使用的字段和分析思路
3. 最后一章为"结论与建议"

输出 JSON 格式：
{{
    "title": "报告标题",
    "theme": "{intent['theme']}",
    "user_intent": "{intent['user_intent_summary']}",
    "chapters": [
        {{"id": "chapter-1", "title": "章节标题", "description": "分析内容",
          "dimensions": ["字段 1", "字段 2"], "analysis_guidance": "分析思路"}}
    ],
    "suggested_charts": [
        {{"chapter_id": "chapter-1", "chart_type": "bar", "title": "图表标题",
          "data_query": {{"dimension": "字段名"}}, "element_key_field": "筛选字段"}}
    ]
}}"""
        response = await self._call_llm(prompt)
        print(f"[REPORT_PLANNER] _generate_plan: LLM 响应长度：{len(response) if response else 0}")

        try:
            plan_data = json.loads(response)
            print(f"[REPORT_PLANNER] _generate_plan: JSON 解析成功")
        except json.JSONDecodeError as e:
            # 如果解析失败，创建默认规划
            print(f"[REPORT_PLANNER] _generate_plan: JSON 解析失败：{e}")
            print(f"[REPORT_PLANNER] _generate_plan: 原始响应：{response[:500] if response else '空'}")
            plan_data = self._create_default_plan(user_request, intent, data_schema)

        # 转换为 Pydantic 模型
        chapters = [
            ChapterPlan(
                id=ch.get("id", f"chapter-{i}"),
                title=ch.get("title", f"第{i+1}章"),
                description=ch.get("description", ""),
                dimensions=ch.get("dimensions", []),
                analysis_guidance=ch.get("analysis_guidance", "")
            )
            for i, ch in enumerate(plan_data.get("chapters", []))
        ]

        suggested_charts = [
            ChartSpec(
                chapter_id=chart.get("chapter_id", ""),
                chart_type=chart.get("chart_type", "bar"),
                data_query=chart.get("data_query", {}),
                title=chart.get("title", ""),
                element_key_field=chart.get("element_key_field")
            )
            for chart in plan_data.get("suggested_charts", [])
        ]

        # 收集所有需要的字段
        required_fields = list(set(
            field
            for ch in chapters
            for field in ch.dimensions
        ))

        return ReportPlan(
            title=plan_data.get("title", "数据分析报告"),
            theme=plan_data.get("theme", intent["theme"]),
            user_intent=plan_data.get("user_intent", intent["user_intent_summary"]),
            chapters=chapters,
            required_fields=required_fields,
            suggested_charts=suggested_charts
        )

    def _create_default_plan(self, user_request: str, intent: Dict, data_schema: Dict) -> Dict:
        """创建默认规划（当 LLM 解析失败时使用）"""
        # 从 data_schema 中提取字段
        columns = []
        for schema in data_schema:
            columns.extend(schema.get("columns", []))

        # 创建简单的章节结构
        chapters = [
            {
                "id": "chapter-1",
                "title": "数据概览",
                "description": "数据基本情况介绍",
                "dimensions": columns[:5],
                "analysis_guidance": "统计行数、列数、数据类型"
            },
            {
                "id": "chapter-2",
                "title": f"{intent['theme']}分析",
                "description": "根据用户需求进行深入分析",
                "dimensions": columns[:10],
                "analysis_guidance": f"分析{intent['theme']}的关键特征"
            }
        ]

        return {
            "title": f"{intent['theme']}分析报告",
            "theme": intent["theme"],
            "user_intent": intent["user_intent_summary"],
            "chapters": chapters,
            "suggested_charts": []
        }

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        print(f"[REPORT_PLANNER] _call_llm: 开始调用 LLM, model={self.model}")
        try:
            from dashscope import MultiModalConversation

            messages = [{
                "role": "user",
                "content": [{"text": prompt}]
            }]

            response = MultiModalConversation.call(
                model=self.model,
                api_key=self.api_key,
                messages=messages,
                result_format='message'
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    result = content[0].get('text', '')
                elif isinstance(content, dict):
                    result = content.get('text', '')
                else:
                    result = str(content)
                print(f"[REPORT_PLANNER] _call_llm: LLM 调用成功，响应长度：{len(result)}")
                return result

            print(f"[REPORT_PLANNER] _call_llm: LLM 调用失败：{response.code} - {response.message}")
            raise ValueError(f"LLM 调用失败：{response.code} - {response.message}")

        except ImportError:
            print(f"[REPORT_PLANNER] _call_llm: dashscope 库未安装")
            raise ValueError("dashscope 库未安装，无法调用 LLM")
        except Exception as e:
            print(f"[REPORT_PLANNER] _call_llm: 异常：{type(e).__name__} - {str(e)}")
            raise ValueError(f"LLM 调用异常：{type(e).__name__} - {str(e)}")
