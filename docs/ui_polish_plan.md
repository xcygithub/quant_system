# 桌面客户端 UI 排版全面优化方案（Phase 1 · 待审阅）

> 状态：**待用户批准，未实施**。批准后才进入 Phase 2 开发。
> 范围：`desktop/` 目录全部 7 个功能页 + 主窗口 + 组件库 + theme.qss。

---

## 一、问题诊断

### A. 布局结构问题

| # | 问题 | 证据 |
|---|------|------|
| A1 | **工具栏信息密度失衡**：刷新/搜索/分组/添加/更多 5 个控件挤在一行，搜索框被压缩到文字截断（"搜索股票代码/名…"），右侧「更多」下拉箭头贴边 | 截图红框区域；`searchEdit max-width: 280px` 但实际可用宽度不足 |
| A2 | **排序行与工具栏割裂**：「排序/每页」单独一行（sort_bar），「全选」Checkbox 孤悬右侧，两行控件逻辑上属于同一组筛选操作，视觉上却断成两截 | watchlist_page.py `_render_list` 两个独立 QHBoxLayout |
| A3 | **页面边距不统一**：BasePage 用 `(24,16,24,16)`，watchlist 内部 view_container 又叠一层 `(24,16,24,16)`，backtest 用 `(10,12,10,10)`，factor_analysis 用 `(12,14,12,14)`，data_mgmt spacing=14……全套共有 **6 种以上边距/间距组合**，无任何规范 | Grep 全量排查结果 |
| A4 | **表格列宽分配不合理**：「代码」列 100px 被截断（显示 "688143…"），「分组」列 80px 却大量留白；数字列右对齐缺失，数字阅读困难 | 截图；`_COL_WIDTHS` 硬编码 |
| A5 | **表格垂直空间浪费**：行高 44px + 大留白区域，15 行数据时表格下方一大片空白；`setMinimumHeight(380)` 硬编码导致小窗口出现双滚动条 | 截图下半部 |
| A6 | **分页控件样式突兀**：「上一页/下一页」是普通大按钮，与中间小号说明文字高度不齐，底部栏左右重量失衡 | 截图底部 |
| A7 | **日志面板裸奔**：底部深色日志条与上方浅色内容区无过渡、无标题栏、无折叠控制，像一块"补丁" | 截图最底部 |

### B. 字体层级问题

| # | 问题 |
|---|------|
| B1 | 字体层级只有两级可用（页面标题 20px / 正文 14px），缺少 H2/H3/辅助文字的完整阶梯；SectionTitle（16px）与普通加粗正文无区分 |
| B2 | 数字展示无等宽数字规范：表格里的价格/涨跌幅/成交量用比例字体，列间数字抖动、无法对齐比较 |
| B3 | MetricCard 数值 22px bold 与页面标题 20px 几乎同级，视觉权重倒挂——卡片数字比页面标题还"响" |
| B4 | 12px 辅助文字（表头、排序标签、分页说明）颜色 `#6C757D` 用在 12px 字号上对比度不足（约 4.0:1），久读疲劳 |

### C. 配色问题

| # | 问题 |
|---|------|
| C1 | **两套色板并存**：theme.qss 用 `#E24B4A/#639922`（涨红跌绿），metric_card.py 内置 `#dc2626/#16a34a/#e5e7eb/#6b7280/#111827`（Tailwind 色），同屏出现时红不是同一个红、灰不是同一个灰 |
| C2 | **硬编码颜色散落各处**：`setStyleSheet()` 内联样式 30+ 处（如 `#FFF7ED/#92400E/#FCD34D` 提示条、`#6C757D` 标签），绕过主题系统，改主题时不会跟随 |
| C3 | 选中态蓝色 `#B5D4F4` 作为整行背景过重，与 hover 色 `#E6F1FB` 拉不开层次 |
| C4 | 主色 `#378ADD` 在白色按钮文字上对比度仅 3.4:1（WCAG AA 需 4.5:1），primaryBtn 白字偏小 |

### D. 视觉层次问题

| # | 问题 |
|---|------|
| D1 | **页面无"卡片化"容器概念**：工具栏、统计卡、表格直接平铺在灰底上，无分组边界，视线不知道先看哪 |
| D2 | MetricCard 无阴影/无 hover 态、四张卡宽度不均（内容定宽 + 尾部 stretch），不像"仪表盘"像"四个便签" |
| D3 | 表格是页面唯一主角但无任何强调：无斑马纹生效感（alternate 色 #F8F9FA 与白色差异过小）、行 hover 反馈弱 |
| D4 | SectionTitle 的蓝底横条样式（`#E6F1FB` 背景 + 4px 左竖线）在多个页面反复出现，与 MetricCard、表格争夺注意力，层级噪音 |
| D5 | 缺少空状态设计：无数据时只有一行灰字，无插画/引导操作 |

