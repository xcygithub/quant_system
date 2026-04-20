# Phase 4 设计文档：回测层完善 - 多因子回测引擎

## 一、设计目标

将 Phase 2 的基本面因子和 Phase 3 的 IC 分析能力集成到回测引擎中，实现：

1. **因子信号生成** - 在回测期间根据因子 IC 动态生成交易信号
2. **IC 加权因子配置** - 根据 IC 分析结果动态调整因子权重
3. **因子暴露度分析** - 归因分析各因子对组合收益的贡献
4. **增强回测报告** - 包含因子暴露度、因子收益归因、分层收益等

---

## 二、现有架构分析

### 2.1 现有组件

| 组件 | 文件 | 职责 | Phase |
|------|------|------|-------|
| `VectorizedBacktest` | backtest/engine.py | 单股票向量化回测 | Phase 1 |
| `MultiStockBacktest` | portfolio/multi_stock_backtest.py | 多股票组合回测 | Phase 3 |
| `MultiFactorStrategy` | strategy/multi_factor.py | 多因子策略（信号生成） | Phase 2 |
| `FundamentalFactors` | strategy/fundamental_factors.py | 基本面因子计算 | Phase 2 |
| `ICAnalyzer` | portfolio/ic_analyzer.py | IC 分析 | Phase 3 |
| `FactorQuantileAnalysis` | portfolio/factor_quantile_analysis.py | 分层回测 | Phase 3 |
| `MarketStockScanner` | portfolio/stock_scanner.py | 全市场扫描 | Phase 3 |
| `StockSelector` | portfolio/selector.py | 选股评分 | Phase 3 |

### 2.2 现有流程问题

```
当前流程：
  回测数据 → 策略生成信号 → 回测引擎执行
              ↑
         手动预设权重

问题：
1. 因子权重静态固定，无法根据 IC 动态调整
2. 缺少因子暴露度跟踪
3. 无法在回测期间根据因子信号选股
4. 回测报告缺少因子归因分析
```

---

## 三、核心模块设计

### 3.1 多因子回测引擎 (`multi_factor_backtest.py`)

#### 类：`MultiFactorBacktest`

**职责**：集成因子信号生成、IC 加权、暴露度分析的完整回测引擎

```python
class MultiFactorBacktest:
    """
    多因子回测引擎

    特点：
    - 在回测期间根据因子 IC 动态调整权重
    - 跟踪组合因子暴露度
    - 生成因子归因分析报告
    - 支持分层回测对比
    """

    def __init__(
        self,
        initial_capital: float = 1000000,
        commission_rate: float = 0.0003,
        stamp_tax: float = 0.001,
        max_positions: int = 5,
        rebalance_days: int = 5,
        max_single_position: float = 0.2,
        max_total_position: float = 0.8,
        stop_loss: float = 0.0,
        min_holding_days: int = 0,
        # 因子配置
        factor_weights: Dict[str, float] = None,  # 初始因子权重
        use_ic_weighting: bool = True,  # 是否根据 IC 动态调整权重
        ic_update_freq: int = 60,  # IC 更新频率（天）
        # IC 阈值
        ic_threshold_strong: float = 0.03,  # 强有效因子阈值
        ic_threshold_weak: float = 0.01,  # 弱有效因子阈值
    ):
        ...

    def run(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        factor_names: List[str] = None,
        initial_weights: Dict[str, float] = None
    ) -> Dict[str, Any]:
        """
        运行多因子回测

        Args:
            symbols: 股票池
            start_date: 开始日期
            end_date: 结束日期
            factor_names: 要使用的因子列表
            initial_weights: 初始因子权重

        Returns:
            回测结果 + 因子分析结果
        """
        ...

    def _generate_factor_signals(
        self,
        date: str,
        stock_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.Series]:
        """
        根据因子生成交易信号

        Returns:
            {symbol: signal_series}
            signal: 1(买入), 0(持有), -1(卖出)
        """
        ...

    def _calculate_factor_exposure(
        self,
        date: str,
        positions: Dict[str, PortfolioPosition]
    ) -> Dict[str, float]:
        """
        计算组合在各因子上的暴露度

        Returns:
            {factor_name: exposure}
        """
        ...

    def _update_ic_weights(self, date: str):
        """
        根据 IC 分析结果更新因子权重
        """
        ...
```

