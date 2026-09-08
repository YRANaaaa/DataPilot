import uuid

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from fastapi import HTTPException

from datapilot.core.config import CHART_DIR
from datapilot.schemas.analysis import (
    GroupAggregateRequest,
    GroupCountRequest,
)
from datapilot.schemas.chart import CreateChartRequest
from datapilot.services.analysis_service import (
    group_aggregate_tool,
    group_count_tool,
)


plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False


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