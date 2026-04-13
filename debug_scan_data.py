"""调试：模拟扫描时的数据获取逻辑"""
import sys
sys.path.insert(0, r'c:\Users\FY\WorkBuddy\Claw\quant_system')

from data.data_manager import DataManager
from datetime import datetime, timedelta
import pandas as pd

# 模拟扫描时的日期范围（90天）
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

print(f"扫描日期范围: {start_date} ~ {end_date}")
print(f"日历天数: {(datetime.now() - datetime.strptime(start_date, '%Y-%m-%d')).days}")
print("=" * 60)

symbol = "600795.SH"
dm = DataManager()

# 获取数据库数据
df = dm._get_kline_from_db(symbol, start_date, end_date)
print(f"\n数据库返回: {len(df)} 条数据")
if not df.empty:
    print(f"日期范围: {df['date'].min()} ~ {df['date'].max()}")

    # 检查数据完整性
    is_complete = dm._check_data_complete(df, start_date, end_date)
    print(f"_check_data_complete 结果: {is_complete}")

    # 详细分析
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.now()
    total_days = (end_dt - start_dt).days
    estimated_trading_days = int(total_days * 0.4)
    threshold = estimated_trading_days * 0.85

    latest_date = pd.to_datetime(df['date']).max()
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\n详细分析:")
    print(f"  日历天数: {total_days}")
    print(f"  估算交易日: {estimated_trading_days}")
    print(f"  阈值(85%): {threshold}")
    print(f"  数据库条数: {len(df)}")
    print(f"  最新数据日期: {latest_date.date() if hasattr(latest_date, 'date') else latest_date}")
    print(f"  昨天日期: {yesterday}")
    print(f"  最新日期 >= 昨天: {str(latest_date.date() if hasattr(latest_date, 'date') else latest_date) >= yesterday}")

    if len(df) < threshold:
        print(f"\n数据量不够: {len(df)} < {threshold}")
    else:
        print(f"\n数据量够: {len(df)} >= {threshold}")

    if str(latest_date.date() if hasattr(latest_date, 'date') else latest_date) < yesterday:
        print(f"数据太旧: {latest_date} < {yesterday}")
    else:
        print(f"数据够新")