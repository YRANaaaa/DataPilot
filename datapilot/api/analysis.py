from fastapi import APIRouter

from datapilot.schemas.analysis import (
    FilterRowsRequest,
    GroupAggregateRequest,
    GroupCountRequest,
    SortRowsRequest,
)
from datapilot.schemas.common import ApiResponse
from datapilot.services.analysis_service import (
    filter_rows_tool,
    group_aggregate_tool,
    group_count_tool,
    sort_rows_tool,
)
from datapilot.services.dataset_service import (
    get_dataset_path,
    read_csv_file,
)


router = APIRouter(
    prefix="/datasets/{dataset_id}/analysis",
    tags=["Analysis"],
)

# 分组计数接口
@router.post("group-count",response_model=ApiResponse)
def group_count(dataset_id: str,request: GroupCountRequest):
    # 1. 查找数据集
    file_path = get_dataset_path(dataset_id)

    # 2. 读取数据
    df = read_csv_file(file_path)

    # 3. 调用分析工具
    result = group_count_tool(df=df,request=request)

    # 4. 返回结果
    return ApiResponse(code=200,message="分组计数完成",
        data={"dataset_id": file_path.stem,
            **result
        }
    )

# 分组聚合接口
@router.post("group-aggregate",response_model=ApiResponse)
def group_aggregate(dataset_id: str,request: GroupAggregateRequest):
    # 1. 获取数据集路径
    file_path = get_dataset_path(dataset_id)

    # 2. 读取CSV
    df = read_csv_file(file_path)

    # 3. 调用Pandas工具
    result = group_aggregate_tool(
        df=df,
        request=request
    )

    # 4. 返回响应
    return ApiResponse(
        code=200,
        message="分组聚合完成",
        data={"dataset_id": file_path.stem,
            **result
        }
    )

# 条件筛选接口
@router.post("filter",response_model=ApiResponse)
def filter_rows(dataset_id: str,request: FilterRowsRequest):
    # 1. 查找数据集
    file_path = get_dataset_path(dataset_id)

    # 2. 读取CSV
    df = read_csv_file(file_path)

    # 3. 调用筛选工具
    result = filter_rows_tool(df=df,request=request)

    # 4. 返回结果
    return ApiResponse(
        code=200,
        message="条件筛选完成",
        data={"dataset_id": file_path.stem,
            **result
        }
    )

# 数据排序接口
@router.post("sort",response_model=ApiResponse)
def sort_rows(dataset_id: str,request: SortRowsRequest):
    # 1. 获取数据集文件
    file_path = get_dataset_path(dataset_id)

    # 2. 读取CSV
    df = read_csv_file(file_path)

    # 3. 调用排序工具
    result = sort_rows_tool(df=df,request=request)

    # 4. 返回响应
    return ApiResponse(
        code=200,
        message="数据排序完成",
        data={
            "dataset_id": file_path.stem,
            **result
        }
    )