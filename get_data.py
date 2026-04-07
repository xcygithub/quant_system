import sqlite3
import pandas as pd
from pathlib import Path

# ====================== 配置 ======================
# 统一使用 Claw 目录下的数据库（与 data_manager.py 保持一致）
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "quant_data.db"


# ====================== 通用查询函数 ======================
def query_sql(sql, params=None):
    """
    通用SQL查询函数，返回DataFrame
    :param sql: 要执行的SQL语句
    :param params: 参数元组，可选
    :return: pd.DataFrame
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(sql, conn, params=params or ())
    conn.close()
    return df


# ====================== 1. 查询股票基础信息表 ======================
def get_stock_info(symbol=None, limit=100):
    """
    查询股票基础信息
    :param symbol: 股票代码，不传则查全部
    :param limit: 限制条数
    """
    if symbol:
        sql = "SELECT * FROM stock_info WHERE symbol = ? LIMIT ?"
        return query_sql(sql, (symbol, limit))
    else:
        sql = f"SELECT * FROM stock_info LIMIT {limit}"
        return query_sql(sql)


# ====================== 2. 查询日线K线表 ======================
def get_daily_kline(symbol, start_date=None, end_date=None, limit=200):
    """
    查询日线数据
    :param symbol: 股票代码 必填
    :param start_date: 开始日期 如 '2025-01-01'
    :param end_date: 结束日期
    """
    if start_date and end_date:
        sql = """
            SELECT * FROM daily_kline 
            WHERE symbol = ? AND date BETWEEN ? AND ? 
            ORDER BY date DESC LIMIT ?
        """
        return query_sql(sql, (symbol, start_date, end_date, limit))
    else:
        sql = "SELECT * FROM daily_kline WHERE symbol = ? ORDER BY date DESC LIMIT ?"
        return query_sql(sql, (symbol, limit))


# ====================== 3. 查询分钟K线表 ======================
def get_minute_kline(symbol, limit=500):
    """查询分钟数据"""
    sql = "SELECT * FROM minute_kline WHERE symbol = ? ORDER BY datetime DESC LIMIT ?"
    return query_sql(sql, (symbol, limit))


# ====================== 4. 查询财务数据表 ======================
def get_financial_data(symbol, limit=20):
    """查询财务数据"""
    sql = "SELECT * FROM financial_data WHERE symbol = ? ORDER BY report_date DESC LIMIT ?"
    return query_sql(sql, (symbol, limit))


# ====================== 测试调用 ======================
if __name__ == '__main__':
    # 1. 查询所有股票基础信息（前10条）
    print("=== 股票基础信息 ===")
    print(get_stock_info(limit=10))

    # 2. 查询某只股票的日线数据（注意：symbol需要带交易所后缀）
    print("\n=== 日线K线 ===")
    print(get_daily_kline(symbol="000001.SH", limit=10))  # 上证指数
    print(get_daily_kline(symbol="601919.SH", limit=10))   # 中远海控

    # 3. 查询某只股票的分钟数据
    print("\n=== 分钟K线 ===")
    print(get_minute_kline(symbol="000001.SH", limit=5))

    # 4. 查询财务数据
    print("\n=== 财务数据 ===")
    print(get_financial_data(symbol="000001.SH", limit=3))