# 量化系统 - 长期记忆

## 项目概述
- 路径: c:\Users\FY\WorkBuddy\Claw\quant_system\
- 框架: Streamlit Web界面 + SQLite本地缓存
- 数据源: Baostock > CSV（只保留这两个数据源）

## 用户偏好与习惯
- 用户使用中文交流
- 量化交易系统项目
- 关注功能完整性和代码质量
- **重要工作习惯**: 每次写完代码必须验证，确保修改生效后再结束任务

## 问题处理方法论（必须遵循）
遇到任何 bug/问题时，严格按以下流程处理：
1. **精准找到问题** - 阅读代码，追踪逻辑链路，定位根本原因。不要猜测，不要治标不治本。
2. **修改代码** - 针对根本原因修复，确保修改精准有效。
3. **写测试用例** - 验证修复生效，确保不再回归。

## 项目已知问题
1. stop_loss.py 缺失 - risk目录缺少
2. 参数优化为空实现
3. 技术指标库不完整

## 数据库路径配置
- **重要修复 (2026-04-07)**：统一使用 `C:\Users\FY\WorkBuddy\Claw\quant_data.db`
- 原问题：存在两个数据库文件造成混乱
- 修复方式：`DataManager` 默认使用 `Claw` 目录下的数据库

## 数据源配置
- **只保留 Baostock 和 CSV 两个数据源** (2026-04-08 更新)
- 优先级: Baostock > CSV
- Baostock 代码格式: 需处理后缀 (.SZ/.SH/.BJ)，正确转换为 sh./sz. 前缀
- **重要**: Baostock 根据后缀判断交易所，000001.SH=上证指数，000001.SZ=平安银行，不能混淆
- 上证指数=000001.SH, 深圳指数=399001.SZ

## 数据读取逻辑（2026-04-08）
- **核心原则**: 先从数据库读取，如果没有数据再从 Baostock 获取
- **读取流程**:
  1. 先从 `quant_data.db` 的 `daily_kline` 表读取股票日线数据
  2. 检查数据完整性（`_check_data_complete` 方法）
  3. 如果数据库中没有数据或不完整，从 Baostock 获取数据
  4. 获取后保存到数据库（`_save_kline_to_db` 方法，先删除再插入避免冲突）
- **数据完整性判断**: 估算交易日数量约为日历天的40%，数据条数 >= 估算交易日×0.85 则认为完整

## 字段映射修复 (2026-04-07)
- AkShare `涨跌额` → `change_amount` (原错误映射为 `change`)
- Eastmoney `涨跌额` → `change_amount` (原错误映射为 `change`)
- 数据库表字段名为 `change_amount`

## 数据保存逻辑修复 (2026-04-07)
- 修复 `INSERT OR REPLACE` 的 UNIQUE constraint 问题
- 改用"先删除再插入"的事务方式确保数据保存成功

## 踩坑经验
- Baostock 代码转换: 不能用数字开头判断(6->sh)，必须用原后缀判断(.SH->sh, .SZ->sz)
- VectorizedBacktest.run(): pct_change()返回NaN导致权益计算错误，需fillna(0)
- multi_stock_backtest: 需要先set_data()再run()，注意方法调用顺序
- StockScore.signal_type默认值是""，导致select_buy_candidates无法匹配"buy"/"hold"，应改为"hold"
- **日期类型不匹配**: df['date']是字符串'2023-01-03'，而all_dates是Timestamp，直接==比较失败，需统一转为字符串
- **position_sizer.py 仓位分配 bug (2026-04-08 已修复)**:
  - **问题**: 当某只股票因金额不足无法购买100股时，权重重新分配逻辑导致其他股票仓位超过 max_single_position 限制
  - **原修复**: 释放无法买入股票的权重给其他股票
  - **新发现bug**: 重新分配时没有检查 max_single_position 限制，导致重新分配后单只仓位超过20%
  - **最终修复 (2026-04-09)**: 移除权重重新分配逻辑。无法买入100股的股票直接将其权重设为0，不再重新分配给其他股票，确保每只股票仓位严格不超过 max_single_position
