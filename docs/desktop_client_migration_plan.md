# 量化系统桌面客户端改造开发计划

> **目标**：将现有 Streamlit Web 应用改造为 PyQt6/PySide6 桌面客户端应用
> **目标平台**：Windows + macOS
> **预计周期**：16 周（4 个月）
> **文档版本**：v1.0 | 2026-07-28

---

## 一、技术栈推荐与选择理由

### 1.1 推荐技术栈总览

| 层次 | 技术选型 | 说明 |
|------|---------|------|
| UI 框架 | **PySide6** (Qt for Python) | Qt 官方维护，LGPL 许可，商业友好 |
| 编程语言 | **Python 3.13**（保持不变） | 复用全部业务逻辑，零迁移成本 |
| 数据可视化 | **pyqtgraph** + **QtWebEngine**（过渡期） | 高性能原生绘图 + 过渡期复用 plotly |
| 数据库 | **SQLite**（保持不变） | 本地文件数据库，天然适配桌面应用 |
| 数据源 | **Baostock + CSV**（保持不变） | 网络数据获取逻辑无需改动 |
| 打包工具 | **PyInstaller** + **NSIS**（Win）/ **dmgbuild**（Mac） | 跨平台打包，生成原生安装包 |
| 异步任务 | **QThread** + **QThreadPool** | Qt 原生线程模型，避免 UI 冻结 |
| 表格组件 | **QTableView** + 自定义 **PandasModel** | 替代 st.dataframe，支持大数据量 |
| 样式系统 | **QSS**（Qt StyleSheet） | 替代 CSS，语法相近，迁移成本低 |

### 1.2 选择 PySide6 而非其他方案的理由

**为什么不选 Electron + Python 后端？**

| 维度 | PySide6 | Electron + Python |
|------|---------|-------------------|
| 安装包体积 | **40-60 MB** | 150-200 MB（含 Chromium） |
| 内存占用 | **50-80 MB** | 200-400 MB |
| 技术栈复杂度 | 纯 Python，单一技术栈 | 需维护 Node.js + Python 两套 |
| 现有代码复用 | 直接 import，函数级调用 | 需搭 HTTP/WebSocket 通信层 |
| 启动速度 | **<1 秒** | 3-5 秒 |
| 与现有项目契合度 | **极高**（同为 Python） | 中（需拆分前后端） |

**为什么不选 PyQt6 而选 PySide6？**

- **许可差异**：PyQt6 是 GPL 许可，商业闭源使用需购买 Riverbank 商业许可；PySide6 是 LGPL 许可，商业使用无额外限制
- **官方维护**：PySide6 由 Qt Group 官方维护，API 稳定性和长期支持有保障
- **API 兼容**：两者 API 几乎完全一致（`PyQt6.QtWidgets` → `PySide6.QtWidgets`），迁移成本极低
- **文档质量**：Qt 官方文档以 PySide6 为首选示例

### 1.3 可视化方案：pyqtgraph + QtWebEngine 双轨策略

当前项目有 **5 个 plotly 绘图函数**（约 550 行代码）和 **10 处 `st.plotly_chart` 调用**。采用双轨策略平衡迁移速度和最终质量：

| 阶段 | 方案 | 适用场景 | 说明 |
|------|------|---------|------|
| 过渡期（阶段 3-4） | QtWebEngineView 嵌入 plotly | 所有图表 | 复用现有 plotly 代码，快速完成功能迁移 |
| 最终态（阶段 4 后期） | pyqtgraph 重写 | K线图、信号图、绩效曲线 | 原生渲染，性能更好，无浏览器内核依赖 |

**pyqtgraph 优势**：
- 纯 Python，无浏览器内核依赖，减少打包体积
- 支持百万级数据点实时渲染（K线图场景刚需）
- 与 Qt 事件循环深度集成，交互响应即时
- 支持自定义 Item（蜡烛图 CandlestickItem）

**QtWebEngine 过渡期价值**：
- 现有 plotly 代码几乎零改动即可在桌面端运行
- 保留 plotly 的丰富交互（hover、zoom、pan）
- 为 pyqtgraph 重写争取时间，避免阻塞页面迁移

---

## 二、目标架构设计

### 2.1 目录结构（改造后）

