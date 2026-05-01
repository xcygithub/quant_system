import os
import sqlite3
from config import DATABASE_PATH

db_path = str(DATABASE_PATH)
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM daily_kline")
    count = cursor.fetchone()[0]
    print(f"当前数据库有 {count} 条数据")

    cursor.execute("DELETE FROM daily_kline")
    print(f"已删除所有数据")
    conn.commit()
    conn.close()
else:
    print("当前路径下无数据库")

print("完成!")