### 3.2 因子信号生成器 (`factor_signal_generator.py`)

#### 类：`FactorSignalGenerator`

**职责**：根据因子值和 IC 加权配置生成交易信号

```python
class FactorSignalGenerator:
    """
    因子信号生成器

    功能：
    - 读取因子值
    - 计算因子得分（横截面百分位）
    - 结合 IC 权重生成加权得分
    - 生成买卖信号
    """

    def __init__(
        self,
        factor_weights: Dict[str, float] = None,
        ic_weights: Dict[str, float] = None,
        use_ic_weighted: bool = True
    ):
        ...

    def generate_signals(
        self,
        factor_data: pd.DataFrame,  # index=symbol, columns=factor_values
        prices: Dict[str, float],  # 当前价格
        position: Dict[str, float] = None  # 当前持仓 {symbol: market_value_ratio}
    ) -> Dict[str, int]:
        """
        生成信号

        Args:
            factor_data: 因子数据
            prices: 当前价格
            position: 当前持仓（可选）

        Returns:
            {symbol: signal}
            signal: 1=买入, 0=持有/不操作, -1=卖出
        """
        ...

    def _calculate_zscore(
        self,
        factor_series: pd.Series
    ) -> pd.Series:
        """计算因子 Z-Score（横截面）"""
        ...

    def _calculate_percentile(
        self,
        factor_series: pd.Series
    ) -> pd.Series:
        """计算因子百分位（横截面）"""
        ...

    def _combine_scores(
        self,
        factor_scores: Dict[str, pd.Series],
        weights: Dict[str, float]
    ) -> pd.Series:
        """合并多因子得分"""
        ...
```

### 3.3 因子暴露度跟踪器 (`factor_exposure_tracker.py`)

#### 类：`FactorExposureTracker`

**职责**：跟踪组合在各因子上的暴露度，计算因子收益贡献

```python
class FactorExposureTracker:
    """
    因子暴露度跟踪器

    功能：
    - 每日记录组合因子暴露度
    - 计算因子收益率
    - 归因分析因子贡献
    """

    def __init__(self, factor_names: List[str]):
        ...

    def record_exposure(
        self,
        date: str,
        positions: Dict[str, PortfolioPosition],
        factor_values: Dict[str, Dict[str, float]]  # {symbol: {factor: value}}
    ):
        """记录每日暴露度"""
        ...

    def calculate_factor_returns(
        self,
        factor_data: pd.DataFrame,  # index=date, columns=symbol, values=factor_values
        returns: pd.DataFrame  # index=date, columns=symbol, values=returns
    ) -> pd.DataFrame:
        """
        计算因子收益率（横截面回归）

        Returns:
            DataFrame(index=date, columns=factor_names)
        """
        ...

    def attribute_returns(
        self,
        portfolio_returns: pd.Series,  # 组合收益率
        factor_returns: pd.DataFrame  # 因子收益率
    ) -> Dict[str, float]:
        """
        收益归因

        Returns:
            {factor_name: contribution}
        """
        ...

    def get_exposure_summary(self) -> pd.DataFrame:
        """获取暴露度摘要"""
        ...
```

### 3.4 因子 IC 动态配置器 (`factor_ic_configurator.py`)

#### 类：`FactorICConfigurator`

**职责**：管理因子 IC 配置，动态调整因子权重