### E. 组件一致性问题

| # | 问题 |
|---|------|
| E1 | 按钮高度名义上 32px，但 ComboBox/LineEdit/Button 的 padding 规则不同（按钮 `padding: 0 16px`，输入框 `padding: 6px 12px`），同行排列时基线不齐、视觉高度不一 |
| E2 | 圆角不统一：按钮 4px、卡片/表格 8px、hero 12px、菜单 8px——缺少"圆角语义"（何时用哪档） |
| E3 | QGroupBox 标题样式（蓝字灰底贴片）与 SectionTitle 是两套分组语言，backtest 页用 GroupBox、watchlist 页用裸布局，风格分裂 |
| E4 | 「更多」QToolButton 没有 objectName，吃默认按钮样式，与 primaryBtn 并排时主次不清 |

---

## 二、设计目标

**风格方向：现代金融终端 ——「克制的专业感」**

参考：东方财富/同花顺桌面端的信息密度 + Linear/Notion 的留白与层级。

四个关键词：
1. **数据优先** —— 表格和数字是绝对主角，装饰性元素（色块、横条）全部让位
2. **层级安静** —— 一页之内最多 3 个视觉层级（标题区 → 工具/筛选 → 数据区），用留白和细分隔线代替彩色横条
3. **密度可控** —— 金融数据密度要高，但控件密度要低；行高、字号、间距成体系
4. **一致性即美感** —— 一套 token、一套组件语言，7 个页面像一个人画的

---

## 三、具体改进措施

### 3.1 设计 Token 体系落地（新增 `desktop/styles/tokens.py`）

把注释里的 token 变成代码里唯一事实来源，所有组件从这里取数：

```
# 间距（4px 基栅）
SPACE_1=4  SPACE_2=8  SPACE_3=12  SPACE_4=16  SPACE_5=20  SPACE_6=24  SPACE_8=32

# 页面边距（全局统一）
PAGE_MARGIN = (24, 20, 24, 20)     # 左右24 上下20
SECTION_GAP = 16                    # 区块间距唯一值
CONTROL_GAP = 8                     # 控件间距唯一值

# 字体阶梯（7级）
FONT_H1=20/600  FONT_H2=16/600  FONT_H3=14/600
FONT_BODY=14/400  FONT_BODY_MED=14/500
FONT_CAPTION=12/400  FONT_NUM=14 (tabular-nums 等宽数字, Consolas/"DIN Alternate")
FONT_METRIC=24/700  # MetricCard 数值，与 H1 拉开差距

# 圆角语义
RADIUS_SM=4 (按钮/输入框)  RADIUS_MD=8 (卡片/表格/弹窗)  RADIUS_LG=12 (仅hero)

# 阴影
SHADOW_CARD = 0 1px 2px rgba(16,24,40,0.05)   # 卡片静态
SHADOW_POP  = 0 4px 12px rgba(16,24,40,0.10)  # 浮层/菜单/批量操作栏

# 统一色板（消灭第二套 Tailwind 色）
UP=#E24B4A  DOWN=#639922  PRIMARY=#378ADD  PRIMARY_HOVER=#185FA5
TEXT_1=#212529  TEXT_2=#343A40  TEXT_3=#6C757D  TEXT_4=#ADB5BD
BG_PAGE=#F5F6F8  BG_CARD=#FFFFFF  BORDER=#E9ECEF  DIVIDER=#F1F3F5
HOVER_BG=#F1F6FC  SELECT_BG=#E6F1FB  # 选中比现在的#B5D4F4更轻
```

**页面背景微调为 `#F5F6F8`**（比现在的 F8F9FA 略深），让白色卡片自然浮出，不需要边框也能分区。

### 3.2 布局结构重构（以自选股页为模板，推广到 7 页）

页面统一三段式骨架：

