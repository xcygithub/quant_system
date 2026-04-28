# 量化交易系统 Web UI 改版设计文档

> **版本**: v1.0
> **日期**: 2026-04-28
> **状态**: 草稿
> **作者**: Frontend Developer

---

## 一、设计目标

### 1.1 核心目标

| 目标 | 描述 | 优先级 |
|------|------|--------|
| **专业金融风格** | 打造专业级量化交易界面，参考同花顺、东方财富等主流金融终端 | P0 |
| **信息密度优化** | 在保持美观的同时，最大化信息展示效率 | P0 |
| **A 股特色支持** | 完美支持红涨绿跌、涨跌停板、K线周期切换等 A 股特性 | P0 |
| **性能体验** | 保持 Streamlit 原生性能，优化加载速度和交互响应 | P1 |
| **移动端适配** | 关键页面支持移动端浏览 | P2 |

### 1.2 设计原则

```
┌─────────────────────────────────────────────────────────────┐
│                      设计原则                                │
├─────────────────────────────────────────────────────────────┤
│  1. 功能优先：UI服务于功能，不为美观牺牲可用性               │
│  2. 一致性：全站统一的配色、字体、间距规范                   │
│  3. 渐进增强：基础功能 → 增强功能 → 高级功能                  │
│  4. 数据可视化优先：表格 → 图表 → 交互式图表                │
│  5. 中国特色：A 股红涨绿跌、涨停跌停、T+1 等                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、当前 UI 分析

### 2.1 现有问题

| 问题类别 | 具体问题 | 影响程度 |
|----------|----------|----------|
| **视觉层面** | 配色单调，缺乏层次感 | [★][★][★] |
| **视觉层面** | 卡片样式简单，无阴影和动效 | [★][★] |
| **布局层面** | 7个标签页拥挤，缺乏视觉焦点 | [★][★][★] |
| **交互层面** | 加载状态提示不明显 | [★][★] |
| **图表层面** | K线图样式可进一步优化 | [★][★] |
| **响应式** | 未考虑移动端适配 | [★][★][★] |

### 2.2 现有优势

| 优势 | 说明 |
|------|------|
| **功能完整** | 7大模块覆盖量化交易全流程 |
| **K线图专业** | 已实现红涨绿跌、均线叠加、信号标记 |
| **数据驱动** | 实时数据展示，信息丰富 |
| **交互清晰** | 分栏布局，操作路径明确 |

---

## 三、视觉设计方案

### 3.1 配色系统

#### 3.1.1 主题选择

**推荐方案：深色主题（金融终端标配）**

```
┌────────────────────────────────────────────────────────────────┐
│                      配色体系                                    │
├────────────────────────────────────────────────────────────────┤
│  主题类型：深色主题                                             │
│  参考竞品：同花顺iFinD、东方财富Choice、万得Wind                │
│  选择理由：                                                     │
│    • 金融从业者长时间盯盘，深色更护眼                           │
│    • 数据可视化效果更好，图表对比度强                          │
│    • 专业感强，符合量化交易系统定位                            │
└────────────────────────────────────────────────────────────────┘
```

#### 3.1.2 色彩规范

```css
/* ==========================================================================
   主色调系统
   ========================================================================== */

/* 基础色彩 */
--bg-primary:       #0f172a;   /* 主背景 - 深蓝黑 */
--bg-secondary:     #1e293b;   /* 次级背景 - 深灰蓝 */
--bg-tertiary:      #334155;   /* 卡片背景 - 中灰蓝 */
--bg-elevated:      #475569;   /* 悬浮背景 */

/* 文字色彩 */
--text-primary:     #f1f5f9;   /* 主要文字 - 亮白 */
--text-secondary:   #94a3b8;   /* 次要文字 - 灰蓝 */
--text-muted:       #64748b;   /* 辅助文字 - 暗灰 */

/* 强调色彩 */
--accent-primary:   #3b82f6;   /* 主强调色 - 科技蓝 */
--accent-secondary: #8b5cf6;   /* 次强调色 - 紫色 */
--accent-success:   #22c55e;   /* 成功色 - 绿色 */
--accent-warning:   #f59e0b;   /* 警告色 - 金色 */
--accent-danger:    #ef4444;   /* 危险色 - 红色 */

/* A股特色色彩（A股市红涨绿跌，与国际相反）*/
--cn-up:            #ff3b3b;   /* A股上涨 - 红色 */
--cn-down:          #00c853;   /* A股下跌 - 绿色 */
--cn-flat:          #64748b;   /* A股平盘 - 灰色 */

/* 边框与分割线 */
--border-default:   #334155;   /* 默认边框 */
--border-hover:     #475569;   /* 悬浮边框 */
--border-active:    #3b82f6;   /* 激活边框 */

