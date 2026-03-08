"""
FastAPI 应用入口
提供报告生成系统的所有 API 接口
"""
import os
import json
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.background import BackgroundTasks
import uvicorn

from backend.config import UPLOAD_DIR, REPORTS_DIR, DASHSCOPE_MODEL, DASHSCOPE_API_KEY
from backend.models.schemas import (
    CreateSessionRequest, CreateSessionResponse,
    SessionListResponse, UploadFileResponse,
    ChatRequest, ChatResponse, ReportResponse
)
from backend.services.session_manager import SessionManager
from backend.utils.file_handler import FileHandler
from backend.utils.chart_builder import ChartBuilder

# 导入新的 Tool-Calling Agent 相关模块
import dashscope
from backend.agents.registry import ToolRegistry
from backend.agents.tool_calling import ToolCallingAgent
from backend.agents.report_agent import ReportAgent
from backend.tools.data_tools import AnalyzeDataTool, GetColumnDistributionTool, GetColumnStatisticsTool
from backend.tools.chart_tools import GenerateChartTool, GenerateCorrelationHeatmapTool, AutoGenerateChartsTool
from backend.tools.report_tools import GenerateDynamicReportTool, GetReportTool
from backend.websocket_manager import ws_manager
from backend.utils.performance_logger import get_perf_logger, track_performance

