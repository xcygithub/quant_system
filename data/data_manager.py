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
    
    def __init__(self, db_path: str = "quant_data.db"):
        """
        初始化数据管理器
        
        Args:
            db_path: SQLite数据库路径
        """
        self.db_path = db_path
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
        
        # 财务数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_data (
                symbol TEXT,
                report_date TEXT,
                eps REAL,
                bvps REAL,
                roe REAL,
                revenue REAL,
                net_profit REAL,
                debt_ratio REAL,
                PRIMARY KEY (symbol, report_date)
            )
        ''')
        
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
        
        # 准备数据
        save_df = df[['symbol', 'date', 'open', 'high', 'low', 'close', 
                      'volume', 'amount', 'turnover', 'amplitude', 
                      'pct_change', 'change']].copy()
        
        # 使用REPLACE避免重复
        save_df.to_sql('daily_kline', conn, if_exists='append', index=False,
                      method='multi', chunksize=1000)
        
        conn.close()
    
    def _check_data_complete(self, df: pd.DataFrame, start_date: str, end_date: str) -> bool:
        """检查数据是否完整"""
        if df.empty:
            return False
        
        # 简单检查：数据条数是否足够
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        expected_days = (end - start).days
        
        # 考虑交易日约为日历日的70%
        expected_trading_days = int(expected_days * 0.7)
        
        return len(df) >= expected_trading_days * 0.9  # 允许10%的缺失
    
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
