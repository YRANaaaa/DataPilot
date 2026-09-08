import logging
import uuid
from pathlib import Path

import pandas as pd
from fastapi import HTTPException

from datapilot.core.config import UPLOAD_DIR


def get_dataset_path(dataset_id: str) -> Path:
    """验证数据集ID并返回对应的CSV路径。"""

    try:
        valid_dataset_id = str(uuid.UUID(dataset_id))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="dataset_id格式错误",
        )

    file_path = UPLOAD_DIR / f"{valid_dataset_id}.csv"

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="数据集不存在",
        )

    return file_path


def read_csv_file(file_path: Path) -> pd.DataFrame:
    """读取已经保存的数据集文件。"""

    try:
        return pd.read_csv(file_path)
    except Exception as error:
        logging.error(f"读取csv文件失败: {error}")
        raise HTTPException(
            status_code=500,
            detail="CSV内容无法读取",
        )