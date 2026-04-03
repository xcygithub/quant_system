"""
因子数据模块 - 负责技术指标和因子的计算
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Callable
import warnings
warnings.filterwarnings('ignore')

class FactorData:
    """因子数据类 - 计算各类技术指标和因子"""
    
    def __init__(self, df: pd.DataFrame):
        """
        初始化
        
        Args:
            df: 包含OHLCV数据的DataFrame
        """
        self.df = df.copy()
        self._validate_data()
        
    def _validate_data(self):
        """验证数据格式"""
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in self.df.columns:
                raise ValueError(f"缺少必要的列: {col}")
    
    # ==================== 趋势指标 ====================
    
    def sma(self, period: int = 20) -> pd.Series:
        """简单移动平均线"""
        return self.df['close'].rolling(window=period).mean()
    
    def ema(self, period: int = 20) -> pd.Series:
        """指数移动平均线"""
        return self.df['close'].ewm(span=period, adjust=False).mean()
    
    def wma(self, period: int = 20) -> pd.Series:
        """加权移动平均线"""
        weights = np.arange(1, period + 1)
        return self.df['close'].rolling(window=period).apply(
            lambda x: np.dot(x, weights) / weights.sum(), raw=True
        )
    
    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """
        MACD指标
        
        Returns:
            Dict包含macd, signal, hist三个序列
        """
        ema_fast = self.ema(fast)
        ema_slow = self.ema(slow)
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'hist': hist
        }
    
    def bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """
        布林带
        
        Returns:
            Dict包含upper, middle, lower三个序列
        """
        middle = self.sma(period)
        std = self.df['close'].rolling(window=period).std()
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }
    
    # ==================== 动量指标 ====================
    
    def rsi(self, period: int = 14) -> pd.Series:
        """相对强弱指标RSI"""
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def kdj(self, n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, pd.Series]:
        """
        KDJ随机指标
        
        Returns:
            Dict包含k, d, j三个序列
        """
        low_list = self.df['low'].rolling(window=n, min_periods=n).min()
        high_list = self.df['high'].rolling(window=n, min_periods=n).max()
        rsv = (self.df['close'] - low_list) / (high_list - low_list) * 100
        
        k = rsv.ewm(com=m1-1, adjust=False).mean()
        d = k.ewm(com=m2-1, adjust=False).mean()
        j = 3 * k - 2 * d
        
        return {'k': k, 'd': d, 'j': j}
    
    def cci(self, period: int = 20) -> pd.Series:
        """商品通道指标CCI"""
        tp = (self.df['high'] + self.df['low'] + self.df['close']) / 3
        ma = tp.rolling(window=period).mean()
        md = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (tp - ma) / (0.015 * md)
        return cci
    
    def williams_r(self, period: int = 14) -> pd.Series:
        """威廉指标"""
        highest_high = self.df['high'].rolling(window=period).max()
        lowest_low = self.df['low'].rolling(window=period).min()
        wr = (highest_high - self.df['close']) / (highest_high - lowest_low) * -100
        return wr
    
    # ==================== 波动率指标 ====================
    
    def atr(self, period: int = 14) -> pd.Series:
        """平均真实波幅ATR"""
        high_low = self.df['high'] - self.df['low']
        high_close = np.abs(self.df['high'] - self.df['close'].shift())
        low_close = np.abs(self.df['low'] - self.df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    
    def volatility(self, period: int = 20) -> pd.Series:
        """历史波动率"""
        returns = self.df['close'].pct_change()
        return returns.rolling(window=period).std() * np.sqrt(252)
    
    # ==================== 成交量指标 ====================
    
    def obv(self) -> pd.Series:
        """能量潮OBV"""
        obv = (np.sign(self.df['close'].diff()) * self.df['volume']).cumsum()
        return obv
    
    def vwap(self) -> pd.Series:
        """成交量加权平均价VWAP"""
        typical_price = (self.df['high'] + self.df['low'] + self.df['close']) / 3
        vwap = (typical_price * self.df['volume']).cumsum() / self.df['volume'].cumsum()
        return vwap
    
    def volume_sma(self, period: int = 20) -> pd.Series:
        """成交量均线"""
        return self.df['volume'].rolling(window=period).mean()
    
    # ==================== 自定义因子 ====================
    
    def price_momentum(self, period: int = 20) -> pd.Series:
        """价格动量因子"""
        return self.df['close'].pct_change(period)
    
    def volume_momentum(self, period: int = 20) -> pd.Series:
        """成交量动量因子"""
        return self.df['volume'].pct_change(period)
    
    def price_volume_trend(self) -> pd.Series:
        """价量趋势因子"""
        pvt = ((self.df['close'] - self.df['close'].shift(1)) / 
               self.df['close'].shift(1) * self.df['volume']).cumsum()
        return pvt
    
    def mean_reversion(self, period: int = 20) -> pd.Series:
        """均值回归因子"""
        sma = self.sma(period)
        return (self.df['close'] - sma) / sma
    
    def volatility_regime(self, short_period: int = 20, long_period: int = 60) -> pd.Series:
        """波动率状态因子"""
        short_vol = self.volatility(short_period)
        long_vol = self.volatility(long_period)
        return short_vol / long_vol
    
    def trend_strength(self, period: int = 20) -> pd.Series:
        """趋势强度因子"""
        returns = self.df['close'].pct_change()
        up_days = (returns > 0).rolling(window=period).sum()
        return up_days / period
    
    def calculate_all_factors(self) -> pd.DataFrame:
        """计算所有因子"""
        result = self.df.copy()
        
        # 移动平均线
        for period in [5, 10, 20, 60]:
            result[f'sma_{period}'] = self.sma(period)
            result[f'ema_{period}'] = self.ema(period)
        
        # MACD
        macd_data = self.macd()
        result['macd'] = macd_data['macd']
        result['macd_signal'] = macd_data['signal']
        result['macd_hist'] = macd_data['hist']
        
        # 布林带
        bb_data = self.bollinger_bands()
        result['bb_upper'] = bb_data['upper']
        result['bb_middle'] = bb_data['middle']
        result['bb_lower'] = bb_data['lower']
        result['bb_position'] = (result['close'] - bb_data['lower']) / (bb_data['upper'] - bb_data['lower'])
        
        # 动量指标
        result['rsi_14'] = self.rsi(14)
        result['rsi_6'] = self.rsi(6)
        
        kdj_data = self.kdj()
        result['kdj_k'] = kdj_data['k']
        result['kdj_d'] = kdj_data['d']
        result['kdj_j'] = kdj_data['j']
        
        result['cci'] = self.cci()
        result['williams_r'] = self.williams_r()
        
        # 波动率
        result['atr'] = self.atr()
        result['volatility_20'] = self.volatility(20)
        result['volatility_60'] = self.volatility(60)
        
        # 成交量
        result['obv'] = self.obv()
        result['vwap'] = self.vwap()
        result['volume_sma_20'] = self.volume_sma(20)
        result['volume_ratio'] = result['volume'] / result['volume_sma_20']
        
        # 自定义因子
        result['momentum_20'] = self.price_momentum(20)
        result['momentum_60'] = self.price_momentum(60)
        result['mean_reversion_20'] = self.mean_reversion(20)
        result['trend_strength_20'] = self.trend_strength(20)
        result['volatility_regime'] = self.volatility_regime()
        
        return result


class FactorAnalyzer:
    """因子分析器 - 分析因子的有效性"""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
    
    def ic_analysis(self, factor_col: str, forward_return_col: str = 'forward_return') -> Dict:
        """
        信息系数(IC)分析
        
        Args:
            factor_col: 因子列名
            forward_return_col: 未来收益率列名
            
        Returns:
            IC统计信息
        """
        # 计算IC
        ic = self.df[factor_col].corr(self.df[forward_return_col])
        
        # 按日期分组计算IC
        if 'date' in self.df.columns:
            ic_series = self.df.groupby('date').apply(
                lambda x: x[factor_col].corr(x[forward_return_col])
            )
        else:
            ic_series = pd.Series([ic])
        
        return {
            'ic_mean': ic_series.mean(),
            'ic_std': ic_series.std(),
            'ic_ir': ic_series.mean() / ic_series.std() if ic_series.std() != 0 else 0,
            'ic_positive_ratio': (ic_series > 0).mean(),
            'ic_series': ic_series
        }
    
    def quantile_analysis(self, factor_col: str, return_col: str = 'forward_return', 
                          n_quantiles: int = 5) -> pd.DataFrame:
        """
        分位数分析
        
        Args:
            factor_col: 因子列名
            return_col: 收益率列名
            n_quantiles: 分位数数量
            
        Returns:
            各分位数的平均收益率
        """
        self.df['quantile'] = pd.qcut(self.df[factor_col], n_quantiles, labels=False, duplicates='drop')
        quantile_returns = self.df.groupby('quantile')[return_col].mean()
        return quantile_returns
    
    def factor_autocorrelation(self, factor_col: str, lag: int = 1) -> float:
        """因子自相关性"""
        if 'date' in self.df.columns and 'symbol' in self.df.columns:
            # 面板数据
            autocorr = self.df.groupby('symbol')[factor_col].apply(
                lambda x: x.autocorr(lag=lag)
            ).mean()
        else:
            autocorr = self.df[factor_col].autocorr(lag=lag)
        return autocorr


if __name__ == "__main__":
    # 测试因子计算
    from data_manager import DataManager
    
    dm = DataManager()
    df = dm.get_daily_kline("000001", "2024-01-01", "2024-12-31")
    
    if not df.empty:
        factor_data = FactorData(df)
        result = factor_data.calculate_all_factors()
        print("计算后的因子列:")
        print(result.columns.tolist())
        print("\n前5行数据:")
        print(result[['date', 'close', 'sma_20', 'rsi_14', 'macd']].head())
