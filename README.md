# 量化交易系统 (Quant Trading System)

> 一个基于 Python 的完整量化交易系统，包含数据获取、因子计算、策略回测、风险管理和可视化分析等功能。

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Web 层 (Streamlit)                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │   app.py         │    │ factor_backtest_ │    │   pages/         │   │
│  │   7标签页主应用  │    │ page.py 多因子   │    │ data_management  │   │
│  │                  │    │     回测页面     │    │   数据管理       │   │
│  └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘   │
└────────────┼───────────────────────┼───────────────────────┼───────────────┘
            │                       │                       │
            ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           业务逻辑层 (Portfolio)                        │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │ MultiStockBacktest│    │MultiFactorBacktest│   │  SignalScanner   │   │
│  │   多股票回测     │    │    多因子回测    │    │    信号扫描     │   │
│  └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘   │
│           │                        │                        │              │
│  ┌────────┴────────────────────┴────────────────────────┴────────┐   │
│  │     Selector / PositionSizer / ICAnalyzer / FactorExposure      │   │
│  │     选股排序 / 仓位分配 / IC分析 / 因子暴露度跟踪            │   │
│  └─────────────────────────────────┬──────────────────────────────┘    │
└────────────────────────────────────┼────────────────────────────────┘
                                     │
┌────────────────────────────────────┼────────────────────────────────┐
│                           数据层 (Data)                               │
│  ┌───────────────┐    ┌────────────┴───────────┐   ┌─────────────┐ │
│  │  DataManager │◄───│    MultiDataSource    │───►│  Baostock  │ │
│  │  统一数据入口│    │     多数据源封装      │   │  Eastmoney │ │
│  ├───────────────┤    └───────────────────────┘   └─────────────┘ │
│  │  SQLite DB   │                                            │
│  │ quant_data   │  ┌─────────────┐  ┌─────────────────────┐    │
│  └───────────────┘  │FactorManager│  │FinancialDataManager│    │
│                     │  因子管理    │  │    财务数据管理    │    │
│                     └─────────────┘  └─────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、功能特性

### 2.1 数据模块 (`data/`)

| 模块 | 文件 | 功能说明 |
|------|------|---------|
| **数据管理器** | `data_manager.py` | 统一数据入口、数据库初始化（20+张表）、委托给子管理器 |
| **K线管理** | `kline_manager.py` | 日线/分钟线数据读写、完整性检查 |
| **因子管理** | `factor_manager.py` | 因子数据读写、IC统计管理 |
| **财务数据管理** | `financial_data_manager.py` | Baostock财务数据获取、批量更新、估值数据 |
| **财务数据源** | `financial_data_source.py` | Baostock API封装（7种报表类型），内置限流控制（每秒1次） |
| **多数据源** | `data_sources.py` | Baostock/Eastmoney/CSV统一封装 |
| **数据提供者** | `data_provider.py` | DataProvider模式（CacheOnly/Online/Backtest） |
| **技术指标** | `factor_data.py` | 30+技术指标计算（趋势类：SMA/EMA/MACD/BB；动量类：RSI/KDJ/CCI；波动率：ATR；成交量：OBV/VWAP等） |
| **缓存策略** | `cache_policy.py` | 数据完整性检查逻辑 |

**数据库表结构（20+张表）**：
- `daily_kline` - 日线数据
- `minute_kline` - 分钟线数据
- 8张财务数据表：
  - `profit_data` - 利润表
  - `balance_data` - 资产负债表
  - `cash_flow_data` - 现金流量表
  - `dupont_data` - 杜邦分析
  - `growth_data` - 成长能力
  - `operation_data` - 营运能力
  - `debt_data` - 偿债能力
  - `valuation_data` - 估值数据
- `factor_values` - 因子值缓存
- `factor_metadata` - 因子元数据
- `scan_results` - 选股扫描结果
- `ic_analysis` / `ic_statistics` - IC分析结果
- `factor_exposure` / `factor_attribution` - 因子暴露度与归因
- `backtest_config` / `backtest_runs` - 回测配置与记录

---

### 2.2 策略模块 (`strategy/`)

| 策略 | 文件 | 说明 |
|------|------|------|
| **均线交叉** | `moving_average.py` | 双均线金叉死叉，支持快速/慢速周期配置 |
| **MACD** | `moving_average.py` | MACD柱状图信号交易 |
| **布林带** | `moving_average.py` | 价格触及轨道交易 |
| **RSI** | `multi_factor.py` | 超买超卖阈值可配置 |
| **多因子** | `multi_factor.py` | 综合多因子选股+择时 |
| **基本面因子** | `fundamental_factors.py` | ROE、PE、PB、营收增长等20+因子 |
| **因子预处理** | `factor_preprocessor.py` | 标准化、正交化、去极值 |

