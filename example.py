"""
量化交易系统使用示例

这个脚本展示了如何使用量化交易系统进行策略回测
"""

# 使用示例代码（需要在正确的Python环境中运行）

EXAMPLE_CODE = '''
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw')

from quant_system.main import QuantSystem

# 初始化系统
system = QuantSystem({
    'initial_capital': 1000000,
    'commission_rate': 0.0003,
    'position_pct': 0.3
})

# 运行回测
results = system.run_backtest(
    strategy='ma_cross',      # 策略名称
    symbol='000001',          # 股票代码（平安银行）
    start_date='2023-01-01',  # 开始日期
    end_date='2024-12-31',    # 结束日期
    strategy_params={         # 策略参数
        'fast_period': 20,
        'slow_period': 60
    }
)

# 多策略对比
comparison = system.compare_strategies(
    strategies=['ma_cross', 'macd', 'rsi', 'bollinger'],
    symbol='000001',
    start_date='2023-01-01',
    end_date='2024-12-31'
)

# 参数优化
optimization = system.optimize_parameters(
    strategy='ma_cross',
    symbol='000001',
    start_date='2023-01-01',
    end_date='2024-12-31',
    param_grid={
        'fast_period': [5, 10, 20],
        'slow_period': [30, 60, 120]
    }
)

print(f"最优参数: {optimization['best_params']}")
'''

print("=" * 70)
print("量化交易系统 - 使用示例")
print("=" * 70)
print()
print("请在正确的Python环境中运行以下代码：")
print()
print(EXAMPLE_CODE)
print()
print("=" * 70)
print("可用策略列表：")
print("  1. ma_cross     - 均线交叉策略")
print("  2. macd         - MACD策略")
print("  3. bollinger    - 布林带策略")
print("  4. rsi          - RSI策略")
print("  5. multi_factor - 多因子策略")
print("=" * 70)
print()
print("启动Web界面：")
print("  streamlit run quant_system/web/app.py")
print()
print("=" * 70)