/* 功能色彩 */
--positive:        #22c55e;   /* 正收益 */
--negative:        #ef4444;   /* 负收益 */
--warning:         #f59e0b;   /* 警告状态 */
--info:            #3b82f6;   /* 信息提示 */
--break-limit-up:  #ff3b3b;   /* 涨停板 */
--break-limit-down:#00c853;   /* 跌停板 */
```

#### 3.1.3 渐变配色

```css
/* 卡片渐变背景 */
--gradient-card: linear-gradient(135deg, #1e293b 0%, #334155 100%);

/* KPI 卡片渐变 */
--gradient-kpi-up:   linear-gradient(135deg, #064e3b 0%, #059669 100%);
--gradient-kpi-down: linear-gradient(135deg, #7f1d1d 0%, #dc2626 100%);
--gradient-kpi-neutral: linear-gradient(135deg, #1e293b 0%, #334155 100%);

/* 图表主题渐变 */
--gradient-chart: linear-gradient(180deg, rgba(59,130,246,0.3) 0%, rgba(59,130,246,0) 100%);
```

### 3.2 字体系统

```css
/* ==========================================================================
   字体系统
   ========================================================================== */

--font-family-cn: 'PingFang SC', 'Microsoft YaHei', 'Hiragino Sans GB', sans-serif;
--font-family-en: 'Inter', 'Roboto', -apple-system, sans-serif;
--font-family-mono: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace;

/* 字号规范 */
--font-size-xs:    0.75rem;   /* 12px - 最小辅助文字 */
--font-size-sm:    0.875rem;  /* 14px - 辅助文字 */
--font-size-base:  1rem;      /* 16px - 正文 */
--font-size-lg:    1.125rem;  /* 18px - 强调文字 */
--font-size-xl:    1.25rem;   /* 20px - 小标题 */
--font-size-2xl:   1.5rem;    /* 24px - 中标题 */
--font-size-3xl:   1.875rem;  /* 30px - 大标题 */
--font-size-4xl:   2.25rem;   /* 36px - 页面标题 */

/* 字重规范 */
--font-weight-normal:    400;
--font-weight-medium:    500;
--font-weight-semibold:  600;
--font-weight-bold:      700;

/* 行高规范 */
--line-height-tight:   1.25;
--line-height-normal:  1.5;
--line-height-loose:   1.75;

/* 数字字体（等宽，便于对齐）*/
.number {
    font-family: var(--font-family-mono);
    font-variant-numeric: tabular-nums;
}
```

### 3.3 间距系统

```css
/* ==========================================================================
   间距系统（基于8px网格）
   ========================================================================== */

--space-1:   0.25rem;   /* 4px */
--space-2:   0.5rem;    /* 8px */
--space-3:   0.75rem;   /* 12px */
--space-4:   1rem;      /* 16px */
--space-5:   1.25rem;   /* 20px */
--space-6:   1.5rem;    /* 24px */
--space-8:   2rem;      /* 32px */
--space-10:  2.5rem;    /* 40px */
--space-12:  3rem;      /* 48px */
--space-16:  4rem;      /* 64px */

/* 组件内间距 */
--padding-card:      var(--space-4);   /* 卡片内边距 */
--padding-section:   var(--space-6);   /* 区块内边距 */
--padding-page:      var(--space-6);   /* 页面内边距 */

/* 圆角规范 */
--radius-sm:   0.25rem;   /* 4px - 小圆角 */
--radius-md:   0.5rem;    /* 8px - 中圆角 */
--radius-lg:   0.75rem;   /* 12px - 大圆角 */
--radius-xl:   1rem;      /* 16px - 超大圆角 */
--radius-full: 9999px;    /* 100% - 圆形 */
```

### 3.4 阴影系统

```css
/* ==========================================================================
   阴影系统
   ========================================================================== */

--shadow-sm:  0 1px 2px 0 rgba(0, 0, 0, 0.3);
--shadow-md:  0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -1px rgba(0, 0, 0, 0.3);
--shadow-lg:  0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3);
--shadow-xl:  0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 10px 10px -5px rgba(0, 0, 0, 0.3);
--shadow-glow-blue:   0 0 20px rgba(59, 130, 246, 0.4);
--shadow-glow-green:  0 0 20px rgba(34, 197, 94, 0.4);
--shadow-glow-red:    0 0 20px rgba(239, 68, 68, 0.4);
```

---

## 四、布局设计方案

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           页面结构                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      顶部导航栏 (Top Bar)                         │   │
│  │  [Logo] 量化交易系统              [搜索] [通知] [主题切换] [用户]  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   标签页导航 (Tabs Bar)                          │   │
│  │                                                                   │   │
│  │   [★]自选股管理  |  [◎]策略回测  |  [▤]多因子回测  |  [⚡]信号扫描   │   │
│  │   [📈]绩效分析  |  [🧪]因子分析  |  [⬢]财务数据管理              │   │
│  │  ───────────────────────────────────────────────────────────    │   │
│  │  [当前选中标签高亮显示]                                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        KPI 仪表盘                                 │   │
│  │  ┌──────────┬──────────┬──────────┬──────────┐              │   │
│  │  │ 总资产   │ 今日收益 │ 持仓数   │ 胜率     │              │   │
│  │  │ ¥1,234K  │ +¥5,678  │ 15只     │ 66.67%  │              │   │
│  │  └──────────┴──────────┴──────────┴──────────┘              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      功能内容区                                    │   │
│  │                      (根据当前标签页变化)                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 导航设计

#### 4.2.1 标签页导航（保留并美化）

**当前方案**：保留现有标签页导航，进行视觉美化

**优化方向**：
- 统一的标签图标 + 文字
- 选中状态更醒目
- 悬浮效果增强
- 支持快捷键切换

```python
# ==========================================================================
# 专业图标配置（Font Awesome 6）
# 引入方式：在 st.set_page_config 后添加以下 CSS
# <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
# ==========================================================================

# 标签页图标配置（与 README.md 保持一致）
TABS_CONFIG = [
    {"icon": "fa-solid fa-star", "label": "自选股管理", "key": "watchlist"},
    {"icon": "fa-solid fa-crosshairs", "label": "策略回测", "key": "backtest"},
    {"icon": "fa-solid fa-layer-group", "label": "多因子回测", "key": "multi_factor"},
    {"icon": "fa-solid fa-bolt", "label": "信号扫描", "key": "signals"},
    {"icon": "fa-solid fa-chart-line", "label": "绩效分析", "key": "performance"},
    {"icon": "fa-solid fa-flask", "label": "因子分析", "key": "factor_analysis"},
    {"icon": "fa-solid fa-database", "label": "财务数据管理", "key": "data_management"},
]

# Font Awesome CSS 引入
FA_CSS = """
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" 
      integrity="sha512-DTOQO9RWCH3ppGqcWaEA1BIZOC6xxalwEsw9c2QQeAIftl+Vegovlnee1c9QX4TctnWMn13TZye+giMm8e2LwA==" 
      crossorigin="anonymous" referrerpolicy="no-referrer" />
"""

# 辅助函数：渲染图标
def render_icon(icon_class: str, size: int = 16, color: str = None):
    """渲染 Font Awesome 图标"""
    color_style = f"color: {color};" if color else ""
    return f'<i class="{icon_class}" style="font-size: {size}px; {color_style}"></i>'

# 创建标签页（带图标）
def create_tabs(st, config):
    """创建带图标的标签页"""
    tab_labels = [f"{render_icon(t['icon'], size=14)}&nbsp;{t['label']}" for t in config]
    return st.tabs(tab_labels)

# 图标参考速查表
ICON_REFERENCE = """
| 功能 | Font Awesome 图标 | CSS Class |
|------|------------------|-----------|
| 自选/收藏 | 实心星 | fa-solid fa-star |
| 瞄准/精准 | 十字准星 | fa-solid fa-crosshairs |
| 多层/组合 | 图层组 | fa-solid fa-layer-group |
| 闪电/信号 | 闪电 | fa-solid fa-bolt |
| 趋势图 | 折线图 | fa-solid fa-chart-line |
| 柱状图 | 柱状图 | fa-solid fa-chart-bar |
| 饼图 | 饼图 | fa-solid fa-chart-pie |
| 实验/分析 | 烧杯 | fa-solid fa-flask |
| 数据库 | 数据库 | fa-solid fa-database |
| 上涨 | 上箭头 | fa-solid fa-caret-up |
| 下跌 | 下箭头 | fa-solid fa-caret-down |
| 成功 | 对勾圆圈 | fa-solid fa-check-circle |
| 错误 | 叉号圆圈 | fa-solid fa-times-circle |
| 警告 | 三角警告 | fa-solid fa-exclamation-triangle |
| 加载 | 旋转动画 | fa-solid fa-spinner |
| 搜索 | 放大镜 | fa-solid fa-search |
| 设置 | 齿轮 | fa-solid fa-gear |
| 刷新 | 同步 | fa-solid fa-rotate |
| 导出 | 下载 | fa-solid fa-download |
| 添加 | 加号 | fa-solid fa-plus |
| 删除 | 垃圾桶 | fa-solid fa-trash |
| 编辑 | 铅笔 | fa-solid fa-pen-to-square |
"""
```

#### 4.2.2 标签页 UI 样式

```css
/* 标签页容器 */
.element-container:has(.stTabs) {
    margin-bottom: 1rem;
}

/* 标签页样式覆盖 */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    padding: 12px 16px;
    border-radius: 12px;
    border: 1px solid #334155;
}

/* 单个标签项 */
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #94a3b8;
    border-radius: 8px;
    padding: 12px 20px;
    font-weight: 500;
    font-size: 14px;
    transition: all 0.25s ease;
    border: 1px solid transparent;
}

/* 悬浮效果 */
.stTabs [data-baseweb="tab"]:hover {
    background: #334155;
    color: #f1f5f9;
}

/* 选中状态 */
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
    color: white !important;
    font-weight: 600;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

/* 标签图标 */
.tab-icon {
    margin-right: 8px;
}
```

### 4.3 响应式断点

```css
/* 响应式断点 */
--breakpoint-sm:  640px;   /* 手机横屏 */
--breakpoint-md:  768px;   /* 平板 */
--breakpoint-lg:  1024px;  /* 小笔记本 */
--breakpoint-xl:  1280px;  /* 桌面 */
--breakpoint-2xl: 1536px;  /* 大屏 */

/* 响应式策略 */
@media (max-width: 768px) {
    .sidebar {
        position: fixed;
        z-index: 100;
        transform: translateX(-100%);
    }
    
    .sidebar.open {
        transform: translateX(0);
    }
    
    .main-content {
        padding: var(--space-4);
    }
}
```

---

## 五、组件设计方案

### 5.1 KPI 仪表盘卡片

**组件定位**：首页核心数据展示，快速了解账户/系统状态

```python
# KPI 卡片布局示例
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="总资产",
        value="¥1,234,567.89",
        delta="+12,345.67 (+1.02%)",
        delta_color="normal"
    )

