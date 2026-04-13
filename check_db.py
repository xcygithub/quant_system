import sqlite3
import os

db_path = r'C:\Users\FY\WorkBuddy\Claw\quant_data.db'
print(f"数据库文件存在: {os.path.exists(db_path)}")
print(f"数据库文件大小: {os.path.getsize(db_path) if os.path.exists(db_path) else 0}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 列出所有表
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print('\n数据库中的表:')
for t in tables:
    print(f"  - {t[0]}")

# 查看 daily_kline 表的记录数
cur.execute("SELECT COUNT(*) FROM daily_kline")
count = cur.fetchone()[0]
print(f"\ndaily_kline 表的记录数: {count}")

if count > 0:
    # 查看最近的10条数据
    cur.execute("SELECT DISTINCT date FROM daily_kline ORDER BY date DESC LIMIT 10")
    rows = cur.fetchall()
    print('\n数据库中最近的日期:')
    for r in rows:
        print(f"  {r[0]}")
else:
    # 查看有哪些股票的数据
    cur.execute("SELECT DISTINCT symbol FROM daily_kline LIMIT 10")
    symbols = cur.fetchall()
    print('\n数据库中的股票:')
    for s in symbols:
        print(f"  {s[0]}")

conn.close()