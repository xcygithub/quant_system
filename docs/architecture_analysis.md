# 量化系统架构分析与优化方案

> 文档日期：2026-04-23
> 目的：记录当前架构问题及修改方案，供后续重构参考

---

## 一、当前架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Web 层 (Streamlit)                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │   app.py          │    │ factor_backtest_ │    │   (其他Tab)      │   │
│  │   主应用页面      │    │ page.py 多因子   │    │                  │   │
│  │                  │    │      回测页面    │    │                  │   │
│  └────────┬─────────┘    └────────┬─────────┘    └──────────────────┘   │
│           │                       │                                       │
└───────────┼───────────────────────┼─────────────────────────────────────┘
            │                       │
            ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           业务逻辑层 (Portfolio)                        │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │ MultiStockBacktest│    │MultiFactorBacktest│   │  SignalScanner   │   │
│  │   多股票回测     │    │    多因子回测     │    │    信号扫描      │   │
│  └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘   │
│           │                       │                       │             │
│  ┌────────┴───────────────────────┴───────────────────────┴────────┐    │
│  │              Selector / PositionSizer / ICAnalyzer              │    │
│  │              选股排序    /   仓位分配   /   IC分析              │    │
│  └────────────────────────────────┬────────────────────────────────┘    │
└───────────────────────────────────┼─────────────────────────────────────┘
                                    │
┌───────────────────────────────────┼─────────────────────────────────────┐
│                           数据层 (Data)                                 │
│  ┌───────────────┐    ┌──────────┴──────────┐    ┌─────────────────┐   │
│  │  DataManager  │◄───│   MultiDataSource   │───►│  Baostock       │   │
│  │  统一数据接口 │    │    多数据源封装      │    │  CSV            │   │
│  ├───────────────┤    └─────────────────────┘    └─────────────────┘   │
│  │  SQLite DB    │                                                    │
│  │  (quant_data) │                                                    │
│  └───────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、当前架构的优点

| 优点 | 说明 |
|------|------|
| **模块化尚可** | 数据层、回测层、Web 层有一定分离 |
| **策略模式初步应用** | `Strategy` 基类 + 子类实现（MovingAverage、MACD 等） |
| **多数据源封装** | `MultiDataSource` 统一接口，支持 Baostock/CSV/Akshare |
| **组合继承结构清晰** | `MultiFactorBacktest` 继承 `MultiStockBacktest`，复用仓位/交易逻辑 |
| **数据库统一存储** | 所有数据通过 `DataManager` 统一管理，避免散落 |

---

## 三、当前架构的主要问题

### 问题 1：数据获取和回测严重耦合（高优先级）

**现状：**
- `_fetch_stock_data()` 直接调用 `dm.get_daily_kline()`
- `get_daily_kline()` 内部有网络请求逻辑 + 时效性检查
- 回测引擎不知道数据是从缓存还是网络获取的

**问题：**
- 网络不通时回测直接失败或极慢
- 无法在回测时绕过时效性检查（之前遇到的问题就是这个）
- 数据获取逻辑分散在 `DataManager` 内部，难以定制

**修改方案：**

```python
# 方案：引入 DataProvider 概念，分离数据获取策略

# 1. 定义数据提供者接口
class DataProvider(ABC):
    @abstractmethod
    def get_stock_data(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        pass

# 2. 实现两种提供者
class CacheOnlyProvider(DataProvider):  # 只读缓存，回测用
    def get_stock_data(self, symbol, start, end):
        return self.dm._get_kline_from_db(symbol, start, end)  # 无网络请求

class OnlineProvider(DataProvider):  # 在线获取，更新数据用
    def get_stock_data(self, symbol, start, end):
        return self.dm.get_daily_kline(symbol, start, end)  # 有网络请求+检查

# 3. 回测引擎接受 DataProvider
class MultiStockBacktest:
    def __init__(self, data_provider: DataProvider = None):
        self.data_provider = data_provider or CacheOnlyProvider(dm)

    def fetch_data(self, symbols, start, end):
        return {s: self.data_provider.get_stock_data(s, start, end)
                for s in symbols}

# 4. Web 层按场景注入
def _fetch_stock_data_for_backtest(dm, symbols, start, end):
    provider = CacheOnlyProvider(dm)  # 回测用，只读缓存
    ...

def update_recent_data(dm, symbols):
    provider = OnlineProvider(dm)  # 更新数据用，走在线
    ...
```

