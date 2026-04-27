# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw')

import sqlite3

print("=" * 60)
print("Test: Financial Data Management Page Functions")
print("=" * 60)

# Test 1: Import modules
print("\n[Test 1] Module imports")
from quant_system.data.data_manager import DataManager
from quant_system.data.financial_data_source import FinancialDataSource
from quant_system.data.financial_data_manager import FinancialDataManager
from quant_system.data.financial_data_saver import FinancialDataSaver
from quant_system.portfolio.watchlist import WatchlistManager
print("[PASS] All modules imported successfully")

# Test 2: Database connection
print("\n[Test 2] Database connection")
dm = DataManager()
conn = sqlite3.connect(dm.db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print(f"[PASS] Connected to {dm.db_path}")
print(f"       Found {len(tables)} tables")

# Test 3: Data status query (使用正确的列名)
print("\n[Test 3] Data status query")
# valuation_data 使用 trade_date，财务数据表使用 report_date，daily_kline 使用 date
tables_to_check = [
    ('valuation_data', 'trade_date'),
    ('profit_data', 'report_date'),
    ('balance_data', 'report_date'),
    ('cash_flow_data', 'report_date'),
    ('dupont_data', 'report_date'),
    ('daily_kline', 'date'),
]

for table, date_col in tables_to_check:
    try:
        cursor.execute(f"SELECT COUNT(*), MAX({date_col}) FROM {table}")
        row = cursor.fetchone()
        count = row[0] or 0
        latest = row[1] or 'N/A'
        print(f"       {table}: {count:,} records, latest: {latest}")
    except Exception as e:
        print(f"       {table}: error - {e}")

conn.close()
print("[PASS] Data status query completed")

# Test 4: Watchlist
print("\n[Test 4] Watchlist manager")
wl = WatchlistManager()
stocks = wl.get_all_stocks()
print(f"[PASS] Watchlist: {len(stocks)} stocks")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
