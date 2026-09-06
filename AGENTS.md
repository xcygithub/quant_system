# AGENTS.md — 量化系统 Vibe Coding 规则

> 本文件是给 AI（vibe coding）工具的项目级规则。按优先级执行：铁律 > 架构 > 量化正确性 > 数据一致性 > 工程治理 > 完成标准。

## 项目速览

- 项目：本地量化研究系统（Python + Streamlit Web / PySide6 桌面端双端）
- 数据库：本地 SQLite `quant_data.db`（项目根目录）
- 数据源：**只保留 Baostock > CSV 两种**
- 分层：`web/ desktop/`（展示）→ `portfolio/`（业务）→ `strategy/ data/factor_data`（策略/因子）→ `data/`（数据）

---

## 一、铁律（违反直接打回）

1. **改完必须验证，验证通过才算完成。** 任何代码改动后必须：
   - 跑全量测试 `python -m pytest tests/`，必须 `0 failed`；
   - 涉及 GUI 的改动必须在完整组件/真机（或 `QT_QPA_PLATFORM=offscreen`）下实例化跑一遍，不能只看 isolated 单元测试通过。
2. **数据源只允许 Baostock > CSV。** 不引入其他数据源；优先读本地 `quant_data.db`，缺了再走 Baostock。
3. **回测链路禁止把网络请求耦合进执行过程。** 回测/因子准备优先走本地缓存（`CacheOnlyProvider`）；在线抓取只在用户显式触发时发生。
4. **只做当前任务要求的最小改动。** 不顺手"优化"无关代码，不删除看起来没用的东西（很可能有配对调用或隐藏依赖）。

---

## 二、架构与分层规则

5. **严格单向依赖，不跨层调用：**
   `web/ desktop/`（展示）→ `portfolio/`（业务）→ `strategy/ data/factor_data`（策略/因子）→ `data/`（数据）
   - 展示层不放业务逻辑，业务逻辑下沉到 `portfolio/` 或 `web/services/`。
   - 数据层不 import 业务层、展示层。
6. **职责分离：** 在线获取和本地读取分离；因子计算、数据存取、回测执行、结果展示各归其位。
7. **同样的功能只有一个实现、一个入口。** UI 暴露的每个按钮都必须真有作用；多入口必须合并成单入口。
8. **状态操作用幂等写法，成对操作必须成对处理。** `setEnabled(False)` 必有对应 `setEnabled(True)`，`show()/hide()` 配对；不要写"半重构"。

---

## 三、量化正确性规则（本项目最容易翻车的部分）

9. **禁止前视偏差（look-ahead bias）。**
   - 财务数据是季度频率、交易日是日频率：必须明确前向填充规则与可用窗口（例如季报只在公告后 T+1 可用），不能把未来财务数据用到历史调仓日。
   - 历史回测判断数据完整性用 `end_date` 作参考，**不用 `datetime.now()`**。
10. **因子口径必须一致，方向必须正确。**
    - 负向因子（PE/PB/部分杠杆指标）在打分时反向处理，避免"高估值反而得分高"。
    - 字段映射、日期语义、正负向方向全局统一；改了因子的计算口径要同步 IC/打分/回测。
11. **禁止用随机/模拟因子跑回测。** 回测必须以真实数据为主，否则结果失真、不可信。
12. **必须考虑交易成本与约束。** 回测默认带手续费 0.0003、印花税 0.001；仓位不超过 `default_max_positions` 和 `default_max_single_position`。
13. **覆盖率/数据完整性必须显式校验。** 多因子回测要校验因子面板覆盖率，覆盖率不足时明确报"缺哪个因子、缺在哪个时间段、怎么处理"，而不是静默失败或输出错误结果。
14. **警惕幸存者偏差。** 股票池应包含已退市/被 ST 的标的（或用明确说明的过滤口径），不能只回测"现在还在"的股票。

---

## 四、数据一致性规则（项目已踩过的坑）

