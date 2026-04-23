# 多因子回测：模拟因子数据替换真实数据方案

## 一、现状诊断

### 1.1 模拟数据来源定位

当前系统中，因子数据模拟生成集中在两个位置：

**位置 A：`web/factor_backtest_page.py` 第 457-506 行 `_prepare_factor_data()`**

该函数是 Web 界面调用多因子回测的入口，为每只股票生成每日因子 DataFrame。其中：

| 因子 | 当前实现 | 真实度 |
|------|----------|--------|
| `roe` | `np.random.uniform(0.05, 0.25)` | 完全模拟 |
| `pe` | `np.random.uniform(5, 30)` | 完全模拟 |
| `pb` | `np.random.uniform(0.5, 5)` | 完全模拟 |
| `revenue_growth` | `np.random.uniform(-0.2, 0.5)` | 完全模拟 |
| `debt_ratio` | `np.random.uniform(0.2, 0.8)` | 完全模拟 |
| `turnover_rate` | `np.random.uniform(0.5, 10)` | 完全模拟 |
| `volume_ratio` | `np.random.uniform(0.5, 3)` | 完全模拟 |
| `momentum_20` | `df['close'].pct_change().rolling(20).sum()` | 真实计算 |

**位置 B：`portfolio/multi_factor_backtest.py` 第 565-584 行测试数据生成**

`__main__` 测试块同样使用 `np.random` 生成 roe/pe/pb/revenue_growth 等基本面因子。

### 1.2 影响范围

- 所有通过 Web 界面执行的多因子回测，基本面因子信号均为随机数
- IC 加权逻辑虽然框架完整，但输入的因子值无真实预测能力
- 回测结果（收益曲线、交易信号）反映的是随机噪声而非真实因子 alpha
- 因子暴露度跟踪、收益归因报告建立在无意义数据上

---

## 二、已有基础设施盘点

### 2.1 真实数据源

| 组件 | 路径 | 能力 | 状态 |
|------|------|------|------|
| `FinancialDataSource` | `data/financial_data_source.py` | Baostock 财务数据获取（利润表/资产负债表/现金流量表/杜邦分析/成长/营运/偿债/估值） | 已实现 |
| `FinancialDataSaver` | `data/financial_data_saver.py` | 将财务数据持久化到 SQLite 8 张表 | 已实现 |
| `FinancialDataManager` | `data/financial_data_manager.py` | 统一接口：update/read/valuation/freshness | 已实现 |
| `FundamentalFactors` | `strategy/fundamental_factors.py` | 从数据库财务数据计算 20+ 基本面因子 | 已实现 |
| `FactorData` | `data/factor_data.py` | 从 K 线计算技术指标（动量/波动率/RSI/MACD/布林带/KDJ 等） | 已实现 |

### 2.2 数据库表结构

已有 8 张财务数据表：

- `profit_data`：利润表（eps, roe, net_profit, business_income, gross_profit_rate, net_profit_ratio...）
- `balance_data`：资产负债表（total_assets, total_equity, debt_ratio, current_ratio, quick_ratio...）
- `cash_flow_data`：现金流量表（oper_cash_flow, invest_cash_flow...）
- `dupont_data`：杜邦分析（roe, asset_turnover, equity_multiplier, net_profit_margin...）
- `growth_data`：成长能力
- `operation_data`：营运能力
- `debtpaying_data`：偿债能力
- `valuation_data`：估值数据（pe, pb, ps, pcf, market_cap, total_shares...）

### 2.3 因子计算能力矩阵

`FundamentalFactors.calculate_all_factors()` 已能计算：

- 估值：pe, pe_ttm, pb, ps, pcf
- 盈利：roe, roe_avg, roa, gross_margin, net_margin, eps_ttm
- 成长：revenue_growth, profit_growth, equity_growth, profit_cagr
- 财务结构：debt_ratio, current_ratio, quick_ratio, equity_multiplier
- 现金流：cash_to_profit, fcf, cash_yield
- 衍生：pb_roe, pe_growth, altman_z

`FactorData.calculate_all_factors()` 已能计算：

- 趋势：sma_5/10/20/60, ema, macd, 布林带
- 动量：momentum_20/60, rsi_14/6, kdj, cci, williams_r
- 波动率：atr, volatility_20/60
- 成交量：obv, vwap, volume_ratio, volume_sma_20
- 自定义：mean_reversion_20, trend_strength_20, volatility_regime

---

## 三、核心难点：财报数据与交易日期的对齐

### 3.1 问题本质

