"""
Agent 基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple

from backend.tools.base import ToolResult


class BaseAgent(ABC):
    """Agent 基类 - 所有 Agent 的抽象父类"""

    @abstractmethod
    async def run(
        self,
        user_message: str,
        context: Dict[str, Any]
    ) -> Tuple[str, List[ToolResult]]:
        """
        运行 Agent

        :param user_message: 用户消息
        :param context: 上下文（包含 session_id, sheets_info 等）
        :return: (回复内容，工具执行结果列表)
        """
        pass
