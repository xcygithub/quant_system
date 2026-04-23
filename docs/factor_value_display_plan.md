# 多因子回测 - 每只股票各因子值展示方案

## 需求背景

当前多因子回测系统在「交易明细」中只展示交易结果（买入价、卖出价、收益率），用户无法看到：

1. **买入时各因子的原始值** —— 如 ROE 是多少、PE 是多少
2. **买入时各因子的百分位得分** —— 如 ROE 在所有股票中排前 15%
3. **综合得分与排名** —— 当日选股时这只股票的加权总分和排名
4. **调仓日全部候选股票的因子对比** —— 当天被评估了哪些股票、各股票因子值如何

本方案解决上述四个层面的展示需求。

---

## 一、现有数据流分析

### 1.1 因子数据流

```
_factor_panel = _build_factor_panel(date, stock_data)
    │  DataFrame(index=symbol, columns=factor_raw_values)
    │  例: index=['000001.SZ','600000.SH'], columns=['roe','pe','momentum_20']
    ▼
signal_generator._calculate_percentile_scores(factor_panel)
    │  {symbol: {factor_name: percentile_score}}
    │  例: {'000001.SZ': {'roe': 85.5, 'pe': 62.3, ...}}
    ▼
signal_generator._calculate_combined_scores(percentile_scores)
    │  {symbol: combined_score}
    │  例: {'000001.SZ': 76.4, '600000.SH': 58.2, ...}
    ▼
排序取前 N → generate_ranking_signals() → {symbol: 1/0}
```

### 1.2 交易记录流

```
_rebalance(date, prices)
    ├─ _select_candidates()  → StockScore 列表（仅含综合得分）
    ├─ position_sizer.allocate() → 仓位分配
    └─ _buy(symbol, ...) → 创建 TradeDetail（无因子信息）
```

### 1.3 关键发现

- `FactorSignalGenerator` 已计算百分位得分和综合得分，但中间结果未保存
- `TradeDetail` 只记录交易信息，不记录因子信息
- `_rebalance()` 执行买入时，因子面板数据仍在内存中，但未传入 `_buy()`

---

## 二、方案设计

### 2.1 展示维度定义

| 维度 | 说明 | 示例 |
|------|------|------|
| 因子原始值 | 因子的真实数值 | ROE=15.2%, PE=12.5, momentum_20=8.3% |
| 因子百分位得分 | 该因子在所有股票中的横截面排名（0-100） | ROE得分=85.5（前14.5%） |
| 综合得分 | IC加权后的总分（0-100） | 综合得分=76.4 |
| 排名 | 当日选股排序 | 排名=2（当日第2名） |
| 调仓面板 | 调仓日全部候选股票的因子对比 | 见下方表格展示 |

### 2.2 数据结构扩展

#### 2.2.1 TradeDetail 扩展（`portfolio/multi_stock_backtest.py`）

```python
@dataclass
class TradeDetail:
    # ... 现有字段不变 ...

    # ===== 新增：买入时因子信息 =====
    # 因子原始值 {factor_name: raw_value}
    factor_values: Dict[str, float] = field(default_factory=dict)
    # 例: {'roe': 0.152, 'pe': 12.5, 'momentum_20': 0.083}

    # 因子百分位得分 {factor_name: percentile}
    factor_percentiles: Dict[str, float] = field(default_factory=dict)
    # 例: {'roe': 85.5, 'pe': 62.3, 'momentum_20': 78.1}

    # 综合得分与排名
    composite_score: float = 0.0   # IC加权综合得分
    rank: int = 0                   # 当日排名（1=第1名）
    total_candidates: int = 0       # 当日候选股票总数
```

**向后兼容**：所有新增字段均有默认值，不影响现有代码。

#### 2.2.2 新增：调仓日快照（`portfolio/multi_factor_backtest.py`）

```python
@dataclass
class RebalanceSnapshot:
    """调仓日快照：记录每次调仓时的完整因子面板"""
    date: str
    # 全部候选股票的综合得分 {symbol: score}
    all_scores: Dict[str, float] = field(default_factory=dict)
    # 全部候选股票的因子原始值 {symbol: {factor: value}}
    all_factor_values: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # 全部候选股票的因子百分位 {symbol: {factor: percentile}}
    all_factor_percentiles: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # 最终买入的股票列表
    selected_symbols: List[str] = field(default_factory=list)
    # 最终卖出的股票列表
    sold_symbols: List[str] = field(default_factory=list)
```

#### 2.2.3 MultiFactorBacktest 新增字段