财务数据按**报告期**发布（如 2024-03-31 一季报），但回测需要每个**交易日**的因子值。一个关键约束是：**财报发布前，市场不应使用该期财报数据**。

例如：
- 2024 年一季报报告期为 2024-03-31
- 实际发布日（pub_date）可能是 2024-04-25
- 在 2024-04-25 之前的回测中，不应使用 2024Q1 的数据
- 2024-04-25 至 2024-08-31（中报发布前），应使用 2024Q1 数据

### 3.2 当前 `FundamentalFactors` 的处理方式

当前实现（`calculate_all_factors`）只取**最新可用**的财务数据，不区分报告期和发布日，也不做每日展开。这适用于"获取今天因子值"的场景，但不适用于**历史回测每日展开**场景。

---

## 四、替换方案（分阶段）

### 阶段一：数据层——建立"每日因子面板"生成能力（优先级：P0）

#### 4.1.1 新增 `FactorPanelBuilder` 类

位置：`data/factor_panel_builder.py`（新增文件）

职责：将财务数据（按报告期）展开为每个交易日的因子面板，处理发布日延迟。

```
输入：
  - symbols: 股票列表
  - start_date, end_date: 回测区间
  - factor_names: 需要的因子列表
  - use_pub_date: 是否考虑发布日延迟（默认 True）

输出：
  - factor_data: Dict[str, pd.DataFrame]
    key = symbol
    value = DataFrame(index=trade_date, columns=factor_names)
```

核心逻辑：

1. **读取财务数据**：对每个 symbol，从 `profit_data`/`balance_data`/`cash_flow_data`/`dupont_data`/`valuation_data` 读取回测区间内的所有报告期数据
2. **发布日对齐**：利用 `profit_data.pub_date` 字段，确定每期财报的可用起始日。若 `pub_date` 缺失，使用报告期 + 90 天作为保守估计
3. **前向填充（Forward Fill）**：对每条时间线，从可用起始日开始，因子值保持不变，直到下一期财报发布
4. **技术指标计算**：对每个 symbol 的 K 线数据，用 `FactorData` 计算 `momentum_20`/`volatility_20`/`volume_ratio`/`turnover_rate` 等技术因子
5. **合并输出**：将基本面因子和技术因子按日期对齐，合并为统一的每日因子面板

#### 4.1.2 关键实现细节

**发布日延迟处理**：

```python
def _get_factor_effective_dates(report_date: str, pub_date: str = None) -> str:
    """
    确定某期财报因子值的有效起始日期
    规则：使用发布日；若发布日缺失，报告期+90天作为保守估计
    """
    if pub_date and pub_date > report_date:
        return pub_date
    # 保守估计：年报+120天，季报+90天
    report_dt = datetime.strptime(report_date, '%Y-%m-%d')
    offset = 120 if report_date.endswith('-12-31') else 90
    return (report_dt + timedelta(days=offset)).strftime('%Y-%m-%d')
```

**前向填充示例**：

| 报告期 | 发布日 | ROE | 有效区间 |
|--------|--------|-----|----------|
| 2023-09-30 | 2023-10-28 | 8.5% | 2023-10-28 ~ 2024-01-29 |
| 2023-12-31 | 2024-04-20 | 12.0% | 2024-04-20 ~ 2024-08-29 |
| 2024-03-31 | 2024-04-25 | 3.2% | 2024-04-25 ~ ... |

**估值因子的特殊处理**：

PE/PB/PS 等估值因子需要每日股价。方案：
1. 从 `valuation_data` 获取每日估值（Baostock 提供每日估值数据）
2. 若 valuation_data 缺失某交易日，用最新可用估值 + 当前股价 重新计算
3. 兜底：用 `股价 / 最新 EPS_TTM` 计算 PE_TTM

**换手率（turnover_rate）处理**：

Baostock 的 `valuation_data` 通常包含换手率字段。若缺失，可用 K 线数据估算：
```
turnover_rate = volume / float_shares * 100
```
需要 `float_shares`（流通股本），可从 `valuation_data.total_shares` 近似，或从 Baostock 获取。

### 阶段二：接口层——替换 `_prepare_factor_data()`（优先级：P0）

#### 4.2.1 修改 `web/factor_backtest_page.py`

将 `_prepare_factor_data()` 从"模拟生成"改为"真实读取"：

