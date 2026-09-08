from datapilot.core.config import CHART_DIR, UPLOAD_DIR
from datapilot.schemas.common import ApiResponse
from datapilot.schemas.analysis import (
    FilterRowsRequest,
    GroupAggregateRequest,
    GroupCountRequest,
    SortRowsRequest,
)
from datapilot.schemas.chart import CreateChartRequest

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


## 文件辅助函数
# 封装数据集路径查找逻辑
def get_dataset_path(dataset_id: str) -> Path:
    # 1. 检查dataset_id是否是合法的uuid
    try:
        valid_dataset_id = str(uuid.UUID(dataset_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="dataset_id格式错误")

    # 2. 拼接文件路径,检查文件是否存在
    file_path = UPLOAD_DIR / f"{valid_dataset_id}.csv"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")

    return file_path

# 封装读取csv文件逻辑
def read_csv_file(file_path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        logging.error(f"读取csv文件失败: {e}")
        raise HTTPException(status_code=500, detail="CSV内容无法读取")


## Pandas分析工具
def group_count_tool(df: pd.DataFrame,request: GroupCountRequest) -> dict:
    group_by = request.group_by
    # 1. 检查字段是否存在
    if group_by not in df.columns:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"字段不存在：{group_by}",
                "available_columns": df.columns.tolist()
            }
        )

    # 2. 取出需要统计的列
    values = df[group_by]

    # 3. 统计缺失数据
    missing_rows = int(values.isnull().sum())

    # 4. 决定是否保留缺失值
    if request.include_missing:
        values = values.fillna("Missing")
    else:
        values = values.dropna()

    # 5. 统计各个值出现的次数
    counts = values.value_counts()

    # 6. 根据请求排序
    ascending = request.sort_order == "asc" # 如果请求是asc,则升序,否则降序
    counts = counts.sort_values(ascending=ascending)

    # 7. 限制返回数量
    counts = counts.head(request.limit)

    # 8. 将Series转换成DataFrame
    result_df = counts.rename_axis(group_by).reset_index(name="count")

    # 9. 转换成JSON友好的数据
    results = json.loads(result_df.to_json(orient="records",force_ascii=False))

    return {
        "group_by": group_by,
        "sort_order": request.sort_order,
        "limit": request.limit,
        "include_missing": request.include_missing,
        "source_rows": int(len(df)),
        "counted_rows": int(len(values)),
        "missing_rows": missing_rows,
        "results": results
    }

# 统计工具函数
def group_aggregate_tool(df: pd.DataFrame,request: GroupAggregateRequest) -> dict:
    group_by = request.group_by
    target = request.target

    # 1. 检查分组字段是否存在
    if group_by not in df.columns:
        raise HTTPException(status_code=400,
            detail={
                "message": f"分组字段不存在：{group_by}",
                "available_columns": df.columns.tolist()
            }
        )

    # 2. 检查目标字段是否存在
    if target not in df.columns:
        raise HTTPException(status_code=400,
            detail={
                "message": f"目标字段不存在：{target}",
                "available_columns": df.columns.tolist()
            }
        )

    # 3. 暂时不允许两个字段相同
    if group_by == target:
        raise HTTPException(status_code=400,
            detail="分组字段和目标字段不能相同"
        )

    # 4. 只提取需要的两列
    work_df = df[[group_by, target]].copy()
    source_rows = int(len(work_df))

    # 5. 记录原始目标字段是否为空
    original_target_not_null = work_df[target].notna()

    # 6. 将目标字段转换成数字类型,并将非数值转换为NaN值
    work_df[target] = pd.to_numeric(work_df[target],errors="coerce")

    # 7. 统计数值转换情况
    valid_numeric_rows = int(work_df[target].notna().sum()) # 统计有效数值行数
    invalid_numeric_rows = int(
        (
            original_target_not_null & work_df[target].isna() # 判断两个条件是否同时为True
        ).sum()
    ) # 统计无效数值行数
    missing_numeric_rows = int((~original_target_not_null).sum()) # 统计缺失数值行数.~取反操作

    # 8. 统计分组字段缺失值
    missing_group_rows = int(work_df[group_by].isna().sum())

    # 9. 处理分组字段缺失值
    if request.include_missing_group:
        work_df[group_by] = work_df[group_by].fillna("Missing")
    else:
        work_df = work_df.dropna(subset=[group_by])

    # 10. 删除无法参与计算的目标值
    work_df = work_df.dropna(subset=[target])
    analyzed_rows = int(len(work_df))

    # 11. 检查是否还有有效数据
    if work_df.empty:
        raise HTTPException(status_code=400,detail="没有可以参与聚合计算的有效数据")

    # 12. 按字段分组并执行聚合
    result = work_df.groupby(group_by)[target].agg(request.aggregation)

    # 13. 根据聚合结果排序
    ascending = request.sort_order == "asc" # 如果请求是asc即True,则升序,否则False降序
    result = result.sort_values(ascending=ascending).head(request.limit)

    # 14. 设置结果列名称
    result_column = f"{request.aggregation}_{target}"

    # 15. Series转换成DataFrame
    result_df = result.rename(result_column).reset_index()

    # 16. 转换成JSON友好的列表
    results = json.loads(result_df.to_json(orient="records",force_ascii=False))

    # 17. 返回结果与计算依据
    return {
        "group_by": group_by,
        "target": target,
        "aggregation": request.aggregation,
        "sort_order": request.sort_order,
        "limit": request.limit,
        "include_missing_group": request.include_missing_group,
        "source_rows": source_rows,
        "valid_numeric_rows": valid_numeric_rows,
        "invalid_numeric_rows": invalid_numeric_rows,
        "missing_numeric_rows": missing_numeric_rows,
        "missing_group_rows": missing_group_rows,
        "analyzed_rows": analyzed_rows,
        "results": results
    }