---

### 2.3 回测引擎 (`backtest/`)

| 引擎 | 说明 |
|------|------|
| **BacktestEngine** | 事件驱动回测，支持限价单、止损单，真实滑点模拟 |
| **VectorizedBacktest** | 向量化回测，速度快，适合参数优化 |

**支持功能**：
- 滑点和手续费模拟（佣金0.03%、印花税0.1%）
- 止损止盈
- 最短持股天数限制
- 多头/空头持仓

---

### 2.4 风险管理 (`risk/`)

| 组件 | 文件 | 功能 |
|------|------|------|
| **RiskManager** | `manager.py` | 风险控制检查（持仓限制、回撤限制、日亏损限制） |
| **PositionSizer** | `manager.py` | 5种仓位计算方法：固定金额、固定比例、波动率调整、凯利公式、风险平价 |
| **StopLossManager** | `stop_loss.py` | 止损止盈管理，支持固定比例止损、时间止损、移动止损 |

**仓位分配方法**：
- `equal` - 等权重分配
- `risk_parity` - 风险平价
- `momentum` - 动量加权
- `score` - 评分加权
- `kelly` - Kelly公式最优仓位

---

### 2.5 绩效分析 (`backtest/performance.py`)

**收益指标**：总收益率、年化收益率、月收益率、日/周/月收益统计

**风险指标**：年化波动率、下行波动率、VaR(95%)、CVaR(95%)、偏度、峰度

**风险调整收益**：夏普比率、索提诺比率、卡玛比率、信息比率、特雷诺比率、Omega比率

**回撤分析**：最大回撤、回撤持续时间、恢复时间、平均回撤

**交易统计**：胜率、盈亏比、连续盈亏、最大单笔盈利/亏损

---

### 2.6 组合管理 (`portfolio/`)

| 模块 | 文件 | 功能 |
|------|------|------|
| **多股票回测** | `multi_stock_backtest.py` | 多股票同时持仓、调仓周期、止损机制、完整交易明细 |
| **多因子回测** | `multi_factor_backtest.py` | 因子暴露度跟踪、IC智能加权、收益归因 |
| **选股器** | `selector.py` | 综合打分排序选股，支持持仓/买入/卖出状态 |
| **仓位分配** | `position_sizer.py` | 等权重、风险平价、动量加权、凯利公式 |
| **自选股管理** | `watchlist.py` | CRUD、分组管理、批量导入导出 |
| **信号扫描** | `signal_scanner.py` | 多策略扫描买入/卖出信号，支持历史信号记录 |
| **市场扫描** | `stock_scanner.py` | 全市场股票扫描，支持多策略并发 |
| **IC分析** | `ic_analyzer.py` | IC时间序列、统计计算、IC报告生成 |
| **因子分层分析** | `factor_quantile_analysis.py` | 分层回测收益分析、分组统计 |
| **因子暴露度** | `factor_exposure_tracker.py` | 每日因子暴露度跟踪、可视化 |
| **因子信号生成** | `factor_signal_generator.py` | 因子信号生成器 |
| **因子IC配置** | `factor_ic_configurator.py` | IC统计计算器、因子IC配置 |
| **回测报告** | `backtest_report.py` | 回测报告生成器 |

---

### 2.7 Web界面 (`web/`)

启动命令：`streamlit run web/app.py`

**页面组成**：
| 页面 | 文件 | 说明 |
|------|------|------|
| **主应用** | `app.py` | Streamlit主应用，包含7个标签页 |
| **因子回测页面** | `factor_backtest_page.py` | 多因子回测专用页面 |
| **数据管理页面** | `pages/data_management.py` | 财务数据管理、数据源配置 |

**7个标签页**：

| 标签页 | 功能 |
|--------|------|
| **⭐ 自选股管理** | 自选股列表、行情展示、K线图（日/周/月/年K）、分组管理 |
| **🎯 策略回测** | 单/多股票回测、5种策略（均线/MACD/布林带/RSI/多因子）、参数配置、权益曲线、交易明细表格 |
| **📊 多因子回测** | 因子选择、IC智能加权、因子分析报告、权重对比 |
| **📈 信号扫描** | 多策略扫描、信号筛选（买入/卖出/持仓）、信号详情展示 |
| **📉 绩效分析** | 绩效指标展示（预留） |
| **🔬 因子分析** | 因子有效性分析（预留） |
| **📥 财务数据管理** | 财务数据状态、批量获取、数据更新 |

