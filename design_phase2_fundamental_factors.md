# Phase 2 设计文档：基本面因子计算与预处理

## 1. 设计目标

在 Phase 1 完成的财务数据获取与存储基础上，构建完整的基本面因子体系，实现：
1. **基本面因子计算** - 从数据库财务数据计算估值、盈利、成长、财务结构、现金流等因子
2. **因子预处理** - 缺失值处理、异常值处理、标准化、中性化
3. **与技术因子融合** - 与现有 `FactorData` 技术因子体系无缝集成

---

## 2. 因子体系设计

### 2.1 五大类因子

| 类别 | 因子名称 | 计算方式 | 因子方向 | 数据表 |
|------|----------|----------|----------|--------|
| **估值因子** | PE (市盈率) | price / eps_ttm | 低估值买入 | valuation_data |
| | PB (市净率) | price / book_value_per_share | 低估值买入 | balance_data |
| | PS (市销率) | price / revenue_per_share | 低估值买入 | valuation_data |
| | PCF (市现率) | price / cash_flow_per_share | 低估值买入 | cash_flow_data |
| | EV/EBITDA | enterprise_value / ebitda | 低估值买入 | derived |
| **盈利因子** | ROE (净资产收益率) | net_profit / equity | 高盈利买入 | profit_data |
| | ROA (资产收益率) | net_profit / total_assets | 高盈利买入 | balance_data |
| | 毛利率 | gross_profit / revenue | 高盈利买入 | profit_data |
| | 净利率 | net_profit / revenue | 高盈利买入 | profit_data |
| | EPS_TTM | 滚动每股收益 | 高盈利买入 | profit_data |
| **成长因子** | 营收增长率 | (revenue_now - revenue_prev) / revenue_prev | 高成长买入 | profit_data |
| | 利润增长率 | (profit_now - profit_prev) / profit_prev | 高成长买入 | profit_data |
| | 净资产增长率 | (equity_now - equity_prev) / equity_prev | 高成长买入 | balance_data |
| | 净利润复合增长率 | CAGR(net_profit, 3年) | 高成长买入 | profit_data |
| **财务结构因子** | 资产负债率 | total_liabilities / total_assets | 适中偏好 | balance_data |
| | 流动比率 | current_assets / current_liabilities | 偿债能力 | balance_data |
| | 速动比率 | (current_assets - inventory) / current_liabilities | 偿债能力 | balance_data |
| | 权益乘数 | total_assets / equity (杜邦) | 杠杆水平 | dupont_data |
| **现金流因子** | 经营现金流/净利润 | oper_cash_flow / net_profit | 现金流优良 | cash_flow_data |
| | 自由现金流 | oper_cash_flow - capex | 现金流优良 | cash_flow_data |
| | 现金流市值比 | oper_cash_flow / market_cap | 现金流优良 | cash_flow_data |

### 2.2 衍生因子

| 因子名称 | 计算公式 | 说明 |
|----------|----------|------|
| PB_ROE | PB / ROE | 成长价值因子 |
| PE_Growth | PE / 利润增长率 | 成长价值因子 |
| Altman_Z | 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5 | Z-Score破产预警 |
| 现金转换率 | 经营现金流 / 净利润 | 盈利质量 |

---

## 3. 核心类设计

### 3.1 FundamentalFactors (基本面因子计算)

```python
class FundamentalFactors:
    """基本面因子计算器"""

    def __init__(self, db_path: str = None):
        """初始化"""
        self.fdm = FinancialDataManager(db_path)

    def calculate_all_factors(self, symbol: str, trade_date: str) -> Dict[str, float]:
        """
        计算某只股票在指定日期的所有基本面因子

        Args:
            symbol: 股票代码
            trade_date: 交易日期

        Returns:
            {因子名: 因子值} 字典
        """
        factors = {}

        # 1. 获取财务数据
        profit = self.fdm.get_profit(symbol)      # 利润表
        balance = self.fdm.get_balance(symbol)     # 资产负债表
        cash_flow = self.fdm.get_cash_flow(symbol) # 现金流量表
        dupont = self.fdm.get_dupont(symbol)       # 杜邦分析
        valuation = self.fdm.get_valuation(symbol) # 估值数据

        # 2. 获取最新价格
        price = self._get_price(symbol, trade_date)

        # 3. 计算各类因子
        factors.update(self._calc_valuation_factors(price, valuation))
        factors.update(self._calc_profitability_factors(profit, balance))
        factors.update(self._calc_growth_factors(profit, balance))
        factors.update(self._calc_financial_structure_factors(balance))
        factors.update(self._calc_cash_flow_factors(cash_flow, profit, valuation))

        # 4. 计算衍生因子
        factors.update(self._calc_derived_factors(factors))

        return factors

    def get_factor_panel(self, symbols: List[str], trade_date: str) -> pd.DataFrame:
        """
        获取多只股票在某日期的因子面板数据

        Args:
            symbols: 股票列表
            trade_date: 交易日期

        Returns:
            DataFrame(index=symbol, columns=因子名)
        """
        pass
```

