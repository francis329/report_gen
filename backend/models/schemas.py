from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class SheetInfo(BaseModel):
    """Sheet 页信息"""
    name: str
    columns: List[str]
    row_count: int


class FileInfo(BaseModel):
    """文件信息"""
    id: str
    filename: str
    sheets: List[SheetInfo] = []
    upload_time: datetime = Field(default_factory=datetime.now)


class Message(BaseModel):
    """对话消息"""
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ClarificationState(BaseModel):
    """澄清状态"""
    is_clarifying: bool = False           # 是否处于澄清中
    clarification_question: str = ""      # 当前澄清问题
    pending_intent: Dict[str, Any] = {}   # 待确认的意图
    turn_count: int = 0                   # 澄清轮次
    ambiguous_aspects: List[str] = []     # 需要澄清的方面


class Session(BaseModel):
    """会话"""
    id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    files: List[FileInfo] = []
    messages: List[Message] = []
    report_id: Optional[str] = None
    clarification_state: Optional[ClarificationState] = None


# API 请求/响应模型
class CreateSessionRequest(BaseModel):
    name: Optional[str] = "新会话"


class CreateSessionResponse(BaseModel):
    session: Session


class SessionListResponse(BaseModel):
    sessions: List[Session]


class UploadFileResponse(BaseModel):
    file_info: FileInfo
    message: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    report_url: Optional[str] = None
    is_clarifying: bool = False           # 是否处于澄清状态
    clarification_question: Optional[str] = None  # 澄清问题（如果有）


class ReportResponse(BaseModel):
    report_id: str
    html_content: str
    download_url: str
