"""重新获取所有自选股的前复权数据"""
import sys
sys.path.insert(0, '.')

from data.data_manager import DataManager
from portfolio.watchlist import WatchlistManager
from datetime import datetime, timedelta

# 创建数据管理器和自选股管理器
dm = DataManager()
wl_manager = WatchlistManager()

# 获取自选股列表
stocks = wl_manager.get_all_stocks()
print(f"自选股数量: {len(stocks)}")

# 设置日期范围（最近2年）
end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

print(f"数据范围: {start_date} ~ {end_date}\n")

# 重新获取每只股票的数据
for stock in stocks:
    symbol = stock.symbol
    print(f"获取 {symbol} 的前复权数据...", end=" ")
    df = dm.get_daily_kline(symbol, start_date, end_date)
    if df is not None and len(df) > 0:
        print(f"成功 {len(df)} 条")
    else:
        print("失败")

print("\n完成!")