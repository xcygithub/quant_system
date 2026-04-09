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
- **position_sizer.py 仓位分配 bug (2026-04-08)**: 当 `max_single_position=0.2` 时，高价股票（如000001.SH上证指数价格2700+）按20%仓位只能分配20万，但买入100股需要27万+，导致 `shares=0`。这些无法买入的股票的权重之前会被保留但实际上没有被使用，造成资金浪费。**修复**: 在 `allocate()` 方法中，当某只股票因金额不足无法购买100股时，释放其权重给其他股票。**解决方案**: 交易高价股票时需要将 `max_single` 设置为30%或更高。

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
1. 止损止盈模块
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
