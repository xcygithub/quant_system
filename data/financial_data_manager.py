"""
财务数据管理器 - 对外统一接口
整合数据获取和持久化，提供统一的数据访问接口
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import sqlite3
import time
import warnings
warnings.filterwarnings('ignore')

from .financial_data_source import FinancialDataSource
from .financial_data_saver import FinancialDataSaver


class FinancialDataManager:
    """
    财务数据管理器

    整合数据获取和持久化，提供统一的数据访问接口
    支持增量更新和全量更新
    """

    def __init__(self, db_path: str = None):
        """
        初始化财务数据管理器

        Args:
            db_path: SQLite数据库路径，默认使用 Claw 目录下的 quant_data.db
        """
        if db_path is None:
            from pathlib import Path
            # 与 DataManager 保持一致，使用 Claw 目录下的数据库
            db_path = Path(__file__).parent.parent.parent / "quant_data.db"

        self.db_path = str(db_path)
        self.source = FinancialDataSource(db_path)
        self.saver = FinancialDataSaver(db_path)

    # ========== 单股票操作 ==========

    def update_single_stock(self, symbol: str,
                            data_types: List[str] = None,
                            start_year: int = None) -> Dict[str, int]:
        """
        更新单只股票的财务数据

        Args:
            symbol: 股票代码，如 '000001.SZ'
            data_types: 要更新的数据类型列表
                        如 ['profit', 'balance', 'cash', 'dupont']
            start_year: 起始年份，默认最近3年

        Returns:
            Dict[str, int]: 每种类型的更新记录数
        """
        if data_types is None:
            data_types = ['profit', 'balance', 'cash', 'dupont']

        if start_year is None:
            start_year = datetime.now().year - 3

        results = {}

        print(f"\n{'='*50}")
        print(f"更新 {symbol} 财务数据 (从 {start_year} 年至今)")
        print(f"{'='*50}")

        # 利润表
        if 'profit' in data_types:
            print(f"\n[1/4] 获取利润表数据...")
            df = self.source.get_profit_data(symbol, start_year=start_year)
            count = self.saver.save_profit_data(df, symbol)
            results['profit'] = count
            print(f"    -> 保存 {count} 条记录")

        # 资产负债表
        if 'balance' in data_types:
            print(f"\n[2/4] 获取资产负债表...")
            df = self.source.get_balance_data(symbol, start_year=start_year)
            count = self.saver.save_balance_data(df, symbol)
            results['balance'] = count
            print(f"    -> 保存 {count} 条记录")

        # 现金流量表
        if 'cash' in data_types:
            print(f"\n[3/4] 获取现金流量表...")
            df = self.source.get_cash_flow_data(symbol, start_year=start_year)
            count = self.saver.save_cash_flow_data(df, symbol)
            results['cash'] = count
            print(f"    -> 保存 {count} 条记录")

        # 杜邦分析
        if 'dupont' in data_types:
            print(f"\n[4/4] 获取杜邦分析数据...")
            df = self.source.get_dupont_data(symbol, start_year=start_year)
            count = self.saver.save_dupont_data(df, symbol)
            results['dupont'] = count
            print(f"    -> 保存 {count} 条记录")

        print(f"\n{'='*50}")
        print(f"{symbol} 更新完成")
        print(f"{'='*50}")

        return results

    # ========== 批量更新 ==========

    def batch_update(self, symbols: List[str],
                     data_types: List[str] = None,
                     progress_callback: Callable = None,
                     start_year: int = None) -> Dict[str, int]:
        """
        批量更新多只股票的财务数据

        Args:
            symbols: 股票代码列表
            data_types: 要更新的数据类型
            progress_callback: 进度回调函数 callback(current, total, symbol)
            start_year: 起始年份

        Returns:
            Dict[str, int]: 每种类型的总更新记录数
        """
        if data_types is None:
            data_types = ['profit', 'balance', 'cash', 'dupont']

        total_results = {dt: 0 for dt in data_types}
        total = len(symbols)

        print(f"\n{'='*60}")
        print(f"批量更新 {total} 只股票的财务数据")
        print(f"数据类型: {data_types}")
        print(f"{'='*60}")

        for i, symbol in enumerate(symbols):
            try:
                print(f"\n[{i+1}/{total}] 处理 {symbol}...")
                results = self.update_single_stock(symbol, data_types, start_year)

                for dt, count in results.items():
                    total_results[dt] = total_results.get(dt, 0) + count

                if progress_callback:
                    progress_callback(i + 1, total, symbol)

            except Exception as e:
                print(f"  更新 {symbol} 失败: {e}")
                continue

            # Baostock 限流：每秒1次
            time.sleep(1.1)

        print(f"\n{'='*60}")
        print(f"批量更新完成")
        print(f"总记录数: {total_results}")
        print(f"{'='*60}")

        return total_results

    # ========== 数据查询 ==========

    def get_financial_data(self, symbol: str,
                          data_type: str = 'profit',
                          start_date: str = None,
                          end_date: str = None) -> pd.DataFrame:
        """
        从数据库读取财务数据

        Args:
            symbol: 股票代码
            data_type: 数据类型 ('profit'/'balance'/'cash'/'dupont'/'growth'/'operation'/'debtpaying')
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            DataFrame，按报告期降序排列
        """
        conn = sqlite3.connect(self.db_path)

        table_map = {
            'profit': 'profit_data',
            'balance': 'balance_data',
            'cash': 'cash_flow_data',
            'dupont': 'dupont_data',
            'growth': 'growth_data',
            'operation': 'operation_data',
            'debtpaying': 'debtpaying_data',
        }

        table = table_map.get(data_type, 'profit_data')

        query = f"SELECT * FROM {table} WHERE symbol = ?"
        params = [symbol]

        if start_date:
            query += " AND report_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND report_date <= ?"
            params.append(end_date)

        query += " ORDER BY report_date DESC"

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            print(f"查询财务数据失败: {e}")
            df = pd.DataFrame()

        conn.close()
        return df

    def get_latest_financial(self, symbol: str,
                             data_type: str = 'profit') -> Optional[Dict]:
        """
        获取最新的财务数据

        Args:
            symbol: 股票代码
            data_type: 数据类型

        Returns:
            Dict or None
        """
        df = self.get_financial_data(symbol, data_type)
        if not df.empty:
            return df.iloc[0].to_dict()
        return None

    def get_valuation(self, symbol: str,
                      trade_date: str = None) -> Optional[Dict]:
        """
        获取估值数据

        Args:
            symbol: 股票代码
            trade_date: 交易日期，默认最新

        Returns:
            Dict or None
        """
        conn = sqlite3.connect(self.db_path)

        if trade_date:
            query = '''
                SELECT * FROM valuation_data
                WHERE symbol = ? AND trade_date = ?
                ORDER BY trade_date DESC LIMIT 1
            '''
            df = pd.read_sql_query(query, conn, params=(symbol, trade_date))
        else:
            query = '''
                SELECT * FROM valuation_data
                WHERE symbol = ?
                ORDER BY trade_date DESC LIMIT 1
            '''
            df = pd.read_sql_query(query, conn, params=(symbol,))

        conn.close()

        if not df.empty:
            return df.iloc[0].to_dict()
        return None

    def get_valuation_multi(self, symbols: List[str] = None,
                            trade_date: str = None) -> pd.DataFrame:
        """
        获取多只股票的估值数据

        Args:
            symbols: 股票代码列表，None 表示全部
            trade_date: 交易日期，默认最新

        Returns:
            DataFrame
        """
        conn = sqlite3.connect(self.db_path)

        if trade_date:
            if symbols:
                placeholders = ','.join(['?' for _ in symbols])
                query = f'''
                    SELECT * FROM valuation_data
                    WHERE symbol IN ({placeholders}) AND trade_date = ?
                    ORDER BY trade_date DESC, symbol
                '''
                params = symbols + [trade_date]
            else:
                query = '''
                    SELECT * FROM valuation_data
                    WHERE trade_date = ?
                    ORDER BY symbol
                '''
                params = [trade_date]
        else:
            if symbols:
                placeholders = ','.join(['?' for _ in symbols])
                query = f'''
                    SELECT * FROM valuation_data
                    WHERE symbol IN ({placeholders})
                    AND trade_date = (SELECT MAX(trade_date) FROM valuation_data WHERE symbol = valuation_data.symbol)
                    ORDER BY symbol
                '''
                params = symbols
            else:
                query = '''
                    SELECT * FROM valuation_data v1
                    WHERE trade_date = (SELECT MAX(trade_date) FROM valuation_data WHERE symbol = v1.symbol)
                    ORDER BY symbol
                '''
                params = []

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            print(f"查询估值数据失败: {e}")
            df = pd.DataFrame()

        conn.close()
        return df

    # ========== 估值全量更新 ==========

    def update_all_valuations(self, trade_date: str = None) -> int:
        """
        更新所有股票的估值数据

        Args:
            trade_date: 交易日期，默认今天

        Returns:
            更新记录数
        """
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        print(f"\n{'='*50}")
        print(f"更新全市场估值数据 ({trade_date})")
        print(f"{'='*50}")

        df = self.source.get_all_stocks_valuation()

        if df.empty:
            print("获取失败")
            return 0

        print(f"获取到 {len(df)} 只股票的估值数据")
        print("保存到数据库...")

        count = self.saver.save_valuation_data(df, trade_date)
        print(f"保存 {count} 条记录")
        print(f"{'='*50}")

        return count

    # ========== 数据新鲜度检查 ==========

    def is_data_fresh(self, symbol: str, table: str = 'profit_data',
                      max_age_days: int = 120) -> bool:
        """
        检查数据是否足够新鲜

        Args:
            symbol: 股票代码
            table: 表名
            max_age_days: 最大允许天数（默认120天约2个季度）

        Returns:
            bool
        """
        conn = sqlite3.connect(self.db_path)

        query = f'''
            SELECT MAX(report_date) FROM {table}
            WHERE symbol = ?
        '''
        try:
            df = pd.read_sql_query(query, conn, params=(symbol,))
        except:
            conn.close()
            return False

        if df.empty or df.iloc[0, 0] is None:
            conn.close()
            return False

        try:
            latest_date = datetime.strptime(str(df.iloc[0, 0]), '%Y-%m-%d')
            age_days = (datetime.now() - latest_date).days
        except:
            conn.close()
            return False

        conn.close()
        return age_days <= max_age_days

    def get_data_freshness(self, symbol: str) -> Dict[str, Dict]:
        """
        获取股票各财务数据的最新日期和新鲜度

        Args:
            symbol: 股票代码

        Returns:
            Dict[表名, {'latest_date': str, 'age_days': int, 'is_fresh': bool}]
        """
        tables = ['profit_data', 'balance_data', 'cash_flow_data', 'dupont_data']
        result = {}

        conn = sqlite3.connect(self.db_path)

        for table in tables:
            query = f'''
                SELECT MAX(report_date) FROM {table}
                WHERE symbol = ?
            '''
            try:
                df = pd.read_sql_query(query, conn, params=(symbol,))
                if df.empty or df.iloc[0, 0] is None:
                    result[table] = {'latest_date': None, 'age_days': None, 'is_fresh': False}
                else:
                    latest_date = str(df.iloc[0, 0])
                    age_days = (datetime.now() - datetime.strptime(latest_date, '%Y-%m-%d')).days
                    result[table] = {
                        'latest_date': latest_date,
                        'age_days': age_days,
                        'is_fresh': age_days <= 120
                    }
            except:
                result[table] = {'latest_date': None, 'age_days': None, 'is_fresh': False}

        conn.close()
        return result

    # ========== 便捷方法 ==========

    def get_profit(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取利润表数据"""
        return self.get_financial_data(symbol, 'profit', start_date)

    def get_balance(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取资产负债表数据"""
        return self.get_financial_data(symbol, 'balance', start_date)

    def get_cash_flow(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取现金流量表数据"""
        return self.get_financial_data(symbol, 'cash', start_date)

    def get_dupont(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取杜邦分析数据"""
        return self.get_financial_data(symbol, 'dupont', start_date)

    # ========== 资源清理 ==========

    def close(self):
        """关闭连接"""
        self.source.logout()

    def __del__(self):
        """析构时确保关闭"""
        try:
            self.close()
        except:
            pass


# ========== 便捷函数 ==========

def update_stock_financial(symbol: str,
                           data_types: List[str] = None) -> Dict[str, int]:
    """
    便捷函数：更新单只股票财务数据

    Args:
        symbol: 股票代码
        data_types: 数据类型列表

    Returns:
        更新记录数
    """
    manager = FinancialDataManager()
    result = manager.update_single_stock(symbol, data_types)
    manager.close()
    return result


def get_stock_profit(symbol: str, start_date: str = None) -> pd.DataFrame:
    """便捷函数：获取利润表"""
    manager = FinancialDataManager()
    df = manager.get_profit(symbol, start_date)
    manager.close()
    return df


def get_stock_valuation(symbol: str) -> Optional[Dict]:
    """便捷函数：获取估值数据"""
    manager = FinancialDataManager()
    val = manager.get_valuation(symbol)
    manager.close()
    return val


if __name__ == "__main__":
    # 测试财务数据管理器
    print("=" * 60)
    print("测试 FinancialDataManager")
    print("=" * 60)

    manager = FinancialDataManager()

    # 测试更新单只股票
    print("\n[测试] 更新 000001.SZ 财务数据...")
    results = manager.update_single_stock('000001.SZ', ['profit', 'balance', 'cash', 'dupont'])
    print(f"更新结果: {results}")

    # 测试读取数据
    print("\n[测试] 读取利润表...")
    df = manager.get_profit('000001.SZ')
    if not df.empty:
        print(f"获取 {len(df)} 条记录")
        print(df.head())

    # 测试估值数据
    print("\n[测试] 读取估值数据...")
    val = manager.get_valuation('000001.SZ')
    if val:
        print(f"PE: {val.get('pe')}, PB: {val.get('pb')}")

    # 测试数据新鲜度
    print("\n[测试] 检查数据新鲜度...")
    freshness = manager.get_data_freshness('000001.SZ')
    for table, info in freshness.items():
        print(f"  {table}: {info}")

    manager.close()
    print("\n测试完成")