- **_buy 仓位检查只看单次不看累计 (2026-04-09 已修复)**:
  - **问题**: `_buy()` 方法中 `max_single_amount` 只检查本次买入金额，不考虑已有持仓市值。每次调仓都给同一股票加仓，导致累计持仓远超 max_single_position
  - **场景**: 单只股票回测（max_positions=1），每次调仓加仓20%，5次后满仓100%
  - **修复1**: `_buy()` 中改为 `current_holding_value + amount > max_single_amount` 检查累计持仓
  - **修复2**: `_rebalance()` 中改为差额买入逻辑：`buy_amount_needed = target_amount - current_holding`，已达目标仓位的不再加仓
- **_check_data_complete 时间判断 bug (2026-04-21 已修复)**:
  - **问题**: 用 `datetime.now()`（当前日期）判断数据是否"最新"，导致回测历史数据时被认为"过时"
  - **场景**: 回测区间 2023-01-01 到 2024-03-19，数据库中有完整数据，但每次都重新获取
  - **修复**: 当 end_date 是历史日期时，用 end_date 作为参考日期；只有 end_date 是今天或未来时才用当前日期逻辑（考虑周末）
- **multi_factor_backtest.py 信号生成缺失 (2026-04-21 已修复)**:
  - **问题**: MultiFactorBacktest 没有覆盖 set_data 方法生成因子信号，导致回测没有交易
  - **修复**: 重写 set_data 方法，遍历每个交易日调用 _generate_factor_signals 生成信号
- **multi_factor_backtest.py 因子面板数据源 bug (2026-04-21 已修复)**:
  - **问题**: _build_factor_panel 从 stock_data（K线数据）中查找因子，但因子数据实际在 factor_data_cache 中
  - **修复**: 优先从 factor_data_cache 获取因子数据，兼容从 stock_data 获取
- **_render_trade_details 列名不匹配 (2026-04-21 已修复)**:
  - **问题**: 期望英文列名（symbol/direction），实际返回中文列名（股票/状态）
  - **修复**: 适配实际列名 '股票'、'状态'、'收益率（%）'、'收益金额（元）'
- **_calculate_results 缺少 trade_details (2026-04-21 已修复)**:
  - **问题**: _calculate_results 返回的结果中没有包含 trade_details 字段
  - **修复**: 在返回值中添加 `'trade_details': self.get_trade_details_df()`

## 回测引擎修复 (2026-04-07)
1. **backtest/engine.py**:
   - VectorizedBacktest.run()中market_return.pct_change()第一值为NaN，添加fillna(0)
   - strategy_return计算时NaN问题，添加fillna(0)
2. **portfolio/selector.py**:
   - StockScore.signal_type默认值改为"hold"（原为""）
3. **portfolio/multi_stock_backtest.py**:
   - _get_common_dates空数组时先检查再访问
   - 添加needs_initial_position逻辑支持首次强制调仓
   - **关键修复**: _get_prices_on_date中日期类型不匹配问题（df['date']是字符串，但all_dates是Timestamp），导致prices永远为空。修复：统一转为字符串比较
4. **web/app.py**:
   - 单股票回测equity_curve列名修复（date->需添加，total_value->strategy_equity）
   - 修复变量名错误：strat->strategy

## 回测模块重构 (2026-04-07 晚)
**web/app.py 策略回测Tab重构**:
- 取消单股票/多股票回测模式的radio切换按钮
- 自动读取自选股列表（wl_manager.get_all_stocks()）
- 每只股票前显示复选框，勾选参与回测
- session_state['backtest_selected_stocks'] 存储选中股票
- 选中1只股票 → 单股票回测逻辑（简洁信号图plot_signals_only）
- 选中多只股票 → 多股票回测逻辑（子图/热力图+组合参数）
- 组合参数（最大持仓数、调仓周期、仓位分配方法等）仅在选中多只时显示

## 已完成功能（2026-04-07）
1. **多股票回测功能** - portfolio模块
   - 自选股管理 (watchlist.py)
   - 选股排序 (selector.py)
   - 仓位分配 (position_sizer.py)
   - 多股票回测引擎 (multi_stock_backtest.py)
