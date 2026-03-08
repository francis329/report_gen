"""
图表生成工具
使用 pyecharts 生成各种可视化图表
"""
from typing import Dict, List, Any, Optional
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Pie, Scatter, HeatMap, Boxplot


class ChartBuilder:
    """图表构建器"""

    @staticmethod
    def create_bar_chart(
        data: Dict[str, Any],
        title: str = "柱状图",
        x_name: str = "",
        y_name: str = ""
    ) -> Dict[str, Any]:
        """创建柱状图"""
        chart = Bar(init_opts=opts.InitOpts(width="100%", height="400px"))

        x_data = data.get("x", [])
        y_data = data.get("y", [])

        chart.add_xaxis(x_data)
        chart.add_yaxis(
            series_name=title,
            y_axis=y_data,
            label_opts=opts.LabelOpts(is_show=True)
        )

        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(name=x_name),
            yaxis_opts=opts.AxisOpts(name=y_name),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
        )

        return {
            "type": "bar",
            "title": title,
            "html": chart.render_embed(),
        }

    @staticmethod
    def create_line_chart(
        data: Dict[str, Any],
        title: str = "折线图",
        x_name: str = "",
        y_name: str = ""
    ) -> Dict[str, Any]:
        """创建折线图"""
        chart = Line(init_opts=opts.InitOpts(width="100%", height="400px"))

        x_data = data.get("x", [])
        y_data = data.get("y", [])

        chart.add_xaxis(x_data)
        chart.add_yaxis(
            series_name=title,
            y_axis=y_data,
            is_smooth=True,
            label_opts=opts.LabelOpts(is_show=False),
        )

        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(name=x_name),
            yaxis_opts=opts.AxisOpts(name=y_name),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
        )

        return {
            "type": "line",
            "title": title,
            "html": chart.render_embed(),
        }

    @staticmethod
    def create_pie_chart(
        data: Dict[str, Any],
        title: str = "饼图"
    ) -> Dict[str, Any]:
        """创建饼图"""
        chart = Pie(init_opts=opts.InitOpts(width="100%", height="400px"))

        pairs = [(k, v) for k, v in data.get("values", {}).items() if v is not None and v > 0]

        # 如果没有有效数据，返回空图表
        if not pairs:
            print(f"[WARN] 饼图数据为空：{data}")
            return {
                "type": "pie",
                "title": title,
                "html": "<div style='text-align:center;padding:40px;color:#999;'>暂无数据</div>",
            }

        chart.add(
            series_name=title,
            data_pair=pairs,
            radius=["40%", "70%"],
        )

        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            tooltip_opts=opts.TooltipOpts(trigger="item"),
        )

        chart.set_series_opts(
            label_opts=opts.LabelOpts(formatter="{b}: {c} ({d}%)")
        )

        return {
            "type": "pie",
            "title": title,
            "html": chart.render_embed(),
        }

    @staticmethod
    def create_scatter_chart(
        data: Dict[str, Any],
        title: str = "散点图",
        x_name: str = "X 轴",
        y_name: str = "Y 轴"
    ) -> Dict[str, Any]:
        """创建散点图"""
        chart = Scatter(init_opts=opts.InitOpts(width="100%", height="400px"))

        chart.add_xaxis(data.get("x", []))
        chart.add_yaxis(
            series_name=title,
            y_axis=data.get("y", []),
            symbol_size=data.get("symbol_size", 10),
        )

        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(name=x_name),
            yaxis_opts=opts.AxisOpts(name=y_name),
            tooltip_opts=opts.TooltipOpts(trigger="item"),
        )

        return {
            "type": "scatter",
            "title": title,
            "html": chart.render_embed(),
        }

    @staticmethod
    def create_heatmap(
        data: Dict[str, Any],
        title: str = "热力图",
        x_labels: List[str] = None,
        y_labels: List[str] = None
    ) -> Dict[str, Any]:
        """创建热力图"""
        chart = HeatMap(init_opts=opts.InitOpts(width="100%", height="500px"))

        values = data.get("values", [])
        x_values = data.get("x", x_labels or [])
        y_values = data.get("y", y_labels or [])

        chart.add_xaxis(x_values)
        chart.add_yaxis(
            series_name=title,
            y_axis=y_values,
            value=values,
            label_opts=opts.LabelOpts(is_show=True),
        )

        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            tooltip_opts=opts.TooltipOpts(trigger="cell"),
        )

        return {
            "type": "heatmap",
            "title": title,
            "html": chart.render_embed(),
        }

    @staticmethod
    def create_boxplot(
        data: Dict[str, Any],
        title: str = "箱线图",
        x_name: str = ""
    ) -> Dict[str, Any]:
        """创建箱线图"""
        chart = Boxplot(init_opts=opts.InitOpts(width="100%", height="400px"))

        chart.add_xaxis(data.get("categories", []))
        chart.add_yaxis(
            series_name=title,
            y_axis=chart.prepare_data(data.get("values", [])),
        )

        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(name=x_name),
            tooltip_opts=opts.TooltipOpts(trigger="item"),
        )

        return {
            "type": "boxplot",
            "title": title,
            "html": chart.render_embed(),
        }

    @staticmethod
    def auto_generate_charts(
        sheets_data: Dict[str, Any],
        analysis_results: Dict[str, Any],
        chart_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        根据数据自动生成合适的图表
        :param sheets_data: 数据字典 {sheet_name: dataframe}
        :param analysis_results: 分析结果
        :param chart_types: 指定的图表类型列表
        """
        charts = []

        if not sheets_data:
            return charts

        # 如果没有指定图表类型，根据数据自动选择
        if not chart_types:
            chart_types = ChartBuilder._suggest_chart_types(analysis_results)

        # 检查是否是合并分析结果（支持两种结构）
        is_merged = analysis_results.get("is_merged", False) or (
            analysis_results.get("merged_analysis", {}).get("is_merged", False)
        )

        if is_merged:
            # 合并分析 - 需要拼接所有 sheet 数据
            merged = analysis_results.get("merged_analysis", {})
            try:
                import pandas as pd
                merged_df = pd.concat(sheets_data.values(), ignore_index=True)
                ChartBuilder._generate_charts_for_sheet(
                    merged_df, "合并数据", merged.get("basic_stats", {}), chart_types, charts
                )
            except Exception as e:
                print(f"合并数据生成图表失败：{e}")
        else:
            # 为每个 sheet 生成图表
            individual = analysis_results.get("individual_analyses", {})
            for sheet_name, df in sheets_data.items():
                if sheet_name in individual:
                    stats = individual[sheet_name].get("basic_stats", {})
                    ChartBuilder._generate_charts_for_sheet(
                        df, sheet_name, stats, chart_types, charts
                    )

        return charts

    @staticmethod
    def _generate_charts_for_sheet(
        df,
        sheet_name: str,
        stats: Dict,
        chart_types: List[str],
        charts: List[Dict[str, Any]]
    ):
        """为单个 sheet 生成图表"""
        columns = stats.get("columns", [])

        for col_stats in columns:
            col_name = col_stats["name"]
            col_type = col_stats.get("type", "categorical")

            if col_name not in df.columns:
                continue

            # 数值型数据生成折线图或柱状图
            if col_type == "numeric" and ("line" in chart_types or "bar" in chart_types):
                if len(df) > 1:
                    values = df[col_name].dropna().tolist()
                    if values:
                        # 限制数据量，最多显示 100 个点
                        chart_data = {
                            "x": list(range(min(len(values), 100))),
                            "y": values[:100],
                        }
                        if "line" in chart_types:
                            charts.append(ChartBuilder.create_line_chart(
                                chart_data,
                                title=f"{sheet_name} - {col_name} 趋势"
                            ))
                        elif "bar" in chart_types:
                            charts.append(ChartBuilder.create_bar_chart(
                                chart_data,
                                title=f"{sheet_name} - {col_name}"
                            ))

            # 分类型数据生成饼图或柱状图
            if col_type == "categorical" and ("pie" in chart_types or "bar" in chart_types):
                if df[col_name].nunique() <= 10 and df[col_name].nunique() > 1:
                    value_counts = df[col_name].value_counts().head(10).to_dict()
                    if "pie" in chart_types:
                        chart_data = {"values": {str(k): int(v) for k, v in value_counts.items()}}
                        charts.append(ChartBuilder.create_pie_chart(
                            chart_data,
                            title=f"{sheet_name} - {col_name} 分布"
                        ))
                    elif "bar" in chart_types:
                        chart_data = {
                            "x": list(value_counts.keys()),
                            "y": list(value_counts.values()),
                        }
                        charts.append(ChartBuilder.create_bar_chart(
                            chart_data,
                            title=f"{sheet_name} - {col_name} 统计"
                        ))

        # 如果有多个数值列，生成散点图
        numeric_cols = [col["name"] for col in columns if col.get("type") == "numeric"]
        if len(numeric_cols) >= 2 and "scatter" in chart_types:
            if numeric_cols[0] in df.columns and numeric_cols[1] in df.columns:
                x_values = df[numeric_cols[0]].dropna().tolist()[:200]
                y_values = df[numeric_cols[1]].dropna().tolist()[:200]
                if len(x_values) == len(y_values) and len(x_values) > 2:
                    chart_data = {"x": x_values, "y": y_values}
                    charts.append(ChartBuilder.create_scatter_chart(
                        chart_data,
                        title=f"{sheet_name} - {numeric_cols[0]} vs {numeric_cols[1]}",
                        x_name=numeric_cols[0],
                        y_name=numeric_cols[1]
                    ))

    @staticmethod
    def _suggest_chart_types(analysis_results: Dict) -> List[str]:
        """根据分析结果建议图表类型"""
        suggestions = ["bar"]  # 默认包含柱状图

        # 检查是否有数值列
        has_numeric = any(
            col.get("type") == "numeric"
            for col in analysis_results.get("basic_stats", {}).get("columns", [])
        )
        if has_numeric:
            suggestions.append("line")

        # 检查是否有分类型列
        has_categorical = any(
            col.get("type") == "categorical"
            for col in analysis_results.get("basic_stats", {}).get("columns", [])
        )
        if has_categorical:
            suggestions.append("pie")

        # 检查是否有多个数值列
        numeric_count = sum(
            1 for col in analysis_results.get("basic_stats", {}).get("columns", [])
            if col.get("type") == "numeric"
        )
        if numeric_count >= 2:
            suggestions.append("scatter")

        return suggestions
