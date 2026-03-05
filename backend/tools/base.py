"""
工具基类
定义工具的抽象接口和数据结构
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    enum: Optional[List[Any]] = None
    default: Optional[Any] = None


class ToolDefinition(BaseModel):
    """工具定义（用于注册和描述）"""
    name: str
    description: str
    parameters: List[ToolParameter] = []


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    message: str = ""


class BaseTool(ABC):
    """工具基类 - 所有工具的抽象父类"""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回工具定义"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        执行工具

        :param kwargs: 工具参数
        :return: 工具执行结果
        """
        pass

    def to_function_schema(self) -> Dict:
        """
        转换为 LLM function calling schema

        :return: function schema 字典
        """
        properties = {}
        required = []

        for param in self.definition.parameters:
            param_schema = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                param_schema["enum"] = param.enum
            if param.default is not None:
                param_schema["default"] = param.default

            properties[param.name] = param_schema

            if param.required:
                required.append(param.name)

        return {
            "name": self.definition.name,
            "description": self.definition.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

    def __repr__(self) -> str:
        return f"<Tool {self.definition.name}>"