2. **Web界面更新** - 新增自选股管理标签页，支持多股票回测
3. **单股票回测交易记录表格** - web/app.py
   - 显示每次操作的收益率明细表格
   - 包含：买入日期/价格/数量/金额，卖出日期/价格/金额
   - 显示：持有天数、收益率、净收益率、收益金额、手续费、状态
   - 持有中股票单独显示浮动盈亏
   - 股票买卖数量已确保为100的整数倍
4. **多股票回测交易详情表格** - portfolio/multi_stock_backtest.py
   - 新增TradeDetail类用于配对买卖计算收益率
   - 新增get_trade_details_df()方法，返回完整交易明细
   - 包含：交易ID、股票代码、买入日期/价格/数量/金额/手续费
   - 包含：卖出日期/价格/数量/金额/手续费、持有天数
   - 包含：收益率、净收益率、收益金额、状态（已卖出/持有中）
   - _buy/_sell方法已确保数量为100整数倍
   - active_trades字典追踪未平仓交易，回测结束时正确处理
5. **交易信号图** - web/app.py（已重构简化）
   - plot_signals_only()：简洁的-1/0/1信号柱状图，横轴日期，纵轴信号
     - 红色柱=买入(1)，绿色柱=卖出(-1)，灰色柱=持仓(0)
     - 参考线标注买入/卖出/持仓位置
   - plot_kline_with_signals()：保留K线+信号叠加图（带MA均线+成交量+信号子图）
   - 单股票回测使用简洁的plot_signals_only()
6. **多股票信号图** - web/app.py
   - plot_multi_stock_signals()：子图分股票展示，每只股票一行简洁信号柱
   - plot_signals_heatmap()：日期×股票的信号热力图，红买绿卖
   - export_signals_to_csv()：导出信号数据到CSV文件
   - 多股票回测可选择：子图展示/热力图/不显示

## 待完成功能
1. 止盈模块（止损已实现）
2. 技术指标库（KDJ、布林带完善）
3. 参数优化（网格搜索）
4. 日志系统

## 已完成功能（2026-04-09）
### 最短持股天数参数
**新增回测参数 `min_holding_days`**：
- 买入股票后，最少持有该天数才能卖出
- 0表示不限制
- 适用场景：避免频繁交易，减少手续费损耗

**修改文件**：
1. `portfolio/multi_stock_backtest.py`:
   - `PortfolioPosition` 添加 `entry_date` 字段和 `get_holding_days()` 方法
   - `__init__` 添加 `min_holding_days` 参数
   - `_check_sell_signals` 添加最短持股天数检查
   - `_rebalance` 调仓换股时检查最短持股天数
   - `_buy` 记录买入日期
2. `backtest/engine.py`:
   - `VectorizedBacktest` 添加 `min_holding_days` 参数
   - `_generate_trades` 卖出时检查最短持股天数
3. `web/app.py`:
   - UI添加最短持股天数输入框（0-60天）
   - 单股票和多股票回测都支持该参数

### 交易明细表格字段名优化（2026-04-09）
**需求**：将表格中数值后面的单位符号移到字段名上，如"收益率（%）"。

**修改文件**：
1. `web/app.py`（单股票回测明细表）:
   - `买入价格` → `买入价格（元）`，数值为纯数字
   - `买入金额` → `买入金额（元）`
   - `卖出价格` → `卖出价格（元）`
   - `卖出金额` → `卖出金额（元）`
   - `收益率` → `收益率（%）`，数值为百分比数值（如 5.23 表示 5.23%）
   - `净收益率` → `净收益率（%）`
   - `收益金额` → `收益金额（元）`
   - `手续费` → `手续费（元）`
   - 持仓明细markdown显示也做了相应调整

2. `portfolio/multi_stock_backtest.py`（多股票回测 `get_trade_details_df()` 方法）:
   - 同样的字段名调整
   - 数值不再包含单位符号

### 止损参数功能（2026-04-09）
**新增回测参数 `stop_loss`**：
- 亏损超过此比例时自动平仓
- 输入正数（如10表示10%），内部存储为负数（-0.1）
- 0表示不止损

