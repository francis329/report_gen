"""
工具注册中心
管理所有可用工具的注册和获取
"""
from typing import Dict, List, Optional

from backend.tools.base import BaseTool, ToolDefinition


class ToolRegistry:
    """工具注册中心 - 单例模式"""

    _instance: Optional['ToolRegistry'] = None
    _tools: Dict[str, BaseTool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset(cls):
        """重置注册表（用于测试）"""
        cls._instance = None
        cls._tools = {}

    def register(self, tool: BaseTool) -> None:
        """
        注册工具

        :param tool: 工具实例
        """
        self._tools[tool.definition.name] = tool

    def unregister(self, name: str) -> bool:
        """
        注销工具

        :param name: 工具名称
        :return: 是否成功注销
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具

        :param name: 工具名称
        :return: 工具实例，不存在则返回 None
        """
        return self._tools.get(name)

    def get_all(self) -> List[BaseTool]:
        """
        获取所有工具

        :return: 工具实例列表
        """
        return list(self._tools.values())

    def has_tool(self, name: str) -> bool:
        """
        检查工具是否存在

        :param name: 工具名称
        :return: 是否存在
        """
        return name in self._tools

    def get_function_schemas(self) -> List[Dict]:
        """
        获取所有工具的 function schema（用于 LLM 工具调用）

        :return: schema 列表
        """
        return [tool.to_function_schema() for tool in self._tools.values()]

    def get_tool_names(self) -> List[str]:
        """
        获取所有工具名称

        :return: 工具名称列表
        """
        return list(self._tools.keys())