**Web图表功能**：
- K线图（支持日/周/月/年K周期，红涨绿跌中国惯例）
- 交易信号标记（红▲买入，绿▼卖出）
- 多股票信号子图/热力图
- 权益曲线图
- 信号导出CSV

---

## 三、项目结构

```
quant_system/
├── config.py                 # 配置文件（数据库路径、回测参数）
├── main.py                    # 系统主入口（QuantSystem类）
├── requirements.txt           # 依赖列表
│
├── data/                      # 数据模块
│   ├── __init__.py
│   ├── data_manager.py        # 数据管理器（20+表初始化）
│   ├── kline_manager.py      # K线数据管理
│   ├── factor_manager.py     # 因子数据管理
│   ├── financial_data_manager.py  # 财务数据管理
│   ├── financial_data_source.py  # Baostock API封装
│   ├── data_sources.py       # 多数据源封装
│   ├── market_data_service.py # 市场数据服务（股票列表/指数/分钟线）
│   ├── factor_data.py        # 技术指标计算（30+指标）
│   ├── cache_policy.py       # 缓存策略
│   └── watchlist.json       # 自选股存储
│
├── strategy/                  # 策略模块
│   ├── __init__.py
│   ├── base.py              # 策略基类
│   ├── moving_average.py     # 均线/MACD/布林带策略
│   ├── multi_factor.py       # 多因子/RSI策略
│   ├── fundamental_factors.py # 基本面因子（20+）
│   └── factor_preprocessor.py # 因子预处理
│
├── backtest/                  # 回测模块
│   ├── __init__.py
│   ├── engine.py             # 双引擎（事件驱动/向量化）
│   └── performance.py        # 绩效分析
│
├── risk/                      # 风险管理
│   ├── __init__.py
│   └── manager.py            # 风险管理器+仓位计算
│
├── portfolio/                 # 组合管理
│   ├── __init__.py
│   ├── multi_stock_backtest.py    # 多股票回测引擎
│   ├── multi_factor_backtest.py   # 多因子回测引擎
│   ├── selector.py           # 选股器
│   ├── position_sizer.py     # 仓位分配器
│   ├── watchlist.py          # 自选股管理
│   ├── signal_scanner.py     # 信号扫描器
│   ├── ic_analyzer.py        # IC分析器
│   ├── factor_exposure_tracker.py # 因子暴露度跟踪
│   └── backtest_report.py    # 回测报告
│
├── web/                       # Web界面
│   ├── __init__.py
│   ├── app.py                # Streamlit主应用（7标签页）
│   ├── factor_backtest_page.py   # 多因子回测专用页面
│   ├── services/
│   │   ├── backtest_service.py        # 回测执行服务
│   │   ├── backtest_presenter.py      # 回测结果展示服务
│   │   └── backtest_params_service.py # 回测参数构建与校验
│   └── pages/
│       └── data_management.py   # 数据管理页面
│
├── analysis/                    # 分析工具
│
├── execution/                   # 交易执行层（预留）
│
├── tests/                      # 测试模块
│   ├── test_single_stock_backtest.py   # 单股票回测
│   ├── test_multi_stock_backtest.py    # 多股票回测
│   ├── test_real_data_backtest.py      # 实盘数据回测
│   ├── test_stop_loss.py               # 止损测试
│   ├── test_position_limit.py          # 仓位限制测试
│   ├── test_data_management.py          # 数据管理测试
│   ├── test_factor_display.py           # 因子展示测试
│   ├── test_trade_details_fix.py       # 交易明细修复测试
│   └── test_web_backtest.py            # Web回测测试
│   ├── test_services_phase4.py         # 服务层回测测试
│   └── test_config_paths_phase4.py     # 配置路径一致性测试
│
├── docs/                       # 设计文档
│   ├── architecture_analysis.md      # 架构分析
│   ├── baostock_data_fetch_plan.md    # Baostock数据获取方案
│   ├── factor_data_real_replacement_plan.md  # 模拟因子替换真实数据方案
│   ├── factor_value_display_plan.md
│   ├── factor_score_display_plan.md
│   └── financial_factor_generation_plan.md
│
└── design_*.md                # 5阶段设计文档
    ├── design_phase1_financial_data.md
    ├── design_phase2_fundamental_factors.md
    ├── design_phase3_stock_selection.md
    ├── design_phase4_multi_factor_backtest.md
    ├── design_phase5_web_factor_backtest.md
    └── design_multi_factor_system.md
```

---