```python
class FactorICConfigurator:
    """
    因子 IC 动态配置器

    功能：
    - 加载因子 IC 历史统计
    - 根据 IC 判定规则调整因子权重
    - 生成因子配置报告
    """

    # IC 判定阈值
    IC_STRONG = 0.03   # 强有效因子 IC > 3%
    IR_STRONG = 0.5    # 稳定有效 IR > 0.5
    IC_WEAK = 0.01     # 弱有效 IC > 1%
    IR_WEAK = 0.2      # 基本稳定 IR > 0.2

    def __init__(self, db_path: str = None):
        ...

    def load_ic_stats(
        self,
        factor_names: List[str],
        lookback_days: int = 252
    ) -> Dict[str, Dict]:
        """加载因子 IC 统计"""
        ...

    def calculate_weights(
        self,
        base_weights: Dict[str, float],
        ic_stats: Dict[str, Dict]
    ) -> Dict[str, float]:
        """
        根据 IC 调整权重

        规则：
        - 强有效因子：权重 × 1.5，上限 0.4
        - 有效因子：权重 × 1.0
        - 弱有效因子：权重 × 0.5
        - 无效因子：权重 × 0.2
        - 负 IC 因子：权重 × 0（排除）
        """
        ...

    def generate_config_report(
        self,
        factor_names: List[str],
        base_weights: Dict[str, float],
        ic_stats: Dict[str, Dict]
    ) -> pd.DataFrame:
        """
        生成因子配置报告

        Returns:
            DataFrame(columns=[因子, 基础权重, IC均值, IR, IC>0比例, 判定, 调整后权重])
        """
        ...
```

---

## 四、数据库 Schema 扩展

### 4.1 新增表

```sql
-- 因子暴露度记录表
CREATE TABLE factor_exposure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    factor_name TEXT NOT NULL,
    factor_value REAL,
    percentile_score REAL,  -- 百分位得分 0-100
    portfolio_weight REAL,  -- 该股票占组合权重
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, symbol, factor_name)
);

-- 因子收益归因表
CREATE TABLE factor_attribution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    factor_name TEXT NOT NULL,
    factor_return REAL,  -- 因子收益率
    portfolio_exposure REAL,  -- 组合暴露度
    attribution REAL,  -- 归因贡献
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, factor_name)
);

-- 多因子回测配置表
CREATE TABLE backtest_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_name TEXT NOT NULL UNIQUE,
    factor_weights TEXT,  -- JSON: {"pe": 0.2, "roe": 0.3, ...}
    ic_adjusted_weights TEXT,  -- JSON: 调整后权重
    ic_stats TEXT,  -- JSON: IC统计
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 回测期间记录表
CREATE TABLE backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_name TEXT,
    start_date TEXT,
    end_date TEXT,
    symbols_count INTEGER,
    total_return REAL,
    annual_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    config_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 索引

```sql
CREATE INDEX idx_factor_exposure_date ON factor_exposure(date);
CREATE INDEX idx_factor_exposure_symbol ON factor_exposure(symbol);
CREATE INDEX idx_factor_attribution_date ON factor_attribution(date);
CREATE INDEX idx_backtest_runs_date ON backtest_runs(start_date, end_date);
```

---

## 五、IC 加权因子配置算法

### 5.1 权重调整规则

```python
def adjust_weights_by_ic(
    base_weights: Dict[str, float],
    ic_stats: Dict[str, Dict[str, float]]
) -> Dict[str, float]:
    """
    根据 IC 统计调整因子权重

    调整系数：
    +--------+--------+--------+--------+
    | IC Mean | IR     | 判定   | 系数   |
    +--------+--------+--------+--------+
    | > 0.03 | > 0.5  | 强有效 | 1.5x   |
    | > 0.02 | > 0.3  | 有效   | 1.0x   |
    | > 0.01 | > 0.2  | 弱有效 | 0.5x   |
    | < 0    | any    | 无效   | 0.0x   |
    | 其他    | < 0.2  | 不稳定 | 0.3x   |
    +--------+--------+--------+--------+

    约束：
    - 单一因子权重上限: 0.4
    - 调整后权重归一化和为 1.0
    - 负 IC 因子直接排除
    """
```

### 5.2 IC 更新策略

```python
# 回测期间 IC 更新
IC_UPDATE_FREQ = 60  # 每 60 个交易日更新一次

# 历史 IC 窗口
IC_LOOKBACK = 252  # 使用 1 年历史计算 IC 统计