# 创建 FastAPI 应用
app = FastAPI(
    title="报告生成 Agent 应用",
    description="智能数据分析与报告生成系统",
    version="2.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求模型
class GenerateReportRequest(BaseModel):
    user_request: str  # 用户分析请求

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
tool_registry.register(GenerateDynamicReportTool(session_manager, DASHSCOPE_API_KEY))
tool_registry.register(GetReportTool(session_manager))

# 启动时日志
print("=" * 50)
print("报告生成 Agent 应用 v2.0")
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
    import time
    perf = get_perf_logger()
    perf.reset()

    # 开始性能追踪
    perf.start("chat_total")
    perf.start("chat_setup")

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
        sheets_info_start = time.time()
        sheets_info = FileHandler.get_all_sheets_info(session_manager, session_id)
        sheets_info_time = time.time() - sheets_info_start
        perf.log("chat_get_sheets_info", sheets_info_time)

        perf.end("chat_setup")

        # 构建上下文
        context = {
            "session_id": session_id,
            "sheets_info": sheets_info,
            "history": session_manager.get_conversation_history(session_id, limit=10)
        }

        # 运行 Agent（自主决定调用工具）
        perf.start("chat_agent_run")
        response_text, tool_results = await ai_agent.run(request.message, context, perf)
        perf.end("chat_agent_run")

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

        perf.end("chat_total")
        perf.log("chat_response_length", len(response_text))

        # 输出性能摘要
        print(f"\n[PERF] 聊天请求性能摘要:")
        print(perf.summary())
        print()

        return ChatResponse(
            response=response_text,
            report_url=report_url,
            is_clarifying=is_clarifying,
            clarification_question=clarification_question
        )

    except Exception as e:
        perf.end("chat_total")
        print(f"[PERF] 聊天请求失败，总耗时：{perf.get_total():.3f}s")
        raise HTTPException(status_code=500, detail=f"AI 服务异常：{str(e)}")


# ==================== WebSocket 进度通知 ====================

@app.websocket("/ws/progress/{session_id}")
async def websocket_progress_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 进度通知端点"""
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            await websocket.receive_text()  # 保持连接
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)


# ==================== 流式聊天 ====================

@app.websocket("/api/sessions/{session_id}/chat/stream")
async def chat_stream(session_id: str, websocket: WebSocket, message: str = Query(..., help="用户消息内容")):
    """流式聊天接口 - 通过 WebSocket 实时推送 AI 回复

    message: 用户消息，通过 WebSocket URL 查询参数传递，如：
             ws://host/api/sessions/xxx/chat/stream?message=你好
    """
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.accept()
        await websocket.send_json({"type": "error", "data": {"message": "会话不存在"}})
        await websocket.close()
        return

    # 验证消息内容
    if not message or not message.strip():
        await websocket.accept()
        await websocket.send_json({"type": "error", "data": {"message": "消息内容为空"}})
        await websocket.close()
        return

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if api_key:
        ai_agent.api_key = api_key
        dashscope.api_key = api_key

    await ws_manager.connect(websocket, session_id)

    try:
        user_message = message.strip()

        await ws_manager.send_message(session_id, "chat_start", {})

        sheets_info = FileHandler.get_all_sheets_info(session_manager, session_id)
        context = {
            "session_id": session_id,
            "sheets_info": sheets_info,
            "history": session_manager.get_conversation_history(session_id, limit=10)
        }

        async def on_text_chunk(chunk: str):
            await ws_manager.send_message(session_id, "chat_chunk", {"text": chunk})

        # 增加超时时间：报告生成可能需要较长时间（默认 60 秒可能不够）
        import asyncio
        try:
            # 使用 wait_for 包装，设置 300 秒超时（5 分钟）
            response_text, tool_results = await asyncio.wait_for(
                ai_agent.run_streaming(user_message, context, on_text_chunk),
                timeout=300
            )
        except asyncio.TimeoutError:
            print(f"[WARNING] 请求超时（超过 300 秒）")
            await ws_manager.send_message(session_id, "error", {"message": "请求处理时间过长，请稍后重试"})
            return

        session_manager.add_message(session_id, "user", user_message)
        session_manager.add_message(session_id, "assistant", response_text)

        report_url = None
        for result in tool_results:
            if result.data and isinstance(result.data, dict):
                if result.data.get('report_id'):
                    report_url = f"/api/reports/{result.data['report_id']}"

        await ws_manager.send_message(session_id, "chat_complete", {
            "response": response_text,
            "report_url": report_url
        })

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[ERROR] 流式聊天失败：{error_detail}")
        await ws_manager.send_message(session_id, "error", {"message": f"AI 服务异常：{str(e)}"})
    finally:
        ws_manager.disconnect(websocket, session_id)


# ==================== 智能报告生成 ====================

@app.post("/api/sessions/{session_id}/generate-report")
async def trigger_report_generation(
    session_id: str,
    request: GenerateReportRequest,
    background_tasks: BackgroundTasks
):
    """
    触发智能报告生成

    报告生成是异步的，通过 WebSocket 推送进度
    """
    # 检查会话是否存在
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 创建 ReportAgent
    report_agent = ReportAgent(session_manager, DASHSCOPE_API_KEY)

    # 进度回调函数
    async def progress_callback(progress: dict):
        await ws_manager.broadcast_progress(session_id, progress)

    # 后台执行报告生成
    async def generate():
        try:
            report_id = await report_agent.generate_report(
                session_id=session_id,
                user_request=request.user_request,
                progress_callback=progress_callback
            )
            # 报告生成完成
            await ws_manager.broadcast_progress(session_id, {
                'stage': 'complete',
                'report_id': report_id
            })
        except Exception as e:
            await ws_manager.broadcast_progress(session_id, {
                'stage': 'error',
                'error': str(e)
            })

    background_tasks.add_task(generate)

    return {
        "status": "started",
        "message": "报告生成已启动，请通过 WebSocket 接收进度通知"
    }


# ==================== 图表数据 ====================

@app.get("/api/charts/{chart_id}/raw-data")
async def get_chart_raw_data(
    chart_id: str,
    session_id: str,
    element_key: Optional[str] = None
):
    """
    获取图表原始数据

    :param chart_id: 图表 ID
    :param session_id: 会话 ID
    :param element_key: 可选，指定图表元素（如饼图的某一块）
    """
    if element_key:
        # 获取特定元素的数据
        data = session_manager.filter_data_by_chart_element(
            session_id=session_id,
            chart_id=chart_id,
            element_key=element_key
        )
    else:
        # 获取全部数据
        query = session_manager.get_chart_data_query(session_id, chart_id)
        data = query.data if query else {}

    return {"data": data}


# ==================== 报告相关 ====================

@app.get("/api/sessions/{session_id}/report", response_model=ReportResponse)
async def get_report(session_id: str):
    """获取会话报告"""
    report_id = session_manager.get_report_id(session_id)
    if not report_id:
        raise HTTPException(status_code=400, detail="暂无报告，请先生成报告")

    from backend.agents.report_agent import ReportAgent

    content = ReportAgent.read_report(report_id)
    if not content:
        raise HTTPException(status_code=404, detail="报告不存在")

    return ReportResponse(
        report_id=report_id,
        html_content=content,
        download_url=f"/api/reports/{report_id}/download"
    )


@app.get("/api/reports/{report_id}", response_class=HTMLResponse)
async def view_report(report_id: str):
    """查看报告"""
    from backend.agents.report_agent import ReportAgent

    content = ReportAgent.read_report(report_id)
    if not content:
        raise HTTPException(status_code=404, detail="报告不存在")
    return HTMLResponse(content=content)


@app.get("/api/reports/{report_id}/download")
async def download_report(report_id: str):
    """下载报告"""
    report_path = REPORTS_DIR / f"{report_id}.html"
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
        "version": "2.0.0",
        "api_key_configured": bool(os.getenv("DASHSCOPE_API_KEY", ""))
    }


# 启动应用
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
