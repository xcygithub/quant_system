# 多因子量化策略系统设计方案

## 一、项目概述

### 1.1 目标
构建一个完整的多因子量化选股系统，支持从 Baostock 获取财务数据、计算多类型因子、进行全市场选股和回测。

### 1.2 现有架构
```
quant_system/
├── data/                    # 数据层
│   ├── data_manager.py      # 数据管理器（K线数据）
│   ├── data_sources.py      # 多数据源（Baostock/Akshare/CSV）
│   └── factor_data.py       # 技术因子计算
├── strategy/                # 策略层
│   ├── base.py              # 策略基类
│   ├── multi_factor.py      # 多因子策略（初级版）
│   └── moving_average.py    # 均线策略
└── portfolio/              # 组合管理
    ├── selector.py          # 选股器
    ├── position_sizer.py    # 仓位管理
    └── multi_stock_backtest.py  # 多股票回测
```

---

## 二、系统架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web 界面层                                 │
│   因子配置 | 选股回测 | 因子分析 | 参数优化                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      API 接口层                                  │
│   FactorAPI | ScreenerAPI | BacktestAPI | AnalyzerAPI          │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      策略引擎层                                   │
│   MultiFactorEngine | FactorSelector | PortfolioOptimizer      │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                       因子层                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  技术因子     │  │  基本面因子   │  │  情绪因子    │          │
│  │  (30+指标)    │  │  (20+指标)    │  │  (待扩展)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                 │
│  因子预处理：去极值 → 中性化 → 标准化 → 因子库                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      数据层                                      │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │   K线数据             │  │   财务数据 (Baostock)           │  │
│  │   daily_kline        │  │   profit_data                  │  │
│  │   minute_kline        │  │   balance_data                 │  │
│  │                      │  │   cash_flow_data              │  │
│  │                      │  │   dupont_data                  │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、数据库设计

### 3.1 现有表结构

```sql
-- K线数据表（已有）
CREATE TABLE daily_kline (
    symbol TEXT,
    date TEXT,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, amount REAL,
    turnover REAL, amplitude REAL,
    pct_change REAL, change_amount REAL,
    PRIMARY KEY (symbol, date)
);
```

### 3.2 新增财务数据表

```sql
-- 股票基础信息表（扩展）
CREATE TABLE stock_info (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    industry TEXT,
    market TEXT,
    list_date TEXT,
    update_time TIMESTAMP
);

-- 盈利能力数据（利润表）
CREATE TABLE profit_data (
    symbol TEXT,
    report_date TEXT,        -- 报告期（如 2024-03-31）
    eps REAL,                -- 每股收益
    roe REAL,                -- 净资产收益率
    net_profit_ratio REAL,   -- 净利率
    gross_profit_rate REAL,  -- 毛利率
    business_income REAL,    -- 营业收入
    net_profit REAL,         -- 净利润
    PRIMARY KEY (symbol, report_date)
);

-- 资产负债数据（资产负债表）
CREATE TABLE balance_data (
    symbol TEXT,
    report_date TEXT,
    total_assets REAL,       -- 总资产
    total_liabilities REAL, -- 总负债
    equity REAL,             -- 所有者权益
    debt_ratio REAL,         -- 资产负债率
    current_ratio REAL,      -- 流动比率
    quick_ratio REAL,        -- 速动比率
    PRIMARY KEY (symbol, report_date)
);

-- 现金流量数据
CREATE TABLE cash_flow_data (
    symbol TEXT,
    report_date TEXT,
    opercash_flow REAL,     -- 经营活动现金流
    investcash_flow REAL,   -- 投资活动现金流
    financecash_flow REAL,  -- 筹资活动现金流
    PRIMARY KEY (symbol, report_date)
);

-- 杜邦分析数据
CREATE TABLE dupont_data (
    symbol TEXT,
    report_date TEXT,
    roe REAL,               -- 净资产收益率
    asset_turnover REAL,    -- 资产周转率
    equity_multiplier REAL, -- 权益乘数
    net_profit_margin REAL, -- 销售净利率
    PRIMARY KEY (symbol, report_date)
);

-- 估值数据（计算因子用）
CREATE TABLE valuation_data (
    symbol TEXT,
    date TEXT,               -- 更新日期（非报告期）
    pe REAL,                 -- 市盈率
    pb REAL,                 -- 市净率
    ps REAL,                 -- 市销率
    pcf REAL,                -- 现金流倍率
    market_cap REAL,         -- 总市值
    float_market_cap REAL,   -- 流通市值
    PRIMARY KEY (symbol, date)
);

-- 财务因子表（预处理后的因子）
CREATE TABLE factor_data (
    symbol TEXT,
    date TEXT,
    factor_name TEXT,        -- 因子名称
    factor_value REAL,        -- 因子值
    PRIMARY KEY (symbol, date, factor_name)
);

-- 选股结果表
CREATE TABLE screening_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_date TEXT,
    symbol TEXT,
    score REAL,
    rank INTEGER,
    factors TEXT,            -- JSON格式存储各因子得分
    UNIQUE(screen_date, symbol)
);

-- 指数成分股权重
CREATE TABLE index_weight (
    index_code TEXT,
    symbol TEXT,
    date TEXT,
    weight REAL,
    PRIMARY KEY (index_code, symbol, date)
);
```

