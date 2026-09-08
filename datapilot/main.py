from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from datapilot.core.config import CHART_DIR
from datapilot.api.health import router as health_router
from datapilot.api.datasets import router as datasets_router
from datapilot.api.analysis import router as analysis_router
from datapilot.api.charts import router as charts_router


# 创建FastAPI应用实例
app = FastAPI(
    title="DataPilot API",
    description="基于AI Agent的可验证数据分析平台",
    version="0.1.0"
)
app.include_router(health_router)
app.include_router(datasets_router)
app.include_router(analysis_router)
app.include_router(charts_router)


# 配置静态文件目录
app.mount(
    "/charts", # 浏览器访问路径
    StaticFiles(directory=str(CHART_DIR)), # 电脑文件目录
    name="charts" # 内部路由
)