"""
会话管理服务
负责创建、删除、查询会话，以及会话数据的隔离存储
"""
import uuid
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from backend.config import UPLOAD_DIR, REPORTS_DIR
from backend.models.schemas import Session, Message, FileInfo, SheetInfo, MessageRole, ClarificationState, AnalysisContext
from backend.models.report import ReportPlan, ChapterResult, ChartDataQuery

# 配置日志
logger = logging.getLogger('session_manager')


class SessionManager:
    """会话管理器"""

    _instance: Optional['SessionManager'] = None
    _sessions: Dict[str, Session] = {}
    _data_store: Dict[str, dict] = {}  # 存储会话相关数据（文件数据、分析结果等）
    _analysis_results_store: Dict[str, Dict] = {}  # 共享分析结果存储（session_id -> analysis_results）

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
        cls._analysis_results_store = {}

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
        # 初始化共享分析结果存储
        self._analysis_results_store[session_id] = {
            "basic_stats": {},
            "column_stats": {},
            "chart_data": [],
            "key_findings": [],
            "last_updated": datetime.now()
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
        # 清理共享分析结果存储
        if session_id in self._analysis_results_store:
            del self._analysis_results_store[session_id]
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
        start_time = time.time()

        # 检查会话是否存在
        if session_id not in self._sessions:
            logger.error(f"[SESSION_MANAGER] store_file_data 失败：session_id '{session_id}' 不存在")
            raise ValueError(f"Session {session_id} not found")

        # 如果 _data_store[session_id] 不存在，初始化它
        if session_id not in self._data_store:
            self._data_store[session_id] = {
                "files_data": {},
                "analysis_results": {},
                "charts": {},
            }

        self._data_store[session_id]["files_data"][file_id] = data

        elapsed = time.time() - start_time
        logger.info(f"[SESSION_MANAGER] store_file_data 完成", extra={
            "session_id": session_id,
            "file_id": file_id,
            "sheet_count": len(data),
            "execution_time": elapsed,
            "action": "store_file_data"
        })

    def get_file_data(self, session_id: str, file_id: str) -> Optional[dict]:
        """获取文件数据"""
        start_time = time.time()

        # 检查会话是否存在
        if session_id not in self._sessions:
            logger.warning(f"[SESSION_MANAGER] get_file_data: session_id '{session_id}' 不存在")
            return None

        # 检查 _data_store[session_id] 是否存在
        if session_id not in self._data_store:
            logger.warning(f"[SESSION_MANAGER] get_file_data: _data_store[{session_id}] 不存在")
            return None

        files_data = self._data_store[session_id].get("files_data", {})
        result = files_data.get(file_id)

        elapsed = time.time() - start_time
        logger.info(f"[SESSION_MANAGER] get_file_data {'成功' if result else '未找到'}", extra={
            "session_id": session_id,
            "file_id": file_id,
            "found": result is not None,
            "execution_time": elapsed,
            "action": "get_file_data"
        })

        return result

    def store_analysis_result(self, session_id: str, result: dict) -> None:
        """存储分析结果"""
        start_time = time.time()

        if session_id not in self._data_store:
            logger.error(f"[SESSION_MANAGER] store_analysis_result 失败：session_id '{session_id}' 不存在")
            raise ValueError(f"Session {session_id} not found")

        self._data_store[session_id]["analysis_results"] = result

        elapsed = time.time() - start_time
        logger.info(f"[SESSION_MANAGER] store_analysis_result 完成", extra={
            "session_id": session_id,
            "execution_time": elapsed,
            "action": "store_analysis_result"
        })

    def get_analysis_result(self, session_id: str) -> Optional[dict]:
        """获取分析结果"""
        start_time = time.time()

        if session_id not in self._data_store:
            logger.warning(f"[SESSION_MANAGER] get_analysis_result: session_id '{session_id}' 不存在")
            return None

        result = self._data_store[session_id].get("analysis_results", {})

        elapsed = time.time() - start_time
        logger.info(f"[SESSION_MANAGER] get_analysis_result {'成功' if result else '空'}", extra={
            "session_id": session_id,
            "has_data": bool(result),
            "execution_time": elapsed,
            "action": "get_analysis_result"
        })

        return result

    def store_charts(self, session_id: str, charts: list) -> None:
        """存储图表数据"""
        start_time = time.time()

        if session_id not in self._data_store:
            logger.error(f"[SESSION_MANAGER] store_charts 失败：session_id '{session_id}' 不存在")
            raise ValueError(f"Session {session_id} not found")

        self._data_store[session_id]["charts"] = charts

        elapsed = time.time() - start_time
        logger.info(f"[SESSION_MANAGER] store_charts 完成", extra={
            "session_id": session_id,
            "chart_count": len(charts),
            "execution_time": elapsed,
            "action": "store_charts"
        })

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

    # ========== 共享分析结果存储方法（新增） ==========

    def store_analysis_result(self, session_id: str, result: Dict) -> None:
        """
        存储分析结果到共享存储（Tool-Calling Agent 调用）

        :param session_id: 会话 ID
        :param result: 分析结果字典，可包含 basic_stats, column_stats, charts 等
        """
        if session_id not in self._analysis_results_store:
            self._analysis_results_store[session_id] = {
                "basic_stats": {},
                "column_stats": {},
                "chart_data": [],
                "key_findings": [],
                "last_updated": datetime.now()
            }

        existing = self._analysis_results_store[session_id]

        # 合并分析结果
        if result.get("basic_stats"):
            existing["basic_stats"].update(result["basic_stats"])
        if result.get("column_stats"):
            existing["column_stats"].update(result["column_stats"])
        if result.get("charts"):
            existing["chart_data"].extend(result["charts"])
        if result.get("key_findings"):
            existing["key_findings"].extend(result["key_findings"])

        existing["last_updated"] = datetime.now()
        print(f"[SessionManager] 已存储分析结果到共享存储，session_id: {session_id}")

    def get_analysis_results(self, session_id: str) -> Optional[Dict]:
        """
        获取共享分析结果（ReportAgent 调用）

        :param session_id: 会话 ID
        :return: 分析结果字典，包含 basic_stats, column_stats, chart_data, key_findings 等
        """
        return self._analysis_results_store.get(session_id)

    def clear_analysis_results(self, session_id: str) -> None:
        """
        清空共享分析结果（会话结束时调用）

        :param session_id: 会话 ID
        """
        if session_id in self._analysis_results_store:
            del self._analysis_results_store[session_id]
            print(f"[SessionManager] 已清空分析结果，session_id: {session_id}")

    def merge_analysis_result(self, session_id: str, result: Dict) -> None:
        """
        合并分析结果到共享存储（支持增量更新）

        :param session_id: 会话 ID
        :param result: 分析结果字典
        """
        self.store_analysis_result(session_id, result)

    def store_analysis_context(self, session_id: str, context: AnalysisContext) -> None:
        """
        存储分析上下文（用于 ReportAgent）

        :param session_id: 会话 ID
        :param context: AnalysisContext 对象
        """
        if session_id not in self._data_store:
            self._data_store[session_id] = {}
        self._data_store[session_id]["analysis_context"] = context
        print(f"[SessionManager] 已存储分析上下文，session_id: {session_id}, request_id: {context.request_id}")

    def get_analysis_context(self, session_id: str) -> Optional[AnalysisContext]:
        """
        获取分析上下文

        :param session_id: 会话 ID
        :return: AnalysisContext 对象或 None
        """
        if session_id not in self._data_store:
            return None
        return self._data_store[session_id].get("analysis_context")
