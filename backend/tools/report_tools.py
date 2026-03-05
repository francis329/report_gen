"""
报告生成工具
提供报告生成相关的工具实现
"""
from backend.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from backend.services.session_manager import SessionManager


class GenerateReportTool(BaseTool):
    """生成报告工具 - 生成完整的 HTML 数据分析报告"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_report",
            description="生成完整的 HTML 格式数据分析报告，包含数据概览、质量分析、详细统计和可视化图表。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID"
                ),
                ToolParameter(
                    name="include_charts",
                    type="boolean",
                    description="是否包含图表",
                    required=False,
                    default=True
                ),
                ToolParameter(
                    name="ai_summary",
                    type="string",
                    description="AI 分析摘要，将添加到报告中",
                    required=False
                )
            ]
        )

    async def execute(self, **kwargs) -> ToolResult:
        from backend.services.report_generator import ReportGenerator

        session_id = kwargs.get("session_id")
        include_charts = kwargs.get("include_charts", True)
        ai_summary = kwargs.get("ai_summary", "")

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")

        session = self.session_manager.get_session(session_id)
        if not session:
            return ToolResult(success=False, error="会话不存在")

        analysis_results = self.session_manager.get_analysis_result(session_id)
        if not analysis_results:
            return ToolResult(
                success=False,
                error="暂无分析结果，请先调用 analyze_data 工具分析数据"
            )

        # 获取图表（如果需要）
        charts = self.session_manager.get_charts(session_id) if include_charts else []

        try:
            # 生成 HTML 报告
            report_id = ReportGenerator.generate_html_report(
                session_id=session_id,
                session_name=session.name,
                analysis_results=analysis_results,
                charts=charts,
                ai_summary=ai_summary
            )

            # 更新会话的报告 ID
            self.session_manager.set_report_id(session_id, report_id)

            return ToolResult(
                success=True,
                data={
                    "report_id": report_id,
                    "view_url": f"/api/reports/{report_id}",
                    "download_url": f"/api/reports/{report_id}/download"
                },
                message="报告已生成"  # 友好消息，不包含路径
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"生成报告失败：{str(e)}"
            )


class UpdateReportTool(BaseTool):
    """更新报告工具 - 在现有报告基础上更新 AI 分析摘要"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="update_report",
            description="更新现有报告的 AI 分析摘要部分。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID"
                ),
                ToolParameter(
                    name="ai_summary",
                    type="string",
                    description="新的 AI 分析摘要"
                )
            ]
        )

    async def execute(self, **kwargs) -> ToolResult:
        from backend.services.report_generator import ReportGenerator

        session_id = kwargs.get("session_id")
        ai_summary = kwargs.get("ai_summary")

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")
        if not ai_summary:
            return ToolResult(success=False, error="缺少 ai_summary 参数")

        session = self.session_manager.get_session(session_id)
        if not session:
            return ToolResult(success=False, error="会话不存在")

        if not session.report_id:
            return ToolResult(
                success=False,
                error="暂无报告，请先生成报告"
            )

        analysis_results = self.session_manager.get_analysis_result(session_id)
        if not analysis_results:
            return ToolResult(success=False, error="暂无分析结果")

        charts = self.session_manager.get_charts(session_id)

        try:
            # 重新生成报告
            report_id = ReportGenerator.generate_html_report(
                session_id=session_id,
                session_name=session.name,
                analysis_results=analysis_results,
                charts=charts,
                ai_summary=ai_summary
            )

            self.session_manager.set_report_id(session_id, report_id)

            return ToolResult(
                success=True,
                data={
                    "report_id": report_id,
                    "view_url": f"/api/reports/{report_id}"
                },
                message="报告已更新"  # 友好消息，不包含路径
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"更新报告失败：{str(e)}"
            )
