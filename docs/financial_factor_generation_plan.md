# 从 Baostock 获取财务数据并生成因子数据的方案

## 一、现状分析

### 已有组件

| 组件 | 状态 | 说明 |
|------|------|------|
| `FinancialDataSource` | 已完成 | Baostock 财务数据获取（利润表/资产负债表/现金流量表/杜邦分析/成长/营运/偿债） |
| `FinancialDataSaver` | 已完成 | 财务数据持久化到 SQLite |
| `FinancialDataManager` | 已完成 | 统一接口，支持单股票/批量更新 |
| `FactorManager` | 已完成 | 因子读写（factor_cache/factor_values 表） |
| 数据库 Schema | 已完成 | 包含 10+ 张财务和因子相关表 |
| 因子元数据 | 已预置 | 23 个基本面因子定义（PE/PB/ROE/营收增长等） |

### 缺失组件

| 组件 | 说明 |
|------|------|
| **FundamentalFactorCalculator** | **核心缺失**：从财务数据计算因子值的计算器 |
| **FactorPipeline** | 因子生成管道：批量计算 + 保存 |
| 财务因子计算逻辑 | 具体的因子计算公式实现 |

---

## 二、目标

构建完整的**基本面因子计算管线**：

```
Baostock 原始财务数据
    ↓ (已实现)
SQLite 财务数据表 (profit_data / balance_data / cash_flow_data / dupont_data)
    ↓ (待实现)
基本面因子计算器 (FundamentalFactorCalculator)
    ↓ (待实现)
因子缓存表 (factor_cache) + 因子值表 (factor_values)
    ↓
多因子回测系统使用真实财务因子
```

---

## 三、方案设计

### 3.1 数据库表结构（已有）

当前 `factor_cache` 表结构：

```sql
CREATE TABLE factor_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,      -- 计算日期
    factor_name TEXT NOT NULL,
    factor_value REAL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, trade_date, factor_name)
)
```

**设计说明**：`trade_date` 是计算日期，不是报告期。由于财务数据是季度频率，计算时会进行前向填充（Forward Fill），将最近一个季度的财务因子应用到该季度内的所有交易日。

### 3.2 核心类设计

#### A. FundamentalFactorCalculator（基本面因子计算器）

**文件位置**：`data/fundamental_factor_calculator.py`

**职责**：从数据库读取财务数据，计算各类基本面因子

**五大类因子**：

| 类别 | 因子 | 数据来源 | 计算公式 |
|------|------|----------|----------|
| **估值因子** | pe | valuation_data | 市盈率 |
| | pb | valuation_data | 市净率 |
| | ps | valuation_data | 市销率 |
| | pcf | valuation_data | 市现率 |
| **盈利因子** | roe | profit_data | 净资产收益率 |
| | roe_avg | profit_data | 摊薄 ROE |
| | gross_margin | profit_data | 毛利率 = 毛利润/营业收入 |
| | net_margin | profit_data | 净利率 = 净利润/营业收入 |
| | roa | balance + profit | 资产收益率 = 净利润/总资产 |
| **成长因子** | revenue_growth | profit_data | 营收增长率 = (本期-上期)/上期 |
| | profit_growth | profit_data | 利润增长率 |
| | equity_growth | balance_data | 净资产增长率 |
| **财务结构** | debt_ratio | balance_data | 资产负债率 |
| | current_ratio | balance_data | 流动比率 |
| | quick_ratio | balance_data | 速动比率 |
| | equity_multiplier | dupont_data | 权益乘数 |
| **现金流** | cash_to_profit | cash_flow + profit | 经营现金流/净利润 |
| | cash_yield | cash_flow + valuation | 现金市值比 |

**关键方法**：

```python
class FundamentalFactorCalculator:
    """基本面因子计算器"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def calculate_factors_for_stock(
        self,
        symbol: str,
        trade_date: str
    ) -> Dict[str, float]:
        """
        计算某只股票在指定日期的所有基本面因子

        Args:
            symbol: 股票代码
            trade_date: 交易日期

        Returns:
            {因子名: 因子值} 字典
        """

    def calculate_single_factor(
        self,
        symbol: str,
        trade_date: str,
        factor_name: str
    ) -> Optional[float]:
        """计算单个因子值"""

    def get_latest_report_date(self, symbol: str, max_age_days: int = 90) -> str:
        """
        获取最新的可用财报日期

        财报披露有时间滞后：
        - 年报：次年4月底前披露
        - 一季报：次年4月底前披露
        - 中报：次年8月底前披露
        - 三季报：次年10月底前披露

        所以需要根据 trade_date 往前推算"实际可用的"财报日期
        """
```

**关键设计：财报日期对齐**

由于财报披露存在滞后，计算因子时需要对齐到"实际可用的"财报：