# IC 稳定性要求
IC_STABILITY_THRESHOLD = 0.5  # IC > 0 比例 > 50%
```

---

## 六、回测流程设计

### 6.1 完整回测流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     MultiFactorBacktest.run()                    │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: 初始化                                                   │
│   - 加载因子 IC 统计                                              │
│   - 计算初始因子权重（IC 调整后）                                 │
│   - 获取回测股票池                                                │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: 每日循环                                                  │
│   │                                                              │
│   ├─▶ Step 2.1: 获取当日数据                                     │
│   │     - K线数据                                                 │
│   │     - 因子数据                                                │
│   │     - IC 更新检查（每60天）                                   │
│   │                                                              │
│   ├─▶ Step 2.2: 计算因子暴露度                                   │
│   │     - 记录组合在各因子上的暴露度                              │
│   │                                                              │
│   ├─▶ Step 2.3: 生成交易信号                                     │
│   │     - 横截面因子得分                                          │
│   │     - IC 加权综合得分                                         │
│   │     - 生成买卖信号                                            │
│   │                                                              │
│   ├─▶ Step 2.4: 仓位管理与调仓                                   │
│   │     - 止损/止盈检查                                           │
│   │     - 信号执行                                                │
│   │     - 调仓再平衡                                              │
│   │                                                              │
│   └─▶ Step 2.5: 记录快照                                         │
│         - 权益快照                                               │
│         - 持仓快照                                               │
│         - 暴露度快照                                             │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: 回测结束处理                                             │
│   - 平仓所有持仓                                                  │
│   - 计算最终结果                                                  │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: 生成分析报告                                              │
│   - 收益指标                                                     │
│   - 风险指标                                                     │
│   - 因子暴露度分析                                               │
│   - 因子收益归因                                                 │
│   - IC 有效性回顾                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 因子信号生成详解

```python
def _generate_factor_signals(self, date, stock_data):
    """
    因子信号生成逻辑

    1. 横截面因子得分
       - 对每个因子，计算个股在横截面上的百分位得分
       - 百分位范围 0-100

    2. IC 加权综合得分
       - combined_score = Σ (factor_percentile_i × ic_weight_i)

    3. 信号生成规则
       - combined_score > 80 → 买入信号 (1)
       - combined_score < 20 → 卖出信号 (-1)
       - 20 <= score <= 80 → 持有 (0)
       - 已有持仓但信号转空 → 卖出

    4. 持仓市值加权信号（用于选股）
       - top_n = max_positions
       - 按综合得分排序，选前 N 只
    """
```

---

## 七、增强回测报告

### 7.1 报告结构

```python
class BacktestReport:
    """
    多因子回测报告

    包含：
    1. 基础回测指标
    2. 因子暴露度分析
    3. 因子收益归因
    4. IC 有效性回顾
    5. 分层回测对比
    """

    def __init__(self, results: Dict):
        ...

    def get_summary(self) -> Dict:
        """回测摘要"""
        ...

    def get_factor_exposure_chart(self) -> altair.Chart:
        """因子暴露度时序图"""
        ...

    def get_factor_attribution_chart(self) -> altair.Chart:
        """因子收益贡献图"""
        ...

    def get_ic_validity_report(self) -> pd.DataFrame:
        """IC 有效性回顾"""
        ...

    def get_quantile_returns(self) -> pd.DataFrame:
        """分层收益表"""
        ...

    def export_to_excel(self, path: str):
        """导出完整报告到 Excel"""
        ...
```

### 7.2 报告模板

```markdown
# 多因子策略回测报告

## 一、回测概况

| 指标 | 值 |
|------|-----|
| 回测期间 | 2023-01-01 ~ 2024-03-19 |
| 股票池 | 全市场 |
| 初始资金 | 1,000,000.00 |
| 最终权益 | 1,234,567.89 |
| 总收益率 | 23.46% |
| 年化收益率 | 18.32% |
| 夏普比率 | 1.45 |
| 最大回撤 | -12.34% |

## 二、因子配置

| 因子 | 基础权重 | IC均值 | IR | 判定 | 调整后权重 |
|------|----------|--------|-----|------|------------|
| roe | 0.25 | 0.052 | 0.68 | 强有效 | 0.35 |
| momentum_20 | 0.20 | 0.031 | 0.42 | 有效 | 0.25 |
| revenue_growth | 0.15 | 0.018 | 0.25 | 弱有效 | 0.10 |
| pb | 0.15 | -0.005 | -0.08 | 无效 | 0.00 |
| pe | 0.10 | 0.012 | 0.15 | 弱有效 | 0.08 |
| ... | ... | ... | ... | ... | ... |

