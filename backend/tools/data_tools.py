"""
数据分析工具
提供数据分析相关的工具实现
"""
import time
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple

from backend.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from backend.services.session_manager import SessionManager


# ==================== 内部数据分析函数 ====================

def _get_basic_statistics(df: pd.DataFrame) -> Dict[str, Any]:
    """获取基础统计信息"""
    stats = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": [],
    }

    for col in df.columns:
        series = df[col]
        col_stats = {
            "name": col,
            "dtype": str(series.dtype),
            "non_null_count": int(series.notna().sum()),
            "null_count": int(series.isna().sum()),
            "null_percentage": float(series.isna().mean() * 100),
            "unique_count": int(series.nunique()),
        }

        # 数值型列的统计
        if pd.api.types.is_numeric_dtype(series):
            col_stats["type"] = "numeric"
            describe = series.describe()
            col_stats.update({
                "min": float(describe["min"]) if pd.notna(describe["min"]) else None,
                "max": float(describe["max"]) if pd.notna(describe["max"]) else None,
                "mean": float(describe["mean"]) if pd.notna(describe["mean"]) else None,
                "median": float(describe["50%"]) if pd.notna(describe["50%"]) else None,
                "std": float(describe["std"]) if pd.notna(describe["std"]) else None,
                "q25": float(describe["25%"]) if pd.notna(describe["25%"]) else None,
                "q75": float(describe["75%"]) if pd.notna(describe["75%"]) else None,
            })
        else:
            col_stats["type"] = "categorical"
            # 获取出现频率最高的值
            if series.notna().any():
                top_values = series.value_counts().head(5).to_dict()
                col_stats["top_values"] = {str(k): int(v) for k, v in top_values.items()}
            else:
                col_stats["top_values"] = {}

        stats["columns"].append(col_stats)

    return stats


def _get_data_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """获取数据质量分析"""
    total_cells = df.size
    null_cells = df.isna().sum().sum()
    duplicate_rows = df.duplicated().sum()

    quality = {
        "total_cells": int(total_cells),
        "null_cells": int(null_cells),
        "null_percentage": float(null_cells / total_cells * 100) if total_cells > 0 else 0,
        "duplicate_rows": int(duplicate_rows),
        "duplicate_percentage": float(duplicate_rows / len(df) * 100) if len(df) > 0 else 0,
        "quality_score": 100 - float(null_cells / total_cells * 100) if total_cells > 0 else 0,
    }

    # 检测异常值（仅数值型）
    outliers = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outlier_count = ((df[col] < lower_bound) | (df[col] > upper_bound)).sum()
        if outlier_count > 0:
            outliers[col] = int(outlier_count)

    quality["outliers"] = outliers

    return quality


