# 多因子回测集成到策略回测Tab方案

## 背景

当前架构：
- `app.py` Tab 2（策略回测）：策略选择下拉框包含"均线交叉/MACD/布林带/RSI/多因子"
- 当选择"多因子"时，使用的是 `strategy/multi_factor.py` 中的简单 `MultiFactorStrategy`（仅基于技术指标计算）
- `app.py` Tab 3（多因子回测）：使用 `portfolio/multi_factor_backtest.py` 的 `MultiFactorBacktest`，功能完整（IC加权、因子暴露度跟踪、归因分析等）

用户希望：在 Tab 2 的策略选择下拉框中选择"多因子"时，直接使用 Tab 3 的完整多因子回测功能。

## 方案设计

### 核心思路
在 Tab 2 中，当选择"多因子"时：
1. 显示多因子专属配置面板（因子选择、权重设置）
2. 使用 `run_multi_factor_backtest()` 或 `MultiFactorBacktest` 执行回测
3. 回测完成后展示结果（包括因子分析报告）

### UI布局调整

**原 Tab 2 布局：**
```
col1: 股票选择 | col2: 策略选择 | col3: 资金参数
```

**调整后：**
当选择"多因子"时，col2 分为上下两部分：
- 上半部分：策略选择下拉框
- 下半部分：多因子配置面板（因子选择、权重、IC加权开关等）

### 代码修改点

#### 1. Tab 2 策略选择逻辑修改 (`app.py` ~line 1035-1061)
```python
# 策略选择
strategy_name = st.selectbox(...)

# 多因子配置面板（当选择多因子时显示）
if strategy_name == "多因子 (Multi-Factor)":
    # 显示因子选择和权重配置
```

#### 2. 回测执行逻辑修改 (`app.py` ~line 1117-1184)
```python
# 原有逻辑：所有策略都使用 MultiStockBacktest
# 修改后：
if strategy_name == "多因子 (Multi-Factor)":
    # 使用 run_multi_factor_backtest()
    results = run_multi_factor_backtest(...)
else:
    # 使用 MultiStockBacktest + 简单策略
```

#### 3. 因子配置复用
从 `factor_backtest_page.py` 复用 `FACTOR_CATEGORIES` 和 `DEFAULT_FACTORS` 定义

## 因子配置面板设计

### 因子分类（复用 `factor_backtest_page.py`）
- 基本面因子：ROE、ROA、毛利率、净利率、EPS、营收增长率、利润增长率、资产周转率
- 估值因子：PE、PB、PS、PCF
- 技术因子：20日动量、60日动量、20日波动率、量比、换手率
- 财务结构：资产负债率、流动比率、速动比率
- 情绪因子：价量趋势、相对强弱

### 配置项
1. **因子多选**：按分类展示，可勾选
2. **权重模式**：
   - IC智能加权（默认）
   - 手动设置权重（滑块）
3. **IC加权参数**（当启用时）：
   - IC更新频率（天）
   - IC历史窗口（天）

## 回测结果展示

### 收益指标（与现有Tab 2一致）
- 总收益率、年化收益率、夏普比率、最大回撤

### 多因子专属结果（新增）
- 因子配置概览（权重对比、IC有效性判定）
- 因子暴露度时序图
- 因子收益归因

## 实施步骤

1. 修改 `app.py` Tab 2 的策略选择下拉框逻辑
2. 添加多因子配置面板的 UI
3. 修改回测执行逻辑，区分多因子/其他策略
4. 添加多因子回测结果展示
5. 测试验证