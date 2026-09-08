from typing import Literal
from pydantic import BaseModel, Field


class CreateChartRequest(BaseModel):
    x_column: str
    y_column: str | None = None
    aggregation: Literal[
        "count", "mean", "sum", "min", "max", "median"
    ] = "count"
    chart_type: Literal["bar", "line"] = "bar"
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=10, ge=1, le=30)
    title: str | None = Field(default=None, max_length=100)