def _get_correlation_matrix(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """获取相关性矩阵"""
    numeric_df = df.select_dtypes(include=[np.number])
    if len(numeric_df.columns) < 2:
        return None

    corr_matrix = numeric_df.corr()
    return {
        "columns": list(corr_matrix.columns),
        "data": corr_matrix.values.tolist(),
    }


def _detect_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """检测列的类型"""
    types = {}
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            types[col] = "datetime"
        elif pd.api.types.is_numeric_dtype(df[col]):
            types[col] = "discrete_numeric" if df[col].nunique() < 10 else "continuous_numeric"
        else:
            types[col] = "categorical"
    return types


def _analyze_sheet(
    df: pd.DataFrame,
    sheet_name: str,
    include_correlation: bool = True
) -> Dict[str, Any]:
    """分析单个 sheet 页数据"""
    result = {
        "sheet_name": sheet_name,
        "basic_stats": _get_basic_statistics(df),
        "data_quality": _get_data_quality(df),
        "column_types": _detect_column_types(df),
    }

    if include_correlation:
        result["correlation"] = _get_correlation_matrix(df)

    return result


def _analyze_multiple_sheets(
    sheets_data: Dict[str, pd.DataFrame],
    merge_for_analysis: bool = False
) -> Dict[str, Any]:
    """
    分析多个 sheet 页数据
    :param sheets_data: {sheet_name: dataframe}
    :param merge_for_analysis: 是否合并后分析
    """
    if not sheets_data:
        return {"error": "没有数据可分析"}

    if merge_for_analysis and len(sheets_data) > 1:
        # 尝试合并所有 sheet（要求结构相同）
        try:
            merged_df = pd.concat(sheets_data.values(), ignore_index=True)
            merged_analysis = _analyze_sheet(merged_df, "Merged")
            merged_analysis["is_merged"] = True
            merged_analysis["source_sheets"] = list(sheets_data.keys())

            return {
                "merged_analysis": merged_analysis,
                "is_merged": True
            }
        except Exception as e:
            return {"error": f"无法合并 sheet 页：{e}"}

    # 分开分析每个 sheet
    return {
        "individual_analyses": {
            name: _analyze_sheet(df, name) for name, df in sheets_data.items()
        },
        "is_merged": False
    }


def _get_column_distribution(df: pd.DataFrame, column: str, top_n: int = 10) -> Dict[str, Any]:
    """获取某一列的分布情况"""
    if column not in df.columns:
        return {"error": f"列 '{column}' 不存在"}

    series = df[column]
    if pd.api.types.is_numeric_dtype(series):
        # 数值型：返回分箱统计
        values = series.dropna()
        if len(values) == 0:
            return {"error": "该列没有有效数据"}

        bins = min(top_n, int(np.sqrt(len(values))))
        bins = max(2, bins)

        hist, bin_edges = np.histogram(values, bins=bins)
        return {
            "type": "histogram",
            "column": column,
            "bins": [(f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}", int(hist[i]))
                    for i in range(len(hist))],
        }
    else:
        # 分类型：返回值频次
        value_counts = series.value_counts().head(top_n)
        return {
            "type": "value_counts",
            "column": column,
            "values": {str(k): int(v) for k, v in value_counts.items()},
        }


def _get_column_statistics(df: pd.DataFrame, column: str) -> Tuple[bool, Dict[str, Any], str]:
    """
    获取某列的统计信息
    :return: (成功标志，统计数据，错误消息)
    """
    if column not in df.columns:
        return False, {}, f"列 '{column}' 不存在"

    col = df[column]
    stats = {
        "column_name": column,
        "dtype": str(col.dtype),
        "non_null_count": int(col.notna().sum()),
        "null_count": int(col.isna().sum()),
        "unique_count": int(col.nunique())
    }

    if pd.api.types.is_numeric_dtype(col):
        stats["type"] = "numeric"
        describe = col.describe()
        stats.update({
            "min": float(describe["min"]) if pd.notna(describe["min"]) else None,
            "max": float(describe["max"]) if pd.notna(describe["max"]) else None,
            "mean": float(describe["mean"]) if pd.notna(describe["mean"]) else None,
            "median": float(describe["50%"]) if pd.notna(describe["50%"]) else None,
            "std": float(describe["std"]) if pd.notna(describe["std"]) else None,
        })
    else:
        stats["type"] = "categorical"
        top_values = col.value_counts().head(5).to_dict()
        stats["top_values"] = {str(k): int(v) for k, v in top_values.items()}

    return True, stats, ""


# ==================== 工具类 ====================

class AnalyzeDataTool(BaseTool):
    """分析数据工具 - 对上传的数据文件进行分析"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_data",
            description="分析数据文件，返回基础统计信息和数据质量评估。"
                       "当用户上传数据文件后需要首先调用此工具进行分析。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID（此参数由系统自动注入，无需指定）",
                    required=False
                ),
                ToolParameter(
                    name="merge_sheets",
                    type="boolean",
                    description="是否合并多个 sheet 进行分析。当多个 sheet 结构相似且需要整体分析时设为 true",
                    required=False,
                    default=False
                )
            ]
        )

    async def _execute_impl(self, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id")
        merge_sheets = kwargs.get("merge_sheets", False)

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")

        # 获取文件数据
        start_time = time.time()
        file_data = self._get_file_data(session_id)
        get_file_time = time.time() - start_time
        print(f"[PERF] analyze_data - 获取文件数据：{get_file_time:.3f}s")

        # 调试日志：详细输出文件数据获取情况
        files = self.session_manager.get_files(session_id)
        print(f"[DEBUG] analyze_data - session_id: {session_id}")
        print(f"[DEBUG] analyze_data - 文件数量：{len(files)}")
        for f in files:
            print(f"[DEBUG] analyze_data - 文件：{f.filename}, ID: {f.id}")
            data = self.session_manager.get_file_data(session_id, f.id)
            print(f"[DEBUG] analyze_data - 文件数据获取结果：{'成功' if data else '失败'}")
            if data:
                print(f"[DEBUG] analyze_data - Sheet 数量：{len(data)}")

        if not file_data:
            # 更详细的错误信息
            if len(files) == 0:
                return ToolResult(success=False, error="未找到数据文件，请先上传文件")
            else:
                return ToolResult(success=False, error="数据文件已上传但无法读取，请检查文件格式")

        # 执行分析
        start_time = time.time()
        result = _analyze_multiple_sheets(file_data, merge_for_analysis=merge_sheets)
        analyze_time = time.time() - start_time
        print(f"[PERF] analyze_data - 执行分析：{analyze_time:.3f}s")

        # 存储分析结果
        start_time = time.time()
        self.session_manager.store_analysis_result(session_id, result)
        store_time = time.time() - start_time
        print(f"[PERF] analyze_data - 存储结果：{store_time:.3f}s")

        total_time = get_file_time + analyze_time + store_time
        print(f"[PERF] analyze_data - 总耗时：{total_time:.3f}s")

        # 生成摘要消息
        if merge_sheets and result.get("merged_analysis"):
            stats = result["merged_analysis"].get("basic_stats", {})
            msg = f"已完成合并分析：{stats.get('row_count', 0)}行 x {stats.get('column_count', 0)}列"
        else:
            individual = result.get("individual_analyses", {})
            msg = f"已完成分析，共 {len(individual)} 个数据表"

        return ToolResult(success=True, data=result, message=msg)

    def _get_file_data(self, session_id: str) -> Optional[Dict[str, pd.DataFrame]]:
        """获取会话的文件数据"""
        files = self.session_manager.get_files(session_id)
        for f in files:
            file_data = self.session_manager.get_file_data(session_id, f.id)
            if file_data:
                return file_data
        return None


class GetColumnDistributionTool(BaseTool):
    """获取列分布工具 - 分析某一列的数据分布"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_column_distribution",
            description="获取某一列的数据分布情况，包括频次统计或分箱统计。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID（此参数由系统自动注入，无需指定）",
                    required=False
                ),
                ToolParameter(
                    name="column_name",
                    type="string",
                    description="要分析的列名"
                ),
                ToolParameter(
                    name="top_n",
                    type="number",
                    description="返回前 N 个值（分类型）或分箱数（数值型），默认 10",
                    required=False,
                    default=10
                )
            ]
        )

    async def _execute_impl(self, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id")
        column_name = kwargs.get("column_name")
        top_n = kwargs.get("top_n", 10)

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")
        if not column_name:
            return ToolResult(success=False, error="缺少 column_name 参数")

        # 获取文件数据
        file_data = self._get_file_data(session_id)
        if not file_data:
            return ToolResult(success=False, error="未找到数据文件")

        # 取第一个 sheet 的数据
        df = list(file_data.values())[0]

        if column_name not in df.columns:
            available = ', '.join(df.columns[:10])
            return ToolResult(
                success=False,
                error=f"列 '{column_name}' 不存在。可用列：{available}"
            )

        distribution = _get_column_distribution(df, column_name, top_n)

        return ToolResult(success=True, data=distribution,
                         message=f"已获取列 '{column_name}' 的分布情况")

    def _get_file_data(self, session_id: str) -> Optional[Dict[str, pd.DataFrame]]:
        """获取会话的文件数据"""
        files = self.session_manager.get_files(session_id)
        for f in files:
            file_data = self.session_manager.get_file_data(session_id, f.id)
            if file_data:
                return file_data
        return None


class GetColumnStatisticsTool(BaseTool):
    """获取列统计工具 - 获取某列的详细统计信息"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_column_statistics",
            description="获取某列的详细统计信息，包括均值、中位数、标准差等（数值型）"
                       "或唯一值数量、高频值等（分类型）。",
            parameters=[
                ToolParameter(
                    name="session_id",
                    type="string",
                    description="会话 ID（此参数由系统自动注入，无需指定）",
                    required=False
                ),
                ToolParameter(
                    name="column_name",
                    type="string",
                    description="要统计的列名"
                )
            ]
        )

    async def _execute_impl(self, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id")
        column_name = kwargs.get("column_name")

        if not session_id:
            return ToolResult(success=False, error="缺少 session_id 参数")
        if not column_name:
            return ToolResult(success=False, error="缺少 column_name 参数")

        # 获取文件数据
        file_data = self._get_file_data(session_id)
        if not file_data:
            return ToolResult(success=False, error="未找到数据文件")

        df = list(file_data.values())[0]

        success, stats, error = _get_column_statistics(df, column_name)
        if not success:
            return ToolResult(success=False, error=error)

        return ToolResult(success=True, data=stats,
                         message=f"已获取列 '{column_name}' 的统计信息")

    def _get_file_data(self, session_id: str) -> Optional[Dict[str, pd.DataFrame]]:
        """获取会话的文件数据"""
        files = self.session_manager.get_files(session_id)
        for f in files:
            file_data = self.session_manager.get_file_data(session_id, f.id)
            if file_data:
                return file_data
        return None