```
quant_system/
├── desktop/                    # [新增] 桌面应用层
│   ├── main.py                 # 应用入口
│   ├── main_window.py          # 主窗口（QMainWindow）
│   ├── styles/                 # QSS 样式文件
│   │   ├── theme.qss           # 全局主题（替代 350 行 CSS）
│   │   └── variables.py        # 颜色/间距常量
│   ├── widgets/                # [新增] 可复用 Qt 组件库
│   │   ├── pandas_table.py     # PandasModel + QTableView（替代 st.dataframe）
│   │   ├── metric_card.py      # 指标卡片（替代 st.metric）
│   │   ├── section_title.py    # 区块标题（替代 _render_page_title）
│   │   ├── chart_container.py  # 图表容器（封装 QtWebEngine/pyqtgraph）
│   │   ├── stock_selector.py   # 股票选择器（替代 selectbox + 自选股）
│   │   └── progress_worker.py  # 异步任务封装（QThread + 信号）
│   ├── models/                 # [新增] 状态管理模型
│   │   ├── app_state.py        # 全局应用状态（替代 session_state）
│   │   ├── backtest_model.py   # 回测状态机
│   │   └── watchlist_model.py  # 自选股模型
│   └── pages/                  # [新增] 页面模块（替代 web/）
│       ├── watchlist_page.py   # 自选股管理（Tab 1）
│       ├── backtest_page.py    # 策略回测（Tab 2）
│       ├── data_mgmt_page.py   # 财务数据管理（Tab 3）
│       ├── factor_analysis_page.py  # 因子分析（Tab 4）
│       ├── factor_backtest_page.py  # 多因子回测（Tab 5）
│       ├── signal_scan_page.py # 信号扫描（Tab 6）
│       └── performance_page.py # 绩效分析（Tab 7）
│
├── data/                       # [不变] 数据层 — 零改动
├── strategy/                   # [不变] 策略层 — 零改动
├── portfolio/                  # [不变] 组合层 — 零改动
├── backtest/                   # [不变] 回测引擎 — 零改动
├── risk/                       # [不变] 风控层 — 零改动
│
├── web/                        # [废弃] 保留至迁移完成后删除
├── services/                   # [调整] 从 web/services/ 提升到顶层
│   ├── backtest_service.py     # 直接复用（336 行纯逻辑）
│   ├── backtest_params_service.py  # 直接复用（94 行纯逻辑）
│   └── factor_preparation_service.py  # 直接复用（63 行纯逻辑）
│
├── config.py                   # [调整] 增加桌面应用配置
├── quant_data.db               # [不变] SQLite 数据库
└── requirements.txt            # [调整] 替换依赖
```

### 2.2 架构分层原则

```
┌─────────────────────────────────────────┐
│  View 层 (desktop/pages/)               │  ← 全部重写
│  QWidget 子类，只负责 UI 渲染和事件捕获    │
├─────────────────────────────────────────┤
│  Model 层 (desktop/models/)             │  ← 新建
│  状态持有者，通过信号通知 View 刷新        │
├─────────────────────────────────────────┤
│  Service 层 (services/)                 │  ← 直接复用
│  纯业务逻辑，无 UI 依赖                   │
├─────────────────────────────────────────┤
│  Data 层 (data/)                        │  ← 零改动
│  DataManager + SQLite + Baostock        │
└─────────────────────────────────────────┘
```

**核心原则**：View 层不直接调用 Data 层，必须通过 Model → Service → Data 的链路。这解决了 Streamlit 中 UI 与业务逻辑混杂的问题（当前 `app.py` 1928 行中混合了 UI 渲染、状态管理、数据获取和回测执行）。

---

## 三、分阶段开发计划

### 阶段 1：基础框架搭建（第 1-2 周）

**目标**：搭建可运行的 PyQt6 应用骨架，完成主窗口和导航框架

**主要任务**：

| 序号 | 任务 | 交付物 | 预估工时 |
|------|------|--------|---------|
| 1.1 | 安装 PySide6 依赖，配置开发环境 | `requirements.txt` 更新 | 0.5 天 |
| 1.2 | 创建 `desktop/main.py` 应用入口 | 可启动的空窗口 | 0.5 天 |
| 1.3 | 实现 `MainWindow` 主窗口类（QMainWindow） | 菜单栏 + 侧边导航 + 中心区域 | 1 天 |
| 1.4 | 实现侧边导航栏（QListWidget 导航 + QStackedWidget 页面容器） | 7 个空页面占位，点击切换 | 1 天 |
| 1.5 | 编写 `theme.qss` 全局样式（从 350 行 CSS 迁移为 QSS） | 统一视觉风格 | 2 天 |
| 1.6 | 实现 `AppState` 全局状态单例（替代 session_state 基础框架） | 状态读写接口 | 1 天 |
| 1.7 | 配置日志系统（logging → QTextEdit 日志面板） | 底部状态栏 + 日志面板 | 1 天 |

**验收标准**：
- [ ] `python desktop/main.py` 可启动，显示主窗口
- [ ] 侧边栏 7 个导航项可切换，显示对应占位页面
- [ ] QSS 主题生效，视觉风格与原 Streamlit 一致（蓝色主色调）
- [ ] 关闭窗口时正确释放资源（DataManager.close()）

**关键技术决策**：

```python
# desktop/main.py 核心结构
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("量化交易系统")
        self.resize(1400, 900)

        # 侧边导航 + 页面堆栈
        self.nav_list = QListWidget()          # 导航列表
        self.page_stack = QStackedWidget()      # 页面容器
        self.nav_list.currentRowChanged.connect(
            self.page_stack.setCurrentIndex
        )

        # 初始化 7 个页面（先放占位 QWidget）
        self._init_pages()

        # 布局：左导航 + 右内容
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.nav_list, 0)       # 固定宽度
        layout.addWidget(self.page_stack, 1)      # 自适应
        self.setCentralWidget(central)

        # 加载全局 QSS
        self._load_stylesheet()

    def _init_pages(self):
        pages = [
            ("自选股管理", WatchlistPage()),
            ("策略回测", BacktestPage()),
            ("财务数据管理", DataMgmtPage()),
            ("因子分析", FactorAnalysisPage()),
            ("多因子回测", FactorBacktestPage()),
            ("信号扫描", SignalScanPage()),
            ("绩效分析", PerformancePage()),
        ]
        for name, page in pages:
            self.nav_list.addItem(name)
            self.page_stack.addWidget(page)
```

---

### 阶段 2：核心组件库开发（第 3-5 周）

**目标**：开发可复用的 Qt 组件库和状态管理模型，为页面迁移打基础

