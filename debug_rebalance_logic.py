"""
验证 _rebalance 中的 target_amount 计算问题
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.position_sizer import PositionSizer, create_position_sizer

# 模拟 _rebalance 的场景
total_capital = 1000000  # 100万
max_single_position = 0.2  # 20%
max_total_position = 0.8  # 80%

candidates = [
    ("000001.SZ", 80, 0.25),
    ("600000.SH", 70, 0.20),
    ("000858.SZ", 65, 0.22)
]

prices = {
    "000001.SZ": 10.0,
    "600000.SH": 8.0,
    "000858.SZ": 9.0
}

print("="*60)
print("验证 _rebalance 中的计算逻辑")
print("="*60)

sizer = create_position_sizer(
    method="equal",
    max_total=max_total_position,
    max_single=max_single_position
)

allocations = sizer.allocate(candidates, total_capital, prices)

print("\nposition_sizer.allocate() 返回的 allocations:")
for a in allocations:
    print(f"\n{a.symbol}:")
    print(f"  weight = {a.weight:.4f} (相对于 max_total_position={max_total_position})")
    print(f"  amount = {a.amount:,.0f} 元 (已计算好的买入金额)")

print("\n" + "="*60)
print("问题分析：")
print("="*60)
print(f"\n如果用 'target_amount = total_assets * alloc.weight' 计算：")
for a in allocations:
    target1 = total_capital * a.weight
    print(f"  {a.symbol}: {total_capital:,} * {a.weight:.4f} = {target1:,.0f} 元")

print(f"\n但其实 position_sizer 已经计算好了 amount = {a.amount:,.0f} 元")
print(f"所以 'total_assets * alloc.weight' 相当于 double 计算了！")
print(f"实际上应该直接用 alloc.amount！")

print("\n" + "="*60)
print("进一步问题：100股整数倍取整")
print("="*60)
print(f"\n假设 price=10, weight=0.2, total_capital=1,000,000:")
print(f"  target_amount = 1,000,000 * 0.2 = 200,000")
print(f"  buy_shares = int(200,000 / 10 / 100) * 100 = 20,000 股")
print(f"  actual_amount = 20,000 * 10 = 200,000 元")

print(f"\n但如果 price=10.6 (高价股票):")
print(f"  target_amount = 1,000,000 * 0.2 = 200,000")
print(f"  buy_shares = int(200,000 / 10.6 / 100) * 100 = 18,800 股")
print(f"  actual_amount = 18,800 * 10.6 = 199,280 元")

print(f"\n问题：alloc.weight 是相对于 max_total_position 的，")
print(f"      不是相对于 total_capital！")