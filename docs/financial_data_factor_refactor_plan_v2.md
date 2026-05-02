# 财务数据与因子分析重构方案（V2）

## 1. 背景与目标

当前系统在财务数据与因子分析链路存在以下问题：

- 多因子回测页面仍使用 `np.random` 模拟关键基本面因子，导致回测信号失真。
- 财务数据采集链路未完整覆盖 Baostock 财务菜单中红框对应的全部季度能力数据。
- 偿债能力数据在现有代码中默认未进入更新流程。
- 估值数据虽然有落库，但字段覆盖与后续因子使用不统一。
- 因子计算对财务字段依赖与数据表映射不够完整，部分因子被临时移除或退化。

本次重构目标：

1. 覆盖并保存红框对应的全部财务数据类型：
   - 季度盈利能力
   - 季度营运能力
   - 季度成长能力
   - 季度偿债能力
   - 季度现金流量
   - 季度杜邦指数
2. 同步纳入估值数据（PE/PB/PS/PCF 及相关字段）的标准化落库。
3. 因子分析和多因子回测统一改为真实财务/估值/行情数据驱动，不再使用随机因子。
4. 在不破坏现有业务接口的前提下，提供可扩展的“全字段保存”能力。

参考文档：<https://www.baostock.com/mainContent?file=home.md>

---

## 2. 重构范围

### 2.1 数据采集层（`data/financial_data_source.py`）

- 统一季度接口调用逻辑，收敛重复代码。
- 对以下数据类型建立完整采集入口：
  - `profit`
  - `operation`
  - `growth`
  - `debtpaying`
  - `cash`
  - `dupont`
- 估值：
  - 保留全市场估值拉取能力。
  - 保留单股历史估值拉取能力。
  - 统一字段命名并增加原始字段保留。

### 2.2 数据落库层（`data/financial_data_saver.py`）

- 在现有结构化表（`profit_data` 等）继续保存核心可计算字段。
- 新增“原始全字段存储”能力，确保接口返回字段不丢失：
  - 新增 `financial_data_raw`（建议）用于按 `symbol + data_type + report_date/trade_date` 存储 `raw_json`。
- 估值数据保存与财务数据保存采用一致的容错与字段规范。

### 2.3 数据管理层（`data/financial_data_manager.py`）

- 默认更新类型调整为“红框六类 + 可选估值”。
- 恢复偿债能力数据更新链路，不再被注释跳过。
- 批量更新与数据新鲜度检查覆盖新增/恢复的数据类型。

### 2.4 因子计算层（`strategy/fundamental_factors.py`）

- 因子与数据来源映射按照真实接口字段重构：
  - 估值因子：`pe/pe_ttm/pb/ps/pcf`
  - 盈利因子：`roe/roe_avg/gross_margin/net_margin/eps_ttm`
  - 成长因子：`revenue_growth/profit_growth/equity_growth/profit_cagr`
  - 结构因子：`debt_ratio/current_ratio/quick_ratio/equity_multiplier`
  - 现金流因子：`cash_to_profit/fcf/cash_yield`
  - 扩展因子：`asset_turnover` 等
- 对“字段缺失、同名异义、0 值占位”增加显式兜底和日志标记。

### 2.5 因子展示与回测层（`web/factor_presenter.py`、`web/factor_backtest_page.py`）

- 因子展示与分类恢复到真实可计算因子集合。
- 多因子回测 `_prepare_factor_data()` 改为真实因子面板构建：
  - 基本面因子来自数据库财务表与估值表
  - 技术因子来自行情数据计算
- 删除随机数模拟因子逻辑。

---

## 3. 数据模型与落库策略

### 3.1 保留现有结构化表（核心计算用）

- `profit_data`
- `balance_data`
- `cash_flow_data`
- `dupont_data`
- `growth_data`
- `operation_data`
- `debtpaying_data`
- `valuation_data`

### 3.2 新增原始表（全字段归档）

建议新增表：

```sql
CREATE TABLE IF NOT EXISTS financial_data_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    data_type TEXT NOT NULL,          -- profit/balance/cash/dupont/growth/operation/debtpaying/valuation
    report_date TEXT,                 -- 季频数据使用
    trade_date TEXT,                  -- 日频估值使用
    baostock_code TEXT,
    raw_json TEXT NOT NULL,           -- 接口完整返回行(JSON)
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, data_type, report_date, trade_date)
);
```

说明：

- 结构化表用于计算和查询效率。
- `financial_data_raw` 用于“接口字段完整留存”和未来字段演进回溯。

---

## 4. 因子与财务接口映射（重构后）

| 因子 | 主要来源 | 备注 |
|---|---|---|
| `pe/pe_ttm/pb/ps/pcf` | `valuation_data` | 优先估值表，缺失时回退估算 |
| `roe/roe_avg` | `profit_data` / `dupont_data` | 优先杜邦或利润表有效值 |
| `gross_margin/net_margin` | `profit_data` | 直接取毛利率/净利率字段 |
| `eps_ttm` | `profit_data` | 直接取 EPS 类字段 |
| `revenue_growth/profit_growth` | `growth_data` / `profit_data` | 优先增长能力表同比字段 |
| `asset_turnover` | `operation_data` / `dupont_data` | 统一口径后使用 |
| `debt_ratio/current_ratio/quick_ratio` | `debtpaying_data` / `balance_data` | 偿债优先，资产负债兜底 |
| `equity_multiplier` | `dupont_data` / `balance_data` | 杜邦优先 |
| `cash_to_profit/fcf/cash_yield` | `cash_flow_data` + `profit_data` + `valuation_data` | 组合计算 |

---

## 5. 实施顺序

### Phase 1（先做）：文档与表结构

1. 完成本方案文档。
2. 数据库初始化中新增 `financial_data_raw`。
3. 明确各接口字段到结构化表的映射和兜底规则。

### Phase 2：采集与落库重构

1. 重构 `FinancialDataSource` 的季度接口抓取逻辑。
2. 恢复并打通 `debtpaying` 采集链路。
3. `FinancialDataSaver` 同时写结构化表与原始表。
4. `FinancialDataManager` 默认更新策略覆盖红框六类并支持估值更新。

### Phase 3：因子层重构

1. `FundamentalFactors` 按新映射重构计算。
2. `FactorPresenter` 同步因子元数据和展示格式。

### Phase 4：回测与页面接入

1. `factor_backtest_page` 移除随机因子生成逻辑。
2. 构建真实因子数据面板并接入 `run_multi_factor_backtest`。
3. 数据管理页面支持红框六类与估值的状态与更新。

### Phase 5：验证

1. 单股抽样核对：接口返回 -> 原始表 -> 结构化表 -> 因子值。
2. 多股回测核对：因子值连续性、非随机性、结果稳定性。
3. 检查数据缺失与异常场景（空值、停牌、新股、无财报）。

---

## 6. 验收标准

- 红框六类季度财务数据与估值数据均可批量抓取并落库。
- 每条接口记录可在 `financial_data_raw` 找到完整原始 JSON。
- 多因子回测链路不再依赖随机数模拟财务因子。
- 因子分析页面可展示真实计算值，并能标注查询日期与财报截止日期。
- 批量更新后，数据管理页面能正确显示各表记录数与最新日期。

---

## 7. 风险与处理

- Baostock 字段口径可能存在版本差异：使用多字段别名映射 + 原始 JSON 留档。
- 限频导致全量更新耗时较长：保留批量进度反馈并支持分批执行。
- 部分股票存在缺失财报：因子计算允许 NaN/0 并在回测中按可用性过滤。