---

## 四、因子体系设计

### 4.1 因子分类

#### A. 技术因子（Technical Factors）
| 因子名称 | 计算方式 | 因子方向 |
|---------|---------|---------|
| momentum_20 | 20日收益率 | 正向 |
| momentum_60 | 60日收益率 | 正向 |
| momentum_120 | 120日收益率 | 正向 |
| rsi_14 | RSI指标 | 反向 |
| rsi_6 | 短期RSI | 反向 |
| macd | MACD指标 | 正向 |
| macd_signal | MACD信号线 | 趋势确认 |
| kdj_k | K值 | 摆动 |
| kdj_j | J值 | 摆动 |
| cci | CCI指标 | 摆动 |
| bollinger_position | 布林带位置 | 摆动 |
| atr_relative | 相对ATR | 反向（低波动） |
| volume_ratio | 量比 | 正向 |
| trend_strength | 趋势强度 | 正向 |
| volatility_20 | 20日波动率 | 反向 |
| volatility_60 | 60日波动率 | 反向 |
| price_relative | 相对强弱 | 正向 |

#### B. 基本面因子（Fundamental Factors）
| 因子名称 | 数据来源 | 因子方向 |
|---------|---------|---------|
| pe_ratio | 实时估值 | 反向（低估值） |
| pb_ratio | 实时估值 | 反向（低估值） |
| ps_ratio | PS市销率 | 反向 |
| roe | 净利润/净资产 | 正向 |
| roe_qoq | ROE环比变化 | 正向 |
| gross_margin | 毛利率 | 正向 |
| net_margin | 净利率 | 正向 |
| asset_turnover | 资产周转率 | 正向 |
| debt_ratio | 资产负债率 | 负向（过高风险） |
| current_ratio | 流动比率 | 正向 |
| quick_ratio | 速动比率 | 正向 |
| revenue_growth | 营收增长率 | 正向 |
| profit_growth | 利润增长率 | 正向 |
| oper_cash_flow | 经营现金流 | 正向 |
| equity_growth | 净资产增长率 | 正向 |
| total_asset_growth | 总资产增长率 | 正向 |

#### C. 分析师预期因子（Analyst Factors）
| 因子名称 | 数据来源 | 因子方向 |
|---------|---------|---------|
| target_price | 券商目标价 | 正向 |
| rating_change | 评级变动 | 正向 |
| earnings_revision | 盈利预测调整 | 正向 |

### 4.2 因子预处理流程

```
原始因子值 → 去极值 → 中性化 → 标准化 → 因子库
              │        │        │
              ▼        ▼        ▼
          Winsorize  行业/市值   Z-Score
          1%/99%     回归残差    标准化
```

#### Step 1: 去极值（Winsorize）
```python
def winsorize(series, lower=0.01, upper=0.99):
    """将超出1%-99%分位的值替换为边界值"""
    q_low = series.quantile(lower)
    q_high = series.quantile(upper)
    return series.clip(q_low, q_high)
```

#### Step 2: 中性化（Neutralization）
```python
def neutralize(factor, market_cap, industry_dummies):
    """行业+市值中性化"""
    X = np.column_stack([np.log(market_cap), industry_dummies])
    beta = np.linalg.lstsq(X, factor, rcond=None)[0]
    residuals = factor - X @ beta
    return residuals
```