```python
def _get_available_report_date(self, trade_date: str) -> str:
    """
    根据交易日期，计算实际可用的最新财报日期

    规则：
    - 如果是4月底之前：只能用到前年年底的年报
    - 如果是8月底之前：可以用到去年年底的年报 + 当年一季报
    - 如果是10月底之前：可以用到去年年底的年报 + 当年一季报 + 中报
    - 否则：可以用到去年年底的年报 + 当年一季报 + 中报 + 三季报
    """
```

#### B. FactorPipeline（因子生成管道）

**文件位置**：`data/factor_pipeline.py`

**职责**：批量计算因子并保存到数据库

```python
class FactorPipeline:
    """因子生成管道"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.calculator = FundamentalFactorCalculator(db_path)
        self.factor_mgr = FactorManager(db_path)

    def calculate_and_save_factors(
        self,
        symbols: List[str],
        trade_dates: List[str],
        factor_names: List[str] = None,
        progress_callback: Callable = None
    ) -> int:
        """
        批量计算并保存因子

        Args:
            symbols: 股票列表
            trade_dates: 交易日期列表
            factor_names: 要计算的因子列表（None 表示全部）
            progress_callback: 进度回调

        Returns:
            保存的记录数
        """

    def calculate_stock_factors(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        frequency: str = 'daily'
    ) -> pd.DataFrame:
        """
        计算某只股票某个时间段的因子

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            frequency: 'daily' 或 'weekly'

        Returns:
            DataFrame: symbol, trade_date, factor_name, factor_value
        """

    def run_full_pipeline(
        self,
        symbols: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        factor_names: List[str] = None
    ) -> Dict[str, int]:
        """
        运行完整因子生成流程

        1. 获取股票列表（如果未提供）
        2. 获取交易日列表
        3. 批量计算因子
        4. 保存到数据库
        """
```

---

## 四、因子计算详解

### 4.1 估值因子

直接从 `valuation_data` 表读取：

```python
def _calculate_valuation_factors(self, symbol: str, trade_date: str) -> Dict[str, float]:
    """从估值表获取"""
    valuation = self._get_valuation(symbol, trade_date)
    if not valuation:
        return {}

    return {
        'pe': valuation.get('pe'),
        'pe_ttm': valuation.get('pe_ttm'),
        'pb': valuation.get('pb'),
        'ps': valuation.get('ps'),
        'pcf': valuation.get('pcf'),
    }
```

### 4.2 盈利因子

从利润表计算：

```python
def _calculate_profitability_factors(
    self,
    symbol: str,
    trade_date: str,
    report_data: pd.DataFrame
) -> Dict[str, float]:
    """从利润表计算盈利因子"""

    if report_data is None or report_data.empty:
        return {}

    latest = report_data.iloc[0]  # 最新财报

    # 毛利率
    gross_margin = 0.0
    if latest.get('business_income', 0) != 0:
        gross_margin = (latest.get('gross_profit_rate', 0) or 0)

    # 净利率
    net_margin = 0.0
    if latest.get('business_income', 0) != 0:
        net_margin = (latest.get('net_profit_ratio', 0) or 0)

    # ROA = 净利润 / 总资产
    roa = 0.0
    balance = self._get_balance(symbol, trade_date)
    if balance and balance.get('total_assets', 0) != 0:
        roa = (latest.get('net_profit', 0) or 0) / balance['total_assets'] * 100

    return {
        'roe': latest.get('roe'),           # 直接从利润表
        'roe_avg': latest.get('roe_avg'),
        'gross_margin': gross_margin,
        'net_margin': net_margin,
        'roa': roa,
    }
```

### 4.3 成长因子

通过同比计算：

```python
def _calculate_growth_factors(
    self,
    symbol: str,
    trade_date: str,
    profit_data: pd.DataFrame
) -> Dict[str, float]:
    """计算成长因子（同比）"""

    if profit_data is None or len(profit_data) < 2:
        return {}

    # 最近两个财报（已按日期降序）
    latest = profit_data.iloc[0]
    previous = profit_data.iloc[1]

    def calc_growth(current, previous):
        if previous and previous != 0:
            return (current - previous) / abs(previous) * 100
        return 0.0

    return {
        'revenue_growth': calc_growth(
            latest.get('business_income', 0),
            previous.get('business_income', 0)
        ),
        'profit_growth': calc_growth(
            latest.get('net_profit', 0),
            previous.get('net_profit', 0)
        ),
    }
```

### 4.4 财务结构因子

从资产负债表读取：

