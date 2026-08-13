# 桌面客户端开发问题记录

> 记录桌面客户端（PySide6 迁移）开发过程中踩过的坑、根因分析与修复方案。
> 按「环境与构建 / 框架与线程 / 页面生命周期 / 组件交互 / 业务逻辑迁移」分类。
> 最近更新：2026-08-13

---

## 一、环境与构建

### ISSUE-ENV-01 Python 入口脚本 import 失败（`ModuleNotFoundError`）

- **现象**：用 `python desktop/main.py` 启动时报 `from desktop.xxx import ...` 找不到模块；用 `python -m desktop.main` 却正常。
- **根因**：`python script.py` 启动时，Python 把**脚本所在目录**（`desktop/`）加入 `sys.path`，而非项目根目录，导致 `from desktop.module import ...` 里第一级包名 `desktop` 找不到。
- **修复**：在 `main.py` 开头自包含 `sys.path` 处理，把项目根目录加入 `sys.path`：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

这样 `python xxx.py` 和 `python -m xxx.yyy` 两种启动方式都能兼容。

---

### ISSUE-ENV-02 pytest 测试目录名与项目包名冲突

- **现象**：`tests/desktop/test_xxx.py` 里 `from desktop.widgets import ...` 导入的是 `tests/desktop/` 而非项目的 `desktop/` 包，导致 import 到错误模块或失败。
- **根因**：`tests/desktop/` 目录名 `desktop` 与项目 `desktop/` 包同名。当 `tests/desktop/__init__.py` 存在时，pytest 会把 `tests/` 加入 `sys.path`，`desktop` 被解析为 `tests/desktop/`。
- **修复**：**删除测试子目录的 `__init__.py`**，让 pytest 不把它当包。

---

### ISSUE-ENV-03 无头环境验证 GUI 组件

- **现象**：CI / 命令行下无法创建 Qt 组件或做冒烟测试。
- **修复**：设置 `QT_QPA_PLATFORM=offscreen` 后即可无头创建 QApplication 和各类 widget。临时验证脚本放在 `.tmp_check/`（已 gitignore；本机 Windows 没有 `/tmp`）。

---

## 二、框架与线程安全

### ISSUE-THREAD-01 QThread 被 GC 导致进程 abort（EXIT=127）

- **现象**：后台任务跑着跑着整个进程直接退出，退出码 127，**没有任何 traceback**。
- **根因**：`AsyncWorker`（QThread 子类）没有 parent，又只被存成局部变量，方法返回后 worker 被 Python 垃圾回收；但底层线程仍在运行，Qt 在 C++ 层访问已销毁对象 → abort。
- **修复**：在 `desktop/widgets/async_worker.py` 用**活跃 worker 注册表**统一持有引用兜底；程序退出时调用 `shutdown_workers()` 统一清理。

---

### ISSUE-THREAD-02 子线程复用主线程 DataManager 导致崩溃/数据错乱

- **现象**：在 `AsyncWorker` 后台线程里直接调用主线程创建的 `DataManager` 实例，出现 sqlite 报错或数据错乱。
- **根因**：`sqlite3` 连接**非线程安全**，跨线程复用同一个连接会出问题。
- **修复**：子线程内**用 `db_path` 自建** `DataManager` / `CacheOnlyProvider`，用完 `try/finally` 关闭，不共享主线程实例。

---

### ISSUE-THREAD-03 sqlite 连接泄漏锁死 db 文件

- **现象**：长驻桌面端连接持续累积，Windows 下最终锁死 `quant_data.db`，测试 teardown 报 `PermissionError`。
- **根因**：`conn.close()` 写在 `try` 块内，异常路径被 `except: pass` 吞掉后**没走到 close**，连接泄漏。
- **修复**：连接关闭必须放在 `finally` 块：

```python
dm = DataManager(db_path)
try:
    ...
finally:
    try:
        dm.close()
    except Exception:
        pass
```

---

## 三、页面构造与生命周期

### ISSUE-PAGE-01 BasePage 子类构造即 AttributeError

- **现象**：页面类在 `super().__init__()` 之后才赋值的属性，`_build_content()` 里访问时直接 AttributeError。
- **根因**：`BasePage.__init__` 内部就会触发 `_build_content()`，所以 `_build_content()` 用到的依赖（如 `self._state`、`self._wl`、`self._db_path`）必须**在 `super().__init__()` 之前**完成赋值。
- **修复**：遵守「依赖先赋值、再调 super」的顺序约定，并在代码里加注释提醒。

---

### ISSUE-PAGE-02 只做编译/导入检查不够，构造期 bug 漏检

- **现象**：页面文件 `import` 没问题、`python -m py_compile` 也通过，但运行时报错。
- **根因**：构造期（`__init__` / `_build_content`）的 bug 只有在真正实例化时才会暴露。
- **修复**：在 `tests/desktop/test_pages_smoke.py` 里，把每个页面在 `MainWindow` 中**真正实例化**，并逐个切换页面，才能覆盖构造期问题。