def filter_rows_tool(df: pd.DataFrame,request: FilterRowsRequest) -> dict:
    column = request.column
    operator = request.operator
    value = request.value

    # 1. 检查字段是否存在
    if column not in df.columns:
        raise HTTPException(status_code=400,
            detail={
                "message": f"字段不存在：{column}",
                "available_columns": df.columns.tolist()
            }
        )

    series = df[column]

    source_rows = int(len(df))
    missing_rows = int(series.isna().sum())
    invalid_numeric_rows = 0

    # 2. 数值比较
    if operator in {"gt","gte","lt","lte"}:
        # 将用户提供的比较值转换为数字
        try:
            compare_value = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400,detail=f"操作符{operator}要求value是数字")

        # 将目标列转换成数字
        numeric_series = pd.to_numeric(series,errors="coerce")

        # 统计原本有值，但无法转换为数字的行数
        invalid_numeric_rows = int(
            (series.notna() & numeric_series.isna()).sum()
        )

        valid_mask = numeric_series.notna() # 有效数值行码

        if operator == "gt":
            condition_mask = valid_mask & (numeric_series > compare_value)

        elif operator == "gte":
            condition_mask = valid_mask & (numeric_series >= compare_value)

        elif operator == "lt":
            condition_mask = valid_mask & (numeric_series < compare_value)

        else:
            condition_mask = valid_mask & (numeric_series <= compare_value)

    # 3. 字符串包含
    elif operator == "contains":
        text_series = series.astype("string")
        condition_mask = text_series.str.contains(
            str(value), # 转换为字符串
            case=request.case_sensitive, # 是否区分大小写
            na=False, # 忽略缺失值
            regex=False # 不使用正则表达式
        )

    # 4. 等于或不等于
    else:
        # value是字符串时，按照文本比较
        if isinstance(value, str):
            text_series = series.astype("string")
            compare_text = value

            if not request.case_sensitive:
                text_series = text_series.str.casefold()
                compare_text = compare_text.casefold()

            if operator == "eq":
                condition_mask = series.notna() & (text_series == compare_text)
            else:
                condition_mask = series.notna() & (text_series != compare_text)

        # value是数字或布尔值时，直接比较
        else:
            if operator == "eq":
                condition_mask = series.notna() & (series == value)
            else:
                condition_mask = series.notna() & (series != value)

    # 5. 筛选所有符合条件的数据
    matched_df = df.loc[condition_mask]
    matched_rows = int(len(matched_df))

    # 6. 限制实际返回行数
    returned_df = matched_df.head(request.limit)

    # 7. 转换成JSON友好的格式
    records = json.loads(returned_df.to_json(orient="records",force_ascii=False))

    return {
        "column": column,
        "operator": operator,
        "value": value,
        "case_sensitive": request.case_sensitive,
        "limit": request.limit,
        "source_rows": source_rows,
        "missing_rows": missing_rows,
        "invalid_numeric_rows":
            invalid_numeric_rows,
        "matched_rows": matched_rows,
        "returned_rows": int(len(records)),
        "truncated": matched_rows > len(records),
        "records": records
    }

# 排序工具函数
def sort_rows_tool(df: pd.DataFrame,request: SortRowsRequest) -> dict:
    column = request.column

    # 1. 检查字段是否存在
    if column not in df.columns:
        raise HTTPException(status_code=400,
            detail={
                "message": f"字段不存在：{column}",
                "available_columns": df.columns.tolist()
            }
        )

    # 2. 创建副本
    work_df = df.copy()
    source_rows = int(len(work_df))
    series = work_df[column]

    # 3. 检查统计缺失值
    missing_rows = int(series.isna().sum())
    invalid_numeric_rows = 0

    # 4. 判断实际排序类型
    if request.sort_as == "auto":
        if pd.api.types.is_numeric_dtype(series):
            actual_sort_as = "number"
        else:
            actual_sort_as = "text"
    else:
        actual_sort_as = request.sort_as

    # 5. 判断是升序还是降序
    ascending = request.sort_order == "asc"

    # 6. 数字排序
    if actual_sort_as == "number":
        numeric_series = pd.to_numeric(series,errors="coerce")
        # 原本不为空，但无法转换成数字的行数统计
        invalid_numeric_rows = int(
            (series.notna() & numeric_series.isna()).sum()
        )
        sorted_df = work_df.sort_values(
            by=column,
            ascending=ascending,
            na_position=request.missing_position, # 缺失值位置
            kind="mergesort", # 归并排序
            key=lambda current_series: pd.to_numeric(current_series,errors="coerce")
        )

    # 7. 文本排序
    else:
        sorted_df = work_df.sort_values(
            by=column,
            ascending=ascending,
            na_position=request.missing_position,
            kind="mergesort",
            key=lambda current_series:current_series.astype("string").str.casefold()
        )

    # 8. 限制返回行数
    returned_df = sorted_df.head(request.limit)

    # 9. 转换成JSON友好格式
    records = json.loads(returned_df.to_json(orient="records",force_ascii=False))

    # 10. 返回排序结果和依据
    return {
        "column": column,
        "sort_order": request.sort_order,
        "requested_sort_as": request.sort_as,
        "actual_sort_as": actual_sort_as,
        "missing_position":
            request.missing_position,
        "limit": request.limit,
        "source_rows": source_rows,
        "missing_rows": missing_rows,
        "invalid_numeric_rows":
            invalid_numeric_rows,
        "returned_rows": int(len(records)),
        "truncated":
            source_rows > len(records),
        "records": records
    }

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