**主要任务**：

| 序号 | 任务 | 替代的 Streamlit 组件 | 预估工时 |
|------|------|----------------------|---------|
| 2.1 | **PandasTableModel + PandasTableView** | st.dataframe（18 处） | 3 天 |
| 2.2 | **MetricCard 组件** | st.metric（28 处） | 1 天 |
| 2.3 | **SectionTitle 组件** | _render_page_title + HTML 注入（25 处） | 1 天 |
| 2.4 | **ChartContainer 组件**（封装 QtWebEngineView） | st.plotly_chart（10 处） | 2 天 |
| 2.5 | **StockSelector 组件**（搜索 + 自选股列表） | st.selectbox + 自选股管理 | 2 天 |
| 2.6 | **AsyncWorker 基类**（QThread + 信号槽） | st.spinner / st.progress（14 处） | 2 天 |
| 2.7 | **AppState 状态管理模型** | st.session_state（129 处） | 3 天 |
| 2.8 | **MessageHelper 工具类** | st.error/warning/info/success（92 处） | 1 天 |

**验收标准**：
- [ ] PandasTableView 可正确显示 10000 行数据，滚动流畅
- [ ] MetricCard 正确显示数值、标签、增量
- [ ] ChartContainer 可渲染 plotly Figure（通过 QtWebEngine）
- [ ] AsyncWorker 执行耗时任务时 UI 不冻结
- [ ] AppState 支持跨页面状态共享（如自选股列表）
- [ ] 每个组件有对应的单元测试

**关键组件设计**：

**(1) PandasTableModel — 替代 st.dataframe**

```python
# desktop/widgets/pandas_table.py
class PandasTableModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._df = df

    def rowCount(self, parent=None):
        return len(self._df)

    def columnCount(self, parent=None):
        return len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            value = self._df.iloc[index.row(), index.column()]
            # 数值格式化：百分比、金额等
            return str(value)
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._df.columns[section])
            return str(self._df.index[section])
```

**(2) AsyncWorker — 替代 st.spinner + 阻塞式调用**

Streamlit 的 `st.spinner` 是同步阻塞的（脚本重运行期间显示 spinner）。PyQt 中必须用 QThread 避免冻结 UI：

```python
# desktop/widgets/progress_worker.py
class AsyncWorker(QThread):
    progress = Signal(int, str)    # 进度百分比, 消息
    finished = Signal(object)      # 结果
    error = Signal(str)            # 错误信息

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
```

**(3) AppState — 替代 st.session_state**

Streamlit 的 `session_state` 是一个全局字典，脚本重运行时保持。PyQt 中需要显式的状态管理对象：

```python
# desktop/models/app_state.py
class AppState(QObject):
    # 信号：状态变化时通知订阅者
    watchlist_changed = Signal(list)
    backtest_result_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self._watchlist = []
        self._backtest_result = {}

    @property
    def watchlist(self):
        return self._watchlist

    def set_watchlist(self, stocks: list):
        self._watchlist = stocks
        self.watchlist_changed.emit(stocks)  # 通知所有页面刷新
```

---

### 阶段 3：页面逐个迁移（第 6-11 周）

**目标**：将 7 个 Tab 页面从 Streamlit 迁移到 PyQt6，优先迁移依赖少的页面

**迁移优先级排序**（按依赖复杂度从低到高）：

| 顺序 | 页面 | 原文件 | 行数 | 迁移难点 | 预估工时 |
|------|------|--------|------|---------|---------|
| 1 | 财务数据管理 | web/pages/data_management.py | 626 | st.spinner(5) + st.rerun(5) | 4 天 |
| 2 | 因子分析 | web/factor_analysis_page.py | 724 | session_state(50处) 最多 | 5 天 |
| 3 | 自选股管理 | web/app.py 内联（324行） | 324 | session_state(52处) | 3 天 |
| 4 | 策略回测 | web/app.py 内联（256行） | 256 | 回测参数表单 + 结果展示 | 4 天 |
| 5 | 绩效分析 | web/app.py 内联 | ~100 | 较简单 | 2 天 |
| 6 | 信号扫描 | web/app.py 内联（228行） | 228 | 扫描进度 + 结果表格 | 3 天 |
| 7 | 多因子回测 | web/factor_backtest_page.py | 1513 | 最大文件，sidebar(1) + session_state(21) | 7 天 |

**每个页面的迁移步骤（标准化流程）**：

1. **拆分**：将 `app.py` 内联的 Tab 逻辑提取为独立文件（如果是内联的）
2. **分析**：列出该页面所有的 `st.session_state` 键和 `st.rerun()` 调用点
3. **建模**：为该页面创建对应的 Model 类，将 session_state 键映射为 Model 属性
4. **迁移 UI**：逐个将 Streamlit 组件替换为 Qt 组件（参考附录映射表）
5. **连接信号槽**：将 `st.rerun()` 调用改为 Model 信号触发 View 刷新
6. **测试**：验证功能与原 Streamlit 版本一致

**验收标准**：
- [ ] 每个页面的功能与原 Streamlit 版本完全一致
- [ ] 所有 `st.session_state` 调用已替换为 Model 属性
- [ ] 所有 `st.rerun()` 调用已替换为信号槽刷新
- [ ] 页面间状态共享正常（如自选股列表在回测页面可用）
- [ ] 耗时操作（数据获取、回测）不冻结 UI

---

### 阶段 4：可视化层迁移（第 12-14 周）

