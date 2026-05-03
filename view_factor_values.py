"""
查看 factor_values 表数据的小工具。

用法示例：
    python view_factor_values.py
    python view_factor_values.py --limit 200
    python view_factor_values.py --symbol 601857.SH
    python view_factor_values.py --factor roe --start-date 2024-01-01 --end-date 2024-12-31
    python view_factor_values.py --export-csv factor_values_dump.csv
"""

import argparse
import sqlite3
from typing import List, Any

import pandas as pd

from config import DATABASE_PATH


def _build_query(args: argparse.Namespace) -> tuple[str, List[Any]]:
    query = """
        SELECT symbol, trade_date, factor_name, factor_value, update_time
        FROM factor_values
        WHERE 1 = 1
    """
    params: List[Any] = []

    if args.symbol:
        query += " AND symbol = ?"
        params.append(args.symbol)
    if args.factor:
        query += " AND factor_name = ?"
        params.append(args.factor)
    if args.start_date:
        query += " AND trade_date >= ?"
        params.append(args.start_date)
    if args.end_date:
        query += " AND trade_date <= ?"
        params.append(args.end_date)

    query += " ORDER BY trade_date DESC, symbol, factor_name"

    if args.limit and args.limit > 0:
        query += " LIMIT ?"
        params.append(args.limit)

    return query, params


def main() -> None:
    parser = argparse.ArgumentParser(description="查看 factor_values 表数据")
    parser.add_argument("--symbol", type=str, help="按股票代码过滤，如 601857.SH")
    parser.add_argument("--factor", type=str, help="按因子过滤，如 roe")
    parser.add_argument("--start-date", type=str, help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=0, help="限制输出行数，0 表示不限制")
    parser.add_argument("--export-csv", type=str, default="", help="导出为 CSV 文件路径")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DATABASE_PATH))
    try:
        query, params = _build_query(args)
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        print("factor_values 表未查到符合条件的数据。")
        return

    print(f"共查询到 {len(df)} 行")
    print("-" * 80)

    with pd.option_context(
        "display.max_rows", None,
        "display.max_columns", None,
        "display.width", 180,
        "display.max_colwidth", 60,
    ):
        print(df.to_string(index=False))

    if args.export_csv:
        df.to_csv(args.export_csv, index=False, encoding="utf-8-sig")
        print(f"\n已导出到: {args.export_csv}")


if __name__ == "__main__":
    main()

