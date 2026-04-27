import sqlite3

db_path = 'C:/Users/FY/WorkBuddy/Claw/quant_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print('=== All Tables ===')
for t in tables:
    print(f'  {t[0]}')

# Check valuation_data structure
print('\n=== valuation_data ===')
cursor.execute("PRAGMA table_info(valuation_data)")
cols = cursor.fetchall()
for c in cols:
    print(f'  {c[1]}: {c[2]}')
cursor.execute("SELECT COUNT(*) FROM valuation_data")
print(f'  Count: {cursor.fetchone()[0]}')

# Check history_valuation_data structure
print('\n=== history_valuation_data ===')
cursor.execute("PRAGMA table_info(history_valuation_data)")
cols = cursor.fetchall()
for c in cols:
    print(f'  {c[1]}: {c[2]}')
cursor.execute("SELECT COUNT(*) FROM history_valuation_data")
print(f'  Count: {cursor.fetchone()[0]}')

conn.close()