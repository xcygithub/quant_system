import sqlite3

conn = sqlite3.connect('quant_data.db')
cur = conn.cursor()

# 查看数据库中所有不重复的日期，按日期降序排列
cur.execute("SELECT DISTINCT date FROM daily_kline ORDER BY date DESC LIMIT 30")
rows = cur.fetchall()
print('数据库中最近的日期:')
for r in rows:
    print(r[0])

# 也查看一下有哪些不同的股票
cur.execute("SELECT DISTINCT symbol FROM daily_kline LIMIT 10")
symbols = cur.fetchall()
print('\n数据库中的股票:')
for s in symbols:
    print(s[0])

conn.close()