```python
class MultiFactorBacktest(MultiStockBacktest):
    # ... 现有字段 ...

    # 调仓日快照列表
    rebalance_snapshots: List[RebalanceSnapshot] = field(default_factory=list)

    # 每日因子面板缓存（用于回溯查询）
    _factor_panel_cache: Dict[str, pd.DataFrame] = {}
    # 格式: {date_str: DataFrame(index=symbol, columns=factor_names)}

    # 每日因子百分位缓存
    _factor_percentiles_cache: Dict[str, Dict[str, Dict[str, float]]] = {}
    # 格式: {date_str: {symbol: {factor: percentile}}}

    # 每日综合得分缓存
    _composite_scores_cache: Dict[str, Dict[str, float]] = {}
    # 格式: {date_str: {symbol: score}}
```

---

## 三、关键方法修改

### 3.1 `_generate_factor_signals()` 修改

在生成信号的同时，缓存中间计算结果：

```python
def _generate_factor_signals(self, date: str, stock_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
    # 构建因子面板
    factor_panel = self._build_factor_panel(date, stock_data)
    if factor_panel.empty:
        return {}

    # ===== 新增：缓存因子面板 =====
    self._factor_panel_cache[date] = factor_panel.copy()

    # 计算百分位得分
    percentile_scores = self.signal_generator._calculate_percentile_scores(factor_panel)
    self._factor_percentiles_cache[date] = percentile_scores

    # 计算综合得分
    combined_scores = self.signal_generator._calculate_combined_scores(percentile_scores)
    self._composite_scores_cache[date] = combined_scores

    # 生成排名信号（原有逻辑）
    top_n = self.max_positions
    raw_signals = self.signal_generator.generate_ranking_signals(factor_panel, top_n=top_n)

    # 转换为信号序列
    signals = {}
    for symbol, signal in raw_signals.items():
        signals[symbol] = pd.Series([signal], index=[date])

    return signals
```

### 3.2 `_rebalance()` 修改

在调仓时创建快照，并将因子信息传入 `_buy()`：

```python
def _rebalance(self, date, prices: Dict[str, float]):
    # ... 原有逻辑：选出候选、计算目标持仓 ...

    # ===== 新增：创建调仓快照 =====
    snapshot = RebalanceSnapshot(date=date)

    # 记录全部候选股票的因子信息
    if date in self._composite_scores_cache:
        snapshot.all_scores = self._composite_scores_cache[date]
    if date in self._factor_panel_cache:
        panel = self._factor_panel_cache[date]
        for symbol in panel.index:
            snapshot.all_factor_values[symbol] = {
                f: panel.loc[symbol, f]
                for f in self.factor_names if f in panel.columns
            }
    if date in self._factor_percentiles_cache:
        snapshot.all_factor_percentiles = self._factor_percentiles_cache[date]

    # 记录卖出股票
    snapshot.sold_symbols = list(to_sell)

    # ... 原有逻辑：分配仓位 ...

    # ===== 修改：买入时传入因子信息 =====
    for alloc in allocations:
        if alloc.symbol in prices and alloc.weight > 0:
            # 计算买入金额和股数（原有逻辑）
            target_amount = total_assets * alloc.weight
            current_holding = self.positions[alloc.symbol].market_value if alloc.symbol in self.positions else 0
            buy_amount_needed = target_amount - current_holding

            if buy_amount_needed <= 0:
                continue

            price = prices[alloc.symbol]
            buy_shares = int(buy_amount_needed / price / 100) * 100
            if buy_shares < 100:
                continue

            # 获取该股票的因子信息
            factor_values = {}
            factor_percentiles = {}
            composite_score = 0.0
            rank = 0

            if date in self._factor_panel_cache:
                panel = self._factor_panel_cache[date]
                if alloc.symbol in panel.index:
                    factor_values = {
                        f: panel.loc[alloc.symbol, f]
                        for f in self.factor_names if f in panel.columns
                    }

            if date in self._factor_percentiles_cache:
                percs = self._factor_percentiles_cache[date]
                factor_percentiles = percs.get(alloc.symbol, {})

            if date in self._composite_scores_cache:
                scores = self._composite_scores_cache[date]
                composite_score = scores.get(alloc.symbol, 0)
                # 计算排名
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                for i, (sym, _) in enumerate(sorted_scores):
                    if sym == alloc.symbol:
                        rank = i + 1
                        break

            # 执行买入（传入因子信息）
            self._buy_multi_factor(
                alloc.symbol, date, price, buy_shares, total_assets, "调仓买入",
                factor_values=factor_values,
                factor_percentiles=factor_percentiles,
                composite_score=composite_score,
                rank=rank,
                total_candidates=len(snapshot.all_scores)
            )

            snapshot.selected_symbols.append(alloc.symbol)

    # 保存调仓快照
    self.rebalance_snapshots.append(snapshot)
    self.last_rebalance_day = self.trading_days
```

