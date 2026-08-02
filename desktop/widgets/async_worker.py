"""
异步任务基础设施 — 替代 st.spinner / st.progress

提供：
- AsyncWorker: 简单异步任务（QThread），无进度反馈
- ProgressWorker: 带进度回调 + 取消支持的异步任务
- run_with_progress: 一行调用启动任务 + 显示进度对话框
- CancelledError: 取消异常

设计依据：web 层有 13 处 st.spinner + 5 处 st.progress，
包裹的耗时操作包括行情加载、回测运行、信号扫描、数据获取等。
"""
import logging
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QProgressDialog

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    """任务被用户取消"""
    pass


# ---------------------------------------------------------------------------
# 活跃 worker 注册表
#
# QThread 在运行期间若被 Python 垃圾回收，Qt 会直接 abort 整个进程
# （"QThread: Destroyed while thread is still running"），且不产生 Python 异常，
# 排查成本极高。调用方很容易把 worker 写成局部变量而踩中此坑，
# 因此在基础设施层统一持有强引用，线程结束后自动释放。
# ---------------------------------------------------------------------------
_ACTIVE_WORKERS = set()


def _sweep_workers():
    """回收已结束的 worker 引用"""
    for w in list(_ACTIVE_WORKERS):
        try:
            if w.isFinished():
                _ACTIVE_WORKERS.discard(w)
        except RuntimeError:
            # 底层 C++ 对象已被销毁
            _ACTIVE_WORKERS.discard(w)


def active_worker_count():
    """当前仍被持有的 worker 数量（供测试与调试使用）"""
    _sweep_workers()
    return len(_ACTIVE_WORKERS)


def shutdown_workers(timeout_ms=3000):
    """请求所有活跃 worker 结束并等待，供应用退出时调用"""
    for w in list(_ACTIVE_WORKERS):
        try:
            if hasattr(w, "cancel"):
                w.cancel()
        except RuntimeError:
            continue
    for w in list(_ACTIVE_WORKERS):
        try:
            if w.isRunning():
                w.wait(timeout_ms)
        except RuntimeError:
            pass
    _ACTIVE_WORKERS.clear()


class _WorkerRetainMixin:
    """让 worker 在运行期间自持强引用，避免被 GC 掉导致进程 abort"""

    def _install_retain(self):
        # finished / error / cancelled 均在子线程发出，
        # 经队列连接投递到主线程后再触发回收
        for sig_name in ("finished", "error", "cancelled"):
            sig = getattr(self, sig_name, None)
            if sig is not None:
                sig.connect(self._schedule_release)

    def _schedule_release(self, *_args):
        # 此刻 run() 刚发完信号、线程尚未完全退出，延后一拍再回收
        QTimer.singleShot(0, _sweep_workers)
        QTimer.singleShot(200, _sweep_workers)

    def start(self, *args, **kwargs):
        _sweep_workers()
        _ACTIVE_WORKERS.add(self)
        super().start(*args, **kwargs)


class AsyncWorker(_WorkerRetainMixin, QThread):
    """简单异步任务执行器

    在子线程中执行任意函数，通过信号通知结果。
    替代 st.spinner 的阻塞式调用。

    启动后 worker 会被内部注册表自动持有，线程结束后释放，
    因此调用方即使把它写成局部变量也不会导致进程崩溃。

    Signals:
        finished(object): 任务完成，携带返回值
        error(str): 任务出错，携带错误信息

    Usage:
        worker = AsyncWorker(fetch_data, symbol)
        worker.finished.connect(self._on_done)
        worker.error.connect(self._on_error)
        worker.start()
    """
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, func, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._install_retain()

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            logger.exception("AsyncWorker 执行失败")
            self.error.emit(str(e))


class ProgressWorker(_WorkerRetainMixin, QThread):
    """带进度回调的异步任务执行器

    支持进度反馈和取消。func 可接受可选的 progress_callback 参数。

    progress_callback 签名: (percent: int, message: str) -> bool
        返回 False 表示用户已取消，func 应停止执行。

    Signals:
        progress(int, str): 进度百分比(0-100), 状态消息
        finished(object): 任务完成
        error(str): 任务出错
        cancelled(): 任务被用户取消

    Usage:
        def fetch(symbols, progress_callback=None):
            for i, s in enumerate(symbols):
                if progress_callback and not progress_callback(
                    int(i/len(symbols)*100), f"加载 {s}..."
                ):
                    return None  # 取消
                load(s)
            return results

        worker = ProgressWorker(fetch, symbols)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_done)
        worker.start()
    """
    progress = Signal(int, str)
    finished = Signal(object)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, func, *args, parent=None, use_callback=True, **kwargs):
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._use_callback = use_callback
        self._cancelled = False
        self._install_retain()

    def cancel(self):
        """请求取消任务（设置标志，由 func 通过 callback 检查）"""
        self._cancelled = True

    @property
    def is_cancelled(self):
        return self._cancelled

    def run(self):
        try:
            if self._use_callback:
                # 注入 progress_callback
                def progress_callback(percent, message=""):
                    if self._cancelled:
                        return False
                    self.progress.emit(int(percent), message)
                    return True

                result = self._func(
                    *self._args,
                    progress_callback=progress_callback,
                    **self._kwargs
                )
            else:
                result = self._func(*self._args, **self._kwargs)

            if self._cancelled:
                self.cancelled.emit()
            else:
                self.finished.emit(result)
        except CancelledError:
            self.cancelled.emit()
        except Exception as e:
            logger.exception("ProgressWorker 执行失败")
            self.error.emit(str(e))


def run_with_progress(parent, func, *args, title="处理中", message="请稍候...",
                      cancelable=True, auto_close=True, minimum_duration=500,
                      use_callback=True, **kwargs):
    """启动异步任务并显示模态进度对话框

    一行调用替代 st.spinner / st.progress 的常见用法。

    Args:
        parent: 父窗口
        func: 要执行的函数（若 use_callback=True，func 需接受 progress_callback 参数）
        title: 进度对话框标题
        message: 初始消息
        cancelable: 是否可取消
        auto_close: 完成后是否自动关闭对话框
        minimum_duration: 对话框出现前的最小延迟(ms)，短任务不弹窗
        use_callback: 是否向 func 注入 progress_callback
        *args, **kwargs: 传给 func 的参数

    Returns:
        ProgressWorker 实例（可用于连接 finished/error 信号）

    Usage:
        worker = run_with_progress(
            self, fetch_stock_data, symbol,
            title="加载数据", message=f"正在加载 {symbol}...",
        )
        worker.finished.connect(self._on_data_loaded)
        worker.error.connect(self._on_error)
    """
    dialog = QProgressDialog(message, "取消" if cancelable else None, 0, 100, parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumDuration(minimum_duration)
    dialog.setAutoClose(auto_close)
    dialog.setAutoReset(True)
    dialog.setMinimumWidth(400)

    worker = ProgressWorker(func, *args, parent=parent,
                            use_callback=use_callback, **kwargs)

    # 进度更新
    def _on_progress(pct, msg):
        dialog.setValue(pct)
        if msg:
            dialog.setLabelText(msg)
    worker.progress.connect(_on_progress)

    # 完成后关闭
    def _on_finished(_result):
        if auto_close:
            dialog.setValue(100)
            dialog.close()
    worker.finished.connect(_on_finished)

    def _on_error(_err):
        if auto_close:
            dialog.close()
    worker.error.connect(_on_error)

    def _on_cancelled():
        dialog.close()
    worker.cancelled.connect(_on_cancelled)

    # 用户点取消
    if cancelable:
        dialog.canceled.connect(worker.cancel)

    worker.start()
    return worker