with col2:
    st.metric(
        label="今日收益",
        value="+¥5,678.90",
        delta="+0.46%",
        delta_color="normal"
    )

with col3:
    st.metric(
        label="持仓股票",
        value="15只",
        delta="较昨日 +2只"
    )

with col4:
    st.metric(
        label="持仓胜率",
        value="66.67%",
        delta="近20日"
    )
```

**KPI 卡片样式（CSS）**：

```css
/* KPI 卡片 */
.kpi-card {
    background: var(--gradient-card);
    border-radius: var(--radius-lg);
    padding: var(--space-5);
    border: 1px solid var(--border-default);
    box-shadow: var(--shadow-md);
    transition: all 0.3s ease;
}

.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
}

.kpi-card .label {
    font-size: var(--font-size-sm);
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
}

.kpi-card .value {
    font-size: var(--font-size-2xl);
    font-weight: 700;
    color: var(--text-primary);
    font-family: var(--font-family-mono);
}

.kpi-card .delta {
    font-size: var(--font-size-sm);
    margin-top: var(--space-2);
}

.kpi-card .delta.positive {
    color: var(--positive);
}

.kpi-card .delta.negative {
    color: var(--negative);
}

/* 涨跌卡片特殊样式 */
.kpi-card.up {
    border-left: 4px solid var(--cn-up);
    background: linear-gradient(135deg, rgba(239,68,68,0.1) 0%, var(--bg-secondary) 100%);
}

.kpi-card.down {
    border-left: 4px solid var(--cn-down);
    background: linear-gradient(135deg, rgba(0,200,83,0.1) 0%, var(--bg-secondary) 100%);
}
```

### 5.2 股票卡片组件

**组件定位**：自选股列表展示，快速浏览多只股票行情

```css
/* 股票卡片 */
.stock-card {
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    cursor: pointer;
    transition: all 0.2s ease;
}

.stock-card:hover {
    background: var(--bg-elevated);
    border-color: var(--border-hover);
    transform: translateX(4px);
}

.stock-card.selected {
    border-color: var(--accent-primary);
    box-shadow: var(--shadow-glow-blue);
}

