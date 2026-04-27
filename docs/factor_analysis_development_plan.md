# 因子分析功能开发计划

## 一、版本规划

| 版本 | 阶段 | 目标 | 优先级 |
|-----|------|------|-------|
| **V0.1** | MVP | 单股因子展示 + 自选股计算 | P0 |
| **V1.0** | 正式版 | 多股排名 + 热力图 + 全量计算 | P1 |
| **V1.1** | 增强版 | 因子历史走势 + 告警功能 | P2 |

---

## 二、技术架构

### 2.1 核心模块职责

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Layer (app.py)                      │
│  - 因子分析 Tab UI                                          │
│  - 用户交互处理                                              │
│  - 结果展示                                                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                Service Layer                                  │
│  ┌─────────────────┐  ┌──────────────────┐                 │
│  │ FactorPresenter  │  │ FactorCalculator │                 │
│  │ 因子展示服务      │  │ 因子计算服务      │                 │
│  │ - 格式化输出      │  │ - 单股计算        │                 │
│  │ - 排名统计        │  │ - 批量计算        │                 │
│  │ - 历史走势        │  │ - 进度管理        │                 │
│  └─────────────────┘  └──────────────────┘                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                Data Layer                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────┐  │
│  │ FundamentalFactors│ │ FactorCache     │  │ DataManager │  │
│  │ 因子计算核心类    │  │ 因子缓存管理      │  │ 行情数据    │  │
│  └─────────────────┘  └──────────────────┘  └─────────────┘  │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              SQLite Database                          │    │
│  │  - factor_values (因子值缓存)                        │    │
│  │  - factor_metadata (因子元数据)                      │    │
│  │  - factor_calc_log (计算日志)                        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 文件结构

```
quant_system/
├── strategy/
│   ├── fundamental_factors.py    # [新增] 基本面因子计算核心类
│   ├── factor_preprocessor.py    # [新增] 因子预处理器
│   └── factor_neutralizer.py      # [新增] 因子中性化
│
├── data/
│   ├── factor_cache.py           # [新增] 因子缓存管理
│   └── data_manager.py           # [扩展] 添加因子相关方法
│
├── web/
│   ├── factor_analysis_page.py   # [新增] 因子分析Tab页面
│   ├── factor_presenter.py       # [新增] 因子展示服务
│   └── app.py                    # [扩展] 集成因子分析Tab
│
└── docs/
    ├── factor_analysis_product_plan.md   # [已创建] 产品方案
    └── factor_analysis_development_plan.md # [本文件] 开发计划
```

---

## 三、开发任务分解

### Phase 1: 基础设施 (预计 4h)

#### T1.1: 数据库表创建
**文件**: `data/database_schema.py` (新增)

```sql
-- 因子值缓存表
CREATE TABLE IF NOT EXISTS factor_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    factor_name TEXT NOT NULL,
    factor_value REAL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, trade_date, factor_name)
);

-- 因子元数据表
CREATE TABLE IF NOT EXISTS factor_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL UNIQUE,
    factor_category TEXT,
    factor_direction TEXT,
    description TEXT,
    formula TEXT
);

-- 因子计算日志表
CREATE TABLE IF NOT EXISTS factor_calc_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calc_type TEXT NOT NULL,
    stock_count INTEGER,
    success_count INTEGER,
    fail_count INTEGER,
    calc_time INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**任务**:
- [ ] 创建数据库Schema初始化脚本
- [ ] 插入因子元数据（20个因子）
- [ ] 添加表索引

#### T1.2: FundamentalFactors 核心类
**文件**: `strategy/fundamental_factors.py` (新建)

**因子体系** (五大类 + 衍生因子):

| 类别 | 因子 | 计算公式 |
|-----|------|---------|
| 估值因子 | PE | price / eps_ttm |
| | PB | price / book_value_per_share |
| | PS | price / revenue_per_share |
| | PCF | price / cash_flow_per_share |
| 盈利因子 | ROE | net_profit / equity |
| | ROA | net_profit / total_assets |
| | 毛利率 | gross_profit / revenue |
| | 净利率 | net_profit / revenue |
| 成长因子 | 营收增长率 | (revenue_now - revenue_prev) / revenue_prev |
| | 利润增长率 | (profit_now - profit_prev) / profit_prev |
| 财务结构 | 资产负债率 | total_liabilities / total_assets |
| | 流动比率 | current_assets / current_liabilities |
| 现金流 | 经营现金流/净利润 | oper_cash_flow / net_profit |
| | 自由现金流 | oper_cash_flow - capex |
| 衍生因子 | PB_ROE | PB / ROE |
| | PE_Growth | PE / 利润增长率 |

**方法设计**:
```python
class FundamentalFactors:
    def calculate_all_factors(self, symbol: str, trade_date: str) -> Dict[str, float]
    def get_factor_panel(self, symbols: List[str], trade_date: str) -> pd.DataFrame
    def calculate_single_factor(self, symbol: str, trade_date: str, factor_name: str) -> float
    def get_factor_history(self, symbol: str, factor_name: str, days: int = 365) -> pd.DataFrame
