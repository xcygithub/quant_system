# 多因子回测 - 买入时因子得分展示方案

## 需求背景

当前多因子回测系统在「交易明细」标签页中只展示交易结果（买入/卖出价格、收益率），无法看到**每次买入时各因子得了多少分、为什么选中这只股票**。用户希望在交易明细中清晰看到每次买入决策的依据。

---

## 一、现有数据流分析

### 1.1 信号生成流程

```
MultiFactorBacktest.set_data()
    └─ _generate_factor_signals(date, stock_data)
            ├─ _build_factor_panel(date, stock_data)  → 构建因子面板
            │   └─ 返回 pd.DataFrame(index=symbol, columns=[factor_values])
            ├─ signal_generator.generate_ranking_signals(factor_panel, top_n)
            │   ├─ _calculate_percentile_scores()  → 计算横截面百分位得分
            │   │   └─ {symbol: {factor: percentile}}
            │   └─ _calculate_combined_scores()   → IC加权综合得分
            │       └─ {symbol: combined_score}
            └─ 返回 {symbol: signal(1/0)}
```

### 1.2 调仓买入流程

```
_rebalance(date, prices)
    ├─ _select_candidates()  → 获取 StockScore 列表（含综合得分）
    ├─ position_sizer.allocate() → 计算仓位分配
    └─ _buy(symbol, date, price, quantity, ...) → 执行买入
            └─ 创建 TradeDetail 记录
```

### 1.3 关键发现

`FactorSignalGenerator` 已经在 `_calculate_percentile_scores()` 中计算了每只股票各因子的百分位得分（0-100分），但这些中间结果**没有被保存下来**，只在内存中用于计算综合得分后就被丢弃了。

---

## 二、方案设计

### 2.1 核心思路

在 `MultiFactorBacktest` 中新增字段 `_current_factor_percentiles` 用于存储当前调仓日各股票的因子百分位得分，在 `_rebalance()` 调用 `_buy()` 时将这些得分一并传入，存入 `TradeDetail` 的扩展字段中。

### 2.2 数据结构变更

#### 2.2.1 TradeDetail 扩展

在 `portfolio/multi_stock_backtest.py` 的 `TradeDetail` 数据类中新增字段：

```python
@dataclass
class TradeDetail:
    # ... 现有字段 ...
    
    # 新增：因子百分位得分（买入时记录）
    factor_percentiles: Dict[str, float] = field(default_factory=dict)
    # 格式示例：{'roe': 85.5, 'pe': 62.3, 'momentum_20': 78.1, ...}
    
    composite_score: float = 0.0  # 综合得分
    rank: int = 0  # 当日排名
```

#### 2.2.2 MultiFactorBacktest 新增字段

```python
class MultiFactorBacktest(MultiStockBacktest):
    # ... existing fields ...
    
    # 新增：当前调仓日的因子百分位得分
    _current_factor_percentiles: Dict[str, Dict[str, float]] = {}
    # 格式：{symbol: {factor_name: percentile_score}}
    
    _current_composite_scores: Dict[str, float] = {}
```

### 2.3 关键方法修改

#### 2.3.1 `_generate_factor_signals()` 修改

在调用 `signal_generator.generate_ranking_signals()` 之后，额外保存因子百分位得分：

```python
def _generate_factor_signals(self, date, stock_data):
    # ... 构建因子面板 ...
    
    # 计算百分位得分（如果尚未缓存）
    if date not in self._factor_percentiles_cache:
        percentiles = self.signal_generator._calculate_percentile_scores(factor_panel)
        self._factor_percentiles_cache[date] = percentiles
    
    # 生成排名信号
    signals = self.signal_generator.generate_ranking_signals(factor_panel, top_n=top_n)
    
    return signals
```

#### 2.3.2 `_rebalance()` 修改

在调用 `_buy()` 前，从缓存中取出因子得分传入：