### 3.3 新增 `_buy_multi_factor()` 方法

在 `MultiFactorBacktest` 中新增专用买入方法：

```python
def _buy_multi_factor(
    self,
    symbol: str,
    date,
    price: float,
    quantity: int,
    total_assets: float,
    reason: str = "",
    factor_values: Dict[str, float] = None,
    factor_percentiles: Dict[str, float] = None,
    composite_score: float = 0.0,
    rank: int = 0,
    total_candidates: int = 0
):
    """
    多因子专用买入方法
    调用父类 _buy() 执行实际买入，然后补充因子信息到 TradeDetail
    """
    # 调用父类买入（执行实际交易逻辑）
    super()._buy(symbol, date, price, quantity, total_assets, reason)

    # 补充因子信息到 active_trades
    if symbol in self.active_trades:
        td = self.active_trades[symbol]
        td.factor_values = factor_values or {}
        td.factor_percentiles = factor_percentiles or {}
        td.composite_score = composite_score
        td.rank = rank
        td.total_candidates = total_candidates
```

### 3.4 `_calculate_results()` 扩展

在回测结果中增加调仓快照：

```python
def _calculate_results(self, dates: List) -> Dict[str, Any]:
    # ... 原有计算逻辑 ...

    results = {
        # ... 原有字段 ...
        'trade_details': self.get_trade_details_df(),
        # ===== 新增 =====
        'rebalance_snapshots': self._get_rebalance_snapshots_df(),
        'factor_names': self.factor_names,
    }

    return results
```

---

## 四、UI 展示方案

### 4.1 交易明细表格扩展

在「交易明细」标签页的表格中，在现有列之后新增因子相关列：

| 新增列 | 说明 | 格式 |
|--------|------|------|
| ROE | 买入时ROE原始值 | 15.2% |
| PE | 买入时PE原始值 | 12.5 |
| Momentum | 买入时20日动量 | 8.3% |
| ... | 其他因子原始值 | ... |
| ROE得分 | ROE百分位得分 | 85.5 |
| PE得分 | PE百分位得分 | 62.3 |
| ... | 其他因子得分 | ... |
| 综合得分 | IC加权总分 | 76.4 |
| 排名 | 当日排名 | 2 / 50 |

**实现要点**：
- 因子原始值列和百分位得分列可折叠（默认只显示百分位得分）
- 使用 `st.expander()` 让用户选择显示哪些因子
- 负向因子（PE/PB/负债率）的得分用颜色标识：高分=绿色（便宜），低分=红色（贵）

### 4.2 交易明细展开详情

点击每行交易记录的「查看详情」展开后显示：

**（1）因子雷达图**

使用 Plotly 绘制雷达图，展示该股票买入时各因子百分位得分：

```python
fig = go.Figure(data=go.Scatterpolar(
    r=[85.5, 62.3, 78.1, 45.2, 88.0],  # 各因子得分
    theta=['ROE', 'PE', '动量', '营收增长', '负债率'],  # 因子名
    fill='toself',
    name='该股票'
))
fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])))
```

**（2）与当日平均水平的对比**

表格展示该股票 vs 当日全部候选股票的均值：

| 因子 | 该股票得分 | 当日平均 | 差值 |
|------|-----------|---------|------|
| ROE | 85.5 | 50.0 | +35.5 |
| PE | 62.3 | 50.0 | +12.3 |
| 动量 | 78.1 | 50.0 | +28.1 |

**（3）买入理由说明**

根据因子得分自动生成文字说明：

> "该股票 ROE 得分 85.5（前14.5%），动量得分 78.1（前21.9%），综合排名第 2 位，被选中买入。"

### 4.3 新增「调仓记录」标签页

在回测结果中新增一个标签页，展示每次调仓的完整信息：

**（1）调仓时间轴**

列出每次调仓的日期和动作：

| 调仓日期 | 买入股票 | 卖出股票 | 持仓数量 |
|---------|---------|---------|---------|
| 2023-02-15 | 600519, 000001 | 600000 | 5只 |
| 2023-02-22 | 601318 | 000001 | 5只 |

**（2）单次调仓的因子面板表格**

选择某次调仓后，展示当日全部候选股票的因子值：

| 股票 | 综合得分 | 排名 | ROE | PE | 动量 | 是否买入 |
|------|---------|------|-----|-----|------|---------|
| 600519 | 92.3 | 1 | 18.5% | 25.3 | 12.1% | 是 |
| 000001 | 85.6 | 2 | 12.1% | 8.5 | 5.3% | 是 |
| 600000 | 45.2 | 8 | 8.5% | 5.2 | -2.1% | 否 |

