"""
报告生成相关的数据模型
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum


class AnalysisType(str, Enum):
    """分析类型"""
    OVERVIEW = "overview"           # 数据概览
    RANKING = "ranking"             # 排名分析
    TREND = "trend"                 # 趋势分析
    DISTRIBUTION = "distribution"   # 分布分析
    COMPARISON = "comparison"       # 对比分析
    CORRELATION = "correlation"     # 相关性分析
    INSIGHT = "insight"             # AI 洞察


class ChapterPlan(BaseModel):
    """
    章节规划

    由 LLM 智能生成，每个章节有明确的分析目标和数据维度
    """
    id: str = Field(..., description="章节 ID（用于导航锚点）")
    title: str = Field(..., description="章节标题（动态生成，具体反映分析内容）")
    description: str = Field(..., description="本章分析什么，解决什么问题")
    dimensions: List[str] = Field(default_factory=list, description="本章使用的字段/维度")
    analysis_guidance: str = Field(..., description="分析思路指导（如：按省份统计失败率，找出 TOP5）")

    class Config:
        use_enum_values = True


class ChartSpec(BaseModel):
    """
    图表规格

    定义图表类型、数据查询条件等
    """
    chapter_id: str = Field(..., description="所属章节 ID")
    chart_type: str = Field(..., description="图表类型：bar/line/pie/scatter/heatmap")
    data_query: Dict[str, Any] = Field(default_factory=dict, description="数据查询条件")
    title: str = Field(..., description="图表标题")
    element_key_field: Optional[str] = Field(None, description="用于筛选原始数据的字段名（点击图表元素时使用）")


class ReportPlan(BaseModel):
    """
    报告规划

    由 ReportPlanner 生成，包含完整的报告结构和分析指导
    """
    title: str = Field(..., description="报告标题（具体反映分析主题）")
    theme: str = Field(..., description="分析主题")
    user_intent: str = Field(..., description="用户意图描述")
    chapters: List[ChapterPlan] = Field(default_factory=list, description="章节规划列表")
    required_fields: List[str] = Field(default_factory=list, description="需要的字段列表")
    suggested_charts: List[ChartSpec] = Field(default_factory=list, description="建议的图表")

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)


class ChapterResult(BaseModel):
    """
    章节执行结果

    由 ReportExecutor 执行后生成，包含分析数据和图表
    """
    chapter_id: str
    title: str
    description: str
    analysis_type: str
    data: Dict[str, Any] = Field(default_factory=dict)
    insights: List[str] = Field(default_factory=list)
    chart_spec: Optional[Dict[str, Any]] = None
    chart_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    content: Optional[str] = None  # 生成的 HTML 内容


class ReportExecutionResult(BaseModel):
    """
    报告执行结果

    包含所有章节的执行结果
    """
    plan: ReportPlan
    chapters: List[ChapterResult] = Field(default_factory=list)
    session_id: str
    success_count: int = 0
    error_count: int = 0

    def add_chapter(self, chapter: ChapterResult):
        self.chapters.append(chapter)
        if chapter.success:
            self.success_count += 1
        else:
            self.error_count += 1


class ChartDataQuery(BaseModel):
    """
    图表数据查询条件

    用于存储图表与原始数据的关联关系，支持点击查看原始数据
    """
    chart_id: str
    chapter_id: str
    dimensions: List[str] = Field(default_factory=list)
    query_type: str  # overview/ranking/trend/distribution/comparison/correlation
    data: Dict[str, Any] = Field(default_factory=dict)
    element_key_field: Optional[str] = None  # 用于筛选的字段名
