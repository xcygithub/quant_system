# 量化交易系统（Quant System）

一个基于 Python + Streamlit 的本地量化研究系统，覆盖：
- 行情与财务数据管理
- 单策略/多股票回测
- 多因子回测与因子分析
- 信号扫描与结果展示

---

## 快速开始

```bash
pip install -r requirements.txt
streamlit run web/app.py
```

默认数据库：`quant_data.db`

---

## 主要目录

```text
quant_system/
├── config.py
├── main.py
├── data/
├── strategy/
├── portfolio/
├── backtest/
├── risk/
├── web/
├── tests/
└── docs/
```

---

## 模块说明

### `data/` 数据层
- `data_manager.py`：统一数据入口与数据库初始化
- `kline_manager.py`：K 线数据管理
- `financial_data_manager.py`：财务数据更新与查询
- `financial_data_source.py`：Baostock 财务接口封装（已优化为懒登录）
- `factor_manager.py`：因子值与因子元数据管理
- `data_provider.py`：`CacheOnlyProvider` / `OnlineProvider` 等提供者

### `strategy/` 策略与因子计算
- `moving_average.py`：MA/MACD/布林带等策略
- `multi_factor.py`：多因子策略逻辑
- `fundamental_factors.py`：基本面因子计算
- `factor_preprocessor.py`：因子预处理

### `portfolio/` 组合与回测业务
- `multi_stock_backtest.py`：多股票回测
- `multi_factor_backtest.py`：多因子回测
- `selector.py` / `position_sizer.py`：选股与仓位分配
- `signal_scanner.py` / `stock_scanner.py`：信号与标的扫描

### `web/` 可视化界面
- `web/app.py`：主应用（策略回测、多因子回测、信号扫描等）
- `web/factor_backtest_page.py`：多因子回测页
- `web/factor_analysis_page.py`：因子分析页
- `web/pages/data_management.py`：数据管理页
- `web/services/`：回测参数构建、执行与结果展示服务

---

## 当前测试集

当前保留并可收集的测试文件（`tests/`）：
- `test_services_phase4.py`
- `test_single_stock_backtest.py`
- `test_stop_loss.py`
- `test_position_limit.py`
- `test_real_data_backtest.py`
- `test_trade_details_fix.py`
- `test_web_backtest.py`
- `test_p0_factor_fixes.py`
- `test_p0_factor_batch_query.py`
- `test_p1_backtest_and_source_refactor.py`

说明：历史调试脚本与无效测试（路径硬编码、收集报错项）已清理。

---

## 常用命令

```bash
# 运行 Web
streamlit run web/app.py

# 仅检查测试收集
pytest --collect-only -q

# 运行全部测试
pytest -q
```

---

## 数据与性能说明

- 多数回测/因子准备链路优先走本地数据库缓存。
- 仅在需要在线抓取财务数据时才触发 Baostock 登录。
- Streamlit 侧结束日期默认已调整为“至今（当天）”。

---

## 风险提示

本项目仅用于学习与研究，不构成任何投资建议。  
实盘前请进行充分回测、参数稳健性验证与风险评估。

