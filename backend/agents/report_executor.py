"""
报告执行器
根据 ReportPlan 逐章执行分析，生成图表和数据
"""
import uuid
from typing import Dict, List, Any, Optional, Callable
import pandas as pd

from backend.models.report import (
    ReportPlan, ChapterPlan, ChapterResult, ChartSpec, ChartDataQuery
)
from backend.services.session_manager import SessionManager
from backend.utils.chart_builder import ChartBuilder


class ReportExecutor:
    """
    报告执行器

    核心职责：
    1. 根据规划逐章执行分析
    2. 调用数据工具获取章节数据
    3. 调用图表工具生成可视化
    4. 支持降级（某章失败不影响其他章节）
    """

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    async def execute(
        self,
        plan: ReportPlan,
        session_id: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        执行报告生成

        :param plan: 报告规划
        :param session_id: 会话 ID
        :param progress_callback: 进度回调函数 async def callback(progress: Dict)
        :return: 执行结果
        """
        print(f"[REPORT_EXECUTOR] 开始执行报告生成，session_id: {session_id}")
        print(f"[REPORT_EXECUTOR] 报告标题：{plan.title}, 共 {len(plan.chapters)} 个章节")

        chapters_result = []
        total_chapters = len(plan.chapters)
        success_count = 0
        fail_count = 0

        for i, chapter in enumerate(plan.chapters):
            print(f"[REPORT_EXECUTOR] 执行章节 {i+1}/{total_chapters}: {chapter.title}")
            try:
                # 进度回调
                progress = int((i / total_chapters) * 100) if total_chapters > 0 else 0
                if progress_callback:
                    await progress_callback({
                        "stage": "executing",
                        "chapter": chapter.title,
                        "progress": 25 + int(progress * 0.6),  # 25-85% 区间
                        "total": total_chapters,
                        "current": i + 1
                    })

                # 执行章节分析
                chapter_data = await self._execute_chapter(chapter, session_id)

                # 存储章节结果
                self.session_manager.store_chapter_result(
                    session_id, chapter.id, chapter_data
                )

                chapters_result.append({
                    "chapter": chapter,
                    "data": chapter_data,
                    "success": True
                })
                success_count += 1
                print(f"[REPORT_EXECUTOR] 章节 {i+1}/{total_chapters} 执行成功")

            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                print(f"[REPORT_EXECUTOR] 章节 {i+1}/{total_chapters} 执行失败：{e}")
                print(f"[REPORT_EXECUTOR] 错误详情：{error_detail}")
                fail_count += 1
                # 降级：记录失败但不中断
                chapter_result = ChapterResult(
                    chapter_id=chapter.id,
                    title=chapter.title,
                    description=chapter.description,
                    analysis_type="overview",
                    success=False,
                    error=str(e)
                )
                self.session_manager.store_chapter_result(
                    session_id, chapter.id, chapter_result
                )
                chapters_result.append({
                    "chapter": chapter,
                    "error": str(e),
                    "success": False
                })

        # 完成
        print(f"[REPORT_EXECUTOR] 报告执行完成，成功：{success_count} 章，失败：{fail_count} 章")
        if progress_callback:
            await progress_callback({
                "stage": "complete",
                "progress": 100
            })

        return {
            "plan": plan,
            "chapters": chapters_result,
            "session_id": session_id
        }

    async def _execute_chapter(
        self,
        chapter: ChapterPlan,
        session_id: str
    ) -> ChapterResult:
        """
        执行单个章节的分析

        :param chapter: 章节规划
        :param session_id: 会话 ID
        :return: 章节结果
        """
        print(f"[REPORT_EXECUTOR] _execute_chapter: 开始执行章节 '{chapter.title}'")
        print(f"[REPORT_EXECUTOR] _execute_chapter: 章节 ID: {chapter.id}, 分析类型指导：{chapter.analysis_guidance[:50] if chapter.analysis_guidance else '无'}")

        # 获取数据
        df = self._get_session_dataframe(session_id)
        print(f"[REPORT_EXECUTOR] _execute_chapter: 获取到 DataFrame: {len(df)}行 x {len(df.columns)}列")

        # 根据 analysis_guidance 推断分析类型
        analysis_type = self._infer_analysis_type(chapter.analysis_guidance, chapter.dimensions)
        print(f"[REPORT_EXECUTOR] _execute_chapter: 推断分析类型为 '{analysis_type}'")

        result = ChapterResult(
            chapter_id=chapter.id,
            title=chapter.title,
            description=chapter.description,
            analysis_type=analysis_type,
            data={},
            insights=[],
            chart_spec=None
        )

        # 根据分析类型执行具体逻辑
        if analysis_type == "overview":
            result.data = self._get_overview_stats(df)
            result.insights = self._generate_overview_insights(result.data)

        elif analysis_type == "ranking":
            result.data = self._get_ranking_data(df, chapter.dimensions, chapter.analysis_guidance)
            result.chart_spec = self._create_chart_spec("bar", result.data, chapter)
            self._store_chart_query(session_id, chapter, result)

        elif analysis_type == "trend":
            result.data = self._get_trend_data(df, chapter.dimensions, chapter.analysis_guidance)
            result.chart_spec = self._create_chart_spec("line", result.data, chapter)
            self._store_chart_query(session_id, chapter, result)

        elif analysis_type == "distribution":
            result.data = self._get_distribution_data(df, chapter.dimensions, chapter.analysis_guidance)
            result.chart_spec = self._create_chart_spec("pie", result.data, chapter)
            self._store_chart_query(session_id, chapter, result)

        elif analysis_type == "comparison":
            result.data = self._get_comparison_data(df, chapter.dimensions, chapter.analysis_guidance)
            result.chart_spec = self._create_chart_spec("bar", result.data, chapter)
            self._store_chart_query(session_id, chapter, result)

        elif analysis_type == "correlation":
            result.data = self._get_correlation_data(df, chapter.dimensions)
            result.chart_spec = self._create_chart_spec("heatmap", result.data, chapter)
            self._store_chart_query(session_id, chapter, result)

        else:
            # 默认按 ranking 处理
            result.data = self._get_ranking_data(df, chapter.dimensions, chapter.analysis_guidance)
            result.chart_spec = self._create_chart_spec("bar", result.data, chapter)
            self._store_chart_query(session_id, chapter, result)

        # 生成章节内容摘要
        result.content = self._generate_chapter_content(result)

        return result

    def _get_session_dataframe(self, session_id: str) -> pd.DataFrame:
        """获取会话的 DataFrame"""
        print(f"[REPORT_EXECUTOR] _get_session_dataframe: 开始获取文件列表，session_id: {session_id}")
        files = self.session_manager.get_files(session_id)
        print(f"[REPORT_EXECUTOR] _get_session_dataframe: 获取到 {len(files)} 个文件")
        if not files:
            print(f"[REPORT_EXECUTOR] _get_session_dataframe: 错误 - 会话中没有数据文件")
            raise ValueError("会话中没有数据文件")

        # 遍历所有文件，找到第一个有数据的文件（与 analyze_data 工具保持一致的逻辑）
        for f in files:
            print(f"[REPORT_EXECUTOR] _get_session_dataframe: 尝试获取文件 ID: {f.id}, 文件名：{f.filename if hasattr(f, 'filename') else 'N/A'}")
            file_data = self.session_manager.get_file_data(session_id, f.id)
            print(f"[REPORT_EXECUTOR] _get_session_dataframe: 文件数据获取结果：{'成功' if file_data else '失败'}")
            if file_data:
                print(f"[REPORT_EXECUTOR] _get_session_dataframe: Sheet 数量：{len(file_data)}")
                df = list(file_data.values())[0]
                print(f"[REPORT_EXECUTOR] _get_session_dataframe: 返回 DataFrame: {len(df)}行 x {len(df.columns)}列")
                return df

        # 所有文件都无法获取数据，尝试从文件系统重新加载
        print(f"[REPORT_EXECUTOR] _get_session_dataframe: 内存中无数据，尝试从文件系统重新加载...")
        raise ValueError("无法获取数据：文件已上传但数据未加载到内存中，请尝试重新上传文件或刷新会话")

    def _infer_analysis_type(self, guidance: str, dimensions: List[str]) -> str:
        """根据分析指导推断分析类型"""
        guidance_lower = guidance.lower()

        if any(kw in guidance_lower for kw in ["概览", "总览", "概况", "overview"]):
            return "overview"
        elif any(kw in guidance_lower for kw in ["top", "排行", "排序", "最高", "最低", "前", "后"]):
            return "ranking"
        elif any(kw in guidance_lower for kw in ["趋势", "变化", "时间", "每日", "每月", "年份", "同比", "环比"]):
            return "trend"
        elif any(kw in guidance_lower for kw in ["分布", "占比", "比例", "份额", "构成"]):
            return "distribution"
        elif any(kw in guidance_lower for kw in ["对比", "比较", "vs", "差异"]):
            return "comparison"
        elif any(kw in guidance_lower for kw in ["相关", "关联"]):
            return "correlation"
        elif any(kw in guidance_lower for kw in ["建议", "结论", "洞察", "总结"]):
            return "insight"
        else:
            # 默认根据字段类型推断
            if len(dimensions) > 0:
                return "ranking"  # 默认按排名分析
            return "overview"

    def _get_overview_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        """获取概览统计"""
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        return {
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": df.columns.tolist(),
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "null_counts": df.isnull().sum().to_dict(),
            "basic_stats": {
                col: {
                    "mean": float(df[col].mean()) if not df[col].isnull().all() else None,
                    "std": float(df[col].std()) if not df[col].isnull().all() else None,
                    "min": float(df[col].min()) if not df[col].isnull().all() else None,
                    "max": float(df[col].max()) if not df[col].isnull().all() else None,
                }
                for col in numeric_cols[:5]  # 最多取前 5 个数值列
            }
        }

    def _generate_overview_insights(self, data: Dict) -> List[str]:
        """生成概览洞察"""
        insights = []

        row_count = data.get("row_count", 0)
        if row_count > 10000:
            insights.append(f"数据量较大，包含 {row_count:,} 条记录")
        elif row_count > 1000:
            insights.append(f"数据包含 {row_count:,} 条记录")

        column_count = data.get("column_count", 0)
        if column_count > 20:
            insights.append(f"数据维度丰富，包含 {column_count} 个字段")

        null_counts = data.get("null_counts", {})
        total_nulls = sum(null_counts.values())
        if total_nulls > 0:
            null_pct = (total_nulls / (row_count * column_count)) * 100 if row_count * column_count > 0 else 0
            if null_pct > 10:
                insights.append(f"数据缺失值比例为 {null_pct:.1f}%，建议关注数据质量")

        return insights

    def _get_ranking_data(
        self,
        df: pd.DataFrame,
        dimensions: List[str],
        guidance: str
    ) -> Dict[str, Any]:
        """获取排名数据"""
        if len(dimensions) >= 1:
            col = dimensions[0]
            if col in df.columns:
                if df[col].dtype in ["object", "category"]:
                    # 分类型：按频次排名
                    ranking = df[col].value_counts().head(10).to_dict()
                    return {
                        "ranking": ranking,
                        "dimension": col,
                        "type": "categorical"
                    }
                else:
                    # 数值型：取 TOP10
                    sorted_df = df.nlargest(10, col)
                    # 修复：使用 iterrows 或直接使用 values 来获取键值对
                    ranking_data = sorted_df[[col]].drop_duplicates().head(10)
                    ranking = {}
                    for idx, row in ranking_data.iterrows():
                        ranking[str(row[col])] = idx
                    return {
                        "ranking": ranking,
                        "dimension": col,
                        "type": "numeric"
                    }
        return {"ranking": {}, "dimension": None, "type": "unknown"}

    def _get_trend_data(
        self,
        df: pd.DataFrame,
        dimensions: List[str],
        guidance: str
    ) -> Dict[str, Any]:
        """获取趋势数据"""
        # 尝试找时间列
        time_col = None
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                time_col = col
                break

        # 如果没找到时间列，用第一个维度
        if not time_col and len(dimensions) >= 1:
            time_col = dimensions[0] if dimensions[0] in df.columns else None

        if time_col and time_col in df.columns:
            # 按时间分组计数
            trend_data = df.groupby(time_col).size().to_dict()
            # 转换时间为字符串格式
            trend_data = {str(k): int(v) for k, v in trend_data.items()}
            return {"trend": trend_data, "time_column": time_col}

        return {"trend": {}, "time_column": None}

    def _get_distribution_data(
        self,
        df: pd.DataFrame,
        dimensions: List[str],
        guidance: str
    ) -> Dict[str, Any]:
        """获取分布数据"""
        if len(dimensions) >= 1:
            col = dimensions[0]
            if col in df.columns:
                dist = df[col].value_counts().to_dict()
                return {
                    "distribution": {str(k): int(v) for k, v in dist.items()},
                    "dimension": col,
                    "total": len(df)
                }
        return {"distribution": {}, "dimension": None, "total": 0}

    def _get_comparison_data(
        self,
        df: pd.DataFrame,
        dimensions: List[str],
        guidance: str
    ) -> Dict[str, Any]:
        """获取对比数据"""
        if len(dimensions) >= 1:
            col = dimensions[0]
            if col in df.columns:
                if df[col].dtype in ["object", "category"]:
                    # 分类型：统计信息
                    stats = df[col].value_counts().to_dict()
                    return {"comparison": stats, "dimension": col, "type": "categorical"}
                else:
                    # 数值型：描述统计
                    stats = df[col].describe().to_dict()
                    return {"comparison": stats, "dimension": col, "type": "numeric"}
        return {"comparison": {}, "dimension": None, "type": "unknown"}

    def _get_correlation_data(
        self,
        df: pd.DataFrame,
        dimensions: List[str]
    ) -> Dict[str, Any]:
        """获取相关性数据"""
        numeric_df = df.select_dtypes(include=["number"])
        if len(numeric_df.columns) >= 2:
            corr_matrix = numeric_df.corr()
            # 转换为列表格式用于热力图
            values = []
            for i, row in enumerate(corr_matrix.values):
                for j, val in enumerate(row):
                    values.append([i, j, round(val, 3)])

            return {
                "correlation": corr_matrix.to_dict(),
                "columns": numeric_df.columns.tolist(),
                "heatmap_values": values
            }
        return {"correlation": {}, "columns": [], "heatmap_values": []}

    def _create_chart_spec(
        self,
        chart_type: str,
        data: Dict,
        chapter: ChapterPlan
    ) -> Optional[Dict[str, Any]]:
        """创建图表规格"""
        try:
            # 准备图表数据
            chart_data = {}
            title = f"{chapter.title} - 可视化"

            if chart_type == "bar":
                if "ranking" in data:
                    ranking = data["ranking"]
                    chart_data = {"x": list(ranking.keys()), "y": list(ranking.values())}
                elif "comparison" in data and data.get("type") == "categorical":
                    comparison = data["comparison"]
                    chart_data = {"x": list(comparison.keys()), "y": list(comparison.values())}

            elif chart_type == "line":
                if "trend" in data:
                    trend = data["trend"]
                    chart_data = {"x": list(trend.keys()), "y": list(trend.values())}

            elif chart_type == "pie":
                if "distribution" in data:
                    dist = data["distribution"]
                    chart_data = {"values": dist}

            elif chart_type == "heatmap":
                if "heatmap_values" in data:
                    chart_data = {
                        "x": data["columns"],
                        "y": data["columns"],
                        "values": data["heatmap_values"]
                    }

            if chart_data:
                return {
                    "type": chart_type,
                    "data": chart_data,
                    "title": title
                }
        except Exception as e:
            print(f"创建图表规格失败：{e}")

        return None

    def _store_chart_query(
        self,
        session_id: str,
        chapter: ChapterPlan,
        result: ChapterResult
    ) -> None:
        """存储图表数据查询条件（用于点击查看原始数据）"""
        if not result.chart_spec:
            return

        chart_id = f"chart-{chapter.id}"

        # 确定用于筛选的字段
        element_key_field = None
        if result.data.get("dimension"):
            element_key_field = result.data["dimension"]
        elif chapter.dimensions:
            element_key_field = chapter.dimensions[0]

        query = ChartDataQuery(
            chart_id=chart_id,
            chapter_id=chapter.id,
            dimensions=chapter.dimensions,
            query_type=result.analysis_type,
            data=result.data,
            element_key_field=element_key_field
        )

        self.session_manager.store_chart_data_query(session_id, chart_id, query)

    def _generate_chapter_content(self, result: ChapterResult) -> str:
        """生成章节内容摘要（用于报告展示）"""
        content_parts = []

        # 数据摘要
        if result.data:
            if result.analysis_type == "overview":
                row_count = result.data.get("row_count", 0)
                col_count = result.data.get("column_count", 0)
                content_parts.append(f"数据包含 {row_count:,} 行，{col_count} 列")

            elif result.analysis_type == "ranking":
                ranking = result.data.get("ranking", {})
                if ranking:
                    top_items = list(ranking.items())[:3]
                    content_parts.append(f"TOP3: {', '.join([f'{k}' for k, v in top_items])}")

            elif result.analysis_type == "distribution":
                dist = result.data.get("distribution", {})
                if dist:
                    total = result.data.get("total", 0)
                    top_item = list(dist.items())[0] if dist else (None, 0)
                    pct = (top_item[1] / total * 100) if total > 0 else 0
                    content_parts.append(f"占比最高：{top_item[0]} ({pct:.1f}%)")

        # 洞察
        if result.insights:
            content_parts.extend(result.insights)

        return " | ".join(content_parts) if content_parts else "分析完成"
