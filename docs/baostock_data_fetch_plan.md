# Baostock 财务数据获取方案

## 一、数据获取来源

### 1.1 Baostock 财务数据接口

**官网地址**：`https://www.baostock.com`

**数据接口文档**：`https://www.baostock.com/mainContent`

所有财务数据接口均通过 `baostock` Python 库调用，需先登录：

```python
import baostock as bs
lg = bs.login()
# 输出: login respond error_code:'0'
```

---

### 1.2 财务数据类型与对应接口

| 数据类型 | 接口函数 | 传参格式 | 更新频率 |
|---------|---------|---------|---------|
| **利润表** | `query_profit_data()` | `code, year, quarter` | 季度 |
| **资产负债表** | `query_balance_data()` | `code, year, quarter` | 季度 |
| **现金流量表** | `query_cash_flow_data()` | `code, year, quarter` | 季度 |
| **杜邦分析** | `query_dupont_data()` | `code, year, quarter` | 季度 |
| **成长能力** | `query_growth_data()` | `code, year, quarter` | 季度 |
| **营运能力** | `query_operation_data()` | `code, year, quarter` | 季度 |
| **偿债能力** | `query_debtpaying_data()` | `code, year, quarter` | 季度 |
| **实时估值** | `query_stocks()` | 无参数（全市场） | 日 |

---

### 1.3 接口传参详解

#### 利润表 `query_profit_data(code, year, quarter)`

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `code` | str | 股票代码（Baostock 格式） | `sz.000001`、`sh.600000` |
| `year` | str | 年份 | `"2023"`、`"2024"` |
| `quarter` | str | 季度（1-4） | `"1"`、`"2"`、`"3"`、`"4"` |

**返回字段**：`date, code, roe, npMargin, gpMargin, opMargin, eps, revenue, income, totalAsset, equity`

**注意**：参数为**字符串**类型，非整数。

---

#### 资产负债表 `query_balance_data(code, year, quarter)`

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | str | 股票代码 |
| `year` | str | 年份 |
| `quarter` | str | 季度（1-4） |

**返回字段**：`date, code, totalAsset, totalLiab, equity, assetImpair, specialRisk, accumProfit`

---

#### 现金流量表 `query_cash_flow_data(code, year, quarter)`

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | str | 股票代码 |
| `year` | str | 年份 |
| `quarter` | str | 季度（1-4） |

**返回字段**：`date, code, operCashFlow, investCashFlow, financeCashFlow, cashFlowRatio`

---

#### 成长能力 `query_growth_data(code, year, quarter)`

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | str | 股票代码 |
| `year` | str | 年份 |
| `quarter` | str | 季度（1-4） |

**返回字段**：`date, code, profitGrow, profitGrowRatio, assetToIncome`

---

#### 营运能力 `query_operation_data(code, year, quarter)`

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | str | 股票代码 |
| `year` | str | 年份 |
| `quarter` | str | 季度（1-4） |

**返回字段**：`date, code, invTurnover, arTurnover, apTurnover`

---

#### 偿债能力 `query_debtpaying_data(code, year, quarter)`

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | str | 股票代码 |
| `year` | str | 年份 |
| `quarter` | str | 季度（1-4） |

**返回字段**：`date, code, currentRatio, quickRatio, cashRatio`

---

#### 全市场估值 `query_stocks()`

无参数，返回所有股票的实时估值数据。

**返回字段**：`code, code_name, tradeDate, pe, pe_ttm, pb, ps, pcf, marketCap, floatMarketCap, totalShares, floatShares`

---

### 1.4 代码格式转换

Baostock 使用 `sz.000001` 格式，而非标准的 `000001.SZ`：

| 标准格式 | Baostock 格式 |
|---------|--------------|
| `000001.SZ` | `sz.000001` |
| `600000.SH` | `sh.600000` |
| `000001.SH` | `sh.000001`（上证指数） |
| `430001.BJ` | `bj.430001` |

---

## 二、什么时候获取财务数据

### 2.1 财报披露时间规则

| 财报类型 | 披露截止日 | 实际可获取时间 |
|---------|----------|---------------|
| **年报** | 次年4月30日 | 次年5月起 |
| **一季报** | 次年4月30日 | 次年5月起 |
| **中报** | 次年8月31日 | 次年9月起 |
| **三季报** | 次年10月31日 | 次年11月起 |

**关键时点**：
- **每年4月30日前**：只能用到前年的年报数据
- **5月-8月**：可用去年年报 + 当年一季报
- **9月-10月**：可用去年年报 + 当年一季报 + 中报
- **11月起**：可用去年年报 + 当年一季报 + 中报 + 三季报

