import os
import sqlite3

db_path = r"C:\Users\FY\WorkBuddy\Claw\quant_data.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM daily_kline")
    count = cursor.fetchone()[0]
    print(f"Claw下数据库有 {count} 条数据")

    cursor.execute("DELETE FROM daily_kline")
    print(f"已删除所有数据")
    conn.commit()
    conn.close()
else:
    print("Claw下无数据库")

print("完成!")