```python
def _prepare_factor_data(
    stock_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
    start_date: str,
    end_date: str,
    dm: DataManager = None
) -> Dict[str, pd.DataFrame]:
    """
    准备因子数据（真实数据版本）
    """
    from data.factor_panel_builder import FactorPanelBuilder

    symbols = list(stock_data.keys())

    # 1. 构建因子面板
    builder = FactorPanelBuilder(db_path='C:/Users/FY/WorkBuddy/Claw/quant_data.db')
    factor_panel = builder.build_panel(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        factor_names=factor_names
    )

    # 2. 与 stock_data 的日期对齐
    factor_data = {}
    for symbol, df in stock_data.items():
        if symbol in factor_panel:
            panel_df = factor_panel[symbol]
            # 确保日期列格式一致
            panel_df['date'] = panel_df.index.strftime('%Y-%m-%d')
            factor_data[symbol] = panel_df.reset_index(drop=True)
        else:
            #  Fallback：对该股票用模拟数据（日志警告）
            factor_data[symbol] = _generate_mock_factors(df, factor_names)

    return factor_data
```

#### 4.2.2 数据预加载策略

财务数据获取是网络 I/O 密集型操作（Baostock 限流 1 秒/次）。回测前需确保数据已在本地数据库：

```python
def _ensure_financial_data(symbols: List[str], start_year: int):
    """回测前检查并预加载财务数据"""
    fdm = FinancialDataManager()
    for symbol in symbols:
        freshness = fdm.get_data_freshness(symbol)
        # 若数据缺失或不新鲜，触发更新
        if not all(info['is_fresh'] for info in freshness.values()):
            fdm.update_single_stock(symbol, start_year=start_year)
    fdm.close()
```

在 `_execute_backtest()` 中加入数据预检查步骤：
1. 获取股票数据前，先检查财务数据新鲜度
2. 对缺失/不新鲜的股票，后台触发 `FinancialDataManager.batch_update()`
3. 使用进度条展示"正在更新财务数据..."

### 阶段三：回测引擎层——替换 `multi_factor_backtest.py` 测试数据（优先级：P1）

#### 4.3.1 修改 `__main__` 测试块

将测试用的 `np.random` 数据替换为从数据库读取的真实数据：

```python
if __name__ == "__main__":
    from data.factor_panel_builder import FactorPanelBuilder
    from data.data_manager import DataManager

    dm = DataManager()
    symbols = ['000001.SZ', '600000.SH', '600519.SH', '600016.SH', '601318.SH']
    start_date, end_date = '2023-01-01', '2023-06-30'

    # 获取真实 K 线数据
    stock_data = {}
    for symbol in symbols:
        df = dm.get_daily_kline(symbol, start_date, end_date)
        if not df.empty:
            stock_data[symbol] = df

    # 获取真实因子数据
    builder = FactorPanelBuilder()
    factor_data = builder.build_panel(symbols, start_date, end_date)

    # 运行回测
    results = run_multi_factor_backtest(
        symbols=symbols,
        stock_data=stock_data,
        factor_data=factor_data,
        ...
    )
```

### 阶段四：IC 统计层——从模拟 IC 切换到真实 IC 计算（优先级：P1）

#### 4.4.1 问题

当前 `FactorICConfigurator` 从 `ic_statistics` / `ic_analysis` 表读取 IC 统计，但这些表目前为空（或只有测试数据）。空表时系统回退到基础权重，不影响回测执行，但无法发挥"IC 智能加权"的价值。

#### 4.4.2 方案

**短期**：IC 加权暂时使用基础权重（当前行为不变），在方案文档中标记为"后续优化"。

**中期**：实现 `ICStatsCalculator.calculate_and_save_ic_stats()` 的批量运行：
1. 用历史真实因子面板 + 未来收益率，逐日计算每个因子的 IC 值
2. 将 IC 序列保存到 `ic_analysis` 表
3. 定期（每周/每月）运行 IC 统计更新任务

这是一个独立的后台任务，不影响本替换方案的核心流程。

---

## 五、数据流全景图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         多因子回测数据流                               │
└──────────────────────────────────────────────────────────────────────┘

  用户操作
     │
     ▼
┌─────────────────┐
│  Web 界面       │  选择股票池、因子、权重、回测区间
│  factor_backtest│
│  _page.py       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│ _execute_backtest()     │────▶│ _ensure_financial_data() │  检查/预加载财务数据
│                         │     │ (FinancialDataManager)   │
└────────┬────────────────┘     └──────────────────────────┘
         │
         ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│ _fetch_stock_data()     │────▶│ DataManager.get_daily_   │  获取 K 线数据
│                         │     │ kline()                  │
└────────┬────────────────┘     └──────────────────────────┘
         │
         ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│ _prepare_factor_data()  │────▶│ FactorPanelBuilder.      │  生成每日因子面板