### 2.2 获取策略

#### 策略A：定期全量获取（推荐）

```
获取时机：
- 每年5月15日左右：获取年报+一季报（全市场）
- 每年9月15日左右：获取中报（全市场）
- 每年11月15日左右：获取三季报（全市场）
```

**优点**：数据完整，覆盖所有股票
**缺点**：单次获取量大，耗时较长（全市场5000+股票 × 7种报表 × 4个季度 ≈ 14万次API调用）

#### 策略B：增量更新（按需获取）

```
获取时机：
- 回测需要某只股票的数据时，动态获取
- 新股票加入自选股时，批量获取历史数据
```

**优点**：按需获取，不浪费资源
**缺点**：首次回测时可能需要等待数据加载

#### 策略C：混合策略（推荐）

```
获取时机：
1. 每日收盘后（盘后更新）：
   - 获取全市场实时估值数据（query_stocks）
   - 更新 valuation_data 表

2. 每周一（盘后）：
   - 检查是否有新财报发布
   - 增量更新已持仓/自选股的财务数据

3. 每年财报密集期（5月、9月、11月）：
   - 批量获取全市场财务数据
   - 重建因子缓存
```

### 2.3 获取优先级

| 优先级 | 数据类型 | 用途 | 获取频率 |
|-------|---------|------|---------|
| P0 | 实时估值（pe/pb/ps/pcf） | 估值因子 | **每日** |
| P1 | 利润表数据 | 盈利因子、成长因子 | **每季度** |
| P2 | 资产负债表 | 财务结构因子 | **每季度** |
| P3 | 现金流量表 | 现金流因子 | **每季度** |
| P4 | 杜邦分析 | ROE分解 | **每季度** |
| P5 | 营运/偿债能力 | 辅助因子 | **每季度** |

---

## 三、在 Web 页面哪里获取

### 3.1 现有 Web 页面结构

```
Web 界面（web/app.py）
├── 首页/概览
├── 自选股管理
├── 单股票回测
├── 多股票回测
└── ⭐ 多因子回测（因子数据获取入口）
```

### 3.2 多因子回测页面（因子数据获取主入口）

**页面路径**：`web/factor_backtest_page.py`

**页面名称**：📊 多因子回测

**现有功能**：
- 因子选择配置
- 因子 IC 分析
- 多因子回测
- 回测结果展示

**待新增功能**：

| 功能 | 位置 | 说明 |
|------|------|------|
| **财务数据状态面板** | 侧边栏顶部 | 显示已获取的财务数据类型、数据条数、最新更新日期 |
| **一键获取财务数据** | 侧边栏 | 按钮触发全量/增量获取 |
| **获取进度显示** | 主区域 | 进度条 + 当前处理股票 |
| **数据 freshness 提示** | 各因子卡片 | 提示数据是否最新 |

### 3.3 新增 Web 页面：数据管理

建议新增独立页面：

**页面名称**：📥 数据管理

**功能模块**：

| 模块 | 功能 | 说明 |
|------|------|------|
| **数据源状态** | 显示各数据表记录数 | 财务数据、K线数据、因子数据的条数和日期范围 |
| **财务数据获取** | 单股票/全市场 | 支持按股票代码或自选股列表获取 |
| **历史数据重置** | 重新获取确认 | 清除历史数据后重新获取 |
| **自动更新设置** | 定时任务配置 | 设置每日/每周自动获取 |

### 3.4 入口位置示意图

