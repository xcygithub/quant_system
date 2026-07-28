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
import logging
warnings.filterwarnings('ignore')

from .financial_data_source import FinancialDataSource
from .financial_data_saver import FinancialDataSaver
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_BENCHMARK_SYMBOLS = {"399001.SZ", "399006.SZ", "000001.SH", "000688.SH"}


def _normalize_symbol(symbol: str) -> str:
    symbol = (symbol or "").strip().upper()
    if ":" in symbol:
        prefix, code = symbol.split(":", 1)
        code = code.strip()
        if prefix == "SH":
            return f"{code}.SH"
        if prefix == "SZ":
            return f"{code}.SZ"
    if symbol.endswith((".SH", ".SZ", ".BJ", ".HK")):
        return symbol
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "1", "2", "3")):
        return f"{symbol}.SZ"
    return f"{symbol}.SZ"


def _is_benchmark_symbol(symbol: str) -> bool:
    return _normalize_symbol(symbol) in _BENCHMARK_SYMBOLS


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
            db_path: SQLite数据库路径，默认使用项目根目录下的 quant_data.db
        """
        if db_path is None:
            # 与 DataManager 保持一致，统一使用全局配置
            db_path = DATABASE_PATH

        self.db_path = str(db_path)
        self.source = FinancialDataSource(db_path)
        self.saver = FinancialDataSaver(db_path)

    # ========== 单股票操作 ==========

    def update_single_stock(self, symbol: str,
                            data_types: List[str] = None,
                            start_year: int = None,
                            end_year: int = None) -> Dict[str, int]:
        """
        更新单只股票的财务数据

        Args:
            symbol: 股票代码，如 '000001.SZ'
            data_types: 要更新的数据类型列表
                        如 ['profit', 'balance', 'cash', 'dupont', 'growth', 'operation', 'debtpaying']
            start_year: 起始年份，默认最近3年

        Returns:
            Dict[str, int]: 每种类型的更新记录数
        """
        if _is_benchmark_symbol(symbol):
            logger.info("跳过指数财务更新: symbol=%s", symbol)
            return {dt: 0 for dt in (data_types or ['profit', 'balance', 'cash', 'dupont', 'growth', 'operation', 'debtpaying'])}

        if data_types is None:
            # 默认更新红框六类财务数据
            data_types = ['profit', 'balance', 'cash', 'dupont', 'growth', 'operation', 'debtpaying']

        if start_year is None:
            # 默认至少覆盖“回测起始年前一年Q3”场景，避免年初因子全0
            start_year = datetime.now().year - 4
        if end_year is None:
            end_year = datetime.now().year

        results = {}

        logger.info(
            "开始更新单股财务数据: symbol=%s start_year=%s end_year=%s data_types=%s",
            symbol, start_year, end_year, data_types
        )

        total_types = len(data_types)
        step = 1

        # 利润表
        if 'profit' in data_types:
            logger.info("更新进度: symbol=%s step=%s/%s data_type=profit", symbol, step, total_types)
            df = self.source.get_profit_data(symbol, start_year=start_year, end_year=end_year)
            count = self.saver.save_profit_data(df, symbol)
            results['profit'] = count
            logger.info("更新完成: symbol=%s data_type=profit saved_rows=%s", symbol, count)
            step += 1

        # 资产负债表
        if 'balance' in data_types:
            logger.info("更新进度: symbol=%s step=%s/%s data_type=balance", symbol, step, total_types)
            df = self.source.get_balance_data(symbol, start_year=start_year, end_year=end_year)
            count = self.saver.save_balance_data(df, symbol)
            results['balance'] = count
            logger.info("更新完成: symbol=%s data_type=balance saved_rows=%s", symbol, count)
            step += 1

        # 现金流量表
        if 'cash' in data_types:
            logger.info("更新进度: symbol=%s step=%s/%s data_type=cash", symbol, step, total_types)
            df = self.source.get_cash_flow_data(symbol, start_year=start_year, end_year=end_year)
            count = self.saver.save_cash_flow_data(df, symbol)
            results['cash'] = count
            logger.info("更新完成: symbol=%s data_type=cash saved_rows=%s", symbol, count)
            step += 1

        # 杜邦分析
        if 'dupont' in data_types:
            logger.info("更新进度: symbol=%s step=%s/%s data_type=dupont", symbol, step, total_types)
            df = self.source.get_dupont_data(symbol, start_year=start_year, end_year=end_year)
            count = self.saver.save_dupont_data(df, symbol)
            results['dupont'] = count
            logger.info("更新完成: symbol=%s data_type=dupont saved_rows=%s", symbol, count)
            step += 1

        # 成长能力
        if 'growth' in data_types:
            logger.info("更新进度: symbol=%s step=%s/%s data_type=growth", symbol, step, total_types)
            df = self.source.get_growth_data(symbol, start_year=start_year, end_year=end_year)
            count = self.saver.save_growth_data(df, symbol)
            results['growth'] = count
            logger.info("更新完成: symbol=%s data_type=growth saved_rows=%s", symbol, count)
            step += 1

        # 营运能力
        if 'operation' in data_types:
            logger.info("更新进度: symbol=%s step=%s/%s data_type=operation", symbol, step, total_types)
            df = self.source.get_operation_data(symbol, start_year=start_year, end_year=end_year)
            count = self.saver.save_operation_data(df, symbol)
            results['operation'] = count
            logger.info("更新完成: symbol=%s data_type=operation saved_rows=%s", symbol, count)
            step += 1

        # 偿债能力
        if 'debtpaying' in data_types:
            logger.info("更新进度: symbol=%s step=%s/%s data_type=debtpaying", symbol, step, total_types)
            df = self.source.get_debtpaying_data(symbol, start_year=start_year, end_year=end_year)
            count = self.saver.save_debtpaying_data(df, symbol)
            results['debtpaying'] = count
            logger.info("更新完成: symbol=%s data_type=debtpaying saved_rows=%s", symbol, count)
            step += 1

        logger.info("单股财务更新完成: symbol=%s results=%s", symbol, results)

        return results

    # ========== 批量更新 ==========

    def batch_update(self, symbols: List[str],
                     data_types: List[str] = None,
                     progress_callback: Callable = None,
                     start_year: int = None,
                     end_year: int = None) -> Dict[str, int]:
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
            # 默认更新红框六类财务数据
            data_types = ['profit', 'balance', 'cash', 'dupont', 'growth', 'operation', 'debtpaying']

        total_results = {dt: 0 for dt in data_types}
        total = len(symbols)

        logger.info("开始批量财务更新: symbols=%s data_types=%s", total, data_types)

        for i, symbol in enumerate(symbols):
            try:
                logger.info("批量更新进度: index=%s total=%s symbol=%s", i + 1, total, symbol)
                results = self.update_single_stock(symbol, data_types, start_year, end_year)

                for dt, count in results.items():
                    total_results[dt] = total_results.get(dt, 0) + count

                if progress_callback:
                    progress_callback(i + 1, total, symbol)

            except Exception as e:
                logger.warning(
                    "批量更新失败: symbol=%s error_type=%s error=%s",
                    symbol, type(e).__name__, e
                )
                continue

            # Baostock 限流：每秒1次
            time.sleep(1.1)

        logger.info("批量更新完成: results=%s", total_results)

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
            logger.warning(
                "查询财务数据失败: symbol=%s data_type=%s start_date=%s end_date=%s error_type=%s error=%s",
                symbol, data_type, start_date, end_date, type(e).__name__, e
            )
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
                WHERE symbol = ? AND trade_date <= ?
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
            logger.warning(
                "查询估值数据失败: symbols_count=%s trade_date=%s error_type=%s error=%s",
                len(symbols) if symbols else 0, trade_date, type(e).__name__, e
            )
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

        logger.info("开始更新全市场估值: trade_date=%s", trade_date)

        df = self.source.get_all_stocks_valuation()

        if df.empty:
            logger.warning("全市场估值获取失败: trade_date=%s", trade_date)
            return 0

        logger.info("全市场估值获取成功: rows=%s", len(df))

        count = self.saver.save_valuation_data(df, trade_date)
        logger.info("全市场估值保存完成: saved_rows=%s trade_date=%s", count, trade_date)

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
        except Exception as e:
            logger.warning(
                "检查数据新鲜度失败: symbol=%s table=%s error_type=%s error=%s",
                symbol, table, type(e).__name__, e
            )
            conn.close()
            return False

        if df.empty or df.iloc[0, 0] is None:
            conn.close()
            return False

        try:
            latest_date = datetime.strptime(str(df.iloc[0, 0]), '%Y-%m-%d')
            age_days = (datetime.now() - latest_date).days
        except Exception as e:
            logger.warning(
                "解析最新日期失败: symbol=%s table=%s raw_date=%s error_type=%s error=%s",
                symbol, table, df.iloc[0, 0], type(e).__name__, e
            )
            conn.close()
            return False

        conn.close()
        return age_days <= max_age_days

    # ========== 数据新鲜度检查 ==========

    def get_data_freshness(self, symbol: str) -> Dict[str, Dict]:
        """
        获取股票各财务数据的最新日期和新鲜度

        Args:
            symbol: 股票代码

        Returns:
            Dict[表名, {'latest_date': str, 'age_days': int, 'is_fresh': bool}]
        """
        tables = [
            'profit_data',
            'balance_data',
            'cash_flow_data',
            'dupont_data',
            'growth_data',
            'operation_data',
            'debtpaying_data'
        ]
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
            except Exception as e:
                logger.warning(
                    "获取数据新鲜度失败: symbol=%s table=%s error_type=%s error=%s",
                    symbol, table, type(e).__name__, e
                )
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

    def get_all_stocks(self) -> List[str]:
        """获取可更新的股票列表"""
        return self.source.get_all_stocks()

    # ========== 资源清理 ==========

    def close(self):
        """关闭连接"""
        self.source.logout()

    def __del__(self):
        """析构时确保关闭"""
        try:
            self.close()
        except Exception:
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