## 三、因子暴露度分析

### 3.1 平均暴露度
| 因子 | 平均暴露度 | 暴露度标准差 |
|------|------------|--------------|
| roe | 0.65 | 0.15 |
| momentum_20 | 0.42 | 0.22 |
| revenue_growth | 0.38 | 0.18 |

### 3.2 暴露度时序图
[图表：各因子暴露度随时间变化]

## 四、因子收益归因

| 因子 | 因子收益率 | 组合暴露度 | 归因贡献 |
|------|-----------|------------|----------|
| roe | 8.5% | 0.65 | 5.53% |
| momentum_20 | 12.3% | 0.42 | 5.17% |
| revenue_growth | 6.8% | 0.38 | 2.58% |
| ... | ... | ... | ... |

**归因小结**：组合收益主要来自 ROE 因子和动量因子贡献

## 五、IC 有效性回顾

| 因子 | IC均值 | IC标准差 | IR | IC>0比例 | 判定 |
|------|--------|----------|-----|----------|------|
| roe | 0.052 | 0.076 | 0.68 | 72% | 强有效 |
| momentum_20 | 0.031 | 0.074 | 0.42 | 65% | 有效 |
| ... | ... | ... | ... | ... | ... |

## 六、分层回测对比

| 组别 | 因子值范围 | 收益率 | 波动率 | 夏普比率 |
|------|-----------|--------|--------|----------|
| G1 (高) | top 20% | 18.5% | 22.3% | 0.83 |
| G2 | 40-60% | 12.3% | 21.8% | 0.56 |
| G3 (低) | bottom 20% | 3.2% | 25.6% | 0.12 |
| 多空 | G1 - G3 | 15.3% | 8.2% | 1.87 |
```

---

## 八、与现有模块的集成

### 8.1 集成关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                    MultiFactorBacktest                          │
│                    (multi_factor_backtest.py)                  │
└─────────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────┐  ┌─────────────────┐  ┌────────────────────┐
│ FactorSignalGen  │  │ ExposureTracker │  │ ICConfigurator     │
│ (因子信号生成)    │  │ (暴露度跟踪)    │  │ (IC动态配置)       │
└──────────────────┘  └─────────────────┘  └────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────┐  ┌─────────────────┐  ┌────────────────────┐
│ FundamentalFactors│  │ DataManager    │  │ ICAnalyzer        │
│ (因子计算)        │  │ (数据读取)      │  │ (IC分析)          │
└──────────────────┘  └─────────────────┘  └────────────────────┘
           │                                      │
           ▼                                      ▼
┌──────────────────┐                   ┌────────────────────┐
│ FactorPreprocessor│                   │ FactorQuantile     │
│ (因子预处理)      │                   │ Analysis           │
└──────────────────┘                   └────────────────────┘
```

### 8.2 继承关系

```python
# MultiFactorBacktest 继承 MultiStockBacktest 的核心逻辑
class MultiFactorBacktest(MultiStockBacktest):
    """
    扩展 MultiStockBacktest：
    1. 添加因子信号生成能力
    2. 添加 IC 动态权重配置
    3. 添加因子暴露度跟踪
    """

    def __init__(self, ...):
        super().__init__(...)
        # 新增组件
        self.signal_generator = FactorSignalGenerator(...)
        self.exposure_tracker = FactorExposureTracker(...)
        self.ic_configurator = FactorICConfigurator(...)

    def run(self, ...):
        # 重写 run 方法，集成因子能力
        ...
```

---

## 九、实施步骤

| 优先级 | 任务 | 文件 | 依赖 |
|--------|------|------|------|
| **P0** | 创建 `factor_signal_generator.py` | portfolio/ | Phase 3 因子 |
| **P0** | 创建 `factor_exposure_tracker.py` | portfolio/ | DataManager |
| **P0** | 创建 `factor_ic_configurator.py` | portfolio/ | ICAnalyzer |
| **P0** | 创建 `multi_factor_backtest.py` | portfolio/ | 以上三个 + MultiStockBacktest |
| **P1** | 扩展数据库 Schema | data/data_manager.py | - |
| **P1** | 创建 `backtest_report.py` 报告生成器 | portfolio/ | 以上全部 |
| **P2** | 扩展 `portfolio/__init__.py` | portfolio/ | - |
| **P2** | Web 界面集成 | web/app.py | - |
| **P2** | 测试验证 | tests/ | - |

