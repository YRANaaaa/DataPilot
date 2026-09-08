from fastapi import APIRouter

from datapilot.schemas.chart import CreateChartRequest
from datapilot.schemas.common import ApiResponse
from datapilot.services.chart_service import create_chart_tool
from datapilot.services.dataset_service import (
    get_dataset_path,
    read_csv_file,
)


router = APIRouter(
    prefix="/datasets/{dataset_id}/analysis",
    tags=["Charts"],
)


@router.post("/chart",response_model=ApiResponse)
def create_chart(dataset_id: str,request: CreateChartRequest):
    # 1. 查找数据集
    file_path = get_dataset_path(dataset_id)

    # 2. 读取CSV
    df = read_csv_file(file_path)

    # 3. 调用图表工具
    result = create_chart_tool(df=df,request=request)

    # 4. 返回结果
    return ApiResponse(
        code=200,
        message="图表生成成功",
        data={
            "dataset_id": file_path.stem,
            **result
        }
    )