/* 股票卡片布局 */
.stock-card .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: var(--space-3);
}

.stock-card .symbol {
    font-weight: 600;
    font-size: var(--font-size-lg);
    color: var(--text-primary);
}

.stock-card .name {
    font-size: var(--font-size-sm);
    color: var(--text-secondary);
    margin-left: var(--space-2);
}

.stock-card .price {
    text-align: right;
}

.stock-card .price-value {
    font-size: var(--font-size-xl);
    font-weight: 700;
    font-family: var(--font-family-mono);
}

.stock-card .price-change {
    font-size: var(--font-size-sm);
    font-family: var(--font-family-mono);
}

/* A股涨跌颜色 */
.stock-card .up {
    color: var(--cn-up);
}

.stock-card .down {
    color: var(--cn-down);
}

/* 股票卡片底部信息 */
.stock-card .footer {
    display: flex;
    justify-content: space-between;
    font-size: var(--font-size-xs);
    color: var(--text-muted);
    padding-top: var(--space-3);
    border-top: 1px solid var(--border-default);
}
```

### 5.3 行情概览组件

**组件定位**：展示自选股整体涨跌分布，快速判断市场情绪

```python
# 行情概览组件示例
market_col1, market_col2, market_col3 = st.columns(3)

# 上涨股票
up_stocks = [s for s in stocks if quote[s].pct_change > 0]
down_stocks = [s for s in stocks if quote[s].pct_change < 0]
flat_stocks = [s for s in stocks if quote[s].pct_change == 0]