**目标**：将 5 个 plotly 绘图函数迁移为 pyqtgraph 原生实现

**主要任务**：

| 序号 | 绘图函数 | 原位置 | 行数 | pyqtgraph 对应方案 | 预估工时 |
|------|---------|--------|------|-------------------|---------|
| 4.1 | plot_kline（K线图） | app.py:511 | 156 | CandlestickItem + BarGraphItem | 3 天 |
| 4.2 | plot_kline_with_signals | app.py:667 | 231 | K线 + InfiniteLine 信号标注 | 3 天 |
| 4.3 | plot_signals_only | app.py:898 | 58 | BarGraphItem 信号柱状图 | 1 天 |
| 4.4 | plot_multi_stock_signals | app.py:956 | 59 | 多子图 BarGraphItem | 1 天 |
| 4.5 | plot_signals_heatmap | app.py:1015 | 51 | HeatmapItem | 1 天 |
| 4.6 | 绩效曲线图 | backtest_presenter.py | - | PlotDataItem + FillBetweenItem | 1 天 |
| 4.7 | 因子分析图表 | factor_analysis_page.py | - | PlotDataItem 散点图/柱状图 | 2 天 |

**验收标准**：
- [ ] 所有图表使用 pyqtgraph 原生渲染（移除 QtWebEngine 依赖）
- [ ] K线图支持缩放、平移、十字光标
- [ ] 信号图正确标注买入（红色）/卖出（绿色）位置
- [ ] 热力图正确显示日期 × 股票矩阵
- [ ] 图表渲染性能：10000+ 数据点流畅交互

---

### 阶段 5：打包与发布（第 15-16 周）

**目标**：生成 Windows 和 macOS 安装包，完成最终测试

**主要任务**：

| 序号 | 任务 | 说明 | 预估工时 |
|------|------|------|---------|
| 5.1 | 编写 PyInstaller 打包脚本 | .spec 文件配置 | 1 天 |
| 5.2 | Windows 打包测试 | 生成 .exe + NSIS 安装包 | 2 天 |
| 5.3 | macOS 打包测试 | 生成 .dmg + 代码签名 | 2 天 |
| 5.4 | 数据库路径适配 | 用户目录迁移 | 1 天 |
| 5.5 | 应用图标和启动画面 | 品牌视觉 | 1 天 |
| 5.6 | 全功能集成测试 | 7 个 Tab 完整流程 | 3 天 |
| 5.7 | 编写用户手册 | 安装和使用说明 | 1 天 |

**验收标准**：
- [ ] Windows 安装包（.exe）可在 Win10/Win11 正常安装运行
- [ ] macOS 安装包（.dmg）可在 Intel + Apple Silicon 正常运行
- [ ] 首次启动自动创建数据库和缓存目录
- [ ] 应用体积 < 80MB
- [ ] 启动时间 < 3 秒

---

## 四、功能模块改造详情

### 4.1 界面相关改造点

#### 4.1.1 Streamlit → PyQt6 组件映射表

| Streamlit 组件 | 使用次数 | PyQt6 替代方案 | 迁移难度 |
|---------------|---------|---------------|---------|
| st.write/markdown/header | 119 | QLabel / QGroupBox（富文本用 QTextBrowser） | 低 — 机械映射 |
| st.session_state | 129 | AppState 单例 + QObject 信号 | **高** — 范式转换 |
| st.number_input | ~40 | QSpinBox / QDoubleSpinBox | 低 |
| st.text_input | ~10 | QLineEdit | 低 |
| st.date_input | ~10 | QDateEdit | 低 |
| st.slider | ~10 | QSlider + QSpinBox 联动 | 低 |
| st.checkbox | ~10 | QCheckBox | 低 |
| st.button | 31 | QPushButton | 低 |
| st.selectbox | ~20 | QComboBox | 低 |
| st.radio | ~4 | QRadioButton + QButtonGroup | 低 |
| st.columns | 39 | QHBoxLayout / QGridLayout | 低 |
| st.tabs | 1（7个Tab） | QTabWidget 或侧边导航 + QStackedWidget | 中 |
| st.expander | 12 | QGroupBox（checkable=True） | 低 |
| st.dataframe | 18 | QTableView + PandasTableModel | 中 — 需自定义 Model |
| st.metric | 28 | 自定义 MetricCard QWidget | 中 |
| st.plotly_chart | 10 | ChartContainer（QtWebEngine → pyqtgraph） | **高** — 阶段4专门处理 |
| st.error/warning/info | 92 | QMessageBox / QStatusBar.showMessage | 低 |
| st.spinner/progress | 14 | QProgressDialog + QThread | 中 — 需异步化 |
| st.rerun | 12 | Model 信号触发 View 刷新 | **高** — 范式转换 |
| st.cache_data | 2 | functools.lru_cache / 自定义缓存 | 低 |
| st.download_button | 2 | QFileDialog.getSaveFileName | 低 |
| st.sidebar | 1 | QDockWidget 或固定侧边栏 | 低 |
| st.markdown(HTML) | 25 | QTextBrowser(HTML) / 自定义 QWidget | 中 |

#### 4.1.2 session_state → Model 范式转换（最核心改造）

**问题分析**：Streamlit 的 `session_state` 是全局字典，脚本每次重运行时保持状态。当前项目有 **129 处** `session_state` 调用，分布在 4 个文件中。这是最大的迁移难点。

