from datapilot.core.config import CHART_DIR, UPLOAD_DIR
from datapilot.schemas.common import ApiResponse
from datapilot.schemas.analysis import (
    FilterRowsRequest,
    GroupAggregateRequest,
    GroupCountRequest,
    SortRowsRequest,
)
from datapilot.schemas.chart import CreateChartRequest
from datapilot.services.dataset_service import (
    get_dataset_path,
    read_csv_file,
)
from datapilot.services.analysis_service import (
    filter_rows_tool,
    group_aggregate_tool,
    group_count_tool,
    sort_rows_tool,
)
from datapilot.services.chart_service import create_chart_tool


from pathlib import Path
import uuid
from io import BytesIO
import logging
from fastapi import FastAPI, UploadFile, File,HTTPException,Query
import pandas as pd
import json
from fastapi.staticfiles import StaticFiles



# 创建FastAPI应用实例
app = FastAPI(
    title="DataPilot API",
    description="基于AI Agent的可验证数据分析平台",
    version="0.1.0"
)

# 配置静态文件目录
app.mount(
    "/charts", # 浏览器访问路径
    StaticFiles(directory=str(CHART_DIR)), # 电脑文件目录
    name="charts" # 内部路由
)


## API接口
# 健康检查接口
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "DataPilot",
        "version": "0.1.0"
    }

# 上传文件接口
@app.post("/datasets/upload", response_model=ApiResponse)
async def upload_dataset(file: UploadFile = File(...)):
    # 1. 检查文件名
    filename = file.filename or ""

    # 2. 检查扩展名
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="文件扩展名必须是csv")

    # 3. 读取文件内容
    file_content = await file.read() # await file.read()异步读取文件内容,字节内容
    if not file_content: # 检查文件内容是否为空
        raise HTTPException(status_code=400, detail="文件内容为空")

    # 4. 尝试用pandas读取csv文件
    try:
        df = pd.read_csv(BytesIO(file_content)) # BytesIO将字节内容转换为文件对象, 用于pandas读取
    except Exception as e:
        logging.error(f"读取csv文件失败: {e}")
        raise HTTPException(status_code=400, detail="CSV内容无法读取")

    # 5. 生成唯一id
    dataset_id = str(uuid.uuid4())

    # 6. 保存文件
    file_path = UPLOAD_DIR / f"{dataset_id}.csv"
    file_path.write_bytes(file_content)

    # 7. 返回文件名,行数,列数和字段名称
    return ApiResponse(
        code=200,
        message="上传成功",
        data={
            "dataset_id": dataset_id,
            "filename": filename,
            "rows": df.shape[0],
            "column_count": df.shape[1],
            "columns": df.columns.tolist()
        }
    )

# 摘要接口
@app.get("/datasets/{dataset_id}/summary", response_model=ApiResponse)
def get_dataset_summary(dataset_id: str):
    # 1. 获取数据集路径
    file_path = get_dataset_path(dataset_id)

    # 2. 读取csv文件内容
    df = read_csv_file(file_path)

    # 3. 统计每列缺失值数量
    missing_values = {
        column: int(count)
        for column, count in df.isnull().sum().items()
    }

    # 4. 获取每列数据类型
    data_types = {
        column: str(dtype)
        for column, dtype in df.dtypes.items()
    }

    # 5. 统计重复行
    duplicate_rows = int(df.duplicated().sum())

    # 6. 返回摘要
    return ApiResponse(
        code=200,
        message="数据集摘要获取成功",
        data={
            "dataset_id": dataset_id,
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "column_names": df.columns.tolist(),
            "missing_values": missing_values,
            "duplicate_rows": duplicate_rows,
            "data_types": data_types
        }
    )

# 数据预览接口
@app.get("/datasets/{dataset_id}/preview", response_model=ApiResponse)
def preview_data(dataset_id: str, limit: int = Query(default=5, ge=1, le=100,description="预览数据行数,默认5行,最小1,最大100")):
    # 1. 获取数据集路径
    file_path = get_dataset_path(dataset_id)

    # 2. 使用pandas读取csv文件内容
    df = read_csv_file(file_path)

    # 3. 取前limit行数据
    preview_df = df.head(limit)

    # 4. 转化为json格式
    records = json.loads(preview_df.to_json(orient="records",force_ascii=False))

    # 5. 返回响应
    return ApiResponse(
        code=200,
        message="数据预览获取成功",
        data={
            "dataset_id": dataset_id,
            "requested_limit": limit,
            "returned_rows": len(records),
            "records": records
        }
    )

# 分组计数接口
@app.post("/datasets/{dataset_id}/analysis/group-count",response_model=ApiResponse)
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
@app.post("/datasets/{dataset_id}/analysis/group-aggregate",response_model=ApiResponse)
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
@app.post("/datasets/{dataset_id}/analysis/filter",response_model=ApiResponse)
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

@app.post("/datasets/{dataset_id}/analysis/sort",response_model=ApiResponse)
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

@app.post("/datasets/{dataset_id}/analysis/chart",response_model=ApiResponse)
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
