"""
诊断 position_sizer 的分配逻辑
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.position_sizer import PositionSizer, create_position_sizer

# 测试场景
total_capital = 1000000  # 100万
max_single_position = 0.2  # 20%
max_total_position = 0.8  # 80%

# 候选股票：(symbol, score, volatility)
candidates = [
    ("000001.SZ", 80, 0.25),
    ("600000.SH", 70, 0.20),
    ("000858.SZ", 65, 0.22)
]

# 价格
prices = {
    "000001.SZ": 10.0,
    "600000.SH": 8.0,
    "000858.SZ": 9.0
}

print("="*60)
print("诊断：position_sizer.allocate() 逻辑")
print("="*60)

print(f"\n初始参数:")
print(f"  total_capital: {total_capital:,}")
print(f"  max_single_position: {max_single_position:.0%}")
print(f"  max_total_position: {max_total_position:.0%}")

print(f"\n候选股票:")
for c in candidates:
    print(f"  {c[0]}: score={c[1]}, volatility={c[2]}")

print(f"\n价格:")
for s, p in prices.items():
    print(f"  {s}: {p}")

# 创建 sizer
sizer = create_position_sizer(
    method="equal",
    max_total=max_total_position,
    max_single=max_single_position
)

print(f"\n调用 allocate()...")
allocations = sizer.allocate(candidates, total_capital, prices)

print(f"\n分配结果:")
total_weight = 0
total_amount = 0
for a in allocations:
    print(f"  {a.symbol}:")
    print(f"    weight: {a.weight:.4f} ({a.weight_percent})")
    print(f"    shares: {a.shares}")
    print(f"    amount: {a.amount:,.0f}")
    total_weight += a.weight
    total_amount += a.amount

print(f"\n总计:")
print(f"  总权重: {total_weight:.4f} ({total_weight:.2%})")
print(f"  总买入金额: {total_amount:,.0f}")
print(f"  初始资金: {total_capital:,}")
print(f"  max_single_position 限制: {max_single_position:.0%} = {total_capital * max_single_position:,.0f}")

print(f"\n验证:")
for a in allocations:
    limit = total_capital * max_single_position
    if a.amount > limit + 1:  # 允许1元误差
        print(f"  [违规] {a.symbol}: 买入 {a.amount:,.0f} > 限制 {limit:,.0f}")
    else:
        print(f"  [OK] {a.symbol}: 买入 {a.amount:,.0f} <= 限制 {limit:,.0f}")