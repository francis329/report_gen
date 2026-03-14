"""
图表生成工具
提供数据可视化相关的工具实现
"""
import time
from typing import Dict, Any, List

from backend.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from backend.services.session_manager import SessionManager


class GenerateChartTool(BaseTool):
    """生成图表工具 - 根据数据生成可视化图表"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_chart",
            description="根据数据生成可视化图表。支持柱状图、折线图、饼图、散点图等类型。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID（此参数由系统自动注入，无需指定）",
                    required=False
                ),
                ToolParameter(
                    name="chart_type",
                    type="string",
                    description="图表类型",
                    enum=["bar", "line", "pie", "scatter"]
                ),
                ToolParameter(
                    name="column",
                    type="string",
                    description="要绘图的列名"
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="图表标题",
                    required=False
                ),
                ToolParameter(
                    name="second_column",
                    type="string",
                    description="第二列名（散点图需要两个数值列）",
                    required=False
                )
            ]
        )

    async def _execute_impl(self, **kwargs) -> ToolResult:
        from backend.utils.chart_builder import ChartBuilder

        session_id = kwargs.get("session_id")
        chart_type = kwargs.get("chart_type", "bar")
        column = kwargs.get("column")
        title = kwargs.get("title", f"{column} - {chart_type}图")
        second_column = kwargs.get("second_column")

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")
        if not column:
            return ToolResult(success=False, error="缺少 column 参数")

        # 获取文件数据
        file_data = None
        files = self.session_manager.get_files(session_id)
        for f in files:
            file_data = self.session_manager.get_file_data(session_id, f.id)
            if file_data:
                break

        if not file_data:
            return ToolResult(success=False, error="未找到数据文件")

        df = list(file_data.values())[0]

        if column not in df.columns:
            return ToolResult(
                success=False,
                error=f"列 '{column}' 不存在。可用列：{', '.join(df.columns[:10])}"
            )

        # 准备数据
        import pandas as pd
        chart_data = {}

        try:
            if chart_type in ["bar", "line"]:
                if pd.api.types.is_numeric_dtype(df[column]):
                    # 数值型：取前 100 个点
                    values = df[column].dropna().tolist()[:100]
                    chart_data = {"x": list(range(len(values))), "y": values}
                else:
                    # 分类型：值频次
                    value_counts = df[column].value_counts().head(20)
                    chart_data = {
                        "x": value_counts.index.tolist(),
                        "y": value_counts.values.tolist()
                    }

            elif chart_type == "pie":
                value_counts = df[column].value_counts().head(15)
                chart_data = {"values": value_counts.to_dict()}

            elif chart_type == "scatter":
                if not second_column:
                    # 自动找另一个数值列
                    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                    if column in numeric_cols:
                        numeric_cols.remove(column)
                    if len(numeric_cols) < 1:
                        return ToolResult(
                            success=False,
                            error="散点图需要至少两个数值列，当前数据只有一个"
                        )
                    second_column = numeric_cols[0]

                if second_column not in df.columns:
                    return ToolResult(success=False, error=f"列 '{second_column}' 不存在")

                # 取两列的完整数据（删除缺失值）
                valid_mask = df[column].notna() & df[second_column].notna()
                x_values = df.loc[valid_mask, column].tolist()[:300]
                y_values = df.loc[valid_mask, second_column].tolist()[:300]

                if len(x_values) < 3:
                    return ToolResult(success=False, error="有效数据点不足")

                chart_data = {"x": x_values, "y": y_values}
                title = f"{column} vs {second_column} 散点图"

            else:
                return ToolResult(success=False, error=f"不支持的图表类型：{chart_type}")

            # 生成图表
            chart_method = getattr(ChartBuilder, f"create_{chart_type}_chart", None)
            if not chart_method:
                return ToolResult(success=False, error=f"图表生成方法不存在")

            chart = chart_method(chart_data, title=title)

            # 存储图表
            charts = self.session_manager.get_charts(session_id)
            charts.append(chart)
            self.session_manager.store_charts(session_id, charts)

            return ToolResult(
                success=True,
                data=chart,
                message=f"已生成 {chart_type} 图表：{title}"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"生成图表失败：{str(e)}"
            )


class GenerateCorrelationHeatmapTool(BaseTool):
    """生成相关性热力图工具"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_correlation_heatmap",
            description="生成数值列之间的相关性矩阵热力图，用于分析变量间的相关关系。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID（此参数由系统自动注入，无需指定）",
                    required=False
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="图表标题",
                    required=False,
                    default="变量相关性热力图"
                )
            ]
        )

    async def _execute_impl(self, **kwargs) -> ToolResult:
        from backend.utils.chart_builder import ChartBuilder
        import numpy as np

        session_id = kwargs.get("session_id")
        title = kwargs.get("title", "变量相关性热力图")

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")

        # 获取文件数据
        file_data = None
        files = self.session_manager.get_files(session_id)
        for f in files:
            file_data = self.session_manager.get_file_data(session_id, f.id)
            if file_data:
                break

        if not file_data:
            return ToolResult(success=False, error="未找到数据文件")

        df = list(file_data.values())[0]

        # 只取数值列
        numeric_df = df.select_dtypes(include=['number'])

        if len(numeric_df.columns) < 2:
            return ToolResult(
                success=False,
                error="至少需要两个数值列才能生成相关性热力图"
            )

        # 计算相关性矩阵
        corr_matrix = numeric_df.corr()

        # 准备热力图数据
        x_labels = corr_matrix.columns.tolist()
        y_labels = corr_matrix.index.tolist()
        values = []
        for i, row in enumerate(corr_matrix.values):
            for j, val in enumerate(row):
                values.append([i, j, round(val, 3)])

        chart_data = {
            "x": x_labels,
            "y": y_labels,
            "values": values
        }

        try:
            chart = ChartBuilder.create_heatmap(chart_data, title=title, x_labels=x_labels, y_labels=y_labels)

            # 存储图表
            charts = self.session_manager.get_charts(session_id)
            charts.append(chart)
            self.session_manager.store_charts(session_id, charts)

            return ToolResult(
                success=True,
                data=chart,
                message=f"已生成相关性热力图，包含 {len(x_labels)} 个变量"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"生成热力图失败：{str(e)}"
            )