### 3.2 FactorPreprocessor (因子预处理器)

```python
class FactorPreprocessor:
    """因子预处理器 - 负责因子清洗和标准化"""

    def __init__(self, method: str = 'zscore'):
        """
        Args:
            method: 标准化方法 ('zscore', 'rank', 'minmax')
        """
        self.method = method
        self.means = {}
        self.stds = {}

    def preprocess(self, df: pd.DataFrame, factors: List[str]) -> pd.DataFrame:
        """
        预处理因子

        Steps:
            1. 缺失值处理
            2. 异常值处理 (Winsorization)
            3. 标准化

        Args:
            df: 因子面板数据
            factors: 因子列名列表

        Returns:
            处理后的DataFrame
        """
        result = df.copy()

        for factor in factors:
            # Step 1: 缺失值处理
            result[factor] = self._handle_missing(result[factor])

            # Step 2: 异常值处理
            result[factor] = self._handle_outliers(result[factor])

        # Step 3: 标准化
        if self.method == 'zscore':
            result[factors] = self._zscore_normalize(result[factors])
        elif self.method == 'rank':
            result[factors] = self._rank_normalize(result[factors])

        return result

    def _handle_missing(self, series: pd.Series) -> pd.Series:
        """缺失值处理策略"""
        # 金融因子用行业中位数填充
        return series.fillna(series.median())

    def _handle_outliers(self, series: pd.Series, n_std: float = 3) -> pd.Series:
        """异常值处理 - Winsorization (缩尾处理)"""
        mean = series.mean()
        std = series.std()
        lower = mean - n_std * std
        upper = mean + n_std * std
        return series.clip(lower, upper)

    def _zscore_normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Z-score标准化"""
        self.means = df.mean()
        self.stds = df.std()
        return (df - self.means) / (self.stds + 1e-8)
```

### 3.3 FactorNeutralizer (因子中性化)

```python
class FactorNeutralizer:
    """因子中性化处理"""

    def neutralize(self, df: pd.DataFrame,
                   factors: List[str],
                   by: str = 'industry') -> pd.DataFrame:
        """
        因子中性化 - 去除行业或市值影响

        Args:
            df: 因子数据 (需包含 industry 或 market_cap 列)
            factors: 要中性化的因子列表
            by: 中性化方式 ('industry' / 'market_cap')

        Returns:
            中性化后的因子
        """
        result = df.copy()

        if by == 'industry':
            # 行业中性化：减去行业均值
            for factor in factors:
                result[factor] = result.groupby('industry')[factor].transform(
                    lambda x: x - x.median()
                )
        elif by == 'market_cap':
            # 市值中性化：回归残差
            for factor in factors:
                result[factor] = self._regress_out_market_cap(
                    result[factor], result['market_cap']
                )

        return result

    def _regress_out_market_cap(self, factor: pd.Series,
                                market_cap: pd.Series) -> pd.Series:
        """回归掉市值因子"""
        from sklearn.linear_model import LinearRegression
        X = np.log(market_cap.values.reshape(-1, 1))
        y = factor.values
        model = LinearRegression().fit(X, y)
        return factor - model.predict(X)
```

---

## 4. 数据库 Schema 扩展

### 4.1 新增表：factor_values (每日因子值缓存)

```sql
CREATE TABLE factor_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    factor_name TEXT NOT NULL,
    factor_value REAL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, trade_date, factor_name)
);

CREATE INDEX idx_factor_values_date ON factor_values(trade_date);
CREATE INDEX idx_factor_values_symbol ON factor_values(symbol);
```

### 4.2 新增表：factor_metadata (因子元数据)

```sql
CREATE TABLE factor_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL UNIQUE,
    factor_category TEXT,      -- 'valuation'|'profitability'|'growth'|'structure'|'cashflow'
    factor_direction TEXT,     -- 'positive' (越高越好) | 'negative' (越低越好)
    description TEXT,
    formula TEXT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. 与现有系统集成

### 5.1 扩展 FactorData 类

在 `data/factor_data.py` 中新增方法：

```python
class FactorData:
    # ... 现有技术因子代码 ...

    def add_fundamental_factors(self, symbols: List[str], trade_date: str):
        """
        添加基本面因子到数据框

        Args:
            symbols: 股票列表
            trade_date: 交易日期
        """
        ff = FundamentalFactors()
        factor_df = ff.get_factor_panel(symbols, trade_date)
        # 合并到 self.df