```
┌────────────────────────────────────────────────┐
│ H1 标题 + 副标题                    [全局操作]  │  ← BasePage 已有，保留
├────────────────────────────────────────────────┤
│ ┌─ 卡片1：工具/筛选区（白卡） ────────────────┐ │
│ │ [刷新] │ [搜索………………280px] [分组▾] [排序▾]│ │  ← 合并为一行
│ │              [添加股票]  [更多▾]            │ │
│ └────────────────────────────────────────────┘ │
│ ┌─ 卡片2：统计区 ────────────────────────────┐ │
│ │ [总数 15] [上涨 9] [下跌 5] [平盘 0]       │ │  ← 等宽4卡
│ └────────────────────────────────────────────┘ │
│ ┌─ 卡片3：数据区（白卡，撑满剩余高度） ───────┐ │
│ │ 表头（吸顶）                                │ │
│ │ 表格（列宽语义化，数字右对齐等宽）           │ │
│ │ ────────────────────────────────────────── │ │
│ │ ‹ 1/1 › 共15只        [每页20▾] [☑全选]   │ │  ← 分页/全选并入表底
│ └────────────────────────────────────────────┘ │
└────────────────────────────────────────────────┘
│ 日志 ▾（可折叠，带标题栏和高度手柄）            │
└────────────────────────────────────────────────┘
```

要点：
- **A1/A2 修复**：工具栏与排序行合并为一个"筛选卡片"，一行放不下时用两列网格而非断行；「全选」移到表头 Checkbox（行业标准做法），删除孤悬 Checkbox
- **A3 修复**：所有页面边距/间距只准用 token，代码里的字面量全部替换
- **A4 修复**：列宽语义化——代码列固定 110px 不截断，名称列弹性拉伸（Stretch），数字列右对齐 + 等宽数字字体，分组列改为轻量 Tag 样式（灰底圆角胶囊）
- **A5 修复**：表格 `stretch` 填满剩余高度，删除硬编码 `setMinimumHeight(380)`；行高 40px，斑马纹对比加强（#FAFBFC 与 #FFFFFF 交替不够，改为 hover 时才高亮 + 选中行左侧 3px 主色竖线）
- **A6 修复**：分页改紧凑式 `‹ 1/3 ›` 图标按钮 + 页码文字，居左；每页大小和全选收纳到表格卡片底部工具行
- **A7 修复**：日志面板加标题栏（"日志" + 清空/折叠按钮），默认折叠为 32px 高一条，点击展开；深色保留但加顶部 1px 分隔线

### 3.3 字体系统

- 建立 tokens 的 7 级阶梯并应用到 QSS：`pageTitleMain`→H1、`sectionTitle`→H2、卡片标题→H3、正文→BODY、辅助→CAPTION
- **数字等宽**：表格数值列、MetricCard 数值、涨跌幅全部用 `font-family: "Consolas","DIN Alternate"` 或 Qt 的 `QFont::setStyleHint` + tabular figures，保证列内数字宽度一致、涨跌对齐
- MetricCard 数值升 24px、页面标题保持 20px——数值是内容，标题是导航，权重纠偏（B3）
- 12px 辅助文字颜色从 `#6C757D` 加深场景化使用，或字号升 12.5→13px（Qt 支持小数字号）保证可读（B4）

### 3.4 配色收敛

- metric_card.py、section_title.py、各页内联 `setStyleSheet` 的硬编码色值 **全部替换为 token 引用**（C1/C2）——具体做法：组件不再内联样式，objectName 全部进 theme.qss；必须动态着色的（涨跌色）从 tokens.py import 常量拼 f-string
- 选中行背景 `#B5D4F4` → `#E6F1FB` + 左侧 3px `#378ADD` 竖线，与 hover `#F1F6FC` 拉开三层（C3）
- primaryBtn 文字加粗至 600、hover 用 `#185FA5`，保证对比度（C4）
- 保留涨红跌绿 `#E24B4A/#639922`（已是项目约定），只消灭第二套色板

### 3.5 视觉层次

- **去横条化**：SectionTitle 从"蓝底横条"改为"H2 文字 + 底部 1px 细分隔线"（D4），装饰噪音消除
- **卡片化**：每页 2~4 张白卡承载功能区，卡片间距 16px，页面灰底衬托（D1）
- MetricCard：等宽分布（不再 stretch 尾巴）、加 1px 边框 + 静态浅阴影、hover 微上浮（D2）
- 空状态组件 `EmptyState`：图标 + 主文案 + 引导按钮（如"暂无自选股 [+ 添加股票]"）（D5）

### 3.6 组件样式统一