**转换策略**：为每个功能域创建独立的 Model 类，通过 Qt 信号通知 View 刷新。

```python
# 转换前（Streamlit 范式）
if 'selected_stocks' not in st.session_state:
    st.session_state['selected_stocks'] = []
selected = st.session_state['selected_stocks']
# ... 修改后
st.session_state['selected_stocks'] = new_list
st.rerun()  # 触发整个脚本重运行

# 转换后（PyQt6 范式）
class WatchlistModel(QObject):
    stocks_changed = Signal(list)  # 状态变化信号

    def __init__(self):
        super().__init__()
        self._stocks = []

    @property
    def stocks(self):
        return self._stocks

    def add_stock(self, symbol: str):
        if symbol not in self._stocks:
            self._stocks.append(symbol)
            self.stocks_changed.emit(self._stocks)  # 通知 View 自动刷新

# View 中连接信号
class WatchlistPage(QWidget):
    def __init__(self, model: WatchlistModel):
        self.model = model
        self.model.stocks_changed.connect(self._refresh_list)

    def _refresh_list(self, stocks):
        self.stock_list.clear()
        self.stock_list.addItems(stocks)
```

**session_state 键映射表**（需逐个处理）：

| session_state 键 | 所在文件 | 出现次数 | 对应 Model |
|-----------------|---------|---------|-----------|
| selected_stocks / backtest_selected_stocks | app.py | 52 | WatchlistModel |
| factor_* (因子配置) | factor_analysis_page.py | 50 | FactorModel |
| backtest_params | factor_backtest_page.py | 21 | BacktestModel |
| data_mgmt_* | data_management.py | 6 | DataMgmtModel |

#### 4.1.3 st.rerun() → 信号槽刷新（范式级转换）

**问题**：Streamlit 通过 `st.rerun()` 重新执行整个脚本来刷新 UI。PyQt 没有等价机制，需要改为局部刷新。

```python
# 转换前：st.rerun() 触发整页刷新
if st.button("更新数据"):
    update_stock_data(symbol)
    st.rerun()  # 重新执行整个脚本

# 转换后：信号触发局部刷新
class DataMgmtPage(QWidget):
    def __init__(self, model):
        self.update_btn = QPushButton("更新数据")
        self.update_btn.clicked.connect(self._on_update)

    def _on_update(self):
        # 启动异步任务，不阻塞 UI
        self.worker = AsyncWorker(update_stock_data, self.symbol)
        self.worker.finished.connect(self._on_update_done)

    def _on_update_done(self, result):
        # 只刷新受影响的组件，不刷新整页
        self.status_label.setText(f"更新完成: {result}")
        self.table_model.update_data(result)
```

#### 4.1.4 自定义 CSS → QSS 迁移

当前 `app.py` 第 39-396 行有约 **350 行自定义 CSS**，定义了：
- CSS 变量（颜色、间距）
- `.app-hero`（渐变标题栏）
- `.metric-label` / `.metric-value`（指标卡片）
- `.market-page-title`（页面标题）
- `.hero-badge`（标签徽章）

**迁移策略**：
1. CSS 变量 → QSS 全局变量（通过 Python 常量类注入）
2. `.app-hero` → 自定义 HeroHeader QWidget
3. `.metric-*` → MetricCard 组件（阶段 2 开发）
4. 渐变背景 → 纯色填充（QSS 不支持复杂渐变，简化为纯色）

```css
/* 转换前 CSS */
.app-hero {
    background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 55%, #2563eb 100%);
    border-radius: 16px;
    padding: 20px 24px;
}

/* 转换后 QSS */
QFrame#heroHeader {
    background-color: #1d4ed8;
    border-radius: 8px;
    padding: 20px 24px;
}
```

#### 4.1.5 HTML 指标卡 → MetricCard 组件

当前通过 `st.markdown` 拼接 HTML 实现指标卡（app.py:1158-1171），迁移为自定义 QWidget：

```python
# desktop/widgets/metric_card.py
class MetricCard(QFrame):
    def __init__(self, label: str, value: str, delta: str = ""):
        super().__init__()
        self.setObjectName("metricCard")

        layout = QVBoxLayout(self)
        self.label_label = QLabel(label)
        self.label_label.setObjectName("metricLabel")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")

        layout.addWidget(self.label_label)
        layout.addWidget(self.value_label)

        if delta:
            self.delta_label = QLabel(delta)
            # 涨红跌绿（中国股市惯例）
            if "+" in delta or "涨" in delta:
                self.delta_label.setStyleSheet("color: #dc2626;")  # 红色
            else:
                self.delta_label.setStyleSheet("color: #16a34a;")  # 绿色
            layout.addWidget(self.delta_label)
```

---

### 4.2 数据存储和本地缓存方案调整

#### 4.2.1 数据库路径策略

**当前问题**：数据库路径硬编码为 `PROJECT_ROOT / "quant_data.db"`，桌面应用安装后项目根目录不可写。

**改造方案**：

```python
# config.py 改造
import sys
from pathlib import Path
from PySide6.QtCore import QStandardPaths

def get_app_data_dir() -> Path:
    """获取应用数据目录（跨平台）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        base = QStandardPaths.writableLocation(
            QStandardPaths.AppDataLocation
        )
    else:
        # 开发环境
        base = str(Path(__file__).parent)
    return Path(base)

# 数据库路径
APP_DATA_DIR = get_app_data_dir()
DATABASE_PATH = APP_DATA_DIR / "quant_data.db"
CACHE_DIR = APP_DATA_DIR / "data_cache"

# 首次启动时自动创建目录
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
```