```python
def _calculate_structure_factors(
    self,
    symbol: str,
    trade_date: str,
    balance_data: pd.DataFrame
) -> Dict[str, float]:
    """计算财务结构因子"""

    if balance_data is None or balance_data.empty:
        return {}

    latest = balance_data.iloc[0]

    return {
        'debt_ratio': latest.get('debt_ratio'),        # 资产负债率
        'current_ratio': latest.get('current_ratio'),  # 流动比率
        'quick_ratio': latest.get('quick_ratio'),      # 速动比率
        'equity_multiplier': latest.get('equity_multiplier'),  # 权益乘数
    }
```

### 4.5 现金流因子

从现金流量表和利润表计算：

```python
def _calculate_cashflow_factors(
    self,
    symbol: str,
    trade_date: str,
    cash_flow: pd.DataFrame,
    profit_data: pd.DataFrame
) -> Dict[str, float]:
    """计算现金流因子"""

    if cash_flow is None or cash_flow.empty:
        return {}

    latest_cf = cash_flow.iloc[0]
    latest_profit = profit_data.iloc[0] if profit_data is not None else {}

    # 经营现金流 / 净利润
    cash_to_profit = 0.0
    net_profit = latest_profit.get('net_profit', 0) or 0
    if net_profit != 0:
        oper_cf = latest_cf.get('oper_cash_flow', 0) or 0
        cash_to_profit = oper_cf / net_profit

    # 现金市值比
    cash_yield = 0.0
    valuation = self._get_valuation(symbol, trade_date)
    if valuation and valuation.get('market_cap', 0) != 0:
        oper_cf = latest_cf.get('oper_cash_flow', 0) or 0
        cash_yield = oper_cf / valuation['market_cap']

    return {
        'cash_to_profit': cash_to_profit,
        'cash_yield': cash_yield,
    }
```

---

## 五、使用流程

### 5.1 单股票因子计算

```python
from data.factor_pipeline import FactorPipeline

pipeline = FactorPipeline()

# 计算某只股票某个时间段的因子
df = pipeline.calculate_stock_factors(
    symbol='000001.SZ',
    start_date='2024-01-01',
    end_date='2024-12-31',
    frequency='daily'
)

print(f"计算了 {len(df)} 条因子记录")
print(df.head(10))
```

### 5.2 批量计算

```python
from data.data_manager import DataManager
from data.factor_pipeline import FactorPipeline

dm = DataManager()
pipeline = FactorPipeline()

# 获取自选股列表
watchlist = dm.get_watchlist()

# 批量计算（每只股票每天每个因子 = watchlist × 交易日数 × 因子数）
pipeline.calculate_and_save_factors(
    symbols=watchlist,
    trade_dates=['2024-01-02', '2024-01-03', ...],  # 或用交易日历
    factor_names=['pe', 'roe', 'revenue_growth'],     # 或 None 表示全部
    progress_callback=lambda i, total, sym: print(f"进度: {i}/{total} - {sym}")
)
```

### 5.3 完整流水线

```python
# 一次性生成所有历史因子
pipeline.run_full_pipeline(
    symbols=None,           # None 表示所有股票
    start_date='2020-01-01',
    end_date='2024-12-31',
    factor_names=None      # None 表示所有因子
)
```

---

## 六、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `data/fundamental_factor_calculator.py` | 新建 | 核心：基本面因子计算器 |
| `data/factor_pipeline.py` | 新建 | 核心：因子生成管道 |
| `data/__init__.py` | 修改 | 导出新类 |
| `data/factor_manager.py` | 已有 | 复用因子读写 |
| `scripts/generate_factors.py` | 新建 | 命令行批量生成脚本 |

---

## 七、实施步骤

### Phase 1: 核心计算器
1. 创建 `FundamentalFactorCalculator` 类
2. 实现各因子计算方法（估值/盈利/成长/结构/现金流）
3. 实现财报日期对齐逻辑
4. 单元测试：验证单股票因子计算正确性

### Phase 2: 管道封装
1. 创建 `FactorPipeline` 类
2. 实现批量计算逻辑
3. 实现进度回调
4. 实现 `run_full_pipeline` 完整流程

### Phase 3: 集成与测试
1. 集成到 `DataManager` 作为便捷方法
2. 运行回测验证因子数据正确性
3. 性能优化（向量化计算、批量写入）

---

## 八、注意事项

1. **财报滞后**：Q1 财报4月底才出，3月份只能用前年年底的年报。需要 `_get_available_report_date()` 逻辑处理。

2. **前向填充**：财务数据是季度频率，计算时需要填充到每日。Baostock 原始数据需要转换。

3. **缺失值处理**：部分股票某些因子为空，需要用行业中位数或 0 填充。

4. **性能考虑**：全市场 A 股 5000+ 股票 × 5 年 × 250 交易日 × 20 因子 = 海量数据。建议分批处理，每批 100 只股票。
