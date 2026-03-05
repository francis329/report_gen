"""
文件上传处理工具
支持 CSV、Excel 文件上传，自动识别多 sheet 页结构
"""
import uuid
import shutil
from pathlib import Path
from typing import List, Tuple
from datetime import datetime

import pandas as pd

from backend.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE
from backend.models.schemas import FileInfo, SheetInfo
from backend.services.session_manager import SessionManager


class FileHandler:
    """文件处理器"""

    @staticmethod
    def validate_file(filename: str, file_size: int) -> Tuple[bool, str]:
        """验证文件"""
        # 检查文件扩展名
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"不支持的文件类型：{ext}，支持的类型：{ALLOWED_EXTENSIONS}"

        # 检查文件大小
        if file_size > MAX_FILE_SIZE:
            return False, f"文件大小超过限制（{MAX_FILE_SIZE / 1024 / 1024}MB）"

        return True, ""

    @staticmethod
    def get_sheet_info(df: pd.DataFrame, sheet_name: str) -> SheetInfo:
        """获取 Sheet 页信息"""
        return SheetInfo(
            name=sheet_name,
            columns=list(df.columns),
            row_count=len(df)
        )

    @staticmethod
    def read_excel_sheets(file_path: Path) -> Tuple[List[SheetInfo], dict]:
        """
        读取 Excel 文件的所有 sheet 页
        返回：(sheet 信息列表，{sheet_name: dataframe})
        """
        # 先读取所有 sheet 名
        excel_file = pd.ExcelFile(file_path)
        sheet_names = excel_file.sheet_names

        sheets_data = {}
        sheet_infos = []

        try:
            for sheet_name in sheet_names:
                try:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                    sheets_data[sheet_name] = df
                    sheet_infos.append(FileHandler.get_sheet_info(df, sheet_name))
                except Exception as e:
                    # 如果某个 sheet 读取失败，继续处理其他 sheet
                    print(f"读取 sheet '{sheet_name}' 失败：{e}")
        finally:
            # 关闭 ExcelFile 释放文件句柄
            excel_file.close()

        return sheet_infos, sheets_data

    @staticmethod
    def read_csv_file(file_path: Path) -> Tuple[List[SheetInfo], dict]:
        """读取 CSV 文件"""
        try:
            # 尝试不同的编码
            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                df = pd.read_csv(file_path, encoding='utf-8-sig')

            sheet_info = SheetInfo(
                name="Sheet1",
                columns=list(df.columns),
                row_count=len(df)
            )

            return [sheet_info], {"Sheet1": df}
        except Exception as e:
            raise ValueError(f"读取 CSV 文件失败：{e}")

    @staticmethod
    def process_uploaded_file(
        session_manager: SessionManager,
        session_id: str,
        filename: str,
        file_content: bytes
    ) -> FileInfo:
        """
        处理上传的文件
        1. 验证文件
        2. 保存到会话目录
        3. 读取数据
        4. 存储到 session_manager
        """
        # 验证文件
        is_valid, error_msg = FileHandler.validate_file(filename, len(file_content))
        if not is_valid:
            raise ValueError(error_msg)

        # 生成文件 ID
        file_id = str(uuid.uuid4())[:8]

        # 获取会话目录
        session_dir = session_manager.get_session_dir(session_id)

        # 保存文件
        file_path = session_dir / file_id
        with open(file_path, 'wb') as f:
            f.write(file_content)

        # 读取文件数据
        ext = Path(filename).suffix.lower()
        try:
            if ext in ['.xlsx', '.xls']:
                sheet_infos, sheets_data = FileHandler.read_excel_sheets(file_path)
            else:  # .csv
                sheet_infos, sheets_data = FileHandler.read_csv_file(file_path)

            if not sheet_infos:
                raise ValueError("文件中没有有效的数据")

            # 创建文件信息
            file_info = FileInfo(
                id=file_id,
                filename=filename,
                sheets=sheet_infos,
                upload_time=datetime.now()
            )

            # 添加到会话
            session_manager.add_file(session_id, file_info)

            # 存储数据
            session_manager.store_file_data(session_id, file_id, sheets_data)

            # 不再提前删除引用，直接返回 file_info
            # session_manager._data_store 中保存着 sheets_data 的引用
            # 不会被垃圾回收

            return file_info

        except Exception as e:
            # 清理已保存的文件
            if file_path.exists():
                file_path.unlink()
            raise e

    @staticmethod
    def get_all_sheets_info(session_manager: SessionManager, session_id: str) -> list:
        """获取会话中所有文件的所有 sheet 信息"""
        all_sheets = []
        files = session_manager.get_files(session_id)

        for file_info in files:
            for sheet in file_info.sheets:
                all_sheets.append({
                    "file_id": file_info.id,
                    "file_name": file_info.filename,
                    "sheet_name": sheet.name,
                    "columns": sheet.columns,
                    "row_count": sheet.row_count
                })

        return all_sheets