#### Step 3: 标准化（Standardization）
```python
def standardize(factor):
    """Z-Score标准化"""
    return (factor - factor.mean()) / factor.std()
```

---

## 五、核心模块设计

### 5.1 模块结构

```
quant_system/
├── data/                              # 数据层
│   ├── data_manager.py               # 数据管理器
│   ├── data_sources.py                # K线数据源
│   ├── financial_data_source.py       # ★ 新增：财务数据源（Baostock）
│   ├── factor_data.py                 # 技术因子计算
│   └── db_schema.sql                  # ★ 新增：数据库Schema
│
├── factors/                           # ★ 新增：因子层
│   ├── __init__.py
│   ├── base.py                        # 因子基类
│   ├── technical_factors.py           # 技术因子
│   ├── fundamental_factors.py        # 基本面因子
│   ├── factor_preprocessor.py         # 因子预处理
│   ├── factor_registry.py             # 因子注册表
│   └── tests/
│       └── test_factors.py
│
├── screening/                         # ★ 新增：选股层
│   ├── __init__.py
│   ├── stock_screener.py              # 全市场选股器
│   ├── factor_weight_optimizer.py    # 因子权重优化
│   ├── ic_analyzer.py                 # IC分析
│   └── tests/
│
├── backtest/                          # 回测层（扩展）
│   ├── engine.py                      # 向量化回测引擎
│   ├── multi_factor_backtest.py       # ★ 新增：多因子回测
│   └── performance.py                 # 绩效分析
│
├── web/                               # Web界面
│   ├── app.py                         # Streamlit应用
│   └── components/
│       ├── factor_config.py           # 因子配置组件
│       ├── screening_panel.py         # 选股面板
│       └── factor_analysis.py        # 因子分析组件
│
└── config/
    ├── factors.yaml                   # 因子配置文件
    └── screening_rules.yaml           # 选股规则配置
```

### 5.2 核心类设计

#### A. FinancialDataSource（财务数据获取）

```python
class FinancialDataSource:
    """
    Baostock 财务数据获取器
    支持：利润表、资产负债表、现金流量表、杜邦分析
    """

    def get_profit_data(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取利润表数据"""

    def get_balance_data(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取资产负债表数据"""

    def get_cash_flow_data(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取现金流量表数据"""

    def get_dupont_data(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取杜邦分析数据"""

    def get_valuation_data(self, symbol: str) -> pd.DataFrame:
        """获取实时估值数据（PE/PB/PS）"""

    def batch_update_financial(self, symbols: List[str], quarters: List[str] = None):
        """批量更新财务数据到数据库"""
```

#### B. FundamentalFactors（基本面因子计算）

```python
class FundamentalFactors:
    """
    基本面因子计算器
    """

    def calculate_all(self, symbol: str, date: str) -> Dict[str, float]:
        """计算某只股票在某日期的所有基本面因子"""

    def calculate_roe(self, profit_df: pd.DataFrame) -> float:
        """ROE = 净利润 / 净资产"""

    def calculate_pe(self, symbol: str, date: str) -> float:
        """市盈率 = 总市值 / 净利润"""

    def calculate_pb(self, symbol: str, date: str) -> float:
        """市净率 = 总市值 / 净资产"""

    def calculate_growth_rates(self, financial_df: pd.DataFrame) -> Dict[str, float]:
        """计算增长率因子（营收、利润、净资产）"""
```

#### C. FactorPreprocessor（因子预处理）

```python
class FactorPreprocessor:
    """
    因子预处理：去极值、中性化、标准化
    """

    def winsorize(self, factor_values: pd.Series,
                  lower: float = 0.01, upper: float = 0.99) -> pd.Series:
        """去极值处理"""

    def neutralize(self, factor_values: pd.Series,
                   market_cap: pd.Series,
                   industry: pd.Series) -> pd.Series:
        """行业+市值中性化"""

    def standardize(self, factor_values: pd.Series) -> pd.Series:
        """Z-Score标准化"""

    def preprocess(self, factor_values: pd.Series,
                   market_cap: pd.Series = None,
                   industry: pd.Series = None) -> pd.Series:
        """一站式预处理"""
```

#### D. StockScreener（全市场选股器）

