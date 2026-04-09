"""检查601919.SH的数据是否是前复权的"""
import sys
sys.path.insert(0, '.')

from data.data_manager import DataManager
from datetime import datetime, timedelta

dm = DataManager()

# 获取601919.SH 2023年6月的数据（除权日期附近）
start_date = '2023-06-20'
end_date = '2023-07-05'

df = dm.get_daily_kline('601919.SH', start_date, end_date)
print(f"601919.SH 数据 ({start_date} ~ {end_date}):")
print(df[['date', 'open', 'high', 'low', 'close']].to_string())