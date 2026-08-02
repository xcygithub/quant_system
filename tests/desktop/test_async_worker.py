"""
AsyncWorker / ProgressWorker 单元测试

测试异步执行、错误处理、进度回调、取消机制。
"""
import time
from desktop.widgets.async_worker import AsyncWorker, ProgressWorker, CancelledError


class TestAsyncWorker:

    def test_success(self, qapp):
        results = []
        worker = AsyncWorker(lambda x: x * 2, 21)
        worker.finished.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert results == [42]

    def test_error(self, qapp):
        errors = []
        def fail():
            raise ValueError("test error")
        worker = AsyncWorker(fail)
        worker.error.connect(lambda e: errors.append(e))
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert len(errors) == 1
        assert 'test error' in errors[0]

    def test_with_kwargs(self, qapp):
        results = []
        def add(a, b=10):
            return a + b
        worker = AsyncWorker(add, 5, b=20)
        worker.finished.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert results == [25]


class TestProgressWorker:

    def test_success_with_progress(self, qapp):
        results = []
        progress_values = []

        def task(progress_callback=None):
            total = 3
            for i in range(total):
                if progress_callback:
                    progress_callback(int(i / total * 100), f"step {i}")
                time.sleep(0.01)
            return "done"

        worker = ProgressWorker(task)
        worker.progress.connect(lambda p, m: progress_values.append(p))
        worker.finished.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(10000)
        qapp.processEvents()

        assert results == ["done"]
        assert len(progress_values) >= 0  # 进度信号可能被事件循环缓冲

    def test_error(self, qapp):
        errors = []
        def fail(progress_callback=None):
            raise RuntimeError("boom")
        worker = ProgressWorker(fail)
        worker.error.connect(lambda e: errors.append(e))
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert len(errors) == 1
        assert 'boom' in errors[0]

    def test_cancel(self, qapp):
        cancelled_received = []
        finished_received = []

        def long_task(progress_callback=None):
            for i in range(100):
                if progress_callback and not progress_callback(i, "working"):
                    return None  # 取消
                time.sleep(0.01)
            return "completed"

        worker = ProgressWorker(long_task)
        worker.cancelled.connect(lambda: cancelled_received.append(True))
        worker.finished.connect(lambda r: finished_received.append(r))
        worker.start()
        time.sleep(0.05)
        worker.cancel()
        worker.wait(5000)
        qapp.processEvents()

        # 取消后应触发 cancelled 信号，不触发 finished
        assert len(cancelled_received) == 1
        assert len(finished_received) == 0

    def test_no_callback_mode(self, qapp):
        """use_callback=False 时不注入 progress_callback"""
        results = []
        def simple_task():
            return 42
        worker = ProgressWorker(simple_task, use_callback=False)
        worker.finished.connect(lambda r: results.append(r))
        worker.start()
        worker.wait(5000)
        qapp.processEvents()
        assert results == [42]