class AutoGenerateChartsTool(BaseTool):
    """自动生成图表工具 - 根据数据特征自动推荐并生成合适的图表"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="auto_generate_charts",
            description="根据数据特征自动推荐并生成合适的图表类型。"
                       "系统会分析数据类型并选择合适的可视化方式。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID（此参数由系统自动注入，无需指定）",
                    required=False
                )
            ]
        )

    async def _execute_impl(self, **kwargs) -> ToolResult:
        from backend.utils.chart_builder import ChartBuilder

        session_id = kwargs.get("session_id")

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")

        # 获取文件数据和分析结果
        file_data = None
        files = self.session_manager.get_files(session_id)
        for f in files:
            file_data = self.session_manager.get_file_data(session_id, f.id)
            if file_data:
                break

        if not file_data:
            return ToolResult(success=False, error="未找到数据文件")

        analysis_results = self.session_manager.get_analysis_result(session_id)

        try:
            # 使用 ChartBuilder 的自动生成功能
            charts = ChartBuilder.auto_generate_charts(file_data, analysis_results or {})

            if not charts:
                return ToolResult(
                    success=False,
                    error="未能生成合适的图表，可能需要手动指定图表类型和列名"
                )

            # 存储所有生成的图表
            existing_charts = self.session_manager.get_charts(session_id)
            # 确保 existing_charts 是列表
            if not isinstance(existing_charts, list):
                existing_charts = []
            existing_charts.extend(charts)
            self.session_manager.store_charts(session_id, existing_charts)

            chart_types = list(set(c.get("type", "unknown") for c in charts))

            return ToolResult(
                success=True,
                data={"charts": charts, "count": len(charts)},
                message=f"已自动生成 {len(charts)} 个图表：{', '.join(chart_types)}"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"自动生成图表失败：{str(e)}"
            )