15. **股票代码转换用后缀判断**（`.SH→sh`、`.SZ→sz`），**不能用数字开头判断**。
16. **指数代码不能混淆：** 上证指数 `000001.SH`、深圳成指 `399001.SZ`。
17. **日期类型统一为字符串再比较。** `df['date']` 与 `Timestamp` 混用会静默失配。
18. **数据保存先删除再插入**（避免 UNIQUE 冲突），**不用 `INSERT OR REPLACE`**。
19. **数据完整性估算：** 交易日 ≈ 日历天 × 40%，条数 ≥ 估算 × 0.85 才判完整。
20. **sqlite 连接必须 `try/finally` 关闭**，`close()` 放 `finally`，不能写进可能被 `except: pass` 吞掉的 try 内。
21. **sqlite 连接非线程安全：** 子线程内用 `db_path` 自建 manager，用完关闭，不共享主线程实例。

---

## 五、工程治理规则

22. **入口脚本必须自包含 sys.path 处理。** `main.py` 开头用 `Path(__file__).resolve().parent.parent` 把项目根加入 `sys.path`，兼容 `python xxx.py` 和 `python -m xxx.yyy`。
23. **测试放 `tests/`，必须能被 pytest 稳定收集。**
    - 测试子目录**不要放 `__init__.py`**（避免与项目包名冲突，如 `tests/desktop/` vs `desktop/`）。
    - 带硬编码本地路径、顶层脚本式执行的"测试脚本"要清理或迁移。
    - 测试里**不要动 `sys.stdout`**（会污染 pytest capture）。
24. **调试临时脚本放 `.tmp_check/`（已 gitignore）。** 本机 Windows 没有 `/tmp`，不要写到 `/tmp`。
25. **不提交缓存产物。** `__pycache__`、`.pytest_cache`、`data_cache`、`logs/`、`quant_data.db` 不入库。
26. **配置集中管理。** 路径、数据源、回测默认参数都放 `config.py`，不在业务代码里散落魔法数字。

---

## 六、完成标准（Definition of Done）

27. 每修复一个问题，遵循：**① 精准定位根因（最小复现脚本）→ ② 最小改动聚焦根因 → ③ 写回归测试锁住 bug → ④ 跑全量测试确认无回归。**
28. **GUI 状态联动 + signal cascade 的组件，必须在完整组件/真机下跑完整状态变化**，不能只看 isolated 单测通过。
29. 有跨模块行为变更时，更新 `README.md`、`.workbuddy/memory` 或 `docs/` 里的相关记录，避免经验丢失。
30. 交付时报告：改了什么、为什么、测试结果（`N passed, 0 failed`）、运行时验证结论。

---

## 七、速查表

### 常用验证命令

```bash
python -m pytest tests/                                  # 全量测试
python -m pytest tests/ -q                               # 简洁输出
QT_QPA_PLATFORM=offscreen python -m pytest tests/desktop/  # 桌面端无头验证
streamlit run web/app.py                                 # Web 端
python desktop/main.py                                   # 桌面端
```

### PySide6 项目级坑（必读）

- `Qt.Checked == 2` 是 `False`，必须用 `Qt.Checked.value`；signal 传的是 int，写法 `state == Qt.Checked or state == Qt.Checked.value`。
- QThread 不能只存局部变量（会被 GC 导致进程 abort，EXIT=127 无 traceback），要进活跃 worker 注册表。
- `BasePage` 子类：`_build_content()` 用到的依赖必须在 `super().__init__()` **之前**赋值。
- 小图标按钮别用 QToolButton（会被 theme.qss 全局样式压扁），用 QLabel + mousePressEvent。
- 页面只做编译/导入检查不够，必须在 MainWindow 里真正实例化才能覆盖构造期 bug。

### 回测参数默认值

- 初始资金：1000000；手续费：0.0003；印花税：0.001；最大持仓数：5；单股最大仓位：0.2
- `min_holding_days`：最短持股天数（0=不限制）；`stop_loss`：输入正数如 10，内部存 -0.1，0=不止损
- 交易明细字段名含单位：收益率（%）、买入金额（元）等