```python
def _rebalance(self, date, prices):
    # ... 选出候选股票 ...
    
    # 获取因子百分位得分
    percentiles = self._factor_percentiles_cache.get(date, {})
    composite_scores = self._current_composite_scores
    
    # 分配仓位并买入
    for alloc in allocations:
        if alloc.symbol in prices and alloc.weight > 0:
            # 传入因子得分
            factor_scores = percentiles.get(alloc.symbol, {})
            composite = composite_scores.get(alloc.symbol, 0)
            rank = sorted_composite_scores.index(alloc.symbol) + 1
            
            self._buy(
                alloc.symbol, date, price, buy_shares, 
                total_assets, "调仓买入",
                factor_percentiles=factor_scores,
                composite_score=composite,
                rank=rank
            )
```

#### 2.3.3 `_buy()` 方法重载

在 `MultiFactorBacktest` 中重写 `_buy()` 方法，支持新增参数：

```python
def _buy(self, symbol, date, price, quantity, total_assets, 
         reason="", factor_percentiles=None, composite_score=0, rank=0):
    # ... 执行买入逻辑（调用父类）...
    
    # 扩展 TradeDetail 记录
    if symbol in self.active_trades:
        self.active_trades[symbol].factor_percentiles = factor_percentiles or {}
        self.active_trades[symbol].composite_score = composite_score
        self.active_trades[symbol].rank = rank
```

#### 2.3.4 `get_trade_details_df()` 修改

扩展交易明细表格，添加因子得分列：

```python
def get_trade_details_df(self) -> pd.DataFrame:
    # ... 现有逻辑 ...
    
    # 添加因子得分列
    for factor in self.factor_names:
        col_name = f'{factor}_得分'
        records[i][col_name] = td.factor_percentiles.get(factor, None)
    
    records[i]['综合得分'] = td.composite_score
    records[i]['排名'] = td.rank
```

---

## 三、UI 展示方案

### 3.1 交易明细表格扩展

在「交易明细」标签页的表格中，新增以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| ROE得分 | ROE因子百分位 | 85.5 |
| PE得分 | 市盈率因子百分位 | 62.3 |
| Momentum得分 | 20日动量百分位 | 78.1 |
| ... | 其他因子列 | ... |
| 综合得分 | IC加权综合得分 | 76.4 |
| 排名 | 当日选股排名 | 2 |

### 3.2 展开详情

在表格中每行添加「查看详情」展开功能，显示：
- 各因子得分的雷达图
- 与当日入选股票的对比
- 买入理由说明

---

## 四、文件修改清单

| 文件 | 修改内容 |
|------|---------|
| `portfolio/multi_stock_backtest.py` | TradeDetail 新增字段 |
| `portfolio/multi_factor_backtest.py` | 新增 `_factor_percentiles_cache`；重写 `_buy`；修改 `_rebalance` |
| `portfolio/factor_signal_generator.py` | 暴露 `_calculate_percentile_scores` 公开方法 |
| `web/factor_backtest_page.py` | 扩展 `_render_trade_details` 展示因子得分列 |

---

## 五、注意事项

1. **向后兼容**：TradeDetail 新增字段有默认值，不影响现有代码
2. **性能考虑**：因子百分位得分缓存占用内存不大，可接受
3. **方向因子**：PE/PB/debt_ratio 等负向因子，得分越高反而可能意味着因子值越差，UI 需要特殊标识（如用绿色表示好，红色表示差）
4. **历史数据**：方案只记录新回测的买入因子得分，历史已有的 TradeDetail 没有这些字段，表格需兼容处理

---

## 六、预期效果

回测完成后，在「交易明细」标签页中：

```
股票 | 买入日期 | 买入价格 | ... | ROE得分 | PE得分 | Momentum得分 | 综合得分 | 排名
------|----------|----------|------|---------|--------|--------------|----------|----
600519 | 2023-02-15 | 1850.0 | ... | 92.3 | 45.2 | 88.7 | 78.5 | 1
000001 | 2023-02-20 | 12.5 | ... | 65.8 | 78.1 | 55.3 | 62.4 | 3
```

点击展开后可看到雷达图对比。