- **高度唯一**：所有可交互控件（Button/ComboBox/LineEdit/SpinBox）min-height 统一 32px，padding 规则对齐，同行基线一致（E1）
- **圆角语义**：4px=控件、8px=容器、12px=仅 Hero（E2）
- **分组语言唯一**：废除 QGroupBox 原生标题样式，backtest 页等改用统一的 `SectionCard`（白卡 + H3 标题）（E3）
- QToolButton「更多」补 objectName=`ghostBtn`，无边框样式，与主按钮拉开主次（E4）

### 3.7 响应式适配

- 主窗口最小宽度设为 1080px（低于此宽度金融表格无可用性）
- 表格名称列 Stretch、数字列 Fixed，窗口变窄时优先压缩名称列而非截断代码列
- 筛选卡片内部用流式思路：宽度 < 1280px 时排序/每页控件自动换到第二行（用 QGridLayout 或判断 resizeEvent，不引入复杂流布局）
- 侧边导航宽度固定 200px → 支持折叠为 56px 图标模式（可选增强，Phase 2 视工作量决定是否纳入）

---

## 四、改动清单

| 文件 | 改动范围 | 改动量 |
|------|---------|--------|
| `desktop/styles/tokens.py` | **新增**：间距/字体/圆角/阴影/色板 token 常量 | 新增 ~80 行 |
| `desktop/styles/theme.qss` | 全面重写：token 注释对齐、新增卡片/SectionCard/EmptyState/ghostBtn/compact分页样式、修正选中/hover 色阶、统一 32px 控件高度 | 重写 ~700 行 |
| `desktop/pages/base_page.py` | 边距改用 token；标题区下加 1px 分隔线；提供 `add_card()` 辅助方法 | 小改 |
| `desktop/pages/watchlist_page.py` | 工具栏+排序行合并为筛选卡片；全选移入表头；分页紧凑化；列宽语义化；删硬编码 minHeight/内联样式；空状态接入 | 中改 ~150 行 |
| `desktop/pages/backtest_page.py` | GroupBox → SectionCard；边距 token 化；删内联样式 | 中改 |
| `desktop/pages/factor_analysis_page.py` | 边距/间距 token 化；内联样式收编 | 小改 |
| `desktop/pages/factor_backtest_page.py` | 同上 | 小改 |
| `desktop/pages/data_mgmt_page.py` | 同上（spacing 14→16 归位） | 小改 |
| `desktop/pages/signal_scan_page.py` | 同上 | 小改 |
| `desktop/pages/performance_page.py` | MetricCard 行等宽化 | 小改 |
| `desktop/widgets/metric_card.py` | 删内置 Tailwind 色板，色值/字号全部从 tokens 取；数值 24px；等宽+阴影 | 中改 |
| `desktop/widgets/section_title.py` | 蓝底横条 → 文字+分隔线样式 | 小改 |
| `desktop/widgets/section_card.py` | **新增**：白卡容器（H3 标题 + 内容区），替代 QGroupBox | 新增 ~60 行 |
| `desktop/widgets/empty_state.py` | **新增**：空状态组件 | 新增 ~50 行 |
| `desktop/widgets/pandas_table.py` | 数字列右对齐+等宽数字；行高 40；选中行竖线指示 | 小改 |
| `desktop/main_window.py` | 日志面板加标题栏+折叠；最小窗口 1080px | 小改 |
| `tests/desktop/` | 更新受影响的组件测试；新增 tokens/section_card/empty_state 测试；全量回归 | 配套 |

**不改**：业务逻辑、数据流、信号槽接口、图表模块（`desktop/charts/`）。纯表现层重构。

## 五、实施顺序（Phase 2 批准后执行）

1. tokens.py + theme.qss 重写（地基）
2. metric_card / section_title / section_card / empty_state 组件层
3. watchlist_page 样板页完整改造 → 截图给您确认风格
4. 样板确认后推广到其余 6 页
5. main_window 日志面板 + 响应式收尾
6. 全量测试回归（当前 188 个测试必须全绿）+ 截图对比

## 六、需要您确认的决策点

1. **整体风格**：「现代金融终端·克制的专业感」是否符合预期？（也可选：深色金融终端风，工作量翻倍）
2. **去横条化**：SectionTitle 蓝底横条全部改成"文字+分隔线"，同意吗？
3. **全选入表头**：删除右侧孤悬「全选」Checkbox、改为表头 Checkbox，同意吗？
4. **页面背景**：`#F8F9FA` → `#F5F6F8`（略深，衬托白卡），同意吗？
5. **侧边导航折叠为图标模式**：纳入本次还是以后再说？（默认：不纳入）
