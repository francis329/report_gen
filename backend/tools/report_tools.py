"""
报告生成工具
提供报告生成相关的工具实现
"""
from typing import Optional
from backend.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from backend.services.session_manager import SessionManager


class GenerateDynamicReportTool(BaseTool):
    """
    生成动态报告工具

    调用 ReportAgent 完成智能报告生成
    """

    def __init__(
        self,
        session_manager: SessionManager,
        api_key: Optional[str] = None
    ):
        self.session_manager = session_manager
        self.api_key = api_key

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_dynamic_report",
            description="根据用户需求和数据特征，智能生成动态分析报告。"
                       "报告结构由 AI 根据分析主题自动创造，不是固定模板。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID",
                    required=True
                ),
                ToolParameter(
                    name="user_request",
                    type="string",
                    description="用户的分析请求文本，例如：'分析主被叫失败原因'、'分析用户流失情况'",
                    required=True
                )
            ]
        )

    async def execute(self, **kwargs) -> ToolResult:
        from backend.agents.report_agent import ReportAgent
        from backend.websocket_manager import ws_manager

        session_id = kwargs.get("session_id")
        # 参数名映射：LLM 可能使用 topic/request 等同义词，统一映射为 user_request
        user_request = kwargs.get("user_request") or kwargs.get("topic") or kwargs.get("request")

        print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 开始执行，session_id: {session_id}, user_request: {user_request}")

        if not session_id:
            print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 错误：缺少 session_id 参数")
            return ToolResult(
                success=False,
                error="缺少 session_id 参数。正确参数：session_id (string), user_request (string)"
            )
        if not user_request:
            print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 错误：缺少 user_request 参数")
            return ToolResult(
                success=False,
                error="缺少 user_request 参数。正确参数：session_id (string), user_request (string)"
            )

        session = self.session_manager.get_session(session_id)
        print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 会话检查：{'存在' if session else '不存在'}")
        if not session:
            return ToolResult(success=False, error="会话不存在")

        try:
            print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 创建 ReportAgent")
            # 创建 ReportAgent
            agent = ReportAgent(self.session_manager, self.api_key)

            # 创建进度回调函数
            async def progress_callback(progress: dict):
                try:
                    await ws_manager.broadcast_progress(session_id, progress)
                except Exception as e:
                    # WebSocket 可能未连接，忽略错误
                    print(f"发送进度通知失败：{e}")

            # 生成报告（带进度回调）
            print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 调用 agent.generate_report()")
            report_id = await agent.generate_report(
                session_id=session_id,
                user_request=user_request,
                progress_callback=progress_callback
            )
            print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 报告生成成功，report_id: {report_id}")

            return ToolResult(
                success=True,
                data={
                    "report_id": report_id,
                    "view_url": f"/api/reports/{report_id}",
                    "download_url": f"/api/reports/{report_id}/download"
                },
                message=f"报告已生成，ID: {report_id}"
            )

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 报告生成失败：{e}")
            print(f"[GENERATE_DYNAMIC_REPORT_TOOL] 错误详情：{error_detail}")
            return ToolResult(
                success=False,
                error=f"报告生成失败：{str(e)}"
            )


class GetReportTool(BaseTool):
    """获取报告工具"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_report",
            description="获取已生成的报告 ID 和访问链接",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID"
                )
            ]
        )

    async def execute(self, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id")

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")

        report_id = self.session_manager.get_report_id(session_id)
        if not report_id:
            return ToolResult(success=False, error="未找到报告，请先生成报告")

        return ToolResult(
            success=True,
            data={
                "report_id": report_id,
                "view_url": f"/api/reports/{report_id}",
                "download_url": f"/api/reports/{report_id}/download"
            },
            message="报告已找到"
        )