```

---

### Phase 2: MVP 功能 (预计 8h)

#### T2.1: 因子计算服务
**文件**: `web/factor_presenter.py` (新建)

**功能**:
- [ ] 单股全量因子计算与展示
- [ ] 因子格式化输出（保留小数位、单位）
- [ ] 因子方向标注（正向/负向）
- [ ] 数据时效性提示

#### T2.2: 因子分析 Tab 页面
**文件**: `web/factor_analysis_page.py` (新建)

**UI组件**:
- [ ] 股票搜索下拉框（支持模糊匹配）
- [ ] 因子类别选择器
- [ ] 单因子展示卡片
- [ ] 全量因子表格
- [ ] 计算按钮组

**交互逻辑**:
- [ ] 选择股票后自动加载因子
- [ ] 因子表格支持排序
- [ ] 计算进度条展示

#### T2.3: 自选股批量计算
**功能**:
- [ ] 一键计算自选股因子
- [ ] 批量写入数据库
- [ ] 异常股票记录与提示

---

### Phase 3: V1.0 增强功能 (预计 10h)

#### T3.1: 多股因子排名
**功能**:
- [ ] 股票复选框组
- [ ] 单因子排名柱状图
- [ ] 排名表格（含行业对比）
- [ ] 导出CSV功能

#### T3.2: 多股多因子热力图
**功能**:
- [ ] 多因子选择器
- [ ] 热力图可视化
- [ ] 对比矩阵表格

#### T3.3: 一键计算全市场
**功能**:
- [ ] 全量计算二次确认弹窗
- [ ] 分批处理机制
- [ ] 后台任务队列
- [ ] 计算频率限制

---

### Phase 4: V1.1 增强功能 (预计 6h)

#### T4.1: 因子历史走势
**功能**:
- [ ] 单因子历史折线图
- [ ] 行业均值对比线
- [ ] 近五年分位数计算

#### T4.2: 因子告警
**功能**:
- [ ] 阈值设置界面
- [ ] 告警规则持久化
- [ ] 告警触发检测

---

## 四、开发任务清单

### 必须完成 (MVP)

| 任务ID | 任务名称 | 预计工时 | 依赖关系 |
|-------|---------|---------|---------|
| T1.1 | 数据库表创建 | 1h | - |
| T1.2 | FundamentalFactors核心类 | 3h | T1.1 |
| T2.1 | 因子计算服务 | 2h | T1.2 |
| T2.2 | 因子分析Tab页面 | 4h | T2.1 |
| T2.3 | 自选股批量计算 | 2h | T2.2 |

### 计划完成 (V1.0)

| 任务ID | 任务名称 | 预计工时 | 依赖关系 |
|-------|---------|---------|---------|
| T3.1 | 多股因子排名 | 3h | T2.2 |
| T3.2 | 多股热力图 | 4h | T3.1 |
| T3.3 | 全量计算功能 | 3h | T2.3 |

### 可选完成 (V1.1)

| 任务ID | 任务名称 | 预计工时 | 依赖关系 |
|-------|---------|---------|---------|
| T4.1 | 因子历史走势 | 3h | T2.2 |
| T4.2 | 因子告警功能 | 3h | T4.1 |

---

## 五、里程碑

| 里程碑 | 完成条件 | 预计日期 |
|-------|---------|---------|
| **M1: 核心能力** | T1.1 + T1.2 + T2.1 完成 | Day 1 |
| **M2: MVP 发布** | T2.2 + T2.3 完成，Tab 可用 | Day 2 |
| **M3: V1.0 完成** | T3.1 + T3.2 + T3.3 完成 | Day 4 |
| **M4: V1.1 完成** | T4.1 + T4.2 完成 | Day 5 |

---

## 六、技术要点

### 6.1 财报时间滞后处理
```python
def get_latest_financial_data(symbol, trade_date):
    """
    获取trade_date之前最新发布的财务数据
    季报发布节奏: 4月(年报+一季报)、8月(中报)、10月(三季报)
    """
    # 找到trade_date之前最近的财报截止日
    # 前推45天作为实际可发布时间
```

### 6.2 数据频率匹配
```python
def forward_fill_quarterly_factor(factor_series: pd.Series) -> pd.Series:
    """
    季频因子前向填充为日频
    用于与日频K线数据对齐
    """
    return factor_series.resample('D').ffill()
```

### 6.3 行业分类映射
```python
# 使用 Baostock 的行业分类或自定义映射表
INDUSTRY_MAP = {
    '000001.SZ': '银行',
    '600519.SH': '白酒',
    '000002.SZ': '房地产',
    # ...
}
```

---

## 七、测试计划

### 7.1 单元测试
- [ ] `test_fundamental_factors.py` - 因子计算正确性
- [ ] `test_factor_preprocessor.py` - 预处理器逻辑
- [ ] `test_factor_presenter.py` - 格式化输出

### 7.2 集成测试
- [ ] 数据库读写测试
- [ ] Web 页面加载测试
- [ ] 批量计算压力测试

### 7.3 验收测试
- [ ] 用户操作流程测试
- [ ] 多浏览器兼容性测试

---

## 八、风险与应对

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| 财报数据缺失 | 因子计算失败 | 返回 NULL，前端显示"数据缺失" |
| 全量计算耗时长 | 用户等待 | 分批处理 + 后台任务 |
| 并发写入冲突 | 数据不一致 | 使用事务 + 乐观锁 |
| 内存占用过高 | 系统不稳定 | 限制批量大小，分批处理 |