│ （替换后）               │     │ build_panel()            │  （核心新增）
└────────┬────────────────┘     └──────────────────────────┘
         │                           ▲
         │                           │ 读取
         ▼                           │
┌─────────────────────────┐     ┌───┴──────────────────────┐
│ run_multi_factor_       │     │  SQLite 数据库            │
│ backtest()              │◄────│  profit_data/balance_    │
│                         │     │  data/cash_flow_data/    │
│  ├─ MultiFactorBacktest │     │  dupont_data/valuation_  │
│  │   ├─ set_data()      │     │  data                    │
│  │   ├─ _build_factor_  │     └──────────────────────────┘
│  │   │   panel()        │
│  │   ├─ _generate_      │
│  │   │   factor_signals │
│  │   └─ run()           │
│  └─ 回测结果            │
└─────────────────────────┘
```

---

## 六、实施优先级与工作量评估

| 阶段 | 内容 | 优先级 | 预估工作量 | 依赖 |
|------|------|--------|-----------|------|
| 1 | 新增 `FactorPanelBuilder` 类 | P0 | 2-3 天 | 无 |
| 2 | 修改 `_prepare_factor_data()` 调用 | P0 | 0.5 天 | 阶段 1 |
| 3 | 数据预加载逻辑集成到 `_execute_backtest` | P0 | 0.5 天 | 无 |
| 4 | 修改 `multi_factor_backtest.py` 测试块 | P1 | 0.5 天 | 阶段 1 |
| 5 | 边界情况处理（缺失数据/不新鲜数据）| P1 | 1 天 | 阶段 1-3 |
| 6 | 验证测试（对比模拟 vs 真实数据回测结果）| P1 | 1 天 | 阶段 1-5 |
| 7 | IC 统计真实计算（后台任务）| P2 | 2 天 | 阶段 1 |

**总计核心工作量：约 4-5 天（阶段 1-6）**

---

## 七、边界情况与兜底策略

### 7.1 财务数据缺失

**场景**：某只股票数据库中没有财务数据（从未更新过）。

**处理**：
1. `FactorPanelBuilder` 检测缺失，记录警告日志
2. 对该股票回退到模拟数据生成（保持回测不中断）
3. Web 界面展示"X 只股票使用模拟因子数据"提示

### 7.2 数据不新鲜

**场景**：财务数据最新报告期是半年前，期间可能有新财报已发布但未更新。

**处理**：
1. `is_data_fresh()` 检测（阈值 120 天约两个季度）
2. 回测执行前自动触发 `fdm.update_single_stock()` 更新
3. Baostock 限流 1 秒/次，10 只股票约需 10-15 秒（含利润表/资产负债表/现金流量表/杜邦分析 4 次调用）

### 7.3 发布日缺失

**场景**：`profit_data.pub_date` 字段为空。

**处理**：
1. 使用报告期 + 偏移量作为保守估计：年报 +120 天，中报 +90 天，季报 +90 天
2. 这会导致回测中因子切换日期略有偏差，但不会导致使用"未来信息"（只会延迟使用，更保守）

### 7.4 估值数据缺失某交易日

**场景**：`valuation_data` 不是每个交易日都有记录。

**处理**：
1. 用最近可用估值记录前向填充
2. 若完全缺失，用 `股价 / 最新 EPS_TTM` 重新计算 PE_TTM
3. 若 EPS 也缺失，该交易日该因子标记为 NaN，信号生成时忽略

### 7.5 技术因子计算窗口不足

**场景**：回测起始日期距离数据起始不足 20 日，`momentum_20` 前 19 天为 NaN。

**处理**：
1. 技术因子保持当前 `FactorData` 的行为（rolling 自然产生 NaN）
2. `multi_factor_backtest._build_factor_panel()` 已有 `dropna` 逻辑，缺失因子的股票当日不参与选股

---

## 八、验证策略

### 8.1 单元验证

为 `FactorPanelBuilder` 编写测试：

```python
def test_panel_builder():
    builder = FactorPanelBuilder()
    panel = builder.build_panel(
        symbols=['000001.SZ'],
        start_date='2023-01-01',
        end_date='2023-06-30',
        factor_names=['roe', 'pe', 'momentum_20']
    )

    df = panel['000001.SZ']

    # 验证：每个交易日都有数据
    assert len(df) >= 100  # 约半年交易日

    # 验证：ROE 不是随机数（连续多日在财报区间内应相同）
    roe_values = df['roe'].dropna()
    assert len(roe_values) > 0
    assert roe_values.std() < 0.01 or (roe_values.nunique() <= 3)  # 半年内财报切换次数有限

    # 验证：momentum_20 基于真实价格计算
    assert df['momentum_20'].iloc[20] != 0  # 第20天后应有值