```python
class StockScreener:
    """
    多因子选股器
    """

    def __init__(self, factor_config: Dict[str, float]):
        """
        Args:
            factor_config: 因子权重配置，如
            {
                'pe_ratio': -0.15,      # 负数表示反向因子
                'roe': 0.25,
                'momentum_20': 0.20,
                'debt_ratio': -0.10,
                'volume_ratio': 0.15,
                ...
            }
        """

    def screen(self, date: str, top_n: int = 50,
               market: str = 'all',
               industry: str = None) -> pd.DataFrame:
        """
        执行选股

        Returns:
            DataFrame with columns: [symbol, name, score, rank, factor_details]
        """

    def get_composite_score(self, symbol: str, date: str) -> float:
        """计算单只股票的综合得分"""
```

#### E. MultiFactorBacktest（多因子回测）

```python
class MultiFactorBacktest:
    """
    多因子策略回测引擎
    """

    def __init__(self,
                 factor_weights: Dict[str, float],
                 rebalance_freq: int = 20,
                 top_n: int = 30,
                 min_holding_days: int = 5,
                 stop_loss: float = 0.08,
                 commission: float = 0.0003):
        """初始化回测参数"""

    def run(self, start_date: str, end_date: str,
            initial_capital: float = 1000000) -> BacktestResult:
        """
        执行回测

        Returns:
            BacktestResult: 包含每日持仓、交易记录、绩效指标
        """
```

---

## 六、Baostock 财务数据 API

### 6.1 Baostock 财务数据接口

```python
import baostock as bs

# 登录
lg = bs.login()

# ===== 1. 利润表数据 =====
rs = bs.query_profit_data(code="sz.000001", year=2024, quarter=1)
# 返回：date, code, roe, np_margin, gp_margin, op_margin, eps, revenue, income, a_intangible_asset, total_asset, equity

# ===== 2. 资产负债表 =====
rs = bs.query_balance_data(code="sz.000001", year=2024, quarter=1)
# 返回：date, code, totalAsset, totalLiab, equity, assetImpair, specialRisk, accumProfit

# ===== 3. 现金流量表 =====
rs = bs.query_cash_flow_data(code="sz.000001", year=2024, quarter=1)
# 返回：date, code, operCashFlow, operCashFlowPS, investCashFlow, financeCashFlow

# ===== 4. 杜邦分析 =====
rs = bs.query_dupont_data(code="sz.000001", year=2024, quarter=1)
# 返回：date, code, roe, assetStoTurn, equityMultipler, profitToSales, salesToGross

# ===== 5. 营业成本 =====
rs = bs.query_operating_cost_data(code="sz.000001", year=2024, quarter=1)

# ===== 6. 偿债能力 =====
rs = bs.query_debtpaying_data(code="sz.000001", year=2024, quarter=1)
# 返回：date, code, currentRatio, quickRatio, cashRatio

# ===== 7. 成长能力 =====
rs = bs.query_growth_data(code="sz.000001", year=2024, quarter=1)
# 返回：date, code, profitGrow, profitGrowRatio, assetToIncome

# ===== 8. 营运能力 =====
rs = bs.query_operation_data(code="sz.000001", year=2024, quarter=1)
# 返回：date, code, invturnover, arturnover, apturnover

# 登出
bs.logout()
```

### 6.2 财务数据更新策略

```python
class FinancialDataUpdater:
    """
    财务数据更新器
    更新频率：每季度财报公布后
    """

    def update_all(self, stock_list: List[str]):
        """更新所有股票的财务数据"""

    def update_quarterly(self, year: int, quarter: int):
        """按季度更新"""

    def get_latest_report_date(self, symbol: str) -> str:
        """获取最新财报日期"""

    def is_data_fresh(self, symbol: str, max_age_days: int = 180) -> bool:
        """检查数据是否新鲜（180天内有更新）"""
```

---

## 七、选股流程设计

### 7.1 每日选股流程

```
                     ┌─────────────────────┐
                     │  1. 获取候选股票池   │
                     │  （自选股/指数成分） │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  2. 获取最新财务数据  │
                     │  （PE/ROE/营收等）   │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  3. 计算因子值       │
                     │  （技术+基本面）      │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  4. 因子预处理       │
                     │  去极值/中性化/标准化│
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  5. 计算综合得分     │
                     │  Σ(因子值 × 权重)    │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  6. 排序选取TopN    │
                     │  + 行业/市值约束     │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  7. 输出选股结果     │
                     │  + 交易信号          │
                     └─────────────────────┘
```

