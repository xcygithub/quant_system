"""
K线数据管理器 - 日线/分钟线数据管理（纯读写 + 可选的数据获取）

职责：
- 日线/分钟线数据的数据库读写
- 可选的数据获取（fetch_daily_kline）- 包含完整性检查和保存逻辑
- 不包含网络请求逻辑本身（由 DataSource 提供）

使用说明：
- 读取：get_daily_kline() / get_minute_kline()
- 保存：save_daily_kline() / save_minute_kline()
- 带获取的读取：fetch_daily_kline() - 会触发在线获取和缓存检查
"""
import pandas as pd
import sqlite3
from typing import Optional, TYPE_CHECKING
from pathlib import Path

from .cache_policy import CachePolicy

if TYPE_CHECKING:
    from .data_sources import MultiDataSource


class KlineManager:
    """
    K线数据管理器

    纯数据读写（get_*/save_*）+ 可选的数据获取（fetch_*）。
    数据获取包含完整性检查和保存逻辑，由内部协调完成。
    """

    def __init__(self, db_path: str, data_source: 'MultiDataSource' = None):
        """
        初始化K线管理器

        Args:
            db_path: SQLite数据库路径
            data_source: 可选的多数据源实例，用于 fetch_daily_kline
        """
        self.db_path = db_path
        self._data_source = data_source

    def set_data_source(self, data_source: 'MultiDataSource'):
        """设置数据源（用于 fetch_daily_kline）"""
        self._data_source = data_source

    @property
    def data_source(self) -> 'MultiDataSource':
        """获取数据源，如果未设置则创建一个"""
        if self._data_source is None:
            from .data_sources import MultiDataSource
            self._data_source = MultiDataSource()
        return self._data_source

    # ========== 日线数据读写 ==========

    def get_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        从数据库读取日线数据

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame 包含 OHLCV 数据
        """
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT symbol, date, open, high, low, close, volume, amount,
                   turnover, amplitude, pct_change, change_amount
            FROM daily_kline
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date
        """
        try:
            df = pd.read_sql_query(query, conn, params=(symbol, start_date, end_date))
            return df
        except Exception as e:
            print(f"[KlineManager] 读取 {symbol} 日线数据失败: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def save_daily_kline(self, df: pd.DataFrame) -> int:
        """
        保存日线数据到数据库（先删除再插入）

        Args:
            df: 日线数据 DataFrame

        Returns:
            int: 保存的记录数
        """
        if df.empty:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 定义所有可能的列（与数据库表结构一致）
        all_cols = ['symbol', 'date', 'open', 'high', 'low', 'close',
                   'volume', 'amount', 'turnover', 'amplitude',
                   'pct_change', 'change_amount']

        # 只选择存在的列，并填充缺失的列为0
        existing_cols = [col for col in all_cols if col in df.columns]
        missing_cols = [col for col in all_cols if col not in df.columns]

        save_df = df[existing_cols].copy()

        # 填充缺失的列
        for col in missing_cols:
            save_df[col] = 0.0

        # 确保列顺序一致
        save_df = save_df[all_cols]

        saved_count = 0
        try:
            cursor.execute("BEGIN TRANSACTION")
            for _, row in save_df.iterrows():
                # 先删除已存在的记录
                cursor.execute("""
                    DELETE FROM daily_kline WHERE symbol = ? AND date = ?
                """, (row['symbol'], row['date']))

                # 插入新记录
                cursor.execute("""
                    INSERT INTO daily_kline
                    (symbol, date, open, high, low, close, volume, amount,
                     turnover, amplitude, pct_change, change_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['symbol'], row['date'], row['open'], row['high'], row['low'],
                    row['close'], row['volume'], row['amount'],
                    row.get('turnover', 0), row.get('amplitude', 0),
                    row.get('pct_change', 0), row.get('change_amount', 0)
                ))
                saved_count += 1
            cursor.execute("COMMIT")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"[KlineManager] 保存日线数据失败: {e}")
            saved_count = 0
        finally:
            conn.close()

        return saved_count

    def delete_daily_kline(self, symbol: str, start_date: str, end_date: str) -> int:
        """
        删除指定日期范围的日线数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            int: 删除的记录数
        """
        conn = sqlite3.connect(self.db_path)
        query = """
            DELETE FROM daily_kline
            WHERE symbol = ? AND date BETWEEN ? AND ?
        """
        try:
            cursor = conn.cursor()
            cursor.execute(query, (symbol, start_date, end_date))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        except Exception as e:
            print(f"[KlineManager] 删除 {symbol} 日线数据失败: {e}")
            return 0
        finally:
            conn.close()

    def fetch_daily_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        use_cache_only: bool = False
    ) -> pd.DataFrame:
        """
        获取日线数据（带完整性检查和在线获取）

        流程：
        1. 从数据库读取现有数据
        2. 检查数据完整性（CachePolicy.check_data_complete）
        3. 如果数据不完整，从在线数据源获取
        4. 保存新数据到数据库
        5. 返回数据

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            use_cache_only: 是否只使用缓存（True=不回测时不触发网络请求）

        Returns:
            DataFrame 包含 OHLCV 数据
        """
        import traceback

        try:
            if not symbol or not start_date or not end_date:
                print(f"[KlineManager] 参数错误: symbol={symbol}, start_date={start_date}, end_date={end_date}")
                return pd.DataFrame()

            # 确保日期格式正确
            try:
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
            except Exception as date_err:
                print(f"[KlineManager] 日期格式错误: {date_err}")
                return pd.DataFrame()

            print(f"[KlineManager] 获取 {symbol} 从 {start_date} 到 {end_date} 的数据...")

            # 步骤1：从数据库读取
            df = self.get_daily_kline(symbol, start_date, end_date)

            # 步骤2：检查数据完整性
            if df.empty or not CachePolicy.check_data_complete(df, start_date, end_date):
                if use_cache_only:
                    # 只读缓存模式：返回数据库中的数据（即使不完整）
                    if not df.empty:
                        print(f"[KlineManager] 缓存模式：从数据库返回 {len(df)} 条历史数据")
                    return df

                print(f"[KlineManager] 数据不完整或为空，尝试从在线数据源获取...")

                # 步骤3：从在线数据源获取
                df_online = self.data_source.get_daily_kline(symbol, start_date, end_date)

                if not df_online.empty:
                    # 步骤4：保存到数据库
                    try:
                        saved = self.save_daily_kline(df_online)
                        print(f"[KlineManager] 已保存 {saved} 条新数据到数据库")
                    except Exception as db_err:
                        print(f"[KlineManager] 保存到数据库失败: {db_err}")

                    df = df_online
                else:
                    print(f"[KlineManager] 从所有数据源获取到空数据")
                    if not df.empty:
                        print(f"[KlineManager] 回退使用数据库中的 {len(df)} 条历史数据")
            else:
                print(f"[KlineManager] 从数据库获取到 {len(df)} 条完整数据")

            return df

        except Exception as e:
            print(f"[KlineManager] 获取 {symbol} 日线数据失败: {e}")
            print(f"[KlineManager] 错误详情: {traceback.format_exc()}")
            return pd.DataFrame()

    def get_latest_daily_date(self, symbol: str) -> Optional[str]:
        """
        获取某股票最新的日线日期

        Args:
            symbol: 股票代码

        Returns:
            str or None: 最新日期
        """
        conn = sqlite3.connect(self.db_path)
        query = "SELECT MAX(date) FROM daily_kline WHERE symbol = ?"
        try:
            df = pd.read_sql_query(query, conn, params=(symbol,))
            if df.empty or df.iloc[0, 0] is None:
                return None
            return str(df.iloc[0, 0])
        except:
            return None
        finally:
            conn.close()

    # ========== 分钟线数据读写 ==========

    def get_minute_kline(
        self,
        symbol: str,
        start_datetime: str = None,
        end_datetime: str = None
    ) -> pd.DataFrame:
        """
        从数据库读取分钟线数据

        Args:
            symbol: 股票代码
            start_datetime: 开始时间（可选）
            end_datetime: 结束时间（可选）

        Returns:
            DataFrame 包含分钟 OHLCV 数据
        """
        conn = sqlite3.connect(self.db_path)

        if start_datetime and end_datetime:
            query = """
                SELECT symbol, datetime, open, high, low, close, volume, amount
                FROM minute_kline
                WHERE symbol = ? AND datetime BETWEEN ? AND ?
                ORDER BY datetime
            """
            params = (symbol, start_datetime, end_datetime)
        else:
            query = """
                SELECT symbol, datetime, open, high, low, close, volume, amount
                FROM minute_kline
                WHERE symbol = ?
                ORDER BY datetime
            """
            params = (symbol,)

        try:
            df = pd.read_sql_query(query, conn, params=params)
            return df
        except Exception as e:
            print(f"[KlineManager] 读取 {symbol} 分钟数据失败: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def save_minute_kline(self, df: pd.DataFrame) -> int:
        """
        保存分钟线数据到数据库

        Args:
            df: 分钟线数据 DataFrame

        Returns:
            int: 保存的记录数
        """
        if df.empty:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        all_cols = ['symbol', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']
        existing_cols = [col for col in all_cols if col in df.columns]
        missing_cols = [col for col in all_cols if col not in df.columns]

        save_df = df[existing_cols].copy()
        for col in missing_cols:
            save_df[col] = 0.0
        save_df = save_df[all_cols]

        saved_count = 0
        try:
            cursor.execute("BEGIN TRANSACTION")
            for _, row in save_df.iterrows():
                cursor.execute("""
                    DELETE FROM minute_kline WHERE symbol = ? AND datetime = ?
                """, (row['symbol'], row['datetime']))

                cursor.execute("""
                    INSERT INTO minute_kline
                    (symbol, datetime, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['symbol'], row['datetime'], row['open'], row['high'],
                    row['low'], row['close'], row['volume'], row['amount']
                ))
                saved_count += 1
            cursor.execute("COMMIT")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"[KlineManager] 保存分钟数据失败: {e}")
            saved_count = 0
        finally:
            conn.close()

        return saved_count

    # ========== 便捷方法 ==========

    def has_data(self, symbol: str) -> bool:
        """
        检查是否有任何日线数据

        Args:
            symbol: 股票代码

        Returns:
            bool
        """
        conn = sqlite3.connect(self.db_path)
        query = "SELECT 1 FROM daily_kline WHERE symbol = ? LIMIT 1"
        try:
            df = pd.read_sql_query(query, conn, params=(symbol,))
            return not df.empty
        except:
            return False
        finally:
            conn.close()

    def get_data_count(self, symbol: str) -> int:
        """
        获取日线数据条数

        Args:
            symbol: 股票代码

        Returns:
            int: 数据条数
        """
        conn = sqlite3.connect(self.db_path)
        query = "SELECT COUNT(*) FROM daily_kline WHERE symbol = ?"
        try:
            df = pd.read_sql_query(query, conn, params=(symbol,))
            return int(df.iloc[0, 0]) if not df.empty else 0
        except:
            return 0
        finally:
            conn.close()


if __name__ == "__main__":
    # 测试
    from config import DATABASE_PATH

    km = KlineManager(str(DATABASE_PATH))

    print("测试 KlineManager:")

    # 测试读取
    df = km.get_daily_kline("000001.SZ", "2024-01-01", "2024-01-31")
    print(f"  读取 000001.SZ: {len(df)} 条数据" if not df.empty else "  无数据")

    # 测试最新日期
    latest = km.get_latest_daily_date("000001.SZ")
    print(f"  最新日期: {latest}")

    # 测试数据条数
    count = km.get_data_count("000001.SZ")
    print(f"  数据条数: {count}")