"""
工具基类
定义工具的抽象接口和数据结构
"""
import time
import traceback
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# 配置工具日志
logger = logging.getLogger('tools')


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
    execution_time: float = 0.0  # 执行耗时（秒）


class BaseTool(ABC):
    """工具基类 - 所有工具的抽象父类"""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回工具定义"""
        pass

    @abstractmethod
    async def _execute_impl(self, **kwargs) -> ToolResult:
        """
        执行工具的具体实现（由子类实现）

        :param kwargs: 工具参数
        :return: 工具执行结果
        """
        pass

    async def execute(self, **kwargs) -> ToolResult:
        """
        执行工具（带日志和错误处理的包装方法）

        :param kwargs: 工具参数
        :return: 工具执行结果
        """
        start_time = time.time()
        tool_name = self.definition.name

        try:
            # 开始执行日志
            logger.info(f"[TOOL] 开始执行：{tool_name}, 参数：{kwargs}", extra={
                "tool_name": tool_name,
                "parameters": kwargs,
                "action": "start"
            })

            # 调用子类实现
            result = await self._execute_impl(**kwargs)
            execution_time = time.time() - start_time

            # 失败日志增强
            if not result.success:
                logger.error(f"[TOOL] 执行失败：{tool_name}, 错误：{result.error}", extra={
                    "tool_name": tool_name,
                    "parameters": kwargs,
                    "error": result.error,
                    "execution_time": execution_time,
                    "action": "failure"
                })
            else:
                # 成功日志
                logger.info(f"[TOOL] 执行成功：{tool_name}, 耗时：{execution_time:.3f}s", extra={
                    "tool_name": tool_name,
                    "parameters": kwargs,
                    "execution_time": execution_time,
                    "action": "success"
                })

            result.execution_time = execution_time
            return result

        except Exception as e:
            execution_time = time.time() - start_time
            error_detail = traceback.format_exc()

            # 异常日志增强
            logger.error(f"[TOOL] 执行异常：{tool_name}", extra={
                "tool_name": tool_name,
                "parameters": kwargs,
                "exception": str(e),
                "traceback": error_detail,
                "execution_time": execution_time,
                "action": "exception"
            })

            return ToolResult(success=False, error=f"{type(e).__name__}: {str(e)}")

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

    def get_usage_example(self) -> str:
        """
        获取工具调用示例（用于系统提示词中指导 LLM）

        :return: JSON 格式的工具调用示例
        """
        example_args = {}
        for param in self.definition.parameters:
            if param.type == "string":
                example_args[param.name] = f"<{param.name}>"
            elif param.type == "number":
                example_args[param.name] = 0
            elif param.type == "boolean":
                example_args[param.name] = False
            elif param.type == "array":
                example_args[param.name] = []
            elif param.type == "object":
                example_args[param.name] = {}

        return f'{{"name": "{self.definition.name}", "arguments": {example_args}}}'

    def __repr__(self) -> str:
        return f"<Tool {self.definition.name}>"