**各平台数据目录**：
- Windows: `C:\Users\<用户>\AppData\Local\quant_system\`
- macOS: `~/Library/Application Support/quant_system/`

#### 4.2.2 数据迁移策略

从 Web 版迁移到桌面版时，需将现有 `quant_data.db` 复制到新路径：

```python
# desktop/main.py 首次启动检查
def migrate_existing_database():
    """首次启动时迁移现有数据库"""
    old_db = Path(__file__).parent.parent / "quant_data.db"
    new_db = DATABASE_PATH

    if not new_db.exists() and old_db.exists():
        import shutil
        shutil.copy2(old_db, new_db)
        logging.info(f"数据库已迁移: {old_db} → {new_db}")
```

#### 4.2.3 缓存策略调整

**当前**：`st.cache_data`（仅 2 处）用于缓存数据获取结果。

**改造**：替换为 `functools.lru_cache` 或自定义缓存类：

```python
# desktop/models/data_cache.py
from functools import lru_cache
from datetime import datetime, timedelta

class TimedCache:
    """带 TTL 的缓存，替代 st.cache_data"""
    def __init__(self, ttl_seconds: int = 3600):
        self._cache = {}
        self._ttl = ttl_seconds

    def get(self, key):
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self._ttl):
                return value
            del self._cache[key]
        return None

    def set(self, key, value):
        self._cache[key] = (value, datetime.now())
```

#### 4.2.4 配置持久化

**新增**：用户偏好配置持久化（回测参数、界面布局等）

```python
# desktop/models/settings.py
import json
from PySide6.QtCore import QSettings

class AppSettings:
    """用户设置持久化（替代 session_state 中的配置项）"""
    def __init__(self):
        self.settings = QSettings("QuantSystem", "Desktop")

    def get(self, key: str, default=None):
        return self.settings.value(key, default)

    def set(self, key: str, value):
        self.settings.setValue(key, value)

    # 便捷方法
    def get_backtest_params(self) -> dict:
        return {
            'initial_capital': self.get('backtest/capital', 1000000),
            'commission': self.get('backtest/commission', 0.0003),
            'max_positions': self.get('backtest/max_positions', 5),
        }
```

---

### 4.3 网络请求层适配

#### 4.3.1 Baostock 网络请求

**当前状态**：Baostock 数据获取在 `data/financial_data_source.py` 和 `data/data_manager.py` 中，使用同步 HTTP 请求。

**改造要点**：

1. **线程隔离**：Baostock 的同步请求会阻塞 Qt 事件循环，必须放入 QThread

```python
# desktop/widgets/progress_worker.py
class DataFetchWorker(AsyncWorker):
    """数据获取专用 Worker"""
    progress = Signal(int, str)  # 进度, 消息

    def run(self):
        try:
            # 在子线程中执行同步网络请求
            for i, symbol in enumerate(self._symbols):
                self.progress.emit(
                    int(i / len(self._symbols) * 100),
                    f"正在获取 {symbol} 数据..."
                )
                df = self._data_manager.get_daily_kline(symbol, ...)
                self._results[symbol] = df

            self.finished.emit(self._results)
        except Exception as e:
            self.error.emit(str(e))
```

2. **Baostock 登录状态管理**：当前使用懒登录，桌面应用需在启动时初始化或首次使用时提示

```python
# desktop/models/app_state.py
class AppState:
    def __init__(self):
        self._baostock_logged_in = False
        self._baostock_lock = threading.Lock()

    def ensure_baostock_login(self):
        """确保 Baostock 已登录（线程安全）"""
        with self._baostock_lock:
            if not self._baostock_logged_in:
                import baostock as bs
                lg = bs.login()
                if lg.error_code == '0':
                    self._baostock_logged_in = True
                else:
                    raise ConnectionError(f"Baostock 登录失败: {lg.error_msg}")
```

3. **请求限流保持不变**：现有 `BAOSTOCK_RATE_LIMIT = 1`（每秒 1 次）逻辑无需改动

#### 4.3.2 网络状态检测

**新增**：桌面应用需要检测网络状态，提示用户

```python
# desktop/widgets/network_status.py
class NetworkStatusWidget(QWidget):
    """网络状态指示器（状态栏显示）"""
    def __init__(self):
        super().__init__()
        self.indicator = QLabel()
        self._update_status()
        # 每 30 秒检查一次
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_status)
        self.timer.start(30000)

    def _update_status(self):
        try:
            # 尝试连接 Baostock 服务器
            import socket
            socket.create_connection(("baostock.com", 80), timeout=3)
            self.indicator.setText("● 在线")
            self.indicator.setStyleSheet("color: #16a34a;")
        except:
            self.indicator.setText("● 离线（仅本地数据）")
            self.indicator.setStyleSheet("color: #dc2626;")
```

---

### 4.4 权限和系统调用的处理

#### 4.4.1 文件系统权限

| 操作 | Web 版（Streamlit） | 桌面版（PyQt6） | 改造点 |
|------|-------------------|----------------|--------|
| 数据库读写 | 项目根目录 | 用户 AppData 目录 | 路径迁移（见 4.2.1） |
| CSV 导出 | 项目根目录 | QFileDialog 用户选择 | 增加文件选择对话框 |
| 报告导出 | 项目根目录 | QFileDialog 用户选择 | 同上 |
| 日志文件 | stdout | AppData/logs/ 目录 | 新增文件日志 |

```python
# CSV 导出改造
# 转换前
st.download_button("导出 CSV", data, file_name="signals.csv")

