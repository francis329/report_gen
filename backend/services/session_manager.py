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
from backend.models.report import ReportPlan, ChapterResult, ChartDataQuery


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
        # 检查会话是否存在
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        # 如果 _data_store[session_id] 不存在，初始化它
        if session_id not in self._data_store:
            print(f"[DEBUG] store_file_data - _data_store[{session_id}] 不存在，正在初始化")
            self._data_store[session_id] = {
                "files_data": {},
                "analysis_results": {},
                "charts": {},
            }

        self._data_store[session_id]["files_data"][file_id] = data
        print(f"[DEBUG] store_file_data - 已存储文件数据，file_id: {file_id}, sheet 数量：{len(data)}")

    def get_file_data(self, session_id: str, file_id: str) -> Optional[dict]:
        """获取文件数据"""
        # 检查会话是否存在
        if session_id not in self._sessions:
            print(f"[DEBUG] get_file_data - session_id '{session_id}' 不存在于 sessions")
            return None

        # 检查 _data_store[session_id] 是否存在，不存在则返回 None（不自动初始化）
        if session_id not in self._data_store:
            print(f"[DEBUG] get_file_data - _data_store[{session_id}] 不存在，文件数据可能已丢失或会话已重置")
            return None

        files_data = self._data_store[session_id].get("files_data", {})
        print(f"[DEBUG] get_file_data - files_data keys: {list(files_data.keys())}, 请求的 file_id: {file_id}")

        result = files_data.get(file_id)
        if result:
            print(f"[DEBUG] get_file_data - 成功获取数据，sheet 数量：{len(result)}")
        else:
            print(f"[DEBUG] get_file_data - 未找到 file_id '{file_id}' 的数据，可用 file_id: {list(files_data.keys())}")
        return result

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

    # ========== 报告生成相关方法（新增） ==========

    def store_report_plan(self, session_id: str, plan: ReportPlan) -> None:
        """存储报告规划"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        if session_id not in self._data_store:
            self._data_store[session_id] = {}
        self._data_store[session_id]["report_plan"] = plan

    def get_report_plan(self, session_id: str) -> Optional[ReportPlan]:
        """获取报告规划"""
        if session_id not in self._data_store:
            return None
        return self._data_store[session_id].get("report_plan")

    def store_chapter_result(self, session_id: str, chapter_id: str, result: ChapterResult) -> None:
        """存储章节分析结果"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        if session_id not in self._data_store:
            self._data_store[session_id] = {}
        if "chapter_results" not in self._data_store[session_id]:
            self._data_store[session_id]["chapter_results"] = {}
        self._data_store[session_id]["chapter_results"][chapter_id] = result

    def get_chapter_result(self, session_id: str, chapter_id: str) -> Optional[ChapterResult]:
        """获取章节分析结果"""
        if session_id not in self._data_store:
            return None
        chapter_results = self._data_store[session_id].get("chapter_results", {})
        return chapter_results.get(chapter_id)

    def get_all_chapter_results(self, session_id: str) -> Dict[str, ChapterResult]:
        """获取所有章节结果"""
        if session_id not in self._data_store:
            return {}
        return self._data_store[session_id].get("chapter_results", {})

    def store_chart_data_query(self, session_id: str, chart_id: str, query: ChartDataQuery) -> None:
        """存储图表数据查询条件（用于点击查看原始数据）"""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        if session_id not in self._data_store:
            self._data_store[session_id] = {}
        if "chart_queries" not in self._data_store[session_id]:
            self._data_store[session_id]["chart_queries"] = {}
        self._data_store[session_id]["chart_queries"][chart_id] = query

    def get_chart_data_query(self, session_id: str, chart_id: str) -> Optional[ChartDataQuery]:
        """获取图表数据查询条件"""
        if session_id not in self._data_store:
            return None
        chart_queries = self._data_store[session_id].get("chart_queries", {})
        return chart_queries.get(chart_id)

    def filter_data_by_chart_element(
        self,
        session_id: str,
        chart_id: str,
        element_key: str
    ) -> List[Dict]:
        """
        根据图表元素筛选原始数据

        :param session_id: 会话 ID
        :param chart_id: 图表 ID
        :param element_key: 元素标识（如饼图的某一块名称、柱状图的某一柱）
        :return: 筛选后的数据列表
        """
        query = self.get_chart_data_query(session_id, chart_id)
        if not query:
            # 没有查询条件，返回空列表
            return []

        # 获取文件数据
        files = self.get_files(session_id)
        if not files:
            return []

        file_data = self.get_file_data(session_id, files[0].id)
        if not file_data:
            return []

        # 获取第一个 sheet 的 DataFrame
        df = list(file_data.values())[0]

        # 根据查询类型和元素筛选数据
        element_field = query.element_key_field or (query.dimensions[0] if query.dimensions else None)

        if element_field and element_field in df.columns:
            filtered_df = df[df[element_field] == element_key]
            return filtered_df.to_dict('records')

        # 如果没有筛选条件，返回全部数据
        return df.to_dict('records')

    def get_report_id(self, session_id: str) -> Optional[str]:
        """获取会话的报告 ID"""
        if session_id not in self._sessions:
            return None
        return self._sessions[session_id].report_id