```
┌─────────────────────────────────────────────────────────┐
│  Streamlit 侧边栏                                         │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ 📊 多因子回测配置                                     │ │
│  │                                                     │ │
│  │ ─── 财务数据状态 ───                                 │ │
│  │ 估值数据：✅ 5000只 2024-04-22                       │ │
│  │ 利润表：✅ 4800只 2024-03-31                         │ │
│  │ 资产负债表：✅ 4800只 2024-03-31                      │ │
│  │ 现金流量表：✅ 4800只 2024-03-31                     │ │
│  │                                                     │ │
│  │ [🔄 更新财务数据 ▼]  ▼ dropdown: 全市场/自选股/单只    │ │
│  │                                                     │ │
│  │ ─── 因子配置 ───                                    │ │
│  │ ☑ ROE    ☑ PE    ☑ 营收增长                         │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  📥 数据管理页面（新增强口）                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │                                                     │ │
│  │  [财务数据获取]  [K线数据获取]  [因子生成]            │ │
│  │                                                     │ │
│  │  数据源状态：                                        │ │
│  │  ┌───────────┬──────────┬────────────┐              │ │
│  │  │ 数据类型   │ 记录数   │ 最新更新   │              │ │
│  │  ├───────────┼──────────┼────────────┤              │ │
│  │  │ 日线数据   │ 12,5000 │ 2024-04-22│              │ │
│  │  │ 利润表     │ 48,000  │ 2024-03-31│              │ │
│  │  │ 资产负债表 │ 48,000  │ 2024-03-31│              │ │
│  │  │ 因子缓存   │ 250,000 │ 2024-04-20│              │ │
│  │  └───────────┴──────────┴────────────┘              │ │
│  │                                                     │ │
│  │  自动更新：[启用 ▼]  周期：[每日 ▼]  时间：[18:00]   │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 四、现有实现状态

### 4.1 已完成组件 ✅

| 组件 | 文件 | 功能 |
|------|------|------|
| `FinancialDataSource` | `data/financial_data_source.py` | Baostock API 封装，支持7种财务数据 |
| `FinancialDataSaver` | `data/financial_data_saver.py` | 数据持久化到 SQLite |
| `FinancialDataManager` | `data/financial_data_manager.py` | 统一接口，批量更新 |
| 数据库 Schema | `data/data_manager.py` | 10+ 张财务数据表 |
| Web 页面 | `web/factor_backtest_page.py` | 多因子回测界面 |

### 4.2 待开发组件 ❌

| 组件 | 说明 |
|------|------|
| **Web 数据获取入口** | 在 factor_backtest_page.py 添加数据状态和获取按钮 |
| **数据管理页面** | 新增独立页面，管理所有数据源 |
| **自动更新机制** | Streamlit 二胎运行时的定时更新 |
| **财务数据状态面板** | 显示各表数据条数、最新日期 |

---

## 五、实施计划

### Phase 1：Web 入口开发
1. 在 `factor_backtest_page.py` 侧边栏添加财务数据状态面板
2. 添加"更新财务数据"按钮
3. 实现获取进度显示

### Phase 2：数据管理页面
1. 新建 `web/data_management_page.py` 页面
2. 实现数据源状态总览
3. 实现单股票/批量/全市场获取功能

### Phase 3：自动更新
1. 实现 Streamlit 下的定时更新机制
2. 配置化调度策略

---

## 六、关键代码片段

### 6.1 Baostock 登录和数据获取

```python
import baostock as bs

# 登录
lg = bs.login()
print(f'login respond error_code:{lg.error_code}')
print(f'login respond error_msg:{lg.error_msg}')

# 获取利润表
rs = bs.query_profit_data(code="sz.000001", year="2023", quarter="4")
print(f'response error_code:{rs.error_code}')
print(f'response error_msg:{rs.error_msg}')

# 遍历数据
data_list = []
while rs.next():
    data_list.append(rs.get_row_data())
df = pd.DataFrame(data_list, columns=rs.fields)

# 登出
bs.logout()
```

### 6.2 批量获取全市场财务数据

```python
from data.financial_data_manager import FinancialDataManager

fdn = FinancialDataManager()

# 获取全市场股票列表
stocks = fdn.get_all_stocks()  # 或从自选股获取

# 批量更新（自动处理限流）
result = fdn.batch_update(
    symbols=stocks,
    data_types=['profit', 'balance', 'cash_flow', 'dupont'],
    start_year=2022,
    end_year=2024,
    progress_callback=lambda i, total, sym: print(f'进度: {i}/{total} - {sym}')
)

print(f"成功: {result['success']}, 失败: {result['failed']}")
```

### 6.3 Web 页面获取按钮

```python
# factor_backtest_page.py 侧边栏

st.sidebar.subheader("📥 财务数据获取")

# 数据状态
if st.sidebar.button("🔄 更新财务数据"):
    with st.spinner("正在获取财务数据..."):
        fdn = FinancialDataManager()
        result = fdn.batch_update(
            symbols=wl_manager.get_all_stocks(),
            data_types=['profit', 'balance', 'cash_flow'],
            progress_callback=lambda i, total, sym: progress.progress(i/total)
        )
    st.sidebar.success(f"更新完成！成功: {result['success']}, 失败: {result['failed']}")
```

---

## 七、注意事项

1. **API 限流**：Baostock 每秒最多1次调用，需加 sleep 延迟
2. **财报滞后**：每年4-10月间存在财报真空期，数据会不完整
3. **数据量估算**：全市场5000+股票 × 7种报表 × 最近3年 ≈ 10万条记录
4. **增量更新**：已存在的记录不会重复插入，使用 `INSERT OR REPLACE`
5. **网络异常**：单次获取失败需有重试机制