**修改文件**：
1. `portfolio/multi_stock_backtest.py`:
   - `__init__` 添加 `stop_loss` 参数
   - 新增 `_check_stop_loss()` 方法
   - 每日循环中调用止损检查
2. `backtest/engine.py`:
   - `VectorizedBacktest` 添加 `stop_loss` 参数
   - `_generate_trades()` 中每日检查止损
3. `web/app.py`:
   - UI添加"止损比例（%）"输入框（0-50%）
   - 单股票和多股票回测都支持

### 数据更新逻辑修复（2026-04-13）
**问题1**：`_check_data_complete` 只检查"数据条数"，不检查"数据是否最新"。

**修复1**：
- 增加日期时效性检查：检查最新日期是否 >= 最近一个交易日
- 考虑周末：周一参考日期是上周五（3天前），而不是简单的昨天

**修改文件**：`data/data_manager.py`
- `_check_data_complete`：增加日期时效性检查（考虑周末）
- `update_recent_data`：使用 `_check_data_complete` 替代内联检查

## Phase 1 完成：Baostock 财务数据获取与存储（2026-04-14）

### 新增文件
1. `data/financial_data_source.py` - Baostock 财务数据获取器
   - 支持 7 种财务数据类型获取
   - 内置 API 限流控制（每秒1次）
   - 代码格式自动转换（000001.SZ ↔ sz.000001）

2. `data/financial_data_saver.py` - 财务数据持久化
   - 批量保存 DataFrame 到 SQLite
   - INSERT OR REPLACE 避免重复
   - 自动判断报表类型（年报/中报/季报）

3. `data/financial_data_manager.py` - 统一接口
   - update_single_stock() / batch_update() 更新数据
   - get_financial_data() / get_valuation() 读取数据
   - get_data_freshness() 数据新鲜度检查

### 数据库扩展
新增 8 张财务数据表：
- profit_data（利润表）、balance_data（资产负债表）
- cash_flow_data（现金流量表）、dupont_data（杜邦分析）
- growth_data（成长能力）、operation_data（营运能力）
- debtpaying_data（偿债能力）、valuation_data（估值数据）
- factor_cache（因子缓存）、update_log（更新日志）

### 与 DataManager 集成
- `DataManager.get_financial_manager()` 获取财务管理器
- `DataManager.get_profit/get_balance/get_cash_flow/get_dupont()` 便捷方法
- `DataManager.get_valuation()` 获取估值
- `DataManager.update_financial_data()` 更新财务数据

### Baostock API 字段映射
- query_profit_data: statDate, roeAvg, npMargin, gpMargin, netProfit, epsTTM, MBRevenue
- query_balance_data: statDate, totalAsset, totalLiab, equity
- query_cash_flow_data: statDate, operCashFlow, investCashFlow, financeCashFlow
- query_dupont_data: statDate, roe, assetStoTurn, equityMultipler, profitToSales
- query_stocks: code, code_name, tradeDate, pe, pb, marketCap, totalShares

## Phase 2 完成：基本面因子计算与预处理（2026-04-19）

### 新增文件
1. `strategy/fundamental_factors.py` - 基本面因子计算器
   - 5大类因子：估值(PE/PB/PS/PCF)、盈利(ROE/ROA/毛利率/净利率)
   - 成长(营收增长/利润增长/净资产增长)、财务结构、现金流
   - 衍生因子：PB_ROE、PE_Growth、Altman_Z
   - `calculate_all_factors()` 单股票因子计算
   - `get_factor_panel()` 多股票因子面板

2. `strategy/factor_preprocessor.py` - 因子预处理器
   - 缺失值处理（中位数/均值/行业中位数）
   - Winsorization缩尾处理（±3σ）
   - 标准化（Z-score/Rank/MinMax/MAD）
   - 中性化（行业中性/市值中性/风格中性）

3. `strategy/factor_neutralizer.py` - 因子中性化（集成到preprocessor）

### 数据库扩展
- `factor_values` 表：每日因子值缓存
- `factor_metadata` 表：因子元数据（24个预设因子）