### 7.2 选股约束

```python
class ScreeningConstraints:
    """选股约束条件"""

    def __init__(self):
        self.market_cap_min = 10_000_000_000   # 最小市值（10亿）
        self.market_cap_max = 500_000_000_000  # 最大市值（5000亿）
        self.pe_min = -100                       # PE下限
        self.pe_max = 100                        # PE上限
        self.debt_ratio_max = 0.9               # 最大资产负债率
        self.volume_min = 10_000_000            # 最小日成交量
        self.listed_days_min = 60               # 最小上市天数
        self.industry_max_weight = 0.3          # 单行业最大权重
        self.stock_max_weight = 0.1            # 单股票最大权重
```

---

## 八、回测模块设计

### 8.1 回测流程

```python
class MultiFactorBacktest:
    """
    多因子回测引擎
    基于向量化回测，支持：
    - 定期调仓（每周/每月）
    - 因子综合得分选股
    - 仓位分配
    - 止损止盈
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.factor_weights = config.factor_weights
        self.rebalance_freq = config.rebalance_freq
        self.top_n = config.top_n
        self.stop_loss = config.stop_loss
        self.commission = config.commission

    def run(self, start_date: str, end_date: str) -> BacktestResult:
        # 1. 初始化
        capital = self.config.initial_capital
        positions = {}  # {symbol: {amount, entry_price, entry_date}}

        # 2. 获取所有股票数据
        all_data = self._load_market_data(start_date, end_date)

        # 3. 按日期循环
        for date in self._trading_days(start_date, end_date, self.rebalance_freq):
            # 4. 选股
            selected = self.screener.screen(date, top_n=self.top_n)

            # 5. 仓位分配
            target_positions = self.position_sizer.allocate(
                selected, capital, self.config.max_single_position
            )

            # 6. 调仓
            self._rebalance(date, positions, target_positions)

            # 7. 更新权益
            self._update_equity(date, positions, all_data)

        # 8. 返回回测结果
        return self._generate_result()
```

### 8.2 绩效指标

```python
class PerformanceMetrics:
    """绩效指标计算器"""

    def calculate(self, equity_curve: pd.Series,
                  benchmark: pd.Series = None) -> Dict:
        """
        计算绩效指标：
        - 年化收益率 (Annual Return)
        - 年化波动率 (Annual Volatility)
        - 夏普比率 (Sharpe Ratio)
        - 最大回撤 (Max Drawdown)
        - 卡玛比率 (Calmar Ratio)
        - 胜率 (Win Rate)
        - 平均持仓天数 (Avg Holding Days)
        - 换手率 (Turnover)
        - 信息比率 (Information Ratio, vs benchmark)
        """
```

---

## 九、Web 界面设计

### 9.1 功能模块

```
┌─────────────────────────────────────────────────────────────────┐
│  多因子策略系统                                                    │
├─────────────────────────────────────────────────────────────────┤
│  [因子配置]  [选股回测]  [因子分析]  [参数优化]  [数据管理]         │
└─────────────────────────────────────────────────────────────────┘

【因子配置 Tab】
├── 因子池选择
│   ├── □ 技术因子：动量、RSI、MACD、KDJ...
│   ├── □ 基本面因子：PE、PB、ROE、营收增长...
│   └── □ 成交量因子：量比、OBV...
│
├── 因子权重配置
│   ├── roe:         [====|----] 25%
│   ├── pe_ratio:    [==|------] -15% (负数表示反向)
│   ├── momentum_20: [===|-----] 20%
│   ├── debt_ratio:  [=|-------] -10%
│   └── volume_ratio:[==|------] 15%
│
├── 因子预处理设置
│   ├── 去极值: 1% / 99%
│   ├── 中性化: □ 市值中性  □ 行业中性
│   └── 标准化: Z-Score
│
└── [保存配置] [加载配置]

【选股回测 Tab】
├── 基础参数
│   ├── 回测区间: [2023-01-01] ~ [2024-12-31]
│   ├── 初始资金: [1,000,000] 元
│   ├── 调仓频率: (●) 20天  ( ) 5天  ( ) 1月
│   └── 最大持仓: [30] 只
│
├── 选股约束
│   ├── 市值范围: [10亿] ~ [5000亿]
│   ├── PE范围:  [-50] ~ [100]
│   └── 行业限制: 单行业不超过 [30]%
│
├── 交易设置
│   ├── 止损比例: [8]%
│   ├── 止盈比例: [20]%
│   └── 最低持股: [5] 天
│
├── 回测结果
│   ├── 收益率曲线图
│   ├── 回测统计
│   │   ├── 年化收益: XX.XX%
│   │   ├── 夏普比率: X.XX
│   │   ├── 最大回撤: XX.XX%
│   │   └── 胜率: XX%
│   └── 持仓明细表
│
└── [开始回测]

【因子分析 Tab】
├── 因子有效性分析
│   ├── IC分析
│   │   ├── 因子: [选择因子]
│   │   ├── IC均值: X.XX
│   │   ├── ICIR: X.XX
│   │   └── IC时序图
│   │
│   └── 分位数组合
│       ├── 分5组
│       └── 各组累计收益曲线
│
├── 因子相关性矩阵
│   └── 热力图展示
│
└── 因子权重优化
    ├── 目标: 最大化夏普比率 / 最大化收益 / 最小化回撤
    └── [开始优化]
```

