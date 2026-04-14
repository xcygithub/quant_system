"""
数据管理器 - 统一的数据获取和缓存管理
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import sqlite3
import os
import json
from pathlib import Path
import time
import warnings
warnings.filterwarnings('ignore')

from .data_sources import MultiDataSource

class DataManager:
    """数据管理器 - 负责数据的获取、缓存和更新"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据管理器

        Args:
            db_path: SQLite数据库路径，默认使用 Claw 目录下的 quant_data.db
        """
        if db_path is None:
            # 统一使用 Claw 目录下的数据库（与项目分离，方便管理）
            db_path = Path(__file__).parent.parent.parent / "quant_data.db"
        self.db_path = str(db_path)
        self.cache_dir = Path("data_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.data_source = MultiDataSource()  # 使用多数据源
        self._init_database()
        
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 股票基础信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_info (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                industry TEXT,
                market TEXT,
                list_date TEXT,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 日线数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_kline (
                symbol TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL,
                turnover REAL,
                amplitude REAL,
                pct_change REAL,
                change_amount REAL,
                PRIMARY KEY (symbol, date)
            )
        ''')
        
        # 分钟数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS minute_kline (
                symbol TEXT,
                datetime TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL,
                PRIMARY KEY (symbol, datetime)
            )
        ''')
        
        # ========== 财务数据表（新版）==========

        # 1. 盈利能力数据（利润表）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                eps REAL,
                roe REAL,
                roe_avg REAL,
                net_profit_ratio REAL,
                gross_profit_rate REAL,
                business_income REAL,
                operating_profit REAL,
                net_profit REAL,
                total_profit REAL,
                inv_net_profit REAL,
                pub_date TEXT,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 2. 资产负债数据（资产负债表）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS balance_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                total_assets REAL,
                total_liabilities REAL,
                total_equity REAL,
                debt_ratio REAL,
                equity_ratio REAL,
                current_assets REAL,
                fixed_assets REAL,
                intangible_assets REAL,
                current_ratio REAL,
                quick_ratio REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 3. 现金流量数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cash_flow_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                oper_cash_flow REAL,
                invest_cash_flow REAL,
                finance_cash_flow REAL,
                cash_equil_change REAL,
                end_cash REAL,
                oper_cash_flow_ps REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 4. 杜邦分析数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dupont_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                roe REAL,
                asset_turnover REAL,
                equity_multiplier REAL,
                net_profit_margin REAL,
                sales_to_grs REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 5. 成长能力数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS growth_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                profit_grow REAL,
                profit_grow_ratio REAL,
                asset_to_income REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 6. 营运能力数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                inv_turnover REAL,
                ar_turnover REAL,
                ap_turnover REAL,
                total_asset_turnover REAL,
                current_asset_turnover REAL,
                fixed_asset_turnover REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 7. 偿债能力数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debtpaying_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                current_ratio REAL,
                quick_ratio REAL,
                cash_ratio REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 8. 估值数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS valuation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                pe REAL,
                pe_ttm REAL,
                pb REAL,
                ps REAL,
                pcf REAL,
                market_cap REAL,
                float_market_cap REAL,
                total_shares REAL,
                float_shares REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date)
            )
        ''')

        # 9. 财务因子缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                factor_value REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date, factor_name)
            )
        ''')

        # 10. 数据更新日志
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS update_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_type TEXT NOT NULL,
                symbol TEXT,
                status TEXT DEFAULT 'running',
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                records_updated INTEGER DEFAULT 0,
                error_message TEXT
            )
        ''')

        # ========== 创建索引 ==========
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_profit_symbol_date ON profit_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_balance_symbol_date ON balance_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cash_symbol_date ON cash_flow_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_dupont_symbol_date ON dupont_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_valuation_symbol_date ON valuation_data(symbol, trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_factor_cache_symbol_date ON factor_cache(symbol, trade_date)')

        conn.commit()
        conn.close()
    
    def get_stock_list(self, market: str = "all") -> pd.DataFrame:
        """
        获取股票列表
        
        Args:
            market: 市场类型 (sh/sz/all)
            
        Returns:
            DataFrame包含股票代码、名称、行业等信息
        """
        try:
            # 获取上海股票
            if market in ["sh", "all"]:
                sh_stocks = ak.stock_sh_a_spot_em()
                sh_stocks['market'] = 'SH'
            else:
                sh_stocks = pd.DataFrame()
                
            # 获取深圳股票
            if market in ["sz", "all"]:
                sz_stocks = ak.stock_sz_a_spot_em()
                sz_stocks['market'] = 'SZ'
            else:
                sz_stocks = pd.DataFrame()
            
            # 合并数据
            all_stocks = pd.concat([sh_stocks, sz_stocks], ignore_index=True)
            
            # 标准化列名
            all_stocks = all_stocks.rename(columns={
                '代码': 'symbol',
                '名称': 'name',
                '最新价': 'price',
                '涨跌幅': 'pct_change',
                '涨跌额': 'change',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '最高': 'high',
                '最低': 'low',
                '今开': 'open',
                '昨收': 'pre_close',
                '量比': 'volume_ratio',
                '换手率': 'turnover',
                '市盈率-动态': 'pe',
                '市净率': 'pb',
                '总市值': 'total_mv',
                '流通市值': 'float_mv',
                '涨速': 'rise_speed',
                '5分钟涨跌': 'change_5min',
                '60日涨跌幅': 'change_60d',
                '年初至今涨跌幅': 'change_ytd'
            })
            
            return all_stocks
            
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return pd.DataFrame()
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取日线数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            DataFrame包含OHLCV数据
        """
        import traceback
        try:
            # 参数验证
            if not symbol or not start_date or not end_date:
                print(f"参数错误: symbol={symbol}, start_date={start_date}, end_date={end_date}")
                return pd.DataFrame()
            
            # 确保日期格式正确
            try:
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
            except Exception as date_err:
                print(f"日期格式错误: {date_err}")
                return pd.DataFrame()
            
            print(f"正在获取 {symbol} 从 {start_date} 到 {end_date} 的数据...")
            
            # 尝试从数据库读取
            df = self._get_kline_from_db(symbol, start_date, end_date)
            
            if df.empty or not self._check_data_complete(df, start_date, end_date):
                print(f"从数据库未获取到完整数据，尝试从在线数据源获取...")
                
                # 使用多数据源获取
                df = self.data_source.get_daily_kline(symbol, start_date, end_date)
                
                if not df.empty:
                    # 保存到数据库
                    try:
                        self._save_kline_to_db(df)
                    except Exception as db_err:
                        print(f"保存到数据库失败: {db_err}")
                else:
                    print(f"从所有数据源获取到空数据")
            else:
                print(f"从数据库获取到 {len(df)} 条数据")
            
            return df
            
        except Exception as e:
            print(f"获取{symbol}日线数据失败: {e}")
            print(f"错误详情: {traceback.format_exc()}")
            return pd.DataFrame()
    
    def get_minute_kline(self, symbol: str, period: str = "1") -> pd.DataFrame:
        """
        获取分钟线数据
        
        Args:
            symbol: 股票代码
            period: 分钟周期 (1/5/15/30/60)
            
        Returns:
            DataFrame包含分钟OHLCV数据
        """
        try:
            # 尝试从akshare获取
            from data_sources import AkshareDataSource
            ak_source = AkshareDataSource()
            if ak_source.is_available:
                import akshare as ak
                df = ak.stock_zh_a_minute(
                    symbol=symbol,
                    period=period,
                    adjust="qfq"
                )
                
                df = df.rename(columns={
                    '时间': 'datetime',
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume',
                    '成交额': 'amount'
                })
                df['symbol'] = symbol
                
                return df
        except Exception as e:
            print(f"获取{symbol}分钟数据失败: {e}")
            return pd.DataFrame()
    
    def get_financial_data(self, symbol: str) -> pd.DataFrame:
        """
        获取财务数据
        
        Args:
            symbol: 股票代码
            
        Returns:
            DataFrame包含财务报表数据
        """
        try:
            # 获取主要财务指标
            import akshare as ak
            df = ak.stock_financial_analysis_indicator(symbol=symbol)
            return df
        except Exception as e:
            print(f"获取{symbol}财务数据失败: {e}")
            return pd.DataFrame()
    
    def get_index_list(self) -> pd.DataFrame:
        """获取指数列表"""
        try:
            import akshare as ak
            df = ak.index_stock_info()
            return df
        except Exception as e:
            print(f"获取指数列表失败: {e}")
            return pd.DataFrame()
    
    def get_index_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取指数K线数据
        
        Args:
            symbol: 指数代码
            start_date: 开始日期
            end_date: 结束日期
        """
        try:
            import akshare as ak
            df = ak.index_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", "")
            )
            
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'pct_change',
                '涨跌额': 'change',
                '换手率': 'turnover'
            })
            
            return df
        except Exception as e:
            print(f"获取指数{symbol}数据失败: {e}")
            return pd.DataFrame()
    
    def _get_kline_from_db(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从数据库读取K线数据"""
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT * FROM daily_kline 
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date
        """
        df = pd.read_sql_query(query, conn, params=(symbol, start_date, end_date))
        conn.close()
        return df
    
    def _save_kline_to_db(self, df: pd.DataFrame):
        """保存K线数据到数据库"""
        if df.empty:
            return

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

        # 使用事务批量插入，先删除已存在的记录，再插入新数据
        # 这样可以避免 INSERT OR REPLACE 可能带来的问题
        try:
            cursor.execute("BEGIN TRANSACTION")
            for _, row in save_df.iterrows():
                # 先删除已存在的记录（如果主键冲突）
                cursor.execute("""
                    DELETE FROM daily_kline WHERE symbol = ? AND date = ?
                """, (row['symbol'], row['date']))

                # 插入新记录
                cursor.execute("""
                    INSERT INTO daily_kline
                    (symbol, date, open, high, low, close, volume, amount, turnover, amplitude, pct_change, change_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['symbol'], row['date'], row['open'], row['high'], row['low'],
                    row['close'], row['volume'], row['amount'], row.get('turnover', 0),
                    row.get('amplitude', 0), row.get('pct_change', 0), row.get('change_amount', 0)
                ))
            cursor.execute("COMMIT")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"保存数据失败: {e}")
        finally:
            conn.close()
    
    def update_recent_data(self, symbols: list, days: int = 10):
        """
        更新指定股票列表的最近N天数据（不包括今天）

        专门用于刷新自选股的最新行情数据。
        逻辑：先检查数据库，如果数据库中已有最近days天的完整数据，则跳过；
        否则从在线数据源获取缺少的数据。

        Args:
            symbols: 股票代码列表
            days: 获取最近多少天的数据（默认10天，确保覆盖5个交易日）

        Returns:
            updated_count: 实际从在线源更新了数据的股票数量
        """
        # 计算日期范围：今天之前的days天（不包括今天）
        # 交易日数量约为日历天的40%，所以取 days*3 作为搜索范围以确保覆盖足够的交易日
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days*3)).strftime("%Y-%m-%d")

        updated_count = 0
        for symbol in symbols:
            try:
                # 先检查数据库中最近days天的数据是否完整
                existing_df = self._get_kline_from_db(symbol, start_date, end_date)

                # 使用 _check_data_complete 检查数据完整性和时效性
                if self._check_data_complete(existing_df, start_date, end_date):
                    # 数据库中已有足够且足够新的数据，跳过更新
                    latest_date = existing_df['date'].max() if not existing_df.empty else "无"
                    print(f"  {symbol} 数据库已有最新数据 ({len(existing_df)} 条，最新: {latest_date})，跳过更新")
                    continue

                # 数据不完整或过时，从在线数据源获取
                print(f"  {symbol} 数据库数据不完整 ({len(existing_df)} 条)，从在线源获取...")
                df = self.data_source.get_daily_kline(symbol, start_date, end_date)
                if not df.empty:
                    # 增量保存到数据库
                    self._save_kline_to_db(df)
                    updated_count += 1
                    print(f"  已更新 {symbol} 最新数据 ({len(df)} 条)")
                else:
                    print(f"  {symbol} 未获取到最新数据")
            except Exception as e:
                print(f"  更新 {symbol} 失败: {e}")

        print(f"数据更新完成: {updated_count}/{len(symbols)} 只股票从在线源更新")
        return updated_count

    def _check_data_complete(self, df: pd.DataFrame, start_date: str, end_date: str) -> bool:
        """检查数据是否完整

        完整性的判断标准：
        1. 数据条数足够（>= 估算交易日 * 85%）
        2. 最新数据日期足够新（>= 昨天）

        只有同时满足两者，才认为数据完整。
        """
        if df.empty:
            return False

        # 更严格的检查：数据条数应该接近交易日数量
        # 交易日数量 = 工作日数量（粗略估算为日历天的1/5，但更准确的是直接计算）
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end - start).days

        if total_days <= 0:
            return True

        # 粗略估算交易日数量（约为日历天的40%，因为扣除周末和假期）
        estimated_trading_days = int(total_days * 0.4)

        # 检查1：数据条数是否足够
        if len(df) < estimated_trading_days * 0.85:
            return False

        # 检查2：最新数据日期是否包含最近一个交易日
        # 关键：需要考虑周末（周末不是交易日）
        # - 周一(0)：最近交易日是上周五（3天前）
        # - 周日(6)：最近交易日是上周五（2天前）
        # - 其他工作日：最近交易日是昨天（1天前）
        today = datetime.now()
        weekday = today.weekday()

        if weekday == 0:  # 周一
            days_back = 3  # 上周五
        elif weekday == 6:  # 周日
            days_back = 2  # 上周五
        else:  # 周二~周六
            days_back = 1  # 昨天

        ref_date = (today - timedelta(days=days_back)).date()
        latest_date = pd.to_datetime(df['date']).max().date()

        if latest_date < ref_date:
            # 数据过时，不完整
            return False

        return True
    
    def update_all_data(self):
        """更新所有数据"""
        print("开始更新数据...")
        
        # 更新股票列表
        print("更新股票列表...")
        stocks = self.get_stock_list()
        
        # 更新指数数据
        print("更新指数数据...")
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        # 主要指数
        indices = ['000001', '000300', '000905', '399001', '399006']
        for idx in indices:
            self.get_index_kline(idx, start_date, end_date)
        
        print("数据更新完成")

    # ========== 财务数据便捷方法 ==========

    def get_financial_manager(self):
        """
        获取财务数据管理器

        Returns:
            FinancialDataManager 实例
        """
        from .financial_data_manager import FinancialDataManager
        return FinancialDataManager(self.db_path)

    def update_financial_data(self, symbol: str,
                             data_types: List[str] = None) -> Dict[str, int]:
        """
        更新财务数据（便捷方法）

        Args:
            symbol: 股票代码，如 '000001.SZ'
            data_types: 数据类型列表，如 ['profit', 'balance', 'cash', 'dupont']

        Returns:
            更新记录数
        """
        fdm = self.get_financial_manager()
        result = fdm.update_single_stock(symbol, data_types)
        fdm.close()
        return result

    def get_financial_data(self, symbol: str,
                          data_type: str = 'profit',
                          start_date: str = None) -> pd.DataFrame:
        """
        获取财务数据（便捷方法）

        Args:
            symbol: 股票代码
            data_type: 数据类型 ('profit'/'balance'/'cash'/'dupont'/'growth'/'operation'/'debtpaying')
            start_date: 起始日期

        Returns:
            DataFrame
        """
        fdm = self.get_financial_manager()
        df = fdm.get_financial_data(symbol, data_type, start_date)
        fdm.close()
        return df

    def get_valuation(self, symbol: str,
                      trade_date: str = None) -> Optional[Dict]:
        """
        获取估值数据（便捷方法）

        Args:
            symbol: 股票代码
            trade_date: 交易日期，默认最新

        Returns:
            Dict or None
        """
        fdm = self.get_financial_manager()
        val = fdm.get_valuation(symbol, trade_date)
        fdm.close()
        return val

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


if __name__ == "__main__":
    # 测试数据管理器
    dm = DataManager()
    
    # 获取股票列表
    stocks = dm.get_stock_list()
    print(f"获取到 {len(stocks)} 只股票")
    print(stocks.head())
    
    # 获取日线数据
    df = dm.get_daily_kline("000001", "2024-01-01", "2024-12-31")
    print(f"\n获取到 {len(df)} 条日线数据")
    print(df.head())