with market_col1:
    st.markdown(f"""
    <div class="market-stat up">
        <div class="stat-icon">📈</div>
        <div class="stat-content">
            <div class="stat-value">{len(up_stocks)}</div>
            <div class="stat-label">上涨</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with market_col2:
    st.markdown(f"""
    <div class="market-stat down">
        <div class="stat-icon">📉</div>
        <div class="stat-content">
            <div class="stat-value">{len(down_stocks)}</div>
            <div class="stat-label">下跌</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with market_col3:
    st.markdown(f"""
    <div class="market-stat flat">
        <div class="stat-icon">➖</div>
        <div class="stat-content">
            <div class="stat-value">{len(flat_stocks)}</div>
            <div class="stat-label">平盘</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
```

### 5.4 K线图组件增强

**当前状态**：已实现基础 K 线图，带均线和成交量

**优化方向**：

```python
# 优化后的 K 线图配置
def plot_kline_enhanced(df, symbol, period='D'):
    """
    增强版K线图
    - 深色主题
    - 鼠标悬浮详情
    - 缩放控制
    - 均线可切换显示
    """

    # 配色方案
    colors = {
        'background': '#0f172a',
        'grid': '#1e293b',
        'text': '#94a3b8',
        'up': '#ff3b3b',      # A股红涨
        'down': '#00c853',    # A股绿跌
        'ma5': '#f59e0b',     # MA5 金色
        'ma10': '#3b82f6',    # MA10 蓝色
        'ma20': '#8b5cf6',    # MA20 紫色
        'ma60': '#06b6d4',    # MA60 青色
    }

    fig = go.Figure()

    # K线
    fig.add_trace(go.Candlestick(
        x=df['date'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='K线',
        increasing_line_color=colors['up'],
        decreasing_line_color=colors['down'],
        increasing_fillcolor=colors['up'],
        decreasing_fillcolor=colors['down'],
    ))

    # 均线（可配置）
    ma_config = {
        'D': {'periods': [5, 10, 20, 60], 'labels': ['MA5', 'MA10', 'MA20', 'MA60']},
        'W': {'periods': [5, 10, 20], 'labels': ['MA5', 'MA10', 'MA20']},
        'M': {'periods': [3, 6, 12], 'labels': ['MA3', 'MA6', 'MA12']},
    }

    for ma_period, ma_label in zip(ma_config[period]['periods'], ma_config[period]['labels']):
        if len(df) >= ma_period:
            df[f'ma{ma_period}'] = df['close'].rolling(ma_period).mean()
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df[f'ma{ma_period}'],
                name=ma_label,
                line=dict(width=1.5, color=colors.get(f'ma{ma_period}', '#888'))
            ))

    # 布局优化
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor=colors['background'],
        plot_bgcolor=colors['background'],
        font=dict(color=colors['text']),
        hovermode='x unified',  # 统一悬浮提示
        xaxis=dict(
            rangeslider=dict(visible=False),
            gridcolor=colors['grid'],
            showgrid=True,
        ),
        yaxis=dict(
            gridcolor=colors['grid'],
            showgrid=True,
            tickformat='.2f',
            title='价格'
        ),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            bgcolor='rgba(0,0,0,0)'
        ),
        margin=dict(t=60, l=60, r=40, b=60),
        height=600,
    )

    return fig
```

### 5.5 数据表格组件

```css
/* 数据表格样式 */
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--font-size-sm);
}

.data-table th {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    font-weight: 500;
    text-align: left;
    padding: var(--space-3) var(--space-4);
    border-bottom: 2px solid var(--border-default);
}

.data-table td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border-default);
    color: var(--text-primary);
}

.data-table tr:hover {
    background: var(--bg-tertiary);
}

.data-table .positive {
    color: var(--cn-up);
}

.data-table .negative {
    color: var(--cn-down);
}

/* 表格数字右对齐 */
.data-table .num {
    font-family: var(--font-family-mono);
    text-align: right;
}
```

### 5.6 按钮组件

```css
/* 按钮基础样式 */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-md);
    font-weight: 500;
    font-size: var(--font-size-sm);
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    outline: none;
}

.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* 主要按钮 */
.btn-primary {
    background: var(--accent-primary);
    color: white;
}

.btn-primary:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
}

/* 次要按钮 */
.btn-secondary {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
}

.btn-secondary:hover:not(:disabled) {
    background: var(--bg-elevated);
    border-color: var(--border-hover);
}

/* 成功按钮 */
.btn-success {
    background: var(--positive);
    color: white;
}

/* 危险按钮 */
.btn-danger {
    background: var(--negative);
    color: white;
}

/* 按钮尺寸 */
.btn-sm {
    padding: var(--space-1) var(--space-3);
    font-size: var(--font-size-xs);
}

.btn-lg {
    padding: var(--space-3) var(--space-6);
    font-size: var(--font-size-base);
}

/* 图标按钮 */
.btn-icon {
    width: 40px;
    height: 40px;
    padding: 0;
    border-radius: var(--radius-full);
}
```

---

## 六、页面设计方案

### 6.1 自选股管理页（优化版）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      自选股管理 (优化版)                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      KPI 仪表盘 (新增)                            │   │
│  │  ┌──────────┬──────────┬──────────┬──────────┬──────────┐      │   │
│  │  │持仓市值  │今日盈亏 │持仓胜率 │持仓数   │涨停数   │      │   │
│  │  │¥1,234K  │+¥5,678  │66.67%   │15只     │1只      │      │   │
│  │  └──────────┴──────────┴──────────┴──────────┴──────────┘      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌───────────────────────────┬───────────────────────────────────┐      │
│  │      自选股列表            │         行情详情                   │      │
│  │  ┌─────────────────────┐   │                                   │      │
│  │  │ 🔍 搜索...   [分组▼]│   │  000001.SZ - 平安银行             │      │
│  │  └─────────────────────┘   │                                   │      │
│  │                            │  ┌─────┬─────┬─────┬─────┬─────┐ │      │
│  │  【全部】 【持仓】 【银行】│  │现价 │涨跌 │涨跌幅│成交量│成交额│ │      │
│  │  【消费】 【科技】 【医药】│  │12.34│+0.15│+1.23%│532万 │6.56亿│ │      │
│  │                            │  └─────┴─────┴─────┴─────┴─────┘ │      │
│  │  ┌─────────────────────┐  │                                   │      │
│  │  │ [★] 000001 平安银行 │  │  [日K][周K][月K][年K]                │      │
│  │  │     12.34  ▲+1.23%│  │                                   │      │
│  │  │     持仓: 1000股   │  │  ┌─────────────────────────────┐  │      │
│  │  └─────────────────────┘  │  │                             │  │      │
│  │  ┌─────────────────────┐  │  │         K 线 图              │  │      │
│  │  │ [★] 600519 贵州茅台 │  │  │                             │  │      │
│  │  │   1850.00 ▼-0.45%│  │  │    红涨绿跌中国特色         │  │      │
│  │  │   持仓: 100股     │  │  │                             │  │      │
│  │  └─────────────────────┘  │  │                             │  │      │
│  │  ┌─────────────────────┐  │  └─────────────────────────────┘  │      │
│  │  │ [★] 000002 万科A    │  │                                   │      │
│  │  │     8.56  ▲+2.34%│  │  技术指标: [MA] [MACD] [RSI] [KDJ] │      │
│  │  │   暂无持仓       │  │                                   │      │
│  │  └─────────────────────┘  │                                   │      │
│  │                            │                                   │      │
│  │  [+ 添加自选股]            │                                   │      │
│  └───────────────────────────┴───────────────────────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**优化点**：
1. ✅ 顶部增加 KPI 仪表盘（持仓市值、今日盈亏、胜率等）
2. ✅ 股票卡片增加持仓信息展示
3. ✅ 增加分组快捷筛选标签
4. ✅ 搜索框与分组筛选组合使用

### 6.2 自选股管理页

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         自选股管理                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────┬───────────────────────────────────┐      │
│  │      自选股列表            │         行情详情                   │      │
│  │  ┌─────────────────────┐   │                                   │      │
│  │  │ 🔍 搜索...   [筛选]│   │  000001.SZ - 平安银行             │      │
│  │  └─────────────────────┘   │                                   │      │
│  │                            │  ┌─────┬─────┬─────┬─────┬─────┐   │      │
│  │  [全部分组 ▼]             │  │现价 │涨跌 │涨跌幅│成交量│成交额│   │      │
│  │                            │  │12.34│+0.15│+1.23%│532万 │6.56亿│   │      │
│  │  ┌─────────────────────┐  │  └─────┴─────┴─────┴─────┴─────┘   │      │
│  │  │ [★] 000001 平安银行 │  │                                   │      │
│  │  │     12.34  ▲+1.23%│  │  [日K][周K][月K][年K]                │      │
│  │  └─────────────────────┘  │                                   │      │
│  │  ┌─────────────────────┐  │  ┌─────────────────────────────┐  │      │
│  │  │ [★] 600519 贵州茅台 │  │  │                             │  │      │
│  │  │   1850.00 ▼-0.45% │  │  │         K 线 图              │  │      │
│  │  └─────────────────────┘  │  │                             │  │      │
│  │  ┌─────────────────────┐  │  │    红涨绿跌中国特色         │  │      │
│  │  │ [★] 000002 万科A    │  │  │                             │  │      │
│  │  │     8.56  ▲+2.34% │  │  │                             │  │      │
│  │  └─────────────────────┘  │  └─────────────────────────────┘  │      │
│  │                            │                                   │      │
│  │  [+ 添加自选股]            │  技术指标: [MA] [MACD] [RSI] [KDJ] │      │
│  │                            │                                   │      │
│  └───────────────────────────┴───────────────────────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.3 策略回测页

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           策略回测                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────┬───────────────────────────────────┐      │
│  │      回测配置             │         回测结果                   │      │
│  │                           │                                   │      │
│  │  股票选择                 │  ┌─────┬─────┬─────┬─────┬─────┐   │      │
│  │  [000001.SZ ▼]           │  │年化 │夏普 │最大 │胜率 │盈亏 │   │      │
│  │                           │  │收益 │比率 │回撤 │    │比  │   │      │
│  │  回测区间                 │  │23.5%│1.85 │-12% │66% │1.52 │   │      │
│  │  [2023-01-01] ~ [2024-12]│  └─────┴─────┴─────┴─────┴─────┘   │      │
│  │                           │                                   │      │
│  │  策略选择                 │  ┌─────────────────────────────┐  │      │
│  │  ○ 均线交叉              │  │                             │  │      │
│  │  ○ MACD                  │  │       权益曲线图             │  │      │
│  │  ● 多因子                │  │       + 基准对比            │  │      │
│  │  ○ RSI                   │  │                             │  │      │
│  │  ○ 布林带                │  └─────────────────────────────┘  │      │
│  │                           │                                   │      │
│  │  策略参数                 │  ┌─────────────────────────────┐  │      │
│  │  快速周期 [20]            │  │       回撤分析图             │  │      │
│  │  慢速周期 [60]            │  └─────────────────────────────┘  │      │
│  │                           │                                   │      │
│  │  初始资金 [1,000,000]     │  交易明细                        │      │
│  │  手续费率 [0.03%]         │  [日期▼] [类型] [价格] [数量]     │      │
│  │                           │  2024-01-15  买入  12.34  1000    │      │
│  │  [▶ 开始回测]             │  2024-02-20  卖出  13.56  1000    │      │
│  │                           │  2024-03-10  买入  12.89  1000    │      │
│  └───────────────────────────┴───────────────────────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.4 多因子回测页

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          多因子回测                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────┬───────────────────────────────────┐      │
│  │      因子配置              │         因子分析报告               │      │
│  │                           │                                   │      │
│  │  基本面因子    [✓]         │  IC分析                           │      │
│  │  ├─ □ ROE (5%)           │  ┌─────────────────────────────┐  │      │
│  │  ├─ ✓ PE (10%)  [滑动条] │  │    IC 时序图                │  │      │
│  │  ├─ ✓ PB (8%)   [滑动条] │  │    IC: 0.12 ± 0.08         │  │      │
│  │  └─ □ 营收增长            │  │    IR: 1.5                  │  │      │
│  │                           │  └─────────────────────────────┘  │      │
│  │  技术因子    [✓]          │                                   │      │
│  │  ├─ ✓ 20日动量 (15%)      │  因子权重                         │      │
│  │  ├─ □ 波动率              │  ┌─────────────────────────────┐  │      │
│  │  └─ ✓ 换手率 (7%)         │  │ PE ████████░░  25%         │  │      │
│  │                           │  │ ROE ██████░░░░  18%         │  │      │
│  │  权重设置                 │  │ 动量 █████████  32%         │  │      │
│  │  [IC智能加权 ▼]           │  │ 其他 ████░░░░░░  25%         │  │      │
│  │                           │  └─────────────────────────────┘  │      │
│  │  选股数量 [TOP 20]        │                                   │      │
│  │  调仓周期 [5日]           │  分层回测收益                     │      │
│  │                           │  ┌─────────────────────────────┐  │      │
│  │  [▶ 开始回测]             │  │    组1 ████████████ +15.2%  │  │      │
│  │  [💾 保存配置]            │  │    组2 ████████░░ +10.5%  │  │      │
│  │                           │  │    组3 ██████░░░░  +5.8%   │  │      │
│  └───────────────────────────┴───────────────────────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 七、交互设计方案

### 7.1 加载状态

```python
# 加载状态组件
def show_loading(message="加载中..."):
    """统一的加载状态展示"""
    return st.spinner(f"⏳ {message}")


# Skeleton Loading（可选增强）
SKELETON_CSS = """
@keyframes shimmer {
    0% { background-position: -200px 0; }
    100% { background-position: calc(200px + 100%) 0; }
}

.skeleton {
    animation: shimmer 1.5s infinite;
    background: linear-gradient(90deg, var(--bg-tertiary) 0%, var(--bg-elevated) 50%, var(--bg-tertiary) 100%);
    background-size: 200px 100%;
    border-radius: var(--radius-md);
}
"""

# 使用示例
with st.spinner("正在加载行情数据..."):
    df = dm.get_daily_kline(symbol, start_date, end_date)
```

### 7.2 提示与反馈

```python
# Toast 提示（使用 st.toast 需要 Streamlit 1.25+）
def show_toast(message, type="info"):
    """显示轻量级提示"""
    icons = {
        "success": "fa-solid fa-check-circle",  # ✓
        "error": "fa-solid fa-times-circle",     # ✗
        "warning": "fa-solid fa-exclamation-triangle",  # ⚠
        "info": "fa-solid fa-info-circle"        # ℹ
    }
    # 渲染 HTML 图标
    icon_html = f'<i class="{icons.get(type, "fa-info-circle")}"></i>'
    st.toast(f"{icon_html} {message}", icon=None)


# 操作确认对话框
def confirm_action(message, key):
    """确认操作对话框"""
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("确认", key=f"{key}_confirm"):
            return True
    with col2:
        if st.button("取消", key=f"{key}_cancel"):
            return False
    return None
```

### 7.3 数据筛选与搜索

```python
# 智能搜索组件
def stock_search():
    """股票代码智能搜索"""
    # 使用 st.text_input + 自动补全
    query = st.text_input(
        "搜索股票",
        placeholder="输入代码或名称...",
        help="支持股票代码（如000001）和名称（如平安银行）"
    )

    if query:
        # 从数据库搜索匹配项
        results = search_stocks(query)
        if results:
            selected = st.selectbox(
                "选择股票",
                options=[f"{r.symbol} - {r.name}" for r in results]
            )
            return selected.split(" - ")[0]
    return None


# 多条件筛选
def create_filter_section():
    """创建筛选区块"""
    with st.expander("🔍 筛选条件", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            price_range = st.slider("价格区间", 0, 100, (10, 50))

        with col2:
            change_range = st.slider("涨跌幅", -10, 10, (-5, 5))

        with col3:
            volume_min = st.number_input("最小成交量", value=1000000)

        if st.button("应用筛选"):
            return {
                'price': price_range,
                'change': change_range,
                'volume': volume_min
            }
```

---

## 八、实施计划

### 8.1 阶段划分

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          实施阶段                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 1: 基础样式重构 (预计 2-3 小时)                                    │
│  ├── 8.1.1 深色主题配置                                                  │
│  ├── 8.1.2 全局 CSS 样式注入                                             │
│  ├── 8.1.3 基础组件样式（卡片、按钮、表格）                               │
│  └── 8.1.4 K线图深色主题适配                                            │
│                                                                          │
│  Phase 2: 布局优化 (预计 2-3 小时)                                       │
│  ├── 8.2.1 侧边栏导航实现                                               │
│  ├── 8.2.2 首页仪表盘重构                                               │
│  ├── 8.2.3 自选股卡片优化                                               │
│  └── 8.2.4 响应式布局适配                                               │
│                                                                          │
│  Phase 3: 高级交互 (预计 3-4 小时)                                       │
│  ├── 8.3.1 加载状态优化                                                 │
│  ├── 8.3.2 图表交互增强                                                 │
│  ├── 8.3.3 数据表格美化                                                 │
│  └── 8.3.4 主题切换功能                                                 │
│                                                                          │
│  Phase 4: 细节打磨 (预计 2-3 小时)                                       │
│  ├── 8.4.1 动效优化                                                     │
│  ├── 8.4.2 移动端适配                                                   │
│  ├── 8.4.3 无障碍访问                                                   │
│  └── 8.4.4 性能优化                                                     │
│                                                                          │
│  总计预计: 9-13 小时                                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Phase 1 详细任务

#### 8.2.1 深色主题配置

**文件**: `web/app.py`

```python
# 在文件开头添加主题配置
# 方式1：使用 Streamlit 内置配置（推荐）
# 在 st.set_page_config 中添加主题相关配置

# 方式2：使用自定义 CSS（更灵活）
THEME_CSS = """
<style>
    /* 全局深色主题 */
    .stApp {
        background-color: #0f172a;
        color: #f1f5f9;
    }

    /* Streamlit 组件覆盖 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #1e293b;
        padding: 8px;
        border-radius: 12px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #94a3b8;
        border-radius: 8px;
        padding: 12px 20px;
    }

    .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important;
        color: white !important;
    }

    /* 按钮样式 */
    .stButton > button {
        background-color: #3b82f6;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        transition: all 0.2s;
    }

    .stButton > button:hover {
        background-color: #2563eb;
        transform: translateY(-1px);
    }

    /* 输入框样式 */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div {
        background-color: #1e293b;
        border-color: #334155;
        color: #f1f5f9;
    }

    /* 数据表格样式 */
    .dataframe {
        background-color: #1e293b !important;
    }

    .dataframe th {
        background-color: #334155 !important;
        color: #f1f5f9 !important;
    }

    .dataframe td {
        color: #f1f5f9 !important;
        border-color: #334155 !important;
    }
</style>
"""
```

#### 8.2.2 KPI 卡片组件

**新建文件**: `web/components/kpi_card.py`

```python
"""
KPI 卡片组件
提供统一的 KPI 展示样式
"""
import streamlit as st
from typing import Optional


def render_kpi_card(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_type: str = "auto",  # "auto", "up", "down", "neutral"
    icon: Optional[str] = None
):
    """
    渲染一个 KPI 卡片

    Args:
        label: 指标名称
        value: 指标值
        delta: 变化值（可选）
        delta_type: 变化类型
        icon: 图标 emoji
    """
    # 根据 delta 自动判断涨跌
    if delta_type == "auto" and delta:
        if delta.startswith("+") or delta.startswith("▲"):
            delta_type = "up"
        elif delta.startswith("-"):
            delta_type = "down"
        else:
            delta_type = "neutral"

    # 样式类
    card_class = f"kpi-card {'up' if delta_type == 'up' else ''} {'down' if delta_type == 'down' else ''}"

    delta_html = ""
    if delta:
        delta_class = "positive" if delta_type == "up" else ("negative" if delta_type == "down" else "")
        delta_html = f'<div class="delta {delta_class}">{delta}</div>'

    icon_html = f'<span class="icon">{icon}</span>' if icon else ""

    html = f"""
    <div class="{card_class}">
        <div class="label">{icon_html}{label}</div>
        <div class="value">{value}</div>
        {delta_html}
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)


# 全局 KPI 样式（需在 app.py 中注册）
KPI_CARD_CSS = """
<style>
.kpi-card {
    background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #334155;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    transition: all 0.3s ease;
}

.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
}

.kpi-card.up {
    border-left: 4px solid #ff3b3b;
}

.kpi-card.down {
    border-left: 4px solid #00c853;
}

.kpi-card .label {
    font-size: 14px;
    color: #94a3b8;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.kpi-card .icon {
    font-size: 20px;
}

.kpi-card .value {
    font-size: 28px;
    font-weight: 700;
    color: #f1f5f9;
    font-family: 'JetBrains Mono', monospace;
}

.kpi-card .delta {
    font-size: 14px;
    margin-top: 8px;
    font-family: 'JetBrains Mono', monospace;
}

.kpi-card .delta.positive {
    color: #ff3b3b;
}

.kpi-card .delta.negative {
    color: #00c853;
}
</style>
"""
```

#### 8.2.3 股票卡片组件

**新建文件**: `web/components/stock_card.py`

```python
"""
股票卡片组件
展示单只股票的行情信息
"""
import streamlit as st
from typing import Optional, Dict


def render_stock_card(
    symbol: str,
    name: str,
    price: float,
    change: float,
    change_pct: float,
    volume: Optional[float] = None,
    selected: bool = False,
    on_click: Optional[callable] = None
):
    """
    渲染一个股票卡片

    Args:
        symbol: 股票代码
        name: 股票名称
        price: 当前价格
        change: 涨跌额
        change_pct: 涨跌幅
        volume: 成交量（可选）
        selected: 是否选中
        on_click: 点击回调
    """
    is_up = change_pct >= 0
    change_class = "up" if is_up else "down"
    change_sign = "+" if is_up else ""
    arrow = "▲" if is_up else "▼"

    card_class = f"stock-card {change_class}"
    if selected:
        card_class += " selected"

    # 格式化数字
    price_str = f"{price:.2f}"
    change_str = f"{change_sign}{change:.2f}"
    change_pct_str = f"{change_sign}{change_pct:.2f}%"

    volume_str = f"{volume/10000:.0f}万" if volume else ""

    html = f"""
    <div class="{card_class}" onclick="window.dispatchEvent(new CustomEvent('stock-select', {{detail: '{symbol}'}}))">
        <div class="header">
            <div class="symbol-info">
                <span class="symbol">{symbol}</span>
                <span class="name">{name}</span>
            </div>
            <div class="price">
                <div class="price-value">{price_str}</div>
                <div class="price-change {change_class}">
                    {arrow} {change_str} ({change_pct_str})
                </div>
            </div>
        </div>
        <div class="footer">
            <span>成交量: {volume_str}</span>
            <span>更新时间: {st.session_state.get('update_time', 'N/A')}</span>
        </div>
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)


# 股票卡片样式
STOCK_CARD_CSS = """
<style>
.stock-card {
    background: #1e293b;
    border-radius: 8px;
    padding: 16px;
    border: 1px solid #334155;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 8px;
}

.stock-card:hover {
    background: #334155;
    transform: translateX(4px);
}

.stock-card.selected {
    border-color: #3b82f6;
    box-shadow: 0 0 20px rgba(59, 130, 246, 0.3);
}

.stock-card.up .price-change {
    color: #ff3b3b;
}

.stock-card.down .price-change {
    color: #00c853;
}

.stock-card .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}