# 转换后
def export_csv(self, df: pd.DataFrame):
    path, _ = QFileDialog.getSaveFileName(
        self, "导出 CSV", "", "CSV 文件 (*.csv)"
    )
    if path:
        df.to_csv(path, index=False, encoding='utf-8-sig')
        QMessageBox.information(self, "成功", f"已导出到: {path}")
```

#### 4.4.2 macOS 特殊处理

| 问题 | 说明 | 解决方案 |
|------|------|---------|
| Apple Silicon 兼容 | PySide6 需 arm64 版本 | 使用 PySide6 >= 6.5（原生支持 ARM） |
| 代码签名 | macOS Gatekeeper 要求 | 使用 `codesign` 命令签名 |
| 文件路径 | 路径分隔符差异 | 统一使用 `pathlib.Path` |
| 暗色模式 | macOS 系统暗色主题 | 检测 `QGuiApplication.styleHints().colorScheme()` |

```python
# macOS 暗色模式适配
def apply_system_theme(app):
    from PySide6.QtGui import QGuiApplication
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        app.setStyleSheet(load_qss("dark_theme.qss"))
    else:
        app.setStyleSheet(load_qss("light_theme.qss"))
```

#### 4.4.3 系统资源管理

**问题**：Streamlit 由服务器管理生命周期，桌面应用需自行管理资源释放。

```python
# desktop/main_window.py
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data_manager = DataManager()
        self._setup_cleanup_handler()

    def _setup_cleanup_handler):
        """确保应用退出时正确释放资源"""
        app = QApplication.instance()
        app.aboutToQuit.connect(self._cleanup)

    def _cleanup(self):
        """资源清理"""
        logging.info("正在关闭应用...")
        try:
            self.data_manager.close()
            # 关闭 Baostock 连接
            import baostock as bs
            try:
                bs.logout()
            except:
                pass
        except Exception as e:
            logging.error(f"清理资源时出错: {e}")

    def closeEvent(self, event):
        """窗口关闭事件"""
        reply = QMessageBox.question(
            self, "确认退出",
            "确定要退出量化系统吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()
```

#### 4.4.4 单实例锁

**新增**：防止用户启动多个应用实例（避免 SQLite 数据库锁冲突）

```python
# desktop/main.py
from PySide6.QtNetwork import QLocalServer, QLocalSocket

def ensure_single_instance():
    """确保只有一个应用实例运行"""
    server_name = "quant_system_singleton"
    socket = QLocalSocket()
    socket.connectToServer(server_name)

    if socket.waitForConnected(500):
        # 已有实例运行，激活已有窗口
        socket.write(b"ACTIVATE")
        socket.waitForBytesWritten()
        sys.exit(0)
    else:
        # 启动本地服务器
        server = QLocalServer()
        QLocalServer.removeServer(server_name)
        server.listen(server_name)
        return server
```

---

## 五、风险与注意事项

### 5.1 高风险项（需重点关注）

#### 风险 1：session_state 范式转换（风险等级：高）

| 维度 | 说明 |
|------|------|
| **风险描述** | 129 处 `session_state` 调用需逐个转换为 Model 属性 + 信号。Streamlit 的"全局字典 + 脚本重运行"与 PyQt 的"对象 + 信号槽"是两种完全不同的状态管理范式 |
| **影响范围** | app.py（52处）、factor_analysis_page.py（50处）、factor_backtest_page.py（21处）、data_management.py（6处） |
| **缓解措施** | 1. 为每个功能域建立独立的 Model 类，逐域迁移而非全局替换<br>2. 先迁移依赖最少的 `data_management.py`（6处）验证模式<br>3. 建立 session_state 键 → Model 属性的映射文档，逐个核对 |
| **回退方案** | 如某个页面迁移受阻，可暂时用全局字典 + 手动刷新替代，后续再重构 |

#### 风险 2：st.rerun() 控制流重构（风险等级：高）

| 维度 | 说明 |
|------|------|
| **风险描述** | Streamlit 的 `st.rerun()` 通过重新执行整个脚本来刷新 UI。PyQt 必须改为局部信号触发，涉及控制流重构而非简单替换 |
| **影响范围** | app.py（7处）、data_management.py（5处） |
| **缓解措施** | 1. 分析每个 `st.rerun()` 的触发场景：数据更新后刷新表格、状态变更后刷新选项<br>2. 将"刷新"拆解为具体的"哪个组件需要更新"<br>3. 使用 Model 信号精确通知需要刷新的 View 组件 |

#### 风险 3：Plotly → pyqtgraph 图表重写（风险等级：高）

| 维度 | 说明 |
|------|------|
| **风险描述** | 5 个绘图函数（550 行）使用 plotly 的高级 API（subplots、annotation、hover info），pyqtgraph API 风格完全不同 |
| **缓解措施** | 1. 采用双轨策略：阶段 3 先用 QtWebEngine 嵌入 plotly（零改动），阶段 4 再用 pyqtgraph 重写<br>2. K线图是核心图表，优先实现并充分测试<br>3. 保留 plotly 版本作为参考实现，对比验证 pyqtgraph 版本的正确性 |

### 5.2 中等风险项

#### 风险 4：QSS 样式能力限制

| 维度 | 说明 |
|------|------|
| **风险描述** | QSS 不支持 CSS 的复杂渐变（linear-gradient）、伪类（:hover 部分支持）、动画。当前 350 行 CSS 中有渐变背景和 hover 效果 |
| **缓解措施** | 1. 渐变背景改为纯色填充（视觉差异可接受）<br>2. hover 效果用 QSS `:hover` 伪类（Qt 支持基础 hover）<br>3. 复杂效果用自定义 QWidget + paintEvent 实现 |

#### 风险 5：跨平台一致性

| 维度 | 说明 |
|------|------|
| **风险描述** | Windows 和 macOS 的字体渲染、控件样式、快捷键习惯不同 |
| **缓解措施** | 1. 使用 QSS 统一控件样式，不依赖系统原生主题<br>2. 快捷键使用 QKeySequence 标准键（Ctrl+C 在 Mac 上自动映射为 Cmd+C）<br>3. 字体使用跨平台回退栈：`"Microsoft YaHei", "PingFang SC", sans-serif` |

#### 风险 6：PyInstaller 打包隐式依赖

| 维度 | 说明 |
|------|------|
| **风险描述** | PyInstaller 可能遗漏动态导入的模块（如 baostock、pandas_ta 的子模块） |
| **缓解措施** | 1. 打包前用 `pipdeptree` 列出完整依赖树<br>2. 在 .spec 文件的 `hiddenimports` 中显式声明<br>3. 每次打包后在干净环境（无 Python 的虚拟机）测试 |

### 5.3 低风险项

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| SQLite 并发 | 桌面应用单进程，无并发问题 | 保持现有 WAL 模式即可 |
| Baostock API 限流 | 现有限流逻辑不变 | 无需改动 |
| 数据库迁移 | 路径变化需迁移 | 首次启动自动复制 |

### 5.4 迁移过程中的注意事项

1. **并行运行期**：阶段 1-3 期间，Streamlit 版本和 PyQt 版本并行存在。确保 `services/` 和 `data/` 层的改动同时兼容两个版本
2. **测试覆盖**：现有 `tests/` 目录有 10 个测试文件，迁移过程中持续运行 `pytest -q` 确保业务逻辑未被破坏
3. **版本控制**：在 `desktop/` 目录开发，不修改 `web/` 目录，直到全部迁移完成后再删除 `web/`
4. **渐进式替换**：每完成一个页面的迁移就提交一次，便于回滚
5. **数据库路径兼容**：开发期间保持 `quant_data.db` 在项目根目录，打包阶段才切换到 AppData 路径
6. **中国股市颜色惯例**：K线图和指标卡中，涨用红色（#dc2626），跌用绿色（#16a34a），与 Streamlit 版本保持一致

---

## 六、附录

### 附录 A：文件改造清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `desktop/` 整个目录 | 新增 | 桌面应用全部代码 |
| `config.py` | 修改 | 增加 AppData 路径逻辑 |
| `requirements.txt` | 修改 | 移除 streamlit，增加 PySide6/pyqtgraph |
| `services/` | 移动 | 从 `web/services/` 提升到顶层 |
| `data/` | 不变 | 零改动 |
| `strategy/` | 不变 | 零改动 |
| `portfolio/` | 不变 | 零改动 |
| `backtest/` | 不变 | 零改动 |
| `risk/` | 不变 | 零改动 |
| `web/` | 废弃 | 迁移完成后删除 |
| `run_web.bat` | 废弃 | 替换为 `run_desktop.bat` |

### 附录 B：requirements.txt 变更

```diff
# 移除
- streamlit>=1.28.0

# 新增
+ PySide6>=6.6.0
+ pyqtgraph>=0.13.3
+ PyInstaller>=6.3.0      # 打包用，可选

# 保持不变
  pandas>=2.0.0
  numpy>=1.24.0
  pandas-ta>=0.3.14b
  scipy>=1.10.0
  matplotlib>=3.7.0       # 可选，部分图表可能仍用
  plotly>=5.15.0          # 过渡期保留，最终移除
  seaborn>=0.12.0         # 可选
  sqlalchemy>=2.0.0
  python-dateutil>=2.8.0
  pytz>=2023.3
```

### 附录 C：各阶段验收检查表

**阶段 1 验收**：
- [ ] `python desktop/main.py` 可启动
- [ ] 主窗口显示 7 个导航项
- [ ] QSS 主题生效
- [ ] 窗口关闭时资源正确释放

**阶段 2 验收**：
- [ ] PandasTableView 可显示 10000 行
- [ ] MetricCard 正确渲染
- [ ] AsyncWorker 不冻结 UI
- [ ] AppState 跨页面状态共享

**阶段 3 验收**（每页单独验收）：
- [ ] 页面功能与 Streamlit 版本一致
- [ ] 无 st.session_state / st.rerun 残留
- [ ] 耗时操作异步执行

**阶段 4 验收**：
- [ ] 所有图表用 pyqtgraph 渲染
- [ ] K线图支持缩放/平移
- [ ] 无 QtWebEngine 依赖

**阶段 5 验收**：
- [ ] Windows .exe 安装包可用
- [ ] macOS .dmg 安装包可用
- [ ] 首次启动自动创建数据库
- [ ] 应用体积 < 80MB

---

*本计划基于对项目 web/ 目录 11 个文件、6012 行代码的完整分析制定。所有组件使用次数、文件行数均为实际统计数据。*