---

## 十、实施计划

### Phase 1: 数据层搭建（1-2周）
- [ ] 实现 `FinancialDataSource` 类，封装 Baostock 财务数据获取
- [ ] 扩展数据库 Schema，新增财务数据表
- [ ] 实现 `DataManager` 财务数据更新方法
- [ ] 编写数据更新脚本，定时更新财务数据

### Phase 2: 因子层搭建（2-3周）
- [ ] 实现 `FundamentalFactors` 基本面因子计算类
- [ ] 实现 `FactorPreprocessor` 因子预处理类
- [ ] 建立因子注册表和管理机制
- [ ] 编写因子计算脚本，批量计算历史因子

### Phase 3: 选股层搭建（2-3周）
- [ ] 实现 `StockScreener` 全市场选股器
- [ ] 实现选股约束机制
- [ ] 实现 `ICAnalyzer` 因子有效性分析
- [ ] 与现有 `MultiFactorStrategy` 集成

### Phase 4: 回测层完善（1-2周）
- [ ] 实现 `MultiFactorBacktest` 多因子回测引擎
- [ ] 实现 `PerformanceMetrics` 绩效指标计算
- [ ] 对接 Web 界面

### Phase 5: Web 界面完善（2-3周）
- [ ] 实现因子配置面板
- [ ] 实现选股回测面板
- [ ] 实现因子分析面板
- [ ] 实现参数优化功能

---

## 十一、关键设计决策

### 11.1 为什么需要独立因子层？
- **复用性**：因子可在选股、回测、实盘多个模块复用
- **可测试性**：每个因子可单独测试其有效性
- **可扩展性**：新增因子只需实现因子类并注册

### 11.2 为什么需要因子预处理？
- **去极值**：避免极端值主导组合
- **中性化**：消除行业和市值偏差
- **标准化**：使不同因子可比

### 11.3 财务数据更新策略
- **频率**：每季度财报公布后更新（4次/年）
- **增量更新**：只更新新增或变化的财报
- **缓存**：本地 SQLite 缓存，减少 Baostock 调用

### 11.4 与现有系统集成
- 复用 `DataManager` 的数据获取和缓存机制
- 复用 `Portfolio` 模块的仓位管理和回测框架
- 因子选股结果直接输入现有回测引擎

---

## 十二、风险与注意事项

1. **Baostock API 限制**：
   - 免费接口有频率限制，每分钟最多60次调用
   - 需要实现缓存和批量获取机制

2. **财务数据质量**：
   - 财报可能有延迟（季报滞后1个月，年报滞后4个月）
   - 需要处理财务数据缺失和异常值

3. **因子共线性**：
   - 部分因子可能高度相关（如PE和PB）
   - 需要进行因子正交化或使用PCA

4. **过拟合风险**：
   - 因子权重优化可能导致过拟合
   - 需要留出验证集进行参数验证

---

## 十三、参考文档

- [Baostock 数据接口文档](http://baostock.com/baostock/index.php)
- [因子投资入门 - 雪球](https://xueqiu.com)
- [量化投资入门 - 聚宽](https://joinquant.com)
