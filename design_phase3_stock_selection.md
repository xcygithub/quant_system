# Phase 3 设计文档：选股层搭建 - 全市场选股与 IC 分析

## 一、设计目标

构建完整的全市场选股系统，包括：

1. **全市场选股扫描器** - 对全市场股票进行因子打分和排序
2. **IC 分析模块** - 评估因子预测能力（IC/IR）
3. **因子有效性分析** - 分层回测、因子动物园
4. **组合构建器** - 基于选股结果的组合优化

---

## 二、核心模块设计

### 2.1 全市场选股扫描器 (`stock_scanner.py`)

#### 类：`MarketStockScanner`

**职责**：对全市场股票进行批量打分

```python
class MarketStockScanner:
    """
    全市场股票扫描器

    功能：
    - 获取全市场股票列表
    - 批量计算技术因子 + 基本面因子
    - 因子预处理（标准化、中性化）
    - 选股打分和排序
    - 输出候选股票列表
    """

    def __init__(
        self,
        data_manager: DataManager,
        fundamental_factors: FundamentalFactors,
        preprocessor: FactorPreprocessor,
        selector: StockSelector
    ):
        ...

    def scan(
        self,
        trade_date: str = None,
        top_n: int = 100,
        exclude_st: bool = True,
        exclude_new_stock_days: int = 90,
        min_market_cap: float = 10e8,  # 最小市值10亿
        factors: List[str] = None,
        weights: Dict[str, float] = None
    ) -> pd.DataFrame:
        """
        扫描全市场股票

        Returns:
            DataFrame(columns=[symbol, name, score, ...因子值, ...维度得分])
        """
        ...

    def _get_tradable_stocks(
        self,
        trade_date: str,
        exclude_st: bool,
        exclude_new_days: int,
        min_market_cap: float
    ) -> List[str]:
        """获取可交易股票列表"""
        ...

    def _batch_calculate_factors(
        self,
        symbols: List[str],
        trade_date: str
    ) -> pd.DataFrame:
        """批量计算因子"""
        ...

    def _preprocess_and_score(
        self,
        factor_panel: pd.DataFrame,
        weights: Dict[str, float]
    ) -> pd.DataFrame:
        """预处理 + 打分"""
        ...
```

#### 扫描流程

```
输入：交易日期、选股参数

Step 1: 获取可交易股票列表
  ├── 过滤ST股票
  ├── 过滤新股（上市不足N天）
  ├── 过滤低市值股票
  └── 过滤停牌/涨跌停股票

Step 2: 批量获取数据
  ├── 获取K线数据（技术因子）
  ├── 获取基本面数据（财务因子）
  └── 获取实时价格（估值因子）

Step 3: 计算因子
  ├── 技术因子：动量、波动率、成交量
  ├── 基本面因子：PE、PB、ROE、增长率...
  └── 预处理：缺失值、异常值、标准化、中性化

Step 4: 因子打分
  ├── 单因子打分（百分制）
  ├── 因子加权综合得分
  └── 排序输出Top N

输出：候选股票列表 + 详细评分
```

#### 数据库新增表

| 表 | 用途 |
|----|------|
| `scan_results` | 选股扫描结果记录 |
| `scan_logs` | 扫描日志（时间、参数、结果统计） |

---

### 2.2 IC 分析模块 (`ic_analyzer.py`)

#### 类：`ICAnalyzer`

**职责**：计算和分析因子的 IC（信息系数）

```python
class ICAnalyzer:
    """
    因子 IC 分析器

    IC (Information Coefficient) = 因子的排序与下期收益的相关系数
    IR (Information Ratio) = IC均值 / IC标准差

    功能：
    - 计算单因子 IC（Pearson / Spearman）
    - 计算因子 IR
    - IC 时间序列分析
    - 因子有效性判断
    """

    def __init__(self, db_path: str = None):
        ...

    def calculate_ic(
        self,
        factor_data: pd.DataFrame,
        forward_returns: pd.Series,
        method: str = 'spearman'  # spearman / pearson
    ) -> float:
        """
        计算因子 IC

        Args:
            factor_data: 因子值（个股横截面）
            forward_returns: 未来收益率
            method: 相关系数方法

        Returns:
            IC 值 (-1 ~ 1)
        """
        ...

    def calculate_ic_series(
        self,
        factor_name: str,
        start_date: str,
        end_date: str,
        window: int = 20,  # 滚动窗口
        method: str = 'spearman'
    ) -> pd.Series:
        """
        计算 IC 时间序列

        Returns:
            Series(index=date, values=ic)
        """
        ...

    def calculate_ir(
        self,
        ic_series: pd.Series
    ) -> float:
        """
        计算 IR (Information Ratio)

        IR = mean(IC) / std(IC)
        """
        ...

    def generate_ic_report(
        self,
        factor_names: List[str],
        start_date: str,
        end_date: str,
        output_path: str = None
    ) -> Dict:
        """
        生成 IC 分析报告

        Returns:
            {
                'factor_stats': {
                    'pe': {'ic_mean': 0.05, 'ic_std': 0.10, 'ir': 0.5, 'ic>0_pct': 0.6},
                    ...
                },
                'best_factor': 'roe',
                'worst_factor': 'pe',
                'recommendations': [...]
            }
        """
        ...
```

