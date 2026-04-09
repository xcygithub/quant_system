"""诊断自选股数据更新问题"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import sqlite3
from data.data_manager import DataManager
from datetime import datetime, timedelta

dm = DataManager()

# 测试更新
symbols = ['000001.SZ']  # 平安银行

print(f"=== 测试 update_recent_data ===")
print(f"时间范围: 最近10天")

# 检查数据库当前数据
print(f"\n1. 检查数据库当前数据...")
conn = sqlite3.connect(dm.db_path)
cursor = conn.cursor()
cursor.execute("""
    SELECT date, close FROM daily_kline
    WHERE symbol = ?
    ORDER BY date DESC
    LIMIT 5
""", ('000001.SZ',))
rows = cursor.fetchall()
print(f"数据库最新5条数据:")
for row in rows:
    print(f"  {row[0]}: close={row[1]}")
conn.close()

# 调用 update_recent_data
print(f"\n2. 调用 update_recent_data...")
result = dm.update_recent_data(symbols, days=10)
print(f"返回值: {result}")

# 再次检查数据库
print(f"\n3. 再次检查数据库...")
conn = sqlite3.connect(dm.db_path)
cursor = conn.cursor()
cursor.execute("""
    SELECT date, close FROM daily_kline
    WHERE symbol = ?
    ORDER BY date DESC
    LIMIT 5
""", ('000001.SZ',))
rows = cursor.fetchall()
print(f"数据库最新5条数据:")
for row in rows:
    print(f"  {row[0]}: close={row[1]}")
conn.close()

# 测试 get_daily_kline
print(f"\n4. 测试 get_daily_kline...")
end_date = datetime.now()
start_date = end_date - timedelta(days=30)
df = dm.get_daily_kline('000001.SZ', start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
print(f"返回数据条数: {len(df)}")
if not df.empty:
    print(f"最新日期: {df.iloc[-1]['date']}")
    print(f"最新收盘价: {df.iloc[-1]['close']}")