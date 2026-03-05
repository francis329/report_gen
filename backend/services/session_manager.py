"""
会话管理服务
负责创建、删除、查询会话，以及会话数据的隔离存储
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from backend.config import UPLOAD_DIR, REPORTS_DIR
from backend.models.schemas import Session, Message, FileInfo, SheetInfo, MessageRole, ClarificationState


class SessionManager:
    """会话管理器"""

    _instance: Optional['SessionManager'] = None
    _sessions: Dict[str, Session] = {}
    _data_store: Dict[str, dict] = {}  # 存储会话相关数据（文件数据、分析结果等）

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset(cls):
        """重置管理器（用于测试）"""
        cls._instance = None
        cls._sessions = {}
        cls._data_store = {}

    def create_session(self, name: str = "新会话") -> Session:
        """创建新会话"""
        session_id = str(uuid.uuid4())[:8]
        session = Session(
            id=session_id,
            name=name,
            created_at=datetime.now(),
            files=[],
            messages=[],
            report_id=None
        )
        self._sessions[session_id] = session
        self._data_store[session_id] = {
            "files_data": {},  # 存储文件数据 {file_id: {sheet_name: dataframe}}
            "analysis_results": {},  # 存储分析结果
            "charts": {},  # 存储图表数据
        }
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[Session]:
        """获取所有会话列表"""
        return list(self._sessions.values())

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有数据"""
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]

        # 删除报告文件
        if session.report_id:
            report_path = REPORTS_DIR / f"{session.report_id}.html"
            if report_path.exists():
                report_path.unlink()

        # 删除会话目录（上传的文件）
        session_dir = UPLOAD_DIR / session_id
        if session_dir.exists():
            try:
                import shutil
                shutil.rmtree(session_dir)
            except Exception as e:
                print(f"删除会话目录失败：{e}")

        # 清理内存中的会话数据
        del self._sessions[session_id]
        del self._data_store[session_id]
        return True

    def add_message(self, session_id: str, role: MessageRole, content: str) -> Message:
        """添加对话消息"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        message = Message(role=role, content=content)
        self._sessions[session_id].messages.append(message)
        return message

    def get_messages(self, session_id: str) -> List[Message]:
        """获取会话的所有消息"""
        if session_id not in self._sessions:
            return []
        return self._sessions[session_id].messages

    def add_file(self, session_id: str, file_info: FileInfo) -> None:
        """添加文件到会话"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        self._sessions[session_id].files.append(file_info)

    def get_files(self, session_id: str) -> List[FileInfo]:
        """获取会话的所有文件"""
        if session_id not in self._sessions:
            return []
        return self._sessions[session_id].files

    def store_file_data(self, session_id: str, file_id: str, data: dict) -> None:
        """存储文件数据（按 sheet 页分开）"""
        if session_id not in self._data_store:
            raise ValueError(f"Session {session_id} not found")
        self._data_store[session_id]["files_data"][file_id] = data

    def get_file_data(self, session_id: str, file_id: str) -> Optional[dict]:
        """获取文件数据"""
        if session_id not in self._data_store:
            return None
        return self._data_store[session_id]["files_data"].get(file_id)

    def store_analysis_result(self, session_id: str, result: dict) -> None:
        """存储分析结果"""
        if session_id not in self._data_store:
            raise ValueError(f"Session {session_id} not found")
        self._data_store[session_id]["analysis_results"] = result

    def get_analysis_result(self, session_id: str) -> Optional[dict]:
        """获取分析结果"""
        if session_id not in self._data_store:
            return None
        return self._data_store[session_id].get("analysis_results", {})

    def store_charts(self, session_id: str, charts: list) -> None:
        """存储图表数据"""
        if session_id not in self._data_store:
            raise ValueError(f"Session {session_id} not found")
        self._data_store[session_id]["charts"] = charts

    def get_charts(self, session_id: str) -> list:
        """获取图表数据"""
        if session_id not in self._data_store:
            return []
        return self._data_store[session_id].get("charts", [])

    def set_report_id(self, session_id: str, report_id: str) -> None:
        """设置会话的报告 ID"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id].report_id = report_id

    def get_session_dir(self, session_id: str) -> Path:
        """获取会话的上传目录"""
        session_dir = UPLOAD_DIR / session_id
        session_dir.mkdir(exist_ok=True)
        return session_dir

    def get_conversation_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """获取对话历史（带限制）"""
        if session_id not in self._sessions:
            return []
        messages = self._sessions[session_id].messages
        # 限制返回最近的消息
        limited_messages = messages[-limit:] if len(messages) > limit else messages
        return [{"role": msg.role.value, "content": msg.content} for msg in limited_messages]

    def get_clarification_state(self, session_id: str) -> Optional[ClarificationState]:
        """获取澄清状态"""
        if session_id not in self._sessions:
            return None
        return self._sessions[session_id].clarification_state

    def set_clarification_state(self, session_id: str, state: ClarificationState) -> None:
        """设置澄清状态"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id].clarification_state = state

    def clear_clarification_state(self, session_id: str) -> None:
        """清除澄清状态"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id].clarification_state = None