### 扩展现有模块
1. `data/data_manager.py`：
   - 新增 factor_values、factor_metadata 表
   - 插入24个默认因子元数据

2. `data/factor_data.py`：
   - 新增 `merge_fundamental_factors()` 方法

3. `portfolio/selector.py`：
   - StockScore 新增基本面打分维度（valuation/profitability/growth/financial_quality）
   - 新增 `fundamental_factors` 参数
   - 新增 `_calculate_fundamental_scores()` 方法

4. `strategy/__init__.py`：
   - 导出 FundamentalFactors、FactorPreprocessor、FactorNeutralizer

## Phase 3 完成：选股层搭建 - 全市场选股与 IC 分析（2026-04-20）

### 新增文件
1. `portfolio/stock_scanner.py` - 全市场选股扫描器
   - MarketStockScanner 类：批量扫描全市场股票
   - 支持 ST 过滤、新股过滤、低市值过滤
   - 批量计算技术因子 + 基本面因子
   - 因子预处理和综合打分

2. `portfolio/ic_analyzer.py` - IC 分析器
   - ICAnalyzer 类：计算因子 IC（信息系数）和 IR（信息比率）
   - 支持 Spearman/Pearson 两种相关系数
   - IC 时间序列分析
   - IC 有效性判定（强有效/有效/弱有效/无效）
   - 生成 IC 分析报告

3. `portfolio/factor_quantile_analysis.py` - 因子分层回测
   - FactorQuantileAnalysis 类：五分位数分层分析
   - 多空组合收益计算
   - 分层回测可视化
   - 生成分层回测报告

### 扩展现有模块
1. `portfolio/selector.py`：
   - 新增 `batch_score_from_factors()` 批量打分方法
   - 新增 `get_top_candidates()` 获取候选股票
   - 新增 `export_scores()` 导出评分结果
   - 新增 `get_factor_importance()` 分析因子重要性

2. `portfolio/__init__.py`：
   - 导出 MarketStockScanner, scan_market
   - 导出 ICAnalyzer, calculate_factor_ic, get_ic_report
   - 导出 FactorQuantileAnalysis, ICAnalysisVisualizer

3. `data/data_manager.py`：
   - 新增 `scan_results` 表：选股扫描结果记录
   - 新增 `ic_analysis` 表：每日 IC 计算结果
   - 新增 `ic_statistics` 表：因子 IC 统计
   - 创建相关索引

### IC 判定规则
| IC/IR 范围 | 判定 | 建议 |
|------------|------|------|
| IR > 0.5 且 IC > 0.03 | 强有效因子 | 高权重 |
| IR > 0.3 且 IC > 0.02 | 有效因子 | 正常权重 |
| IR > 0.2 且 IC > 0.01 | 弱有效 | 观察使用 |
| IR < 0.2 或 IC < 0 | 无效因子 | 不使用 |

## Phase 4 完成：回测层完善 - 多因子回测引擎（2026-04-20）

### 新增文件
1. `portfolio/factor_signal_generator.py` - 因子信号生成器
   - FactorSignalGenerator 类：根据因子 IC 加权得分生成交易信号
   - 支持横截面百分位计算
   - 支持排名信号和买卖信号生成

2. `portfolio/factor_exposure_tracker.py` - 因子暴露度跟踪器
   - FactorExposureTracker 类：跟踪组合在各因子上的暴露度
   - 计算因子收益率（横截面回归法）
   - 收益归因分析

3. `portfolio/factor_ic_configurator.py` - IC 动态配置器
   - FactorICConfigurator 类：根据 IC 统计动态调整因子权重
   - ICStatsCalculator 类：计算和保存 IC 统计
   - 权重调整规则：强有效1.5x，有效1.0x，弱有效0.5x，无效0.0x

4. `portfolio/multi_factor_backtest.py` - 多因子回测引擎
   - MultiFactorBacktest 类：继承 MultiStockBacktest
   - 集成因子信号生成、IC 动态权重、暴露度分析
   - 生成因子归因分析报告

5. `portfolio/backtest_report.py` - 回测报告生成器
   - BacktestReport 类：生成增强回测报告
   - 支持导出 Excel/HTML
   - 包含因子暴露度、归因分析、IC 有效性回顾