---

### 问题 2：DataManager 职责过重（高优先级）

**现状：** `DataManager` 一个类包含：
- 数据库表初始化
- 日线数据读写
- 分钟数据读写
- 财务数据读写
- 因子数据读写
- 数据更新逻辑
- 完整性检查逻辑

**问题：** 违反单一职责原则，修改任意一个功能都可能影响其他功能。

**修改方案：**

```
data/
├── __init__.py
├── data_manager.py          # 只保留数据库连接和表初始化
├── kline_manager.py         # 日线/分钟线数据管理（纯读写）
├── financial_manager.py     # 财务数据管理（读写）
├── factor_manager.py        # 因子数据管理（读写）
├── data_provider.py         # 数据提供者（获取策略）
├── data_sources.py          # 外部数据源接口
└── cache_policy.py           # 缓存策略（完整性检查逻辑）
```

---

### 问题 3：Web 层和业务逻辑耦合（中等优先级）

**现状：**
- `app.py` 和 `factor_backtest_page.py` 直接实例化 `DataManager`
- 业务逻辑（如 `_execute_backtest`、`_fetch_stock_data`）写在 Web 层
- Streamlit 的 `session_state` 滥用（日期选择器问题就是因此产生）

**问题：**
- 难以单独测试业务逻辑（必须启动 Streamlit）
- 业务逻辑无法复用（其他入口无法调用）
- `session_state` 中的 key 容易冲突或过期

**修改方案：**

```python
# 1. 抽取业务服务层
services/
├── backtest_service.py      # 回测业务逻辑（与 Web 无关）
│   ├── BacktestService.execute(symbols, config) -> Results
│   ├── DataService.fetch_for_backtest() -> Dict
│   └── DataService.update_recent() -> int
└── __init__.py

# 2. Web 层只做 UI 渲染和状态编排
web/
├── app.py                   # 只负责 Streamlit 页面渲染
├── factor_backtest_page.py   # 只负责 UI 组件
└── services/
    └── backtest_ui_service.py  # UI 与 service 的粘合层

# 3. session_state 管理重构
#    用 Pydantic dataclass 替代零散的 session_state key
from pydantic import BaseModel
from datetime import date
from typing import Optional, Dict, Any

class BacktestSession(BaseModel):
    start_date: date = date(2023, 1, 1)
    end_date: date = date(2024, 3, 19)
    results: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True

# 使用
if 'mfbt_session' not in st.session_state:
    st.session_state.mfbt_session = BacktestSession()

session = st.session_state.mfbt_session
session.end_date = st.date_input("结束日期", value=session.end_date)
```

---

### 问题 4：因子计算和数据准备耦合（中等优先级）

**现状：**
- `_prepare_factor_data()` 在 `factor_backtest_page.py` 中生成模拟因子数据
- 实际的因子计算逻辑分散在 `FactorData` / `FactorSignalGenerator` 等多个模块
- 没有统一的因子计算管道

**修改方案：**

```python
# 1. 统一因子计算管道
factor/
├── pipeline.py
│   class FactorPipeline:
│       def compute(stock_data, factor_names, start_date, end_date) -> Dict[str, DataFrame]
│       def validate(factor_data) -> bool
│       def get_factor_metadata(name) -> FactorMeta

# 2. 因子数据与 K 线数据分离存储
#    因子数据存 factor_values 表，K 线数据存 daily_kline 表
#    回测时根据日期动态 join，而不是预计算好放一起

# 3. 支持真实财务因子
#    当前因子是模拟的，应能从 financial_data_manager 读取真实 ROE/PE 等
```

---

### 问题 5：继承层次过深，修改成本高（低优先级）

**现状：**
```
Strategy (抽象基类)
  └── MultiFactorStrategy
        └── MultiFactorBacktest (多重继承)
              └── MultiStockBacktest
```

**问题：** `MultiFactorBacktest` 继承 `MultiStockBacktest`，但实际上多因子回测的逻辑和多股票回测有较大差异，强行继承导致很多方法需要 override。