## 四、技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python 3.8+ |
| **数据处理** | pandas, numpy |
| **数据获取** | baostock, eastmoney |
| **技术指标** | pandas-ta, scipy |
| **可视化** | matplotlib, plotly, seaborn |
| **Web框架** | Streamlit |
| **数据库** | SQLite |
| **其他** | python-dateutil, pytz |

---

## 五、启动方式

```bash
# 进入项目目录
cd quant_system

# 安装依赖
pip install -r requirements.txt

# 运行主程序（命令行演示）
python main.py

# 启动Web界面
streamlit run web/app.py
```

---

## 六、快速使用

### 6.1 代码调用

```python
from main import QuantSystem

# 初始化
system = QuantSystem({
    'initial_capital': 1000000,
    'commission_rate': 0.0003
})

# 单策略回测
results = system.run_backtest(
    strategy='ma_cross',
    symbol='000001.SZ',
    start_date='2023-01-01',
    end_date='2024-12-31',
    strategy_params={'fast_period': 20, 'slow_period': 60}
)

# 多策略对比
comparison = system.compare_strategies(
    strategies=['ma_cross', 'macd', 'rsi'],
    symbol='000001.SZ',
    start_date='2023-01-01',
    end_date='2024-12-31'
)

# 参数优化
optimization = system.optimize_parameters(
    strategy='ma_cross',
    symbol='000001.SZ',
    start_date='2023-01-01',
    end_date='2024-12-31',
    param_grid={
        'fast_period': [5, 10, 20],
        'slow_period': [30, 60, 120]
    }
)
```

### 6.2 Web界面使用

1. 启动：`streamlit run web/app.py`
2. 自选股管理：添加股票到自选列表
3. 策略回测：选择股票、策略、参数，运行回测
4. 查看结果：权益曲线、交易明细、绩效指标

### 6.3 数据源配置

系统支持多个数据源，配置优先级：**Baostock > CSV**

| 数据源 | 说明 | 格式转换 |
|--------|------|----------|
| **Baostock** | 主要数据源，支持日线、财务数据 | 000001.SH → sh.000001 |
| **CSV** | 本地数据文件 | - |

**数据库路径（默认）**：`quant_system/quant_data.db`

### 6.4 数据库表一览

| 表名 | 用途 |
|------|------|
| `daily_kline` | 日线行情 |
| `minute_kline` | 分钟线行情 |
| `profit_data` | 利润表数据 |
| `balance_data` | 资产负债表 |
| `cash_flow_data` | 现金流量表 |
| `dupont_data` | 杜邦分析数据 |
| `growth_data` | 成长能力指标 |
| `operation_data` | 营运能力指标 |
| `debt_data` | 偿债能力指标 |
| `valuation_data` | 估值指标 |
| `factor_values` | 因子值缓存 |
| `factor_metadata` | 因子元数据 |
| `ic_analysis` | IC分析结果 |
| `ic_statistics` | IC统计结果 |
| `factor_exposure` | 因子暴露度 |
| `factor_attribution` | 收益归因 |
| `scan_results` | 选股扫描结果 |
| `backtest_config` | 回测配置 |
| `backtest_runs` | 回测记录 |

---

## 七、已知问题与优化方向

### 架构问题（详见 `docs/architecture_analysis.md`）

| 优先级 | 问题 | 建议 |
|--------|------|------|
| P0 | 数据获取与回测耦合 | 引入DataProvider概念 |
| P0 | Web session_state滥用 | 重构为Pydantic dataclass |
| P1 | DataManager职责过重 | 分离为KlineManager/FactorManager/FinancialManager |
| P1 | Web层和业务逻辑耦合 | 抽取业务服务层 |

### 待完成功能

- [x] 止损模块 ✅ 已实现
- [ ] 止盈模块
- [ ] 参数优化（网格搜索）
- [ ] 日志系统
- [ ] 实盘交易接口
- [ ] 技术指标库完善（KDJ、布林带）

---

## 八、重构进展（2026-05）

- **阶段1（入口与配置）**：统一数据库路径为 `config.DATABASE_PATH`，启动时打印实际生效路径。
- **阶段2（Web服务层）**：`web/app.py` 回测执行链已拆分到 `web/services/`。
- **阶段3（DataManager收敛）**：市场数据能力下沉到 `MarketDataService`，近期更新逻辑下沉到 `KlineManager`。
- **阶段4（测试与文档）**：新增服务层测试与配置路径测试，文档已同步。

---

## ⚠️ 风险提示

1. **本系统仅供学习研究使用，不构成投资建议**
2. 回测结果不代表未来收益
3. 量化交易存在风险，请谨慎使用
4. 实盘交易前请充分测试策略

---

**免责声明**：本系统仅供学习研究使用，投资有风险，入市需谨慎。
