import json

import pandas as pd
from fastapi import HTTPException

from datapilot.schemas.analysis import (
    FilterRowsRequest,
    GroupAggregateRequest,
    GroupCountRequest,
    SortRowsRequest,
)

## Pandas分析工具
# 分组计算函数
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


# 分组聚合工具函数
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


# 条件筛选函数
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