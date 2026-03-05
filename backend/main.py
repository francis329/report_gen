"""
FastAPI 应用入口
提供报告生成系统的所有 API 接口
"""
import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.config import UPLOAD_DIR, REPORTS_DIR, DASHSCOPE_MODEL
from backend.models.schemas import (
    CreateSessionRequest, CreateSessionResponse,
    SessionListResponse, UploadFileResponse,
    ChatRequest, ChatResponse, ReportResponse
)
from backend.services.session_manager import SessionManager
from backend.utils.file_handler import FileHandler
from backend.services.report_generator import ReportGenerator
from backend.utils.chart_builder import ChartBuilder

# 导入新的 Tool-Calling Agent 相关模块
import dashscope
from backend.agents.registry import ToolRegistry
from backend.agents.tool_calling import ToolCallingAgent
from backend.tools.data_tools import AnalyzeDataTool, GetColumnDistributionTool, GetColumnStatisticsTool
from backend.tools.chart_tools import GenerateChartTool, GenerateCorrelationHeatmapTool, AutoGenerateChartsTool
from backend.tools.report_tools import GenerateReportTool

# 创建 FastAPI 应用
app = FastAPI(
    title="报告生成 Agent 应用",
    description="智能数据分析与报告生成系统",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
session_manager = SessionManager()

# 初始化新的 Tool-Calling Agent
tool_registry = ToolRegistry()
ai_agent = ToolCallingAgent(tool_registry)

# 注册所有工具
tool_registry.register(AnalyzeDataTool(session_manager))
tool_registry.register(GetColumnDistributionTool(session_manager))
tool_registry.register(GetColumnStatisticsTool(session_manager))
tool_registry.register(GenerateChartTool(session_manager))
tool_registry.register(GenerateCorrelationHeatmapTool(session_manager))
tool_registry.register(AutoGenerateChartsTool(session_manager))
tool_registry.register(GenerateReportTool(session_manager))

# 启动时日志
print("=" * 50)
print("报告生成 Agent 应用启动")
print(f"API 密钥已配置：{bool(os.getenv('DASHSCOPE_API_KEY', ''))}")
print(f"AI 模型：{DASHSCOPE_MODEL}")
print("=" * 50)


# ==================== 会话管理 ====================

@app.post("/api/sessions", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    session = session_manager.create_session(request.name)
    return CreateSessionResponse(session=session)


@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions():
    """获取会话列表"""
    sessions = session_manager.list_sessions()
    return SessionListResponse(sessions=sessions)


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"message": "会话已删除"}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"session": session}


# ==================== 文件上传 ====================

@app.post("/api/sessions/{session_id}/upload", response_model=UploadFileResponse)
async def upload_file(session_id: str, file: UploadFile = File(...)):
    """上传数据文件 - 仅保存文件，不自动分析和生成图表"""
    # 检查会话是否存在
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        # 读取文件内容
        file_content = await file.read()

        # 处理文件
        file_info = FileHandler.process_uploaded_file(
            session_manager=session_manager,
            session_id=session_id,
            filename=file.filename,
            file_content=file_content
        )

        # 不再自动分析和生成图表
        # 由 Agent 根据用户需求智能决定何时调用工具

        return UploadFileResponse(
            file_info=file_info,
            message=f"文件已上传：{file.filename}，共 {len(file_info.sheets)} 个数据表"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败：{str(e)}")


# ==================== 聊天交互 ====================

@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest):
    """发送消息进行对话 - 使用新的 Tool-Calling Agent"""
    # 检查会话是否存在
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 检查是否配置了 API 密钥
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if api_key:
        ai_agent.api_key = api_key
        dashscope.api_key = api_key

    try:
        # 获取所有 sheet 信息
        sheets_info = FileHandler.get_all_sheets_info(session_manager, session_id)

        # 构建上下文
        context = {
            "session_id": session_id,
            "sheets_info": sheets_info,
            "history": session_manager.get_conversation_history(session_id, limit=10)
        }

        # 运行 Agent（自主决定调用工具）
        response_text, tool_results = await ai_agent.run(request.message, context)

        # 添加用户消息
        session_manager.add_message(session_id, "user", request.message)
        session_manager.add_message(session_id, "assistant", response_text)

        # 检查是否有工具执行结果需要处理
        is_clarifying = False
        clarification_question = None
        report_url = None

        for result in tool_results:
            if result.data and isinstance(result.data, dict):
                if result.data.get('report_id'):
                    report_url = f"/api/reports/{result.data['report_id']}"

        return ChatResponse(
            response=response_text,
            report_url=report_url,
            is_clarifying=is_clarifying,
            clarification_question=clarification_question
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 服务异常：{str(e)}")


# ==================== 报告相关 ====================

@app.get("/api/sessions/{session_id}/report", response_model=ReportResponse)
async def get_report(session_id: str, ai_summary: Optional[str] = ""):
    """获取会话报告"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    analysis_results = session_manager.get_analysis_result(session_id)
    if not analysis_results:
        raise HTTPException(status_code=400, detail="暂无分析结果，请先上传文件并进行分析")

    try:
        # 生成报告
        report_id = ReportGenerator.generate_report(
            session_manager=session_manager,
            session_id=session_id,
            ai_summary=ai_summary or ""
        )

        return ReportResponse(
            report_id=report_id,
            html_content=ReportGenerator.read_report(report_id) or "",
            download_url=f"/api/reports/{report_id}/download"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成报告失败：{str(e)}")


@app.get("/api/reports/{report_id}", response_class=HTMLResponse)
async def view_report(report_id: str):
    """查看报告"""
    content = ReportGenerator.read_report(report_id)
    if not content:
        raise HTTPException(status_code=404, detail="报告不存在")
    return HTMLResponse(content=content)


@app.get("/api/reports/{report_id}/download")
async def download_report(report_id: str):
    """下载报告"""
    report_path = ReportGenerator.get_report_path(report_id)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="报告不存在")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=report_path,
        filename=f"report_{report_id}.html",
        media_type="text/html"
    )


# ==================== 配置相关 ====================

@app.post("/api/config/ai-key")
async def set_ai_key(api_key: str):
    """设置 AI API 密钥"""
    import dashscope
    ai_agent.api_key = api_key
    os.environ["DASHSCOPE_API_KEY"] = api_key
    dashscope.api_key = api_key
    return {"message": "API 密钥已设置"}


@app.get("/api/tools")
async def list_tools():
    """获取可用工具列表"""
    tools = []
    for tool in tool_registry.get_all():
        tools.append({
            "name": tool.definition.name,
            "description": tool.definition.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "enum": p.enum,
                    "default": p.default
                }
                for p in tool.definition.parameters
            ]
        })
    return {"tools": tools}


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "api_key_configured": bool(os.getenv("DASHSCOPE_API_KEY", ""))
    }


# 启动应用
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
