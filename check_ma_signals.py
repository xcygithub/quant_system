"""检查 000001.SH 的 MA 信号"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager

dm = DataManager()
df = dm.get_daily_kline('000001.SH', '2023-01-01', '2024-12-31')

# 计算 MA
df['fast_ma'] = df['close'].rolling(window=20).mean()
df['slow_ma'] = df['close'].rolling(window=60).mean()

# 信号
df['signal'] = (df['fast_ma'] > df['slow_ma']).astype(int) - (df['fast_ma'] <= df['slow_ma']).astype(int)

# 统计
print('Signal distribution:')
print(f'  Buy(1): {sum(df["signal"] == 1)}')
print(f'  Sell(-1): {sum(df["signal"] == -1)}')
print(f'  Hold(0): {sum(df["signal"] == 0)}')

# 显示部分数据
print()
print('First 20 days (close vs MA):')
for i in range(min(20, len(df))):
    row = df.iloc[i]
    date_str = str(row['date'])[:10]
    close = row['close']
    fast = f'{row["fast_ma"]:.2f}' if pd.notna(row['fast_ma']) else 'N/A'
    slow = f'{row["slow_ma"]:.2f}' if pd.notna(row['slow_ma']) else 'N/A'
    sig = int(row['signal'])
    print(f'  Day {i} ({date_str}): close={close:.2f}, fast_ma={fast}, slow_ma={slow}, signal={sig}')

print()
print('Last 20 days:')
for i in range(max(len(df)-20, 0), len(df)):
    row = df.iloc[i]
    date_str = str(row['date'])[:10]
    close = row['close']
    fast = f'{row["fast_ma"]:.2f}' if pd.notna(row['fast_ma']) else 'N/A'
    slow = f'{row["slow_ma"]:.2f}' if pd.notna(row['slow_ma']) else 'N/A'
    sig = int(row['signal'])
    print(f'  Day {i} ({date_str}): close={close:.2f}, fast_ma={fast}, slow_ma={slow}, signal={sig}')