"""
WebSocket 管理器
用于实时推送报告生成进度
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Any
import asyncio


class WebSocketManager:
    """
    WebSocket 连接管理器

    管理所有活跃的 WebSocket 连接，支持按 session_id 分组广播消息
    """

    def __init__(self):
        # {session_id: [WebSocket, ...]}
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # 用于线程安全的锁
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        接受并注册 WebSocket 连接

        :param websocket: WebSocket 连接
        :param session_id: 会话 ID（用于分组）
        """
        await websocket.accept()
        async with self._lock:
            if session_id not in self.active_connections:
                self.active_connections[session_id] = []
            self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """
        断开并移除 WebSocket 连接

        :param websocket: WebSocket 连接
        :param session_id: 会话 ID
        """
        if session_id in self.active_connections:
            try:
                self.active_connections[session_id].remove(websocket)
            except ValueError:
                pass  # 连接已不在列表中

            # 如果该 session 没有连接了，清理 entry
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast_progress(self, session_id: str, progress: Dict[str, Any]) -> None:
        """
        广播进度更新给指定 session 的所有连接

        :param session_id: 会话 ID
        :param progress: 进度信息
            {
                "stage": "planning" | "executing" | "generating" | "complete" | "error",
                "message": "人类可读的进度描述",
                "progress": 0-100 的整数，
                "chapter": "当前章节名称（可选）",
                "report_id": "生成的报告 ID（完成时）"
            }
        """
        message = {
            "type": "progress",
            "data": progress
        }

        async with self._lock:
            connections = self.active_connections.get(session_id, []).copy()

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                # 连接已断开，忽略
                pass

    async def send_message(self, session_id: str, message_type: str, data: Dict[str, Any]) -> None:
        """
        发送自定义消息

        :param session_id: 会话 ID
        :param message_type: 消息类型
        :param data: 消息数据
        """
        message = {
            "type": message_type,
            "data": data
        }

        async with self._lock:
            connections = self.active_connections.get(session_id, []).copy()

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

    def get_connection_count(self, session_id: str) -> int:
        """获取指定 session 的连接数"""
        return len(self.active_connections.get(session_id, []))

    def get_all_session_ids(self) -> List[str]:
        """获取所有有活跃连接的 session ID"""
        return list(self.active_connections.keys())


# 全局单例
ws_manager = WebSocketManager()
