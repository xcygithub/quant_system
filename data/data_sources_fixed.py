"""
多数据源支持模块 - 修复版
提供多种数据源获取方式，增强重试机制和错误处理
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import warnings
import time
import requests
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings('ignore', category=InsecureRequestWarning)


class DataSourceBase:
    """数据源基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.is_available = True
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取日线数据"""
        raise NotImplementedError
    
    def test_connection(self) -> bool:
        """测试连接是否可用"""
        return True


class BaostockDataSource(DataSourceBase):
    """Baostock数据源 - 备选方案"""
    
    def __init__(self):
        super().__init__("baostock")
        try:
            import baostock as bs
            self.bs = bs
            self.is_available = True
        except ImportError:
            self.is_available = False
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从baostock获取日线数据"""
        if not self.is_available:
            return pd.DataFrame()
        
        try:
            # 登录
            lg = self.bs.login()
            if lg.error_code != '0':
                print(f"  [!] Baostock登录失败: {lg.error_msg}")
                return pd.DataFrame()
            
            # 转换代码格式
            if symbol.startswith('6'):
                code = f"sh.{symbol}"
            else:
                code = f"sz.{symbol}"
            
            # 获取数据
            rs = self.bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close,volume,amount",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"  # 复权类型：3=后复权，2=前复权，1=不复权
            )
            
            if rs.error_code != '0':
                print(f"  [!] 查询失败: {rs.error_msg}")
                self.bs.logout()
                return pd.DataFrame()
            
            # 解析数据
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            self.bs.logout()
            
            if not data_list:
                return pd.DataFrame()
            
            # 转换为DataFrame
            df = pd.DataFrame(data_list, columns=[
                'date', 'code', 'open', 'high', 'low', 'close', 'volume', 'amount'
            ])
            
            # 类型转换
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['symbol'] = symbol
            df['data_source'] = 'baostock'
            
            print(f"  [OK] 成功获取 {len(df)} 条数据")
            return df
            
        except Exception as e:
            print(f"  [!] Baostock错误: {e}")
            try:
                self.bs.logout()
            except:
                pass
            return pd.DataFrame()


class EastmoneyDataSource(DataSourceBase):
    """东方财富直接API - 备选方案"""
    
    def __init__(self):
        super().__init__("eastmoney")
        self.is_available = True
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从东方财富直接获取数据"""
        try:
            # 转换日期格式
            start = start_date.replace("-", "")
            end = end_date.replace("-", "")
            
            # 构建URL
            url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                'secid': f"0.{symbol}" if symbol.startswith(('0', '3')) else f"1.{symbol}",
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                'klt': '101',  # 日K
                'fqt': '1',    # 前复权
                'beg': start,
                'end': end,
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            data = response.json()
            
            if 'data' not in data or data['data'] is None:
                print(f"  [!] 无数据返回")
                return pd.DataFrame()
            
            klines = data['data'].get('klines', [])
            if not klines:
                return pd.DataFrame()
            
            # 解析K线数据
            rows = []
            for kline in klines:
                parts = kline.split(',')
                rows.append({
                    'date': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': float(parts[5]),
                    'amount': float(parts[6]),
                    'amplitude': float(parts[7]),
                    'pct_change': float(parts[8]),
                    'change': float(parts[9]),
                    'turnover': float(parts[10]) if len(parts) > 10 else 0
                })
            
            df = pd.DataFrame(rows)
            df['symbol'] = symbol
            df['data_source'] = 'eastmoney'
            
            print(f"  [OK] 成功获取 {len(df)} 条数据")
            return df
            
        except Exception as e:
            print(f"  [!] Eastmoney错误: {e}")
            return pd.DataFrame()


class CSVDataSource(DataSourceBase):
    """本地CSV文件数据源"""
    
    def __init__(self, data_dir: str = "stock_data"):
        super().__init__("csv")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.is_available = True
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从本地CSV文件读取数据"""
        try:
            # 尝试查找CSV文件
            csv_file = self.data_dir / f"{symbol}.csv"
            
            if not csv_file.exists():
                csv_file = self.data_dir / f"{symbol}_daily.csv"
            
            if not csv_file.exists():
                return pd.DataFrame()
            
            # 读取CSV
            df = pd.read_csv(csv_file)
            df.columns = df.columns.str.lower().str.strip()
            
            if 'date' not in df.columns and 'trade_date' in df.columns:
                df = df.rename(columns={'trade_date': 'date'})
            
            # 过滤日期范围
            df['date'] = pd.to_datetime(df['date'])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
            df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            
            df['symbol'] = symbol
            df['data_source'] = 'csv'
            
            print(f"  [OK] 从CSV读取 {len(df)} 条数据")
            return df
            
        except Exception as e:
            print(f"  [!] CSV读取错误: {e}")
            return pd.DataFrame()


class MultiDataSource:
    """多数据源管理器 - 自动切换数据源"""
    
    def __init__(self, prefer_source: str = None):
        self.sources = []
        self.prefer_source = prefer_source
        self._init_sources()
    
    def _init_sources(self):
        """初始化所有数据源"""
        # 已移除 Akshare 数据源
        self.sources.append(EastmoneyDataSource())
        self.sources.append(BaostockDataSource())
        self.sources.append(CSVDataSource())
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str, 
                       prefer_source: str = None) -> pd.DataFrame:
        """获取日线数据，自动尝试多个数据源"""
        prefer = prefer_source or self.prefer_source
        
        print(f"\n获取股票 {symbol} 数据 ({start_date} 至 {end_date})")
        
        # 如果指定了优先数据源
        if prefer:
            for source in self.sources:
                if source.name == prefer and source.is_available:
                    print(f"使用指定数据源: {source.name}")
                    df = source.get_daily_kline(symbol, start_date, end_date)
                    if not df.empty:
                        return df
        
        # 按顺序尝试所有数据源
        for source in self.sources:
            if not source.is_available:
                continue
            
            print(f"尝试数据源: {source.name}...")
            try:
                df = source.get_daily_kline(symbol, start_date, end_date)
                if not df.empty:
                    print(f"[OK] 成功从 {source.name} 获取数据\n")
                    return df
            except Exception as e:
                print(f"  [!] {source.name} 失败: {e}")
                continue
        
        print("[X] 所有数据源都不可用\n")
        return pd.DataFrame()
    
    def get_available_sources(self) -> list:
        """获取可用的数据源列表"""
        return [s.name for s in self.sources if s.is_available]


if __name__ == "__main__":
    # 测试多数据源
    print("="*60)
    print("量化系统数据源测试")
    print("="*60)
    
    mds = MultiDataSource()
    print(f"\n可用数据源: {mds.get_available_sources()}")
    
    # 测试获取数据
    test_symbols = ["000001", "600519", "601919"]
    
    for symbol in test_symbols:
        df = mds.get_daily_kline(symbol, "2024-01-01", "2024-01-31")
        if not df.empty:
            print(f"数据预览:")
            print(df.head(3)[['date', 'open', 'close', 'high', 'low', 'volume']].to_string(index=False))
            print()