### 扩展现有模块
1. `data/data_manager.py`：
   - 新增 `factor_exposure` 表：因子暴露度记录
   - 新增 `factor_attribution` 表：因子收益归因
   - 新增 `backtest_config` 表：多因子回测配置
   - 新增 `backtest_runs` 表：回测期间记录

2. `portfolio/__init__.py`：
   - 导出 Phase 4 新模块

### IC 权重调整规则
| 有效性判定 | IC/IR 条件 | 调整系数 | 单一上限 |
|------------|-----------|----------|----------|
| 强有效 | IC>3% 且 IR>0.5 | 1.5x | 40% |
| 有效 | IC>2% 且 IR>0.3 | 1.0x | 30% |
| 弱有效 | IC>1% 且 IR>0.2 | 0.5x | 20% |
| 无效/不稳定 | IC<0 或 IR<0.2 | 0.0x | 排除 |

### 使用示例
```python
from portfolio.multi_factor_backtest import run_multi_factor_backtest

results = run_multi_factor_backtest(
    symbols=stock_pool,
    stock_data=stock_data,
    start_date='2023-01-01',
    end_date='2024-03-19',
    initial_capital=1000000,
    max_positions=5,
    rebalance_days=20,
    factor_weights={
        'roe': 0.25,
        'pe': 0.15,
        'momentum_20': 0.20
    },
    use_ic_weighting=True
)

# 生成报告
from portfolio.backtest_report import BacktestReport
report = BacktestReport(results, results['factor_report'])
report.export_to_excel('multi_factor_backtest.xlsx')
```

## Phase 5 完成：Web界面 - 因子配置与回测面板（2026-04-20）

### 新增文件
1. `web/factor_backtest_page.py` - 多因子回测Web页面（约400行）
   - `render_factor_backtest_page()`: 主渲染函数
   - `FACTOR_CATEGORIES`: 因子分类定义（5类22个因子）
   - `DEFAULT_FACTORS`: 默认因子配置
   - 侧边栏配置：因子选择、权重设置、IC加权参数、回测参数
   - 主内容区：收益概览、因子分析、交易明细、配置管理

### 扩展现有文件
1. `web/app.py`:
   - 新增导入 `from quant_system.web.factor_backtest_page import render_factor_backtest_page`
   - 标签页从5个扩展到6个
   - 新增 Tab 3: 📊 多因子回测

### Web 标签页结构
| Tab | 名称 | 说明 |
|-----|------|------|
| Tab 1 | ⭐ 自选股管理 | 自选股行情展示 |
| Tab 2 | 🎯 策略回测 | 单股票/多股票策略回测 |
| Tab 3 | 📊 多因子回测 | Phase 5 新增 |
| Tab 4 | 📈 信号扫描 | 批量信号扫描 |
| Tab 5 | 📉 绩效分析 | 绩效分析 |
| Tab 6 | 🔬 因子分析 | 因子IC分析 |

### 因子分类（5类22个因子）
- **基本面因子**：roe, roa, gross_margin, net_margin, eps, revenue_growth, profit_growth, asset_turnover
- **估值因子**：pe, pb, ps, pcf
- **技术因子**：momentum_20, momentum_60, volatility_20, volume_ratio, turnover_rate
- **财务结构**：debt_ratio, current_ratio, quick_ratio
- **情绪因子**：price_volume_trend, relative_strength

### Web界面功能
1. **侧边栏配置**
   - 因子分类多选（expander折叠）
   - 权重模式切换：IC智能加权 / 手动设置
   - IC加权参数：更新频率、历史窗口
   - 股票池来源：自选股 / 自定义列表
   - 回测参数：期间、资金、持仓、风控

2. **主内容区（4个标签页）**
   - 收益概览：指标卡片、权益曲线、月度收益
   - 因子分析：权重对比、IC判定、暴露度时序、归因分析
   - 交易明细：可筛选的交易记录表
   - 配置管理：保存/加载配置、历史记录

3. **进度回调**
   - 实时显示回测进度
   - 支持中断回测










