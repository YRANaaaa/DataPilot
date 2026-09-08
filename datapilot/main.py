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


from pathlib import Path
import uuid
from io import BytesIO
import logging
from fastapi import FastAPI, UploadFile, File,HTTPException,Query
import pandas as pd
import json
import matplotlib

matplotlib.use("Agg") # 设置Matplotlib后端为Agg
import matplotlib.pyplot as plt
from fastapi.staticfiles import StaticFiles

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei","SimHei"] # 设置中文字体
plt.rcParams["axes.unicode_minus"] = False # 解决负号显示问题



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



# 创建图表工具函数
def create_chart_tool(df: pd.DataFrame,request: CreateChartRequest) -> dict:
    # 1. 根据聚合方式获得图表数据
    if request.aggregation == "count":
        count_request = GroupCountRequest(
            group_by=request.x_column,
            sort_order=request.sort_order,
            limit=request.limit,
            include_missing=False
        )
        analysis_result = group_count_tool(df=df,request=count_request) # 调用分组计数工具
        value_column = "count"

    else:
        # mean、sum等操作必须提供y_column
        if request.y_column is None:
            raise HTTPException(status_code=400,
                detail=(
                    "aggregation不是count时，"
                    "必须提供y_column"
                )
            )

        aggregate_request = GroupAggregateRequest(
            group_by=request.x_column,
            target=request.y_column,
            aggregation=request.aggregation,
            sort_order=request.sort_order,
            limit=request.limit,
            include_missing_group=False
        )

        analysis_result = group_aggregate_tool(df=df,request=aggregate_request) # 调用分组聚合工具
        value_column = f"{request.aggregation}_{request.y_column}"

    # 2. 将统计结果转回DataFrame
    chart_df = pd.DataFrame(analysis_result["results"])
    if chart_df.empty:
        raise HTTPException(status_code=400,detail="没有可以用于绘图的数据")

    # 3. 提取X轴和Y轴数据
    x_values = chart_df[request.x_column].astype(str).tolist()
    y_values = pd.to_numeric(chart_df[value_column],errors="coerce").tolist()

    # 4. 创建图片
    fig, ax = plt.subplots(figsize=(10, 6))

    # 5. 根据图表类型绘图
    if request.chart_type == "bar":
        ax.bar(x_values,y_values,color="#4C78A8")
    else:
        ax.plot(x_values,y_values,marker="o",color="#4C78A8")

    # 6. 设置标题和坐标轴
    if request.title:
        chart_title = request.title
    elif request.aggregation == "count":
        chart_title = f"{request.x_column}数量统计"
    else:
        chart_title = f"{request.x_column}分组{request.aggregation}_{request.y_column}"

    ax.set_title(chart_title)
    ax.set_xlabel(request.x_column)
    ax.set_ylabel(value_column)

    ax.tick_params(axis="x",rotation=45) # 旋转X轴标签
    ax.grid(axis="y", linestyle="--", alpha=0.3) # 添加网格线

    # 7. 生成唯一图片名称
    chart_id = str(uuid.uuid4())
    chart_filename = f"{chart_id}.png"
    chart_path = CHART_DIR / chart_filename

    # 8. 保存并关闭图片
    fig.tight_layout()
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # 9. 返回图表信息
    return {
        "chart_id": chart_id,
        "chart_type": request.chart_type,
        "x_column": request.x_column,
        "y_column": request.y_column,
        "aggregation": request.aggregation,
        "value_column": value_column,
        "title": chart_title,
        "chart_url": (
            f"/charts/{chart_filename}"
        ),
        "data_points": int(len(chart_df)),
        "chart_data": analysis_result["results"]
    }

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