---

## 十、关键设计决策

### 10.1 因子信号 vs 价格信号

当前 `MultiStockBacktest` 使用价格信号（MA 金叉死叉）：
- 优点：简单、延迟低
- 缺点：无法利用基本面因子

新增因子信号模式：
- 根据因子 IC 加权得分生成信号
- 可与价格信号叠加或切换

### 10.2 IC 更新的频率选择

| 更新频率 | 优点 | 缺点 |
|----------|------|------|
| 每日更新 | 实时适应市场 | 计算量大、可能过拟合 |
| 每周更新 | 平衡 | - |
| 每月更新 | 稳定 | 滞后 |
| **每60天更新** | 平衡稳定性与适应性 | 默认选择 |

### 10.3 暴露度计算方法

采用**市值加权横截面百分位**：

```python
exposure[f] = Σ (weight_i × percentile_score_i[f]) / Σ weight_i

其中：
- weight_i = 股票 i 的持仓市值 / 组合总市值
- percentile_score_i[f] = 因子 f 在横截面上的百分位 (0-100)
```

---

## 十一、使用示例

### 11.1 基础使用

```python
from portfolio.multi_factor_backtest import MultiFactorBacktest
from portfolio.ic_analyzer import ICAnalyzer

# Step 1: 创建回测引擎
backtest = MultiFactorBacktest(
    initial_capital=1000000,
    max_positions=5,
    rebalance_days=5,
    factor_weights={
        'roe': 0.25,
        'pe': 0.15,
        'momentum_20': 0.20,
        'revenue_growth': 0.15,
        'pb': 0.10,
        'debt_ratio': 0.15
    },
    use_ic_weighting=True,
    ic_update_freq=60
)

# Step 2: 运行回测
results = backtest.run(
    symbols=stock_pool,  # 股票池
    start_date='2023-01-01',
    end_date='2024-03-19',
    factor_names=['roe', 'pe', 'momentum_20', 'revenue_growth', 'pb', 'debt_ratio']
)

# Step 3: 查看结果
print(f"总收益率: {results['total_return']:.2%}")
print(f"年化收益率: {results['annual_return']:.2%}")
print(f"夏普比率: {results['sharpe_ratio']:.2f}")
print(f"最大回撤: {results['max_drawdown']:.2%}")

# Step 4: 查看因子分析
factor_report = results['factor_report']
print(factor_report.get_exposure_summary())
```

### 11.2 自定义 IC 配置

```python
from portfolio.factor_ic_configurator import FactorICConfigurator

# 创建 IC 配置器
configurator = FactorICConfigurator()

# 加载 IC 统计
ic_stats = configurator.load_ic_stats(
    factor_names=['roe', 'pe', 'momentum_20'],
    lookback_days=252
)

# 生成配置报告
report = configurator.generate_config_report(
    factor_names=['roe', 'pe', 'momentum_20'],
    base_weights={'roe': 0.33, 'pe': 0.33, 'momentum_20': 0.34},
    ic_stats=ic_stats
)
print(report)

# 计算调整后权重
adjusted_weights = configurator.calculate_weights(
    base_weights={'roe': 0.33, 'pe': 0.33, 'momentum_20': 0.34},
    ic_stats=ic_stats
)
print(f"调整后权重: {adjusted_weights}")
```

### 11.3 生成完整报告

```python
from portfolio.backtest_report import BacktestReport

# 创建报告
report = BacktestReport(results)

# 导出到 Excel
report.export_to_excel('multi_factor_backtest_report.xlsx')

# 获取因子暴露度图
exposure_chart = report.get_factor_exposure_chart()
exposure_chart.save('factor_exposure.html')

# 获取归因分析
attribution_chart = report.get_factor_attribution_chart()
attribution_chart.save('factor_attribution.html')
```