```

### 8.2 端到端验证

1. 选择 5-10 只自选股，回测区间 2023-01-01 至 2024-03-19
2. 对比"模拟因子"vs"真实因子"回测结果：
   - 模拟因子：交易信号应接近随机，组合换手率可能异常
   - 真实因子：ROE/PE 等因子应有稳定选股偏好，收益归因中各因子贡献应合理
3. 检查因子暴露度时序：真实因子的暴露度应有趋势（如价值因子暴露度持续为正），而非随机波动

### 8.3 数据一致性验证

随机抽取几个交易日的因子面板，人工核对：
- `roe` 值是否与该股票最新杜邦分析一致
- `pe` 值是否约等于 `收盘价 / eps_ttm`
- `revenue_growth` 是否与利润表同比增速一致

---

## 九、风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Baostock 接口不稳定或限速 | 数据更新慢，首次使用体验差 | 本地 SQLite 缓存，增量更新；首次预加载时显示进度条 |
| 财报发布日字段缺失/不准确 | 回测可能使用"未来信息"，导致收益高估 | 保守策略：发布日缺失时，报告期 +90 天；提供 `use_pub_date=False` 选项用于敏感性测试 |
| 估值数据（PE/PB）缺失 | 估值因子无法计算 | 用股价+财务数据自行计算 PE_TTM 作为兜底 |
| 不同股票财报发布节奏不同 | 因子面板中部分股票因子值缺失 | `dropna` 处理，缺失因子的股票当日不参与排名 |
| 历史回测数据量较大 | 内存占用高（N 股票 × M 交易日 × K 因子）| 按需加载，分批次构建面板；使用 pickle 缓存已构建的面板 |

---

## 十、附录：因子数据来源对照表

| 因子名 | 类别 | 真实数据来源 | 计算/获取方式 | 所在表 |
|--------|------|-------------|--------------|--------|
| roe | 基本面 | dupont_data.roe / profit+balance | 直接读取或 net_profit/total_equity | dupont_data |
| roa | 基本面 | profit+balance | net_profit / total_assets | 计算 |
| gross_margin | 基本面 | profit_data | gross_profit_rate | profit_data |
| net_margin | 基本面 | profit_data | net_profit_ratio | profit_data |
| eps_ttm | 基本面 | profit_data | epsTTM | profit_data |
| revenue_growth | 基本面 | profit_data | business_income 同比 | 计算 |
| profit_growth | 基本面 | profit_data | net_profit 同比 | 计算 |
| equity_growth | 基本面 | balance_data | total_equity 同比 | 计算 |
| pe | 估值 | valuation_data | 直接读取，或 price/eps_ttm | valuation_data |
| pb | 估值 | valuation_data | 直接读取 | valuation_data |
| ps | 估值 | valuation_data | 直接读取 | valuation_data |
| pcf | 估值 | valuation_data | 直接读取 | valuation_data |
| debt_ratio | 财务结构 | balance_data | debt_ratio | balance_data |
| current_ratio | 财务结构 | balance_data | current_ratio | balance_data |
| quick_ratio | 财务结构 | balance_data | quick_ratio | balance_data |
| equity_multiplier | 财务结构 | dupont_data | equity_multiplier | dupont_data |
| asset_turnover | 财务结构 | dupont_data | asset_turnover | dupont_data |
| cash_to_profit | 现金流 | cash_flow+profit | oper_cash_flow / net_profit | 计算 |
| fcf | 现金流 | cash_flow_data | oper_cash_flow（简化） | cash_flow_data |
| momentum_20 | 技术 | K 线数据 | close.pct_change().rolling(20).sum() | 计算 |
| momentum_60 | 技术 | K 线数据 | close.pct_change().rolling(60).sum() | 计算 |
| volatility_20 | 技术 | K 线数据 | close.pct_change().rolling(20).std() | 计算 |
| volume_ratio | 技术 | K 线数据 | volume / volume_sma_20 | 计算 |
| turnover_rate | 技术 | valuation_data / K线 | 直接读取，或 volume/float_shares | valuation_data |
| price_volume_trend | 技术 | K 线数据 | PVT 累积 | 计算 |
| relative_strength | 技术 | K 线数据 | 个股收益/指数收益 | 计算 |

---

*文档版本：v1.0*
*制定日期：2026-04-22*
