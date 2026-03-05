"""
报告生成服务
整合分析结果和图表，生成 HTML 格式报告
"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from backend.config import REPORTS_DIR
from backend.services.session_manager import SessionManager


class ReportGenerator:
    """报告生成器"""

    @staticmethod
    def generate_html_report(
        session_id: str,
        session_name: str,
        analysis_results: Dict[str, Any],
        charts: List[Dict[str, Any]],
        ai_summary: str = ""
    ) -> str:
        """生成 HTML 报告"""
        report_id = str(uuid.uuid4())[:8]

        # 生成报告内容
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据分析报告 - {session_name}</title>
    <script src="https://cdn.jsdelivr.net/pyecharts/v2/pyecharts.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
            margin-bottom: 30px;
            border-radius: 10px;
        }}
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}
        .header p {{
            opacity: 0.9;
            font-size: 1.1rem;
        }}
        .section {{
            background: white;
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        .section h3 {{
            color: #555;
            margin: 20px 0 10px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-card .label {{
            color: #666;
            font-size: 0.9rem;
            margin-top: 5px;
        }}
        .quality-score {{
            font-size: 3rem;
            font-weight: bold;
        }}
        .quality-good {{ color: #28a745; }}
        .quality-medium {{ color: #ffc107; }}
        .quality-poor {{ color: #dc3545; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
            color: #555;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .chart-container {{
            margin: 30px 0;
        }}
        .ai-summary {{
            background: #f0f4ff;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }}
        .footer {{
            text-align: center;
            padding: 30px;
            color: #666;
            font-size: 0.9rem;
        }}
        .tag {{
            display: inline-block;
            padding: 4px 12px;
            background: #e9ecef;
            border-radius: 20px;
            font-size: 0.85rem;
            margin: 2px;
        }}
        .tag-numeric {{ background: #e3f2fd; color: #1976d2; }}
        .tag-categorical {{ background: #f3e5f5; color: #7b1fa2; }}
        .progress-bar {{
            height: 8px;
            background: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.3s;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 数据分析报告</h1>
            <p>{session_name}</p>
            <p style="margin-top: 10px; font-size: 0.9rem;">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        {ReportGenerator._generate_overview_section(analysis_results)}
        {ReportGenerator._generate_quality_section(analysis_results)}
        {ReportGenerator._generate_detailed_analysis_section(analysis_results)}
        {ReportGenerator._generate_charts_section(charts)}
        {ReportGenerator._generate_ai_analysis_section(ai_summary)}

        <div class="footer">
            <p>本报告由 AI 驱动的报告生成系统自动生成</p>
        </div>
    </div>
</body>
</html>
"""

        # 保存报告
        report_path = REPORTS_DIR / f"{report_id}.html"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return report_id

    @staticmethod
    def _generate_overview_section(analysis_results: Dict) -> str:
        """生成概览部分"""
        total_rows = 0
        total_cols = 0
        sheet_count = 0

        # 检查是否是合并分析结果（两种结构都支持）
        # 结构 1: {"merged_analysis": {...}, "is_merged": True}
        # 结构 2: {"merged_analysis": {"is_merged": True, ...}}
        is_merged = analysis_results.get("is_merged", False) or (
            analysis_results.get("merged_analysis", {}).get("is_merged", False)
        )

        if is_merged:
            merged = analysis_results.get("merged_analysis", {})
            stats = merged.get("basic_stats", {})
            total_rows = stats.get("row_count", 0)
            total_cols = stats.get("column_count", 0)
            # 获取 source_sheets 数量，如果没有则设为 1
            source_sheets = merged.get("source_sheets", [])
            sheet_count = len(source_sheets) if source_sheets else 1
        else:
            individual = analysis_results.get("individual_analyses", {})
            for sheet_name, analysis in individual.items():
                stats = analysis.get("basic_stats", {})
                total_rows += stats.get("row_count", 0)
                total_cols = max(total_cols, stats.get("column_count", 0))
                sheet_count += 1

        return f"""
        <div class="section">
            <h2>📈 数据概览</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="value">{total_rows:,}</div>
                    <div class="label">总行数</div>
                </div>
                <div class="stat-card">
                    <div class="value">{total_cols}</div>
                    <div class="label">列数</div>
                </div>
                <div class="stat-card">
                    <div class="value">{sheet_count}</div>
                    <div class="label">数据表</div>
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _generate_quality_section(analysis_results: Dict) -> str:
        """生成数据质量部分"""
        # 检查是否是合并分析结果
        is_merged = analysis_results.get("is_merged", False) or (
            analysis_results.get("merged_analysis", {}).get("is_merged", False)
        )

        if is_merged:
            merged = analysis_results.get("merged_analysis", {})
            quality = merged.get("data_quality", {})
        else:
            individual = analysis_results.get("individual_analyses", {})
            if individual:
                # 取第一个 sheet 的质量作为代表
                first_sheet = list(individual.values())[0]
                quality = first_sheet.get("data_quality", {})
            else:
                quality = {}

        score = quality.get("quality_score", 0)
        if score >= 80:
            score_class = "quality-good"
        elif score >= 60:
            score_class = "quality-medium"
        else:
            score_class = "quality-poor"

        outliers_count = sum(quality.get("outliers", {}).values()) if isinstance(quality.get("outliers"), dict) else 0

        return f"""
        <div class="section">
            <h2>🔍 数据质量</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="quality-score {score_class}">{score:.1f}</div>
                    <div class="label">质量评分</div>
                </div>
                <div class="stat-card">
                    <div class="value">{quality.get('null_percentage', 0):.1f}%</div>
                    <div class="label">缺失值比例</div>
                </div>
                <div class="stat-card">
                    <div class="value">{quality.get('duplicate_percentage', 0):.1f}%</div>
                    <div class="label">重复行比例</div>
                </div>
                <div class="stat-card">
                    <div class="value">{outliers_count}</div>
                    <div class="label">异常值数量</div>
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _generate_detailed_analysis_section(analysis_results: Dict) -> str:
        """生成详细数据分析部分"""
        sections = []

        # 检查是否是合并分析结果
        is_merged = analysis_results.get("is_merged", False) or (
            analysis_results.get("merged_analysis", {}).get("is_merged", False)
        )

        if is_merged:
            # 合并分析
            merged = analysis_results.get("merged_analysis", {})
            sections.append(
                ReportGenerator._generate_single_sheet_analysis(
                    merged, "合并数据"
                )
            )
        else:
            # 分开分析每个 sheet
            individual = analysis_results.get("individual_analyses", {})
            for sheet_name, analysis in individual.items():
                sections.append(
                    ReportGenerator._generate_single_sheet_analysis(analysis, sheet_name)
                )

        if not sections:
            return ""

        return f"""
        <div class="section">
            <h2>📋 详细数据分析</h2>
            {''.join(sections)}
        </div>
        """

    @staticmethod
    def _generate_single_sheet_analysis(analysis: Dict, sheet_name: str) -> str:
        """生成单个 sheet 的分析报告"""
        if not analysis:
            return ""

        basic_stats = analysis.get("basic_stats", {})
        data_quality = analysis.get("data_quality", {})

        # 数值型列统计
        numeric_stats = ""
        numeric_cols = [
            col for col in basic_stats.get("columns", [])
            if col.get("type") == "numeric"
        ]

        if numeric_cols:
            numeric_rows = ""
            for col in numeric_cols[:10]:  # 最多显示 10 个数值列
                mean_val = col.get("mean")
                median_val = col.get("median")
                std_val = col.get("std")
                min_val = col.get("min")
                max_val = col.get("max")
                q25_val = col.get("q25")
                q75_val = col.get("q75")

                numeric_rows += f"""
                <tr>
                    <td>{col.get('name', 'N/A')}</td>
                    <td>{mean_val if mean_val is not None else 'N/A'}</td>
                    <td>{median_val if median_val is not None else 'N/A'}</td>
                    <td>{std_val if std_val is not None else 'N/A'}</td>
                    <td>{min_val if min_val is not None else 'N/A'} / {max_val if max_val is not None else 'N/A'}</td>
                    <td>{q25_val if q25_val is not None else 'N/A'} - {q75_val if q75_val is not None else 'N/A'}</td>
                </tr>
                """

            numeric_stats = f"""
            <h3 style="margin-top: 20px;">数值型列统计</h3>
            <table>
                <thead>
                    <tr>
                        <th>列名</th>
                        <th>均值</th>
                        <th>中位数</th>
                        <th>标准差</th>
                        <th>最小值 / 最大值</th>
                        <th>25% - 75% 分位</th>
                    </tr>
                </thead>
                <tbody>
                    {numeric_rows}
                </tbody>
            </table>
            """

        # 分类型列统计
        categorical_stats = ""
        categorical_cols = [
            col for col in basic_stats.get("columns", [])
            if col.get("type") == "categorical"
        ]

        if categorical_cols:
            cat_rows = ""
            for col in categorical_cols[:10]:  # 最多显示 10 个分类型列
                top_values = col.get("top_values", {})
                top_values_html = ", ".join([f"{k}: {v}" for k, v in list(top_values.items())[:5]])

                cat_rows += f"""
                <tr>
                    <td>{col.get('name', 'N/A')}</td>
                    <td>{col.get('unique_count', 0)}</td>
                    <td>{top_values_html if top_values_html else 'N/A'}</td>
                </tr>
                """

            categorical_stats = f"""
            <h3 style="margin-top: 20px;">分类型列统计</h3>
            <table>
                <thead>
                    <tr>
                        <th>列名</th>
                        <th>唯一值数量</th>
                        <th>高频值 (Top 5)</th>
                    </tr>
                </thead>
                <tbody>
                    {cat_rows}
                </tbody>
            </table>
            """

        # 数据质量信息
        quality_html = ""
        if data_quality:
            quality_html = f"""
            <h3 style="margin-top: 20px;">数据质量</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="value">{data_quality.get('quality_score', 0):.1f}</div>
                    <div class="label">质量评分</div>
                </div>
                <div class="stat-card">
                    <div class="value">{data_quality.get('null_percentage', 0):.1f}%</div>
                    <div class="label">缺失值比例</div>
                </div>
                <div class="stat-card">
                    <div class="value">{data_quality.get('duplicate_percentage', 0):.1f}%</div>
                    <div class="label">重复行比例</div>
                </div>
            </div>
            """

        return f"""
        <div style="margin-bottom: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
            <h3 style="color: #667eea; margin-bottom: 15px;">📊 {sheet_name}</h3>
            <div class="stats-grid" style="margin-bottom: 20px;">
                <div class="stat-card">
                    <div class="value">{basic_stats.get('row_count', 0):,}</div>
                    <div class="label">行数</div>
                </div>
                <div class="stat-card">
                    <div class="value">{basic_stats.get('column_count', 0)}</div>
                    <div class="label">列数</div>
                </div>
            </div>
            {quality_html}
            {numeric_stats}
            {categorical_stats}
        </div>
        """

    @staticmethod
    def _generate_charts_section(charts: List[Dict]) -> str:
        """生成图表部分"""
        if not charts:
            return ""

        charts_html = ""
        for i, chart in enumerate(charts):
            charts_html += f"""
            <div class="section chart-container">
                <h3>{chart.get('title', '图表')}</h3>
                {chart.get('html', '')}
            </div>
            """

        return f"""
        <div class="section">
            <h2>📊 可视化图表</h2>
            {charts_html}
        </div>
        """

    @staticmethod
    def _generate_ai_analysis_section(ai_summary: str) -> str:
        """生成 AI 分析结果部分"""
        if not ai_summary:
            return ""

        # 格式化 AI 分析内容，支持换行和加粗
        formatted_content = ai_summary.replace('\n\n', '</p><p style="margin: 10px 0;">')
        formatted_content = formatted_content.replace('\n', '<br>')
        formatted_content = formatted_content.replace('**', '<strong>').replace('**', '</strong>')

        return f"""
        <div class="section">
            <h2>🤖 AI 分析结果</h2>
            <div class="ai-summary">
                <p style="margin: 0;">{formatted_content}</p>
            </div>
        </div>
        """

    @staticmethod
    def generate_report(
        session_manager: SessionManager,
        session_id: str,
        ai_summary: str = ""
    ) -> str:
        """
        生成完整报告
        :return: report_id
        """
        session = session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # 获取分析结果
        analysis_results = session_manager.get_analysis_result(session_id)
        if not analysis_results:
            raise ValueError("No analysis results found")

        print(f"分析结果类型：{type(analysis_results)}")
        print(f"分析结果 keys: {analysis_results.keys() if isinstance(analysis_results, dict) else 'N/A'}")

        # 获取图表
        charts = session_manager.get_charts(session_id)
        print(f"图表数量：{len(charts)}")

        # 生成 HTML 报告
        report_id = ReportGenerator.generate_html_report(
            session_id=session_id,
            session_name=session.name,
            analysis_results=analysis_results,
            charts=charts,
            ai_summary=ai_summary
        )

        # 更新会话
        session_manager.set_report_id(session_id, report_id)

        return report_id

    @staticmethod
    def get_report_path(report_id: str) -> Path:
        """获取报告文件路径"""
        return REPORTS_DIR / f"{report_id}.html"

    @staticmethod
    def read_report(report_id: str) -> Optional[str]:
        """读取报告内容"""
        report_path = ReportGenerator.get_report_path(report_id)
        if not report_path.exists():
            return None

        with open(report_path, 'r', encoding='utf-8') as f:
            return f.read()
