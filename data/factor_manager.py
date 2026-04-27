"""
因子数据管理器 - 因子数据管理（读写）

职责：
- 因子元数据管理（factor_metadata 表）
- 因子值存储（factor_values 表）
- 财务因子缓存（factor_cache 表）
- IC分析结果（ic_analysis, ic_statistics 表）

不包含：
- 因子计算逻辑（由 FactorPipeline 等模块负责）
- 网络请求（由数据源模块负责）
"""
import pandas as pd
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime


class FactorManager:
    """
    因子数据管理器

    负责因子的存储和读取，不负责计算。
    """

    def __init__(self, db_path: str):
        """
        初始化因子管理器

        Args:
            db_path: SQLite数据库路径
        """
        self.db_path = db_path

    # ========== 因子元数据 ==========

    def get_factor_metadata(self, factor_name: str = None) -> pd.DataFrame:
        """
        获取因子元数据

        Args:
            factor_name: 因子名称（可选，不传则获取全部）

        Returns:
            DataFrame
        """
        conn = sqlite3.connect(self.db_path)

        if factor_name:
            query = "SELECT * FROM factor_metadata WHERE factor_name = ?"
            df = pd.read_sql_query(query, conn, params=(factor_name,))
        else:
            query = "SELECT * FROM factor_metadata ORDER BY factor_category, factor_name"
            df = pd.read_sql_query(query, conn)

        conn.close()
        return df

    def save_factor_metadata(
        self,
        factor_name: str,
        factor_category: str,
        factor_direction: str,
        description: str = None,
        formula: str = None
    ) -> bool:
        """
        保存因子元数据

        Args:
            factor_name: 因子名称
            factor_category: 因子类别
            factor_direction: 因子方向 (positive/negative/neutral)
            description: 描述
            formula: 计算公式

        Returns:
            bool: 是否成功
        """
        conn = sqlite3.connect(self.db_path)
        query = """
            INSERT OR REPLACE INTO factor_metadata
            (factor_name, factor_category, factor_direction, description, formula, update_time)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            cursor = conn.cursor()
            cursor.execute(query, (factor_name, factor_category, factor_direction, description, formula))
            conn.commit()
            return True
        except Exception as e:
            print(f"[FactorManager] 保存因子元数据失败: {e}")
            return False
        finally:
            conn.close()

    def get_factor_categories(self) -> List[str]:
        """
        获取所有因子类别

        Returns:
            List[str]: 类别列表
        """
        conn = sqlite3.connect(self.db_path)
        query = "SELECT DISTINCT factor_category FROM factor_metadata ORDER BY factor_category"
        try:
            df = pd.read_sql_query(query, conn)
            return df['factor_category'].tolist()
        except:
            return []
        finally:
            conn.close()

    # ========== 因子值 ==========

    def save_factor_values(
        self,
        df: pd.DataFrame,
        symbol: str = None
    ) -> int:
        """
        保存因子值

        Args:
            df: DataFrame，包含 symbol, trade_date, factor_name, factor_value 列
            symbol: 股票代码（可选，如果 df 中没有）

        Returns:
            int: 保存的记录数
        """
        if df.empty:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 确保必要的列存在
        required_cols = ['symbol', 'trade_date', 'factor_name', 'factor_value']
        if not all(col in df.columns for col in required_cols):
            print(f"[FactorManager] 数据缺少必要列: {required_cols}")
            conn.close()
            return 0

        saved_count = 0
        try:
            cursor.execute("BEGIN TRANSACTION")
            for _, row in df.iterrows():
                cursor.execute("""
                    DELETE FROM factor_values
                    WHERE symbol = ? AND trade_date = ? AND factor_name = ?
                """, (row['symbol'], row['trade_date'], row['factor_name']))

                cursor.execute("""
                    INSERT INTO factor_values
                    (symbol, trade_date, factor_name, factor_value, update_time)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (row['symbol'], row['trade_date'], row['factor_name'], row['factor_value']))
                saved_count += 1
            cursor.execute("COMMIT")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"[FactorManager] 保存因子值失败: {e}")
            saved_count = 0
        finally:
            conn.close()

        return saved_count

    def get_factor_values(
        self,
        symbol: str,
        factor_name: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取因子值

        Args:
            symbol: 股票代码
            factor_name: 因子名称（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            DataFrame
        """
        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM factor_values WHERE symbol = ?"
        params = [symbol]

        if factor_name:
            query += " AND factor_name = ?"
            params.append(factor_name)

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date"

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            print(f"[FactorManager] 获取因子值失败: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def get_factor_matrix(
        self,
        symbols: List[str],
        factor_names: List[str],
        trade_date: str
    ) -> pd.DataFrame:
        """
        获取因子截面数据矩阵

        Args:
            symbols: 股票代码列表
            factor_names: 因子名称列表
            trade_date: 交易日期

        Returns:
            DataFrame: pivot 后的因子值矩阵
        """
        if not symbols or not factor_names:
            return pd.DataFrame()

        conn = sqlite3.connect(self.db_path)

        placeholders = ','.join(['?' for _ in symbols])
        factor_placeholders = ','.join(['?' for _ in factor_names])

        query = f"""
            SELECT symbol, factor_name, factor_value
            FROM factor_values
            WHERE symbol IN ({placeholders})
              AND factor_name IN ({factor_placeholders})
              AND trade_date = ?
            ORDER BY symbol, factor_name
        """
        params = symbols + factor_names + [trade_date]

        try:
            df = pd.read_sql_query(query, conn, params=params)
            if not df.empty:
                # pivot 成宽表
                df = df.pivot(index='symbol', columns='factor_name', values='factor_value')
                df = df.reset_index()
        except Exception as e:
            print(f"[FactorManager] 获取因子矩阵失败: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    # ========== IC 分析 ==========

    def save_ic_result(
        self,
        factor_name: str,
        trade_date: str,
        ic_value: float,
        ic_rank: float = None,
        forward_return: float = None,
        sample_count: int = None
    ) -> bool:
        """
        保存 IC 分析结果

        Args:
            factor_name: 因子名称
            trade_date: 交易日期
            ic_value: IC 值
            ic_rank: RankIC 值
            forward_return: 前向收益
            sample_count: 样本数量

        Returns:
            bool
        """
        conn = sqlite3.connect(self.db_path)
        query = """
            INSERT OR REPLACE INTO ic_analysis
            (factor_name, trade_date, ic_value, ic_rank, forward_return, sample_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            cursor = conn.cursor()
            cursor.execute(query, (factor_name, trade_date, ic_value, ic_rank, forward_return, sample_count))
            conn.commit()
            return True
        except Exception as e:
            print(f"[FactorManager] 保存 IC 结果失败: {e}")
            return False
        finally:
            conn.close()

    def get_ic_series(
        self,
        factor_name: str,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取 IC 时间序列

        Args:
            factor_name: 因子名称
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame，按日期升序
        """
        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM ic_analysis WHERE factor_name = ?"
        params = [factor_name]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date"

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            print(f"[FactorManager] 获取 IC 序列失败: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def save_ic_statistics(
        self,
        factor_name: str,
        ic_mean: float,
        ic_std: float,
        ir: float,
        ic_positive_ratio: float,
        latest_ic: float = None
    ) -> bool:
        """
        保存 IC 统计信息

        Args:
            factor_name: 因子名称
            ic_mean: IC 均值
            ic_std: IC 标准差
            ir: IR (IC_mean / IC_std)
            ic_positive_ratio: IC 为正的比例
            latest_ic: 最新 IC 值

        Returns:
            bool
        """
        conn = sqlite3.connect(self.db_path)
        query = """
            INSERT OR REPLACE INTO ic_statistics
            (factor_name, ic_mean, ic_std, ir, ic_positive_ratio, latest_ic, update_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            cursor = conn.cursor()
            cursor.execute(query, (
                factor_name, ic_mean, ic_std, ir, ic_positive_ratio, latest_ic,
                datetime.now().strftime('%Y-%m-%d')
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"[FactorManager] 保存 IC 统计失败: {e}")
            return False
        finally:
            conn.close()

    def get_ic_statistics(self, factor_name: str = None) -> pd.DataFrame:
        """
        获取 IC 统计信息

        Args:
            factor_name: 因子名称（可选）

        Returns:
            DataFrame
        """
        conn = sqlite3.connect(self.db_path)

        if factor_name:
            query = "SELECT * FROM ic_statistics WHERE factor_name = ?"
            df = pd.read_sql_query(query, conn, params=(factor_name,))
        else:
            query = "SELECT * FROM ic_statistics ORDER BY ir DESC"
            df = pd.read_sql_query(query, conn)

        conn.close()
        return df

    # ========== 财务因子缓存 ==========

    def save_factor_cache(
        self,
        df: pd.DataFrame
    ) -> int:
        """
        保存财务因子缓存

        Args:
            df: DataFrame，包含 symbol, trade_date, factor_name, factor_value

        Returns:
            int: 保存的记录数
        """
        if df.empty:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        required_cols = ['symbol', 'trade_date', 'factor_name', 'factor_value']
        if not all(col in df.columns for col in required_cols):
            print(f"[FactorManager] 数据缺少必要列")
            conn.close()
            return 0

        saved_count = 0
        try:
            cursor.execute("BEGIN TRANSACTION")
            for _, row in df.iterrows():
                cursor.execute("""
                    DELETE FROM factor_cache
                    WHERE symbol = ? AND trade_date = ? AND factor_name = ?
                """, (row['symbol'], row['trade_date'], row['factor_name']))

                cursor.execute("""
                    INSERT INTO factor_cache
                    (symbol, trade_date, factor_name, factor_value, update_time)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (row['symbol'], row['trade_date'], row['factor_name'], row['factor_value']))
                saved_count += 1
            cursor.execute("COMMIT")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"[FactorManager] 保存因子缓存失败: {e}")
            saved_count = 0
        finally:
            conn.close()

        return saved_count

    def get_factor_cache(
        self,
        symbol: str,
        factor_name: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        获取财务因子缓存

        Args:
            symbol: 股票代码
            factor_name: 因子名称（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            DataFrame
        """
        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM factor_cache WHERE symbol = ?"
        params = [symbol]

        if factor_name:
            query += " AND factor_name = ?"
            params.append(factor_name)

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date"

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            print(f"[FactorManager] 获取因子缓存失败: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df


if __name__ == "__main__":
    # 测试
    from config import DATABASE_PATH

    fm = FactorManager(str(DATABASE_PATH))

    print("测试 FactorManager:")

    # 测试因子元数据
    meta = fm.get_factor_metadata()
    print(f"  因子元数据: {len(meta)} 条")

    # 测试因子类别
    cats = fm.get_factor_categories()
    print(f"  因子类别: {cats}")

    # 测试 IC 统计
    ic_stats = fm.get_ic_statistics()
    print(f"  IC 统计: {len(ic_stats)} 条")