**高亮显示**：买入的股票行用绿色背景，卖出的用红色背景。

**（3）因子得分热力图**

对单次调仓的全部候选股票，绘制因子得分热力图：

```
        ROE得分  PE得分  动量得分  营收增长得分
600519   92.3    45.2    88.7      78.1
000001   65.8    78.1    55.3      62.4
600000   42.1    88.5    35.2      48.6
...
```

使用颜色映射：高分=深绿，低分=深红。

### 4.4 因子暴露度增强

在现有「因子分析」标签页的「因子暴露度时序」中，增加一个子图：

**持仓股票的因子原始值时序**

对当前持仓的每只股票，绘制各因子原始值随时间变化：

```python
# 子图1：组合因子暴露度（已有）
# 子图2：持仓股票ROE时序
for symbol in current_holdings:
    fig.add_trace(go.Scatter(x=dates, y=roe_values[symbol], name=symbol))
```

---

## 五、文件修改清单

| 文件 | 修改内容 |
|------|---------|
| `portfolio/multi_stock_backtest.py` | TradeDetail 新增 `factor_values`, `factor_percentiles`, `composite_score`, `rank`, `total_candidates` 字段 |
| `portfolio/multi_factor_backtest.py` | 新增 `RebalanceSnapshot` 数据类；新增 `_factor_panel_cache`、`_factor_percentiles_cache`、`_composite_scores_cache`；新增 `_buy_multi_factor()`；修改 `_generate_factor_signals()` 缓存中间结果；修改 `_rebalance()` 创建快照并传入因子信息；修改 `_calculate_results()` 返回调仓快照 |
| `web/factor_backtest_page.py` | 扩展 `_render_trade_details()` 展示因子列和雷达图；新增 `_render_rebalance_history()` 调仓记录标签页；在结果标签页中新增「调仓记录」标签 |

---

## 六、实施优先级

| 优先级 | 内容 | 说明 |
|--------|------|------|
| P0 | TradeDetail 扩展 + `_buy_multi_factor()` | 核心数据层，所有展示的基础 |
| P0 | `_generate_factor_signals()` 缓存 + `_rebalance()` 修改 | 确保因子信息能被记录 |
| P1 | 交易明细表格扩展（原始值 + 百分位得分 + 综合得分 + 排名） | 最直观的展示 |
| P1 | 交易明细展开详情（雷达图 + 对比表 + 文字说明） | 深入分析单只股票 |
| P2 | 新增「调仓记录」标签页（时间轴 + 因子面板表 + 热力图） | 全局视角看每次调仓 |
| P2 | 因子原始值时序图 | 跟踪持仓股票因子变化 |

---

## 七、注意事项

1. **向后兼容**：TradeDetail 新增字段均有默认值，不影响旧回测结果。旧数据在表格中因子列显示为空即可。

2. **方向因子展示**：PE、PB、debt_ratio 等负向因子，百分位得分的含义与正向因子相反：
   - 高分 = 因子值差（如 PE 很高 = 很贵）
   - 低分 = 因子值好（如 PE 很低 = 很便宜）
   - UI 中应使用颜色区分：正向因子高分=绿，负向因子高分=红

3. **内存占用**：缓存每日因子面板会占用一定内存。假设 50 只股票 × 250 交易日 × 10 因子 ≈ 10MB，可接受。若股票数多，可在回测结束后清理缓存。

4. **缓存清理策略**：在 `run()` 方法结束时调用 `_clear_caches()` 释放内存。

5. **性能影响**：缓存操作只是字典赋值，对回测性能影响可忽略。

---

## 八、预期效果

回测完成后，用户可以在以下位置看到因子值：

**交易明细表格**：
```
股票   | 买入日期   | 买入价格 | ... | ROE  | PE   | 动量 | ROE得分 | PE得分 | 动量得分 | 综合得分 | 排名
-------|-----------|---------|-----|------|------|------|---------|--------|----------|----------|----
600519 | 2023-02-15 | 1850.0 | ... | 18.5%| 25.3 | 12.1%| 92.3    | 45.2   | 88.7     | 78.5     | 1/50
000001 | 2023-02-20 | 12.5   | ... | 12.1%| 8.5  | 5.3% | 65.8    | 78.1   | 55.3     | 62.4     | 3/50
```

**调仓记录**：
```
2023-02-15 调仓：
  买入: 600519(综合得分92.3, 排名1), 000001(综合得分85.6, 排名2)
  卖出: 600000(综合得分45.2, 排名8)
  候选股票总数: 50只
```

点击展开后可以看到完整的因子面板对比和雷达图。

---

*文档版本：v1.0*
*制定日期：2026-04-22*