---

### ISSUE-PAGE-03 视图切换时旧 worker 回调访问已删除控件（竞态崩溃）

- **现象**：列表视图/详情视图频繁切换时偶发崩溃。
- **根因**：后台 worker 完成后，回调访问已被 `_clear_view()` 删除的控件（如表格、图表容器），Qt 报 `RuntimeError: wrapped C/C++ object has been deleted`。
- **修复**：
  1. 每次 `_render_xxx` 时自增一个 token，worker 回调先校验 token 是否过期，过期则直接 return。
  2. 渲染函数内部用 `try/except RuntimeError` 兜底，捕获「容器已被删除」静默跳过。

---

## 四、组件与交互

### ISSUE-UI-01 ToggleSwitch 点击开关本体无反应（事件冒泡二次 toggle）

- **现象**：自选股页「自动刷新」开关，点击**开关本体（轨道）**没反应；点右侧文字却偶尔能切换。
- **根因**（已用 QTest 模拟点击确认）：点击轨道触发**两次 toggle，状态抵消**。事件链路：

```
点击轨道 → _TrackWidget.mousePressEvent → clicked.emit() → toggle 一次(False→True)
        → super().mousePressEvent(event) → QWidget 默认 ignore → 事件冒泡给父级
        → ToggleSwitch.mousePressEvent → _toggle() → toggle 第二次(True→False)
```

诊断输出：`events=[True, False] checked=False`（状态弹回，视觉上"没反应"）。

- **修复**：在 `_TrackWidget.mousePressEvent` 中 emit 后 `event.accept()` 阻止冒泡：

```python
def mousePressEvent(self, event):
    if event.button() == Qt.LeftButton:
        self.clicked.emit()
        event.accept()  # 阻止事件冒泡给父级，避免二次 toggle
        return
    super().mousePressEvent(event)
```

- **教训**：自定义 `QWidget` 子控件的 `mousePressEvent` 里，`super().mousePressEvent(event)` 默认会 `ignore()` 导致事件冒泡给父级；若父子都处理同一事件，会重复触发。要么 `accept()` 阻断，要么只在一层处理。

---

### ISSUE-UI-02 QGroupBox.setChecked(False) 不自动折叠内容

- **现象**：可折叠 GroupBox 初始 `setChecked(False)` 后，内部内容仍然显示。
- **根因**：PySide6 某些版本上，`setChecked(False)` 不会自动折叠子内容。
- **修复**：手动连接 `toggled` 信号，显式同步内容 widget 的 `setVisible(checked)`，并在初始化后调用一次确保状态正确。

---

### ISSUE-UI-03 复杂表单弹窗用 QMessageBox 会触发废弃警告

- **现象**：用 `QMessageBox` 承载「添加自选股」表单，`setButtonText` 触发 `DeprecationWarning`。
- **根因**：`QMessageBox.setButtonText(int, str)` 已废弃；且 QMessageBox 不适合嵌入复杂表单布局。
- **修复**：改用 `QDialog` + `QFormLayout` + `QDialogButtonBox`，通过 `accepted/rejected` 信号处理提交与取消，校验失败时拒绝 `accept()`。

---

### ISSUE-UI-04 同一功能分散在多处导致用户困惑（【刷新】按了没动作）

- **现象**：自选股页【刷新】按钮按了"没有任何动作"——表格数据不变、loading 太快看不见；只有【更多→批量在线刷新】才真正从 Baostock 拉取数据。
- **根因**：UI 改造时把原【刷新行情】【批量刷新行情】分成两个入口：
  - 【刷新】按钮（`_on_refresh_quotes`）→ `_schedule_quotes_load` → `CacheOnlyProvider` 只读本地 sqlite（毫秒级完成、数据零变化）
  - 【更多→批量在线刷新】→ `_on_batch_refresh_quotes` → `run_with_progress` 走 Baostock 网络

  表面上"合并到单入口"，实际只搬了菜单位置，**网络刷新被独立留在「更多」**，违背了设计意图。

- **同类问题**：`_on_export_group`（更多→导出本组用于回测）与 `_on_batch_export`（底部→导出回测）功能重复，都是"标记用于回测"，仅数据源不同（全组 vs 勾选）。

- **修复**（2026-08-13）：
  1. `_on_refresh_quotes` 直接调用 `_on_batch_refresh_quotes`，**【刷新】= 唯一从 Baostock 在线拉取行情的入口**；
  2. 删除【更多】菜单里的「批量在线刷新」和「导出本组用于回测」；
  3. 删除「自动刷新」开关（与手动刷新功能重叠，且易制造静默网络流量）；
  4. 修改 `_on_batch_export`：无勾选时导出当前筛选全组（保持"全组导出"能力），有勾选时导出勾选项，**底部「导出回测」= 唯一标记用于回测的入口**。