.stock-card .symbol-info {
    display: flex;
    flex-direction: column;
}

.stock-card .symbol {
    font-weight: 600;
    font-size: 16px;
    color: #f1f5f9;
}

.stock-card .name {
    font-size: 13px;
    color: #94a3b8;
    margin-top: 2px;
}

.stock-card .price {
    text-align: right;
}

.stock-card .price-value {
    font-size: 20px;
    font-weight: 700;
    color: #f1f5f9;
    font-family: 'JetBrains Mono', monospace;
}

.stock-card .price-change {
    font-size: 13px;
    font-family: 'JetBrains Mono', monospace;
    margin-top: 2px;
}

.stock-card .footer {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #64748b;
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid #334155;
}
</style>
"""
```

---

## 九、关键文件修改清单

| 序号 | 文件路径 | 修改内容 | 优先级 |
|------|----------|----------|--------|
| 1 | `web/app.py` | 添加全局样式、修改页面配置 | P0 |
| 2 | `web/app.py` | 重构首页为仪表盘布局 | P0 |
| 3 | `web/app.py` | 添加侧边栏导航 | P1 |
| 4 | `web/factor_backtest_page.py` | 深色主题适配 | P1 |
| 5 | `web/factor_analysis_page.py` | 深色主题适配 | P1 |
| 6 | `web/pages/data_management.py` | 深色主题适配 | P1 |
| 7 | `web/components/__init__.py` | 新建组件目录 | P0 |
| 8 | `web/components/kpi_card.py` | 新建 KPI 组件 | P0 |
| 9 | `web/components/stock_card.py` | 新建股票卡片组件 | P0 |
| 10 | `web/components/chart_config.py` | 新建图表配置工具 | P1 |

---

## 十、风险与注意事项

### 10.1 兼容性风险

| 风险 | 缓解措施 |
|------|----------|
| Streamlit 版本兼容 | 使用 `st.markdown` + HTML/CSS，不依赖特定版本特性 |
| 浏览器兼容 | 使用标准 CSS3 属性，添加前缀 |auto |
| 移动端体验 | 响应式布局，降级处理复杂组件 |

### 10.2 性能风险

| 风险 | 缓解措施 |
|------|----------|
| CSS 过多影响加载 | 使用 CSS Variables 复用样式 |
| 图表渲染慢 | 使用 Plotly 的 `use_container_width=True` 自适应 |
| 大数据量卡顿 | 使用 Streamlit 的缓存机制 `@st.cache_data` |

### 10.3 维护注意事项

1. **CSS 命名空间**：所有自定义 CSS 使用唯一前缀避免冲突
2. **主题变量化**：颜色、间距等使用 CSS Variables 便于统一调整
3. **组件模块化**：各组件独立维护，便于迭代
4. **文档同步**：样式修改时同步更新设计文档

---

## 十一、附录

### 11.1 参考资料

- [Streamlit 官方文档](https://docs.streamlit.io/)
- [Plotly Python 文档](https://plotly.com/python/)
- [同花顺 iFinD 界面风格参考](https://www.10jqka.com.cn/)
- [东方财富 Choice 界面风格参考](https://choice.eastmoney.com/)
- [Material Design 色彩系统](https://m3.material.io/styles/color)

### 11.2 技术栈清单

```txt
核心框架:
- Streamlit >= 1.28.0

图表库:
- Plotly >= 5.18.0

可选增强库:
- streamlit-extras (工具函数)
- streamlit-echarts (ECharts 图表)
- streamlit-antd-components (Ant Design 组件)

字体:
- JetBrains Mono (数字等宽字体)
- Inter (UI 字体)
```

### 11.3 设计符号对照表

```
A  股特色:
    • 红色 (#FF3B3B) = 上涨 = 买入信号
    • 绿色 (#00C853) = 下跌 = 卖出信号
    • 灰色 (#64748B) = 平盘 = 持有

常用图标:
    📈 上涨/正收益
    📉 下跌/负收益
    [★] 自选股
    🎯 回测/精准
    📊 数据分析
    📈 K线图
    🔬 因子分析
    fa-gear 设置
    🔍 搜索
    fa-plus 添加
    🗑️ 删除
```

---

**文档版本历史**

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|----------|
| v1.0 | 2026-04-28 | Frontend Developer | 初始版本 |
| v1.1 | 2026-04-28 | Frontend Developer | 更新图标方案：Emoji → Font Awesome；修正标签页"财务数据"→"财务数据管理"与README保持一致 |
