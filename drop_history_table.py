import sqlite3
from config import DATABASE_PATH

db_path = str(DATABASE_PATH)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 删除 history_valuation_data 表
try:
    cursor.execute("DROP TABLE IF EXISTS history_valuation_data")
    print("已删除 history_valuation_data 表")
except Exception as e:
    print(f"删除失败: {e}")

conn.commit()
conn.close()
print("完成")