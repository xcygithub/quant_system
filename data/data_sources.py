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


class AkshareDataSource(DataSourceBase):
    """akshare数据源 - 增强版，带重试机制"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        super().__init__("akshare")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        try:
            import akshare as ak
            self.ak = ak
            self.is_available = True
        except ImportError:
            self.is_available = False
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从akshare获取日线数据，带重试机制"""
        if not self.is_available:
            return pd.DataFrame()
        
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    delay = self.retry_delay * (2 ** (attempt - 1)) + np.random.uniform(0, 1)
                    print(f"  第 {attempt + 1} 次尝试，等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                
                df = self.ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=start,
                    end_date=end,
                    adjust="qfq"
                )
                
                if not df.empty:
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
                        '涨跌额': 'change_amount',  # 修复：与数据库表字段名一致
                        '换手率': 'turnover'
                    })
                    df['symbol'] = symbol
                    df['data_source'] = 'akshare'
                    print(f"  [OK] 成功获取 {len(df)} 条数据")
                    return df
                    
            except Exception as e:
                error_msg = str(e)
                if "Connection aborted" in error_msg or "RemoteDisconnected" in error_msg:
                    print(f"  [!] 连接被断开 (尝试 {attempt + 1}/{self.max_retries})")
                elif "Read timed out" in error_msg:
                    print(f"  [!] 读取超时 (尝试 {attempt + 1}/{self.max_retries})")
                else:
                    print(f"  [!] 错误: {error_msg[:50]}...")
                
                if attempt == self.max_retries - 1:
                    print(f"  [X] 达到最大重试次数，放弃")
        
        return pd.DataFrame()


class BaostockDataSource(DataSourceBase):
    """Baostock数据源 - 推荐备选方案"""
    
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
            lg = self.bs.login()
            if lg.error_code != '0':
                print(f"  [!] Baostock登录失败: {lg.error_msg}")
                return pd.DataFrame()
            
            # 转换代码格式：处理带后缀的格式如 000001.SZ -> sz.000001
            # 优先根据原后缀判断，避免 000001.SH 和 000001.SZ 混淆
            if symbol.endswith('.SH'):
                code = f"sh.{symbol[:-3]}"  # 000001.SH -> sh.000001
            elif symbol.endswith('.SZ'):
                code = f"sz.{symbol[:-3]}"  # 000001.SZ -> sz.000001
            elif symbol.endswith('.BJ'):
                code = f"bj.{symbol[:-3]}"  # 000001.BJ -> bj.000001
            else:
                # 没有后缀时，根据数字判断
                clean_symbol = symbol
                if clean_symbol.startswith('6') or clean_symbol.startswith('9'):
                    code = f"sh.{clean_symbol}"
                else:
                    code = f"sz.{clean_symbol}"
            
            rs = self.bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close,volume,amount",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"
            )
            
            if rs.error_code != '0':
                print(f"  [!] 查询失败: {rs.error_msg}")
                self.bs.logout()
                return pd.DataFrame()
            
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            self.bs.logout()
            
            if not data_list:
                return pd.DataFrame()
            
            df = pd.DataFrame(data_list, columns=[
                'date', 'code', 'open', 'high', 'low', 'close', 'volume', 'amount'
            ])
            
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
            start = start_date.replace("-", "")
            end = end_date.replace("-", "")
            
            url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                'secid': f"0.{symbol}" if symbol.startswith(('0', '3')) else f"1.{symbol}",
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                'klt': '101',
                'fqt': '1',
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
                    'change_amount': float(parts[9]),  # 修复：与数据库表字段名一致
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
                # 尝试其他命名格式
                csv_file = self.data_dir / f"{symbol}_daily.csv"
            
            if not csv_file.exists():
                print(f"未找到 {symbol} 的CSV文件，请在 {self.data_dir} 目录下放置数据文件")
                return pd.DataFrame()
            
            # 读取CSV
            df = pd.read_csv(csv_file)
            
            # 标准化列名
            df.columns = df.columns.str.lower().str.strip()
            
            # 确保有date列
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
            
            print(f"从CSV文件读取到 {len(df)} 条数据")
            return df
            
        except Exception as e:
            print(f"读取CSV文件失败: {e}")
            return pd.DataFrame()
    
    def save_to_csv(self, df: pd.DataFrame, symbol: str):
        """保存数据到CSV文件"""
        try:
            csv_file = self.data_dir / f"{symbol}.csv"
            df.to_csv(csv_file, index=False)
            print(f"数据已保存到 {csv_file}")
        except Exception as e:
            print(f"保存CSV文件失败: {e}")


class SimulatedDataSource(DataSourceBase):
    """模拟数据源 - 最后备选"""
    
    def __init__(self):
        super().__init__("simulated")
        self.is_available = True
    
    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """生成模拟日线数据"""
        try:
            date_range = pd.date_range(start=start_date, end=end_date, freq='B')
            n_days = len(date_range)
            
            if n_days == 0:
                return pd.DataFrame()
            
            np.random.seed(hash(symbol) % 2**32)
            initial_price = 50 + (hash(symbol) % 100)
            returns = np.random.normal(0.0005, 0.02, n_days)
            prices = initial_price * (1 + returns).cumprod()
            
            df = pd.DataFrame({
                'date': date_range.strftime('%Y-%m-%d'),
                'open': prices * (1 + np.random.normal(0, 0.005, n_days)),
                'high': prices * (1 + np.abs(np.random.normal(0, 0.01, n_days))),
                'low': prices * (1 - np.abs(np.random.normal(0, 0.01, n_days))),
                'close': prices,
                'volume': np.random.randint(1000000, 10000000, n_days),
                'amount': np.random.randint(100000000, 1000000000, n_days),
                'amplitude': np.abs(np.random.normal(0, 0.02, n_days)) * 100,
                'pct_change': returns * 100,
                'change': prices * returns,
                'turnover': np.random.uniform(1, 5, n_days),
            })
            
            df['high'] = df[['open', 'close', 'high']].max(axis=1)
            df['low'] = df[['open', 'close', 'low']].min(axis=1)
            df['symbol'] = symbol
            df['data_source'] = 'simulated'
            
            return df
            
        except Exception as e:
            print(f"生成模拟数据失败: {e}")
            return pd.DataFrame()


class MultiDataSource:
    """多数据源管理器 - 自动切换数据源"""
    
    def __init__(self, prefer_source: str = "baostock"):
        self.sources = []
        self.prefer_source = prefer_source
        self._init_sources()
    
    def _init_sources(self):
        """初始化所有数据源"""
        # 只保留 baostock 和 csv 两个数据源
        self.sources.append(BaostockDataSource())  # 优先使用baostock（真实数据）
        self.sources.append(CSVDataSource())  # 本地CSV文件作为备选
    
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
    mds = MultiDataSource()
    print(f"可用数据源: {mds.get_available_sources()}")
    
    # 测试获取数据
    df = mds.get_daily_kline("000001", "2024-01-01", "2024-01-31")
    if not df.empty:
        print(f"\n获取到 {len(df)} 条数据")
        print(df.head())
