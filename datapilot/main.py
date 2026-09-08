from datapilot.core.config import CHART_DIR
from datapilot.schemas.common import ApiResponse
from datapilot.schemas.chart import CreateChartRequest
from datapilot.services.dataset_service import (
    get_dataset_path,
    read_csv_file,
)
from datapilot.services.chart_service import create_chart_tool
from datapilot.api.health import router as health_router
from datapilot.api.datasets import router as datasets_router
from datapilot.api.analysis import router as analysis_router


from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles



# 创建FastAPI应用实例
app = FastAPI(
    title="DataPilot API",
    description="基于AI Agent的可验证数据分析平台",
    version="0.1.0"
)
app.include_router(health_router)
app.include_router(datasets_router)
app.include_router(analysis_router)

# 配置静态文件目录
app.mount(
    "/charts", # 浏览器访问路径
    StaticFiles(directory=str(CHART_DIR)), # 电脑文件目录
    name="charts" # 内部路由
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