```

### 5.2 扩展 MultiFactorStrategy

```python
class MultiFactorStrategy:
    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            # 技术因子
            'technical_factors': {
                'momentum_20': 0.2,
                'rsi': 0.1,
            },
            # 基本面因子
            'fundamental_factors': {
                'roe': 0.15,
                'pe': 0.1,
                'revenue_growth': 0.15,
            },
            # 预处理
            'preprocess': {
                'method': 'zscore',
                'neutralize': 'industry',
            }
        }
```

### 5.3 扩展 StockSelector

```python
class StockSelector:
    def __init__(self, weights: Dict[str, float] = None):
        default_weights = {
            # 技术维度
            'momentum': 0.2,
            'signal': 0.2,
            'volatility': 0.1,
            'liquidity': 0.1,
            # 基本面维度
            'valuation': 0.15,      # 估值
            'profitability': 0.1,    # 盈利
            'growth': 0.1,          # 成长
            'financial_quality': 0.05 # 财务质量
        }
```

---

## 6. 文件结构

```
strategy/
├── __init__.py
├── base.py
├── moving_average.py
├── multi_factor.py          # 扩展支持基本面因子
├── fundamental_factors.py   # [新增] 基本面因子计算
├── factor_preprocessor.py   # [新增] 因子预处理器
└── factor_neutralizer.py    # [新增] 因子中性化

data/
├── factor_data.py           # 扩展添加 add_fundamental_factors()
└── factor_metadata.db       # [新增] 因子元数据SQLite
```

---

## 7. 实施步骤

### Step 1: 创建因子计算核心类
- [ ] 创建 `strategy/fundamental_factors.py`
- [ ] 实现 `FundamentalFactors` 类
- [ ] 实现5大类因子的计算方法

### Step 2: 创建因子预处理器
- [ ] 创建 `strategy/factor_preprocessor.py`
- [ ] 实现缺失值、异常值、标准化处理
- [ ] 实现行业中性化、市值中性化

### Step 3: 扩展数据库 Schema
- [ ] 创建 `factor_values` 表
- [ ] 创建 `factor_metadata` 表
- [ ] 插入因子元数据

### Step 4: 集成到现有系统
- [ ] 扩展 `FactorData` 类添加基本面因子方法
- [ ] 扩展 `MultiFactorStrategy` 支持因子配置
- [ ] 扩展 `StockSelector` 添加基本面打分维度

### Step 5: 测试与验证
- [ ] 测试因子计算正确性
- [ ] 测试预处理流程
- [ ] 回测验证因子有效性

---

## 8. 使用示例

```python
# 示例1: 计算单只股票的基本面因子
from strategy.fundamental_factors import FundamentalFactors

ff = FundamentalFactors()
factors = ff.calculate_all_factors('000001.SZ', '2024-03-15')
print(f"ROE: {factors['roe']:.4f}")
print(f"PE: {factors['pe']:.2f}")

# 示例2: 批量计算并预处理
from strategy.factor_preprocessor import FactorPreprocessor

symbols = ['000001.SZ', '600000.SH', '600519.SH']
factor_df = ff.get_factor_panel(symbols, '2024-03-15')

preprocessor = FactorPreprocessor(method='zscore')
processed_df = preprocessor.preprocess(factor_df, factors_list)

# 示例3: 集成到选股流程
from portfolio.selector import StockSelector

selector = StockSelector(weights={
    'valuation': 0.2,
    'profitability': 0.2,
    'growth': 0.2,
    'momentum': 0.2,
    'liquidity': 0.2
})
scores = selector.score_stocks(stock_data, fundamental_factors=factor_df)
```

---

## 9. 注意事项

1. **财务报表时间滞后**: 季度报告在季度结束后15-45天发布，需处理"最新财报日期"与"实际可用日期"的差异
2. **数据频率不匹配**: 财务数据是季度的，K线是日度的，需进行前向填充 (forward-fill)
3. **异常值处理**: 金融数据存在肥尾特性，Winsorization 比 Z-score 截断更稳健
4. **因子共线性**: 同一类别因子间存在较强相关性 (如 PE 和 PB)，需注意多重共线性问题
5. **动态阈值**: 不同市场环境下因子有效性会变化，需定期回测重新校准