#### IC 分析指标

| 指标 | 计算方式 | 有效性判断 |
|------|----------|------------|
| **IC Mean** | IC序列均值 | > 0.02 有价值 |
| **IC Std** | IC序列标准差 | 越小越稳定 |
| **IR** | IC均值/IC标准差 | > 0.5 稳定有效 |
| **IC > 0 %** | IC正比例 | > 50% 方向稳定 |
| **Rank IC** | 使用秩相关 | 更稳健 |

#### IC 判定规则

```
IC Mean > 0.03 且 IR > 0.5 → 有效因子，强推荐
IC Mean > 0.02 且 IR > 0.3 → 有效因子，推荐
IC Mean > 0.01 且 IR > 0.2 → 弱有效，可尝试
IC Mean < 0 或 IR < 0.2   → 无效因子，不推荐
```

---

### 2.3 因子分层分析模块 (`factor分层回测.py`)

#### 类：`Factor分层回测`

```python
class Factor分层回测:
    """
    因子分层回测

    将股票按因子值分为N组，观察各组收益差异
    """

    def __init__(self, backtest_engine: VectorizedBacktest):
        ...

    def分层_analysis(
        self,
        factor_name: str,
        stock_returns: pd.DataFrame,  # rows=date, cols=symbol
        factor_data: pd.DataFrame,     # rows=date, cols=symbol
        n_groups: int = 5,
        holding_period: int = 20
    ) -> Dict:
        """
        分层分析

        Returns:
            {
                'group_returns': DataFrame,  # 各组收益率
                'long_short_return': Series, # 多空组合收益
                'turnover': DataFrame,       # 各组换手率
                'metrics': {
                    'long_short_ir': 0.8,
                    'top_minus_bottom': 0.12,
                    'spread稳定性': ...
                }
            }
        """
        ...
```

#### 分层分析可视化

```
月收益热力图：
         Group1   Group2   Group3   Group4   Group5
2024-01   5.2%     3.1%     2.4%     1.8%    -0.3%
2024-02   3.8%     2.9%     2.1%     1.2%    -1.1%
...

多空组合累计收益曲线：
    ↑ [Group1 - Group5 收益差]
```

---

### 2.4 选股器增强 (`selector.py` 扩展)

#### 新增类方法

```python
class StockSelector:
    """扩展功能"""

    def batch_score_from_factors(
        self,
        factor_panel: pd.DataFrame,
        factor_weights: Dict[str, float] = None
    ) -> List[StockScore]:
        """
        从因子面板批量打分

        Args:
            factor_panel: DataFrame(index=symbol, columns=因子值)
            factor_weights: 因子权重

        Returns:
            股票评分列表
        """
        ...

    def get_top_candidates(
        self,
        scores: List[StockScore],
        n: int = 10,
        by_factor: str = None  # 按某因子排序
    ) -> List[StockScore]:
        """获取最佳候选"""
        ...

    def export_scores(
        self,
        scores: List[StockScore],
        path: str
    ) -> None:
        """导出评分结果"""
        ...
```

---

## 三、数据库 Schema 扩展

### 3.1 新增表