- **设计原则**：**同样的功能只要一个地方实现**。UI 暴露的每个按钮都必须真有作用；多入口必须合并为单入口。

---

### ISSUE-UI-05 重构时误删"成对操作"导致按钮永远 disabled（【刷新】点不了）

- **现象**：自选股页【刷新】按钮文字是"刷新"（看起来正常）但其实是 disabled 状态（灰化），用户点击没反应。
- **根因**：上一轮重构删除「自动刷新」相关字段时，为了删 `self._is_auto_refreshing` 这个废弃状态，把 `_on_quotes_loaded` 和 `_on_quotes_load_error` 里这一行：

  ```python
  self._refresh_btn.setEnabled(not self._is_auto_refreshing)
  ```

  简化成了 `self._refresh_btn.setText("刷新")`——**漏掉了 `setEnabled(True)`**！

  而 `_schedule_quotes_load` 在加载时仍然调用 `setEnabled(False)` 禁用按钮、加载完后 `_on_quotes_loaded` 应该恢复 enabled，但被误删后**按钮永远是 disabled**，看起来"点了没反应"。

- **诊断过程**：用 QTest 模拟点击 + 检查 `isEnabled()`，发现点击后 `text='刷新'` 但 `isEnabled()=False`——锁定 bug。

- **修复**：在 `_on_quotes_loaded` 和 `_on_quotes_load_error` 的 `if not silent:` 分支里同时恢复 `setEnabled(True)` 和 `setText("刷新")`。

- **教训**：
  1. 重构/删除字段时，要**仔细搜索所有"配对调用"**：`setEnabled(False)` 必有对应的 `setEnabled(True)`，`show()/hide()` 配对，`text/disable` 配对。只删一行留一行的"半重构"很容易出 bug。
  2. UI 状态恢复应该做成**幂等**（无副作用 setEnabled(True)），不应嵌入"未自动刷新时 enabled"这种条件判断——简化掉反而更容易理解。
  3. 重要按钮的状态转换应该写**回归测试**锁住 enabled/text 双状态。

---

## 五、业务逻辑迁移（web → desktop）

> 以下为业务层在迁移/测试中暴露的边界问题，与 UI 框架无关，但会影响桌面端表现。

### ISSUE-BIZ-01 回测 pct_change 首值 NaN

- **现象**：`VectorizedBacktest.run()` 收益率序列首值为 NaN，导致指标计算出错。
- **修复**：`pct_change()` 结果 `fillna(0)`。

### ISSUE-BIZ-02 多股票回测未 set_data 直接 run 报错

- **现象**：`multi_stock_backtest` 未先 `set_data()` 就 `run()` 报错。
- **修复**：调用顺序固定为 **先 `set_data()` 再 `run()`**。

### ISSUE-BIZ-03 StockScore.signal_type 默认值错误

- **现象**：信号类型默认 `""` 导致下游判断异常。
- **修复**：默认值改为 `"hold"`。

### ISSUE-BIZ-04 日期类型不匹配

- **现象**：`df['date']` 是字符串，`all_dates` 是 `Timestamp`，比较/匹配失败。
- **修复**：统一转成字符串后再比较。

### ISSUE-BIZ-05 历史回测数据完整性误判

- **现象**：`_check_data_complete` 在历史回测时误用 `datetime.now()` 判断完整性，导致历史区间被误判缺失。
- **修复**：历史回测时用 **`end_date` 作参考**，不用 `datetime.now()`。

### ISSUE-BIZ-06 仓位分配：买不起 100 股的股票

- **现象**：`position_sizer` 对无法买入 100 股的股票仍分配权重，导致超限。
- **修复**：买不起 100 股的股票**权重直接设为 0**，且**不重新分配**给其他股票（避免连锁超限）。

### ISSUE-BIZ-07 买入仓位检查只算单次金额

- **现象**：`_buy` 仓位检查只看单次买入金额，累计持仓可能超上限。
- **修复**：改为检查**累计持仓**而非单次买入金额。

### ISSUE-BIZ-08 交易明细列名不匹配

- **现象**：`_render_trade_details` 期望英文列名，实际返回中文列名（股票/状态）。
- **修复**：适配实际返回的中文列名。

### ISSUE-BIZ-09 测试用例中修改 sys.stdout 污染 capture

- **现象**：某测试里 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer)`，其后所有用例报 `ValueError: I/O operation on closed file`。
- **根因**：该操作在 pytest 下关闭了 capture 的底层 buffer。
- **修复**：测试中**不要动 `sys.stdout`**。

---

## 附：修复验证流程（通用）

每次修复问题后，遵循以下流程确保生效：

1. **定位根因**：用最小可复现脚本（offscreen + QTest）确认，而非凭猜测。
2. **改代码**：最小改动，聚焦根因。
3. **写回归测试**：把 bug 固化为单元测试，防止再次引入。
4. **跑全量测试**：`python -m pytest tests/`，确认无回归。