**修改方案：**

```python
# 用组合替代继承
class MultiStockBacktest:
    def __init__(self, ...):
        self.position_manager = PositionManager(...)
        self.selector = StockSelector(...)
        self.sizer = PositionSizer(...)

    def run(self, stock_data, signals):
        ...

class MultiFactorBacktest:
    def __init__(self, ...):
        self.backtest = MultiStockBacktest(...)  # 组合
        self.factor_pipeline = FactorPipeline(...)
        self.ic_calculator = ICAnalyzer(...)

    def run(self, stock_data, factor_config):
        # 多因子特有的预处理
        factor_data = self.factor_pipeline.compute(stock_data, ...)
        # 转换为信号
        signals = self.factor_pipeline.to_signals(factor_data)
        # 委托给通用回测引擎
        return self.backtest.run(stock_data, signals)
```

---

### 问题 6：配置管理散落各处（低优先级）

**现状：**
- 回测参数在 Web 的 `session_state` 中
- 因子权重在 `FACTOR_CATEGORIES` 字典中
- 数据库路径硬编码在 `DataManager.__init__`
- 多数据源优先级在 `MultiDataSource` 构造函数中

**修改方案：**

```
config/
├── default_config.py         # 默认配置（数据库路径、日志级别等）
├── backtest_params.py        # 回测参数结构（Pydantic Model）
├── factor_weights.py        # 因子权重配置
└── data_sources.json         # 数据源优先级配置（可运行时修改）

# 统一配置入口
from config import config
config.get('db.path')
config.set('data_sources.priority', ['baostock', 'csv'])
```

---

## 四、架构修改优先级汇总

| 优先级 | 问题 | 工作量 | 收益 |
|--------|------|--------|------|
| **P0** | 数据获取与回测解耦 | 中 | 高 - 解决当前核心痛点 |
| **P0** | Web 层 session_state 重构 | 中 | 高 - 解决日期选择器问题 |
| **P1** | DataManager 职责分离 | 高 | 中 - 降低维护成本 |
| **P1** | 抽取业务服务层 | 高 | 高 - 可测试、可复用 |
| **P2** | 因子计算管道统一 | 中 | 中 - 支持真实因子 |
| **P2** | 继承改组合 | 中 | 低 - 减少技术债务 |
| **P3** | 统一配置管理 | 低 | 低 - 提升可维护性 |

---

## 五、当前维护性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **代码重复** | 6/10 | 中等 - 有重复的日期处理、数据获取逻辑 |
| **圈复杂度** | 7/10 | 中等 - 部分方法过长（如 `get_daily_kline` 约 60 行） |
| **依赖管理** | 5/10 | 较差 - 循环依赖风险（`portfolio.__init__.py` 有 try/except 处理） |
| **可测试性** | 5/10 | 较差 - 业务逻辑强依赖 Streamlit session_state |
| **可扩展性** | 6/10 | 中等 - 策略模式可用，但新数据源/新因子需要修改核心代码 |
| **文档完整性** | 4/10 | 较差 - 有 design_*.md 但代码注释少 |

**总体评价：** 项目在快速迭代阶段积累了一定技术债务，但核心架构还算清晰。如果继续开发 6 个月以上，建议优先做 **P0** 的两项重构，能显著提升开发效率和稳定性。

---

## 六、已知的具体 Bug 和问题记录

| 记录日期 | 问题 | 状态 |
|----------|------|------|
| 2026-04-23 | Streamlit session_state 导致日期选择器默认值不生效 | 待修复 |
| 2026-04-23 | 回测时 `get_daily_kline` 时效性检查导致请求 today 数据 | ✅ 已修复（2026-04-23）：引入 DataProvider 概念 |
| 2026-04-22 | `get_latest_quote` 每次刷新都触发网络请求 | 已修复：改为只读数据库 |
| 2026-04-23 | DataManager 职责过重（get_daily_kline 混合获取-检查-保存逻辑） | ✅ 已修复：KlineManager.fetch_daily_kline() 分载职责 |

---

*本文档为架构分析记录，随着重构推进应及时更新状态和进度。*
