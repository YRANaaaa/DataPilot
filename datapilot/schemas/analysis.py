from typing import Literal
from pydantic import BaseModel, Field


class GroupCountRequest(BaseModel):
    group_by: str
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=10, ge=1, le=100)
    include_missing: bool = False


class GroupAggregateRequest(BaseModel):
    group_by: str
    target: str
    aggregation: Literal[
        "mean", "sum", "min", "max", "median"
    ] = "mean"
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=10, ge=1, le=100)
    include_missing_group: bool = False


class FilterRowsRequest(BaseModel):
    column: str
    operator: Literal[
        "eq", "ne", "gt", "gte", "lt", "lte", "contains"
    ]
    value: str | int | float | bool
    case_sensitive: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class SortRowsRequest(BaseModel):
    column: str
    sort_order: Literal["asc", "desc"] = "desc"
    sort_as: Literal["auto", "number", "text"] = "auto"
    missing_position: Literal["first", "last"] = "last"
    limit: int = Field(default=20, ge=1, le=100)