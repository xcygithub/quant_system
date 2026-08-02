"""
sqlite 连接泄漏回归测试

背景：`FundamentalFactors.get_report_publish_date()` 早期把 `conn.close()`
写在 try 内部，异常又被 `except Exception: pass` 吞掉。只要查询失败
（例如老库的 profit_data 没有 pub_date 列），每次调用都会泄漏一个连接：

- 长驻的桌面客户端里连接数会持续累积；
- Windows 下临时 db 文件被占用，测试 teardown 的 os.remove 直接
  PermissionError [WinError 32]，并连带污染后续所有用例。

本测试用 factory 子类跟踪 connect/close 配对，确保调用后无残留连接。
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.fundamental_factors import FundamentalFactors


def _make_db_without_pub_date() -> str:
    """构造一个 profit_data 缺少 pub_date 列的老版本数据库"""
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        """
        CREATE TABLE profit_data (
            symbol TEXT,
            report_date TEXT,
            roe REAL
        )
        """
    )
    conn.execute("INSERT INTO profit_data VALUES ('AAA', '2023-12-31', 0.15)")
    conn.commit()
    conn.close()
    return tmp.name


class _ConnTracker:
    """跟踪 sqlite3.connect / close 配对"""

    def __init__(self):
        self.open_ids = set()
        self._orig = sqlite3.connect
        tracker = self

        class TrackedConn(sqlite3.Connection):
            def close(self):
                tracker.open_ids.discard(id(self))
                return super().close()

        self._factory = TrackedConn

    def __enter__(self):
        def _connect(*args, **kwargs):
            kwargs.setdefault('factory', self._factory)
            conn = self._orig(*args, **kwargs)
            self.open_ids.add(id(conn))
            return conn

        sqlite3.connect = _connect
        return self

    def __exit__(self, *exc):
        sqlite3.connect = self._orig
        return False


def test_get_report_publish_date_no_conn_leak_on_query_error():
    """查询失败（缺列）时也必须关闭连接"""
    db_path = _make_db_without_pub_date()
    try:
        ff = FundamentalFactors(db_path=db_path)
        with _ConnTracker() as tracker:
            for _ in range(5):
                # 缺少 pub_date 列 -> 查询抛异常 -> 走 fallback 分支
                result = ff.get_report_publish_date('AAA', '2023-12-31', lag_days=45)
                assert result == '2024-02-14'      # 2023-12-31 + 45 天
            assert not tracker.open_ids, (
                f'泄漏了 {len(tracker.open_ids)} 个 sqlite 连接'
            )
        ff.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)          # 有泄漏时 Windows 会 PermissionError


def test_temp_db_removable_after_factor_panel():
    """回归：计算因子面板后临时库必须能被删除（Windows 文件锁）"""
    db_path = _make_db_without_pub_date()
    ff = FundamentalFactors(db_path=db_path)
    try:
        ff.get_report_publish_date('AAA', '2023-12-31')
    finally:
        ff.close()

    os.remove(db_path)                  # 泄漏时这里会抛 PermissionError
    assert not os.path.exists(db_path)