```sql
-- 选股扫描结果表
CREATE TABLE scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date TEXT NOT NULL,           -- 扫描日期
    symbol TEXT NOT NULL,              -- 股票代码
    symbol_name TEXT,                  -- 股票名称
    rank INTEGER,                      -- 排名
    composite_score REAL,              -- 综合得分
    valuation_score REAL,             -- 估值得分
    profitability_score REAL,          -- 盈利得分
    growth_score REAL,                -- 成长得分
    momentum_score REAL,              -- 动量得分
    liquidity_score REAL,             -- 流动性得分
    pe REAL, pb REAL, roe REAL,       -- 原始因子值
    is_selected INTEGER DEFAULT 0,    -- 是否被选中
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- IC 分析结果表
CREATE TABLE ic_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,         -- 因子名
    trade_date TEXT NOT NULL,          -- 计算日期
    ic_value REAL,                     -- IC值
    ic_rank REAL,                      -- Rank IC
    forward_return REAL,               -- 同期收益
    sample_count INTEGER,              -- 样本数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(factor_name, trade_date)
);

-- IC 统计表（定期计算）
CREATE TABLE ic_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL UNIQUE,
    ic_mean REAL,                      -- IC均值
    ic_std REAL,                       -- IC标准差
    ir REAL,                           -- IR
    ic_positive_ratio REAL,            -- IC>0比例
    latest_ic REAL,                    -- 最新IC
    update_date TEXT,                  -- 更新日期
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 四、使用流程

### 4.1 日常选股流程

```python
# Step 1: 初始化组件
dm = DataManager()
ff = FundamentalFactors()
preprocessor = FactorPreprocessor()
scanner = MarketStockScanner(dm, ff, preprocessor, selector)

# Step 2: 全市场扫描
results = scanner.scan(
    trade_date='2024-03-19',
    top_n=50,
    exclude_st=True,
    min_market_cap=50e8  # 50亿以上
)

# Step 3: 查看结果
print(results[['symbol', 'name', 'composite_score', 'valuation_score', 'roe']].head(20))

# Step 4: 进一步筛选
candidates = selector.filter_and_rank(
    scores,
    min_score=70,
    by_factor='valuation_score'
)
```

### 4.2 IC 分析流程

```python
# Step 1: 计算各因子 IC
analyzer = ICAnalyzer()
ic_stats = analyzer.generate_ic_report(
    factor_names=['pe', 'pb', 'roe', 'revenue_growth', 'momentum_20'],
    start_date='2023-01-01',
    end_date='2024-03-19'
)

# Step 2: 查看结果
print(f"最佳因子: {ic_stats['best_factor']}, IR={ic_stats['factor_stats'][best_factor]['ir']:.2f}")

# Step 3: 根据 IC 调整因子权重
for factor, stats in ic_stats['factor_stats'].items():
    if stats['ir'] > 0.5:
        print(f"因子 {factor}: 强有效，推荐高权重")
    elif stats['ir'] > 0.3:
        print(f"因子 {factor}: 有效，适中权重")
```

---

## 五、与现有模块的集成

| 现有模块 | 扩展点 |
|----------|--------|
| `DataManager` | 新增 `get_tradable_stocks()`, `get_market_data()` |
| `FundamentalFactors` | 新增 `batch_calculate()` 批量计算 |
| `FactorPreprocessor` | 已有，无需修改 |
| `StockSelector` | 新增 `batch_score_from_factors()` |
| `MultiFactorStrategy` | 使用 `MarketStockScanner` 获取全市场候选 |

---

## 六、实施步骤

| 优先级 | 任务 | 文件 |
|--------|------|------|
| **P0** | 创建 `stock_scanner.py` 全市场扫描器 | portfolio/ |
| **P0** | 创建 `ic_analyzer.py` IC分析器 | portfolio/ |
| **P1** | 创建 `factor分层回测.py` | portfolio/ |
| **P1** | 扩展 `selector.py` 批量打分方法 | portfolio/ |
| **P1** | 创建数据库表 | data/data_manager.py |
| **P2** | 创建 Web 界面集成 | web/app.py |
| **P2** | 测试验证 | tests/ |

---

## 七、关键设计决策

### 7.1 性能优化

- **批量获取K线**：使用 `get_daily_kline_batch()` 替代循环获取
- **并行计算**：使用 `concurrent.futures` 并行计算因子
- **缓存策略**：
  - 基本面因子缓存到 `factor_values` 表
  - IC 计算结果缓存到 `ic_statistics` 表

### 7.2 数据完整性

- **缺失值处理**：行业报告中位数填充
- **异常值处理**：Winsorization ±3σ
- **数据对齐**：横截面数据按日期对齐

### 7.3 可扩展性

- **因子插件化**：新增因子只需在 `FACTOR_METADATA` 注册
- **回测框架兼容**：与现有 `VectorizedBacktest` 无缝集成