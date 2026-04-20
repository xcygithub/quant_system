"""
全市场股票扫描器
对全市场股票进行因子打分和排序
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

try:
    from data import DataManager
    from data.financial_data_manager import FinancialDataManager
    from strategy.fundamental_factors import FundamentalFactors
    from strategy.factor_preprocessor import FactorPreprocessor
    from portfolio.selector import StockSelector, StockScore
except ImportError:
    from quant_system.data import DataManager
    from quant_system.data.financial_data_manager import FinancialDataManager
    from quant_system.strategy.fundamental_factors import FundamentalFactors
    from quant_system.strategy.factor_preprocessor import FactorPreprocessor
    from quant_system.portfolio.selector import StockSelector, StockScore


class MarketStockScanner:
    """
    全市场股票扫描器

    功能：
    - 获取全市场股票列表
    - 批量计算技术因子 + 基本面因子
    - 因子预处理（标准化、中性化）
    - 选股打分和排序
    - 输出候选股票列表
    """

    def __init__(
        self,
        data_manager: DataManager = None,
        fundamental_factors: FundamentalFactors = None,
        preprocessor: FactorPreprocessor = None,
        selector: StockSelector = None
    ):
        """
        初始化扫描器

        Args:
            data_manager: DataManager实例
            fundamental_factors: 基本面因子计算器
            preprocessor: 因子预处理器
            selector: 选股器
        """
        self.dm = data_manager or DataManager()
        self.ff = fundamental_factors or FundamentalFactors()
        self.preprocessor = preprocessor or FactorPreprocessor()
        self.selector = selector or StockSelector()

    def scan(
        self,
        trade_date: str = None,
        top_n: int = 100,
        exclude_st: bool = True,
        exclude_new_stock_days: int = 90,
        min_market_cap: float = 10e8,  # 最小市值10亿
        factors: List[str] = None,
        weights: Dict[str, float] = None
    ) -> pd.DataFrame:
        """
        扫描全市场股票

        Args:
            trade_date: 交易日期，默认今天
            top_n: 返回前N只
            exclude_st: 是否排除ST股票
            exclude_new_stock_days: 排除上市不足N天的股票
            min_market_cap: 最小市值（元）
            factors: 使用的因子列表
            weights: 因子权重

        Returns:
            DataFrame(columns=[symbol, name, score, ...因子值, ...维度得分])
        """
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        print(f"[扫描] 日期: {trade_date}, Top {top_n}")

        # Step 1: 获取可交易股票列表
        tradable = self._get_tradable_stocks(
            trade_date,
            exclude_st,
            exclude_new_stock_days,
            min_market_cap
        )
        print(f"[扫描] 可交易股票: {len(tradable)} 只")

        if len(tradable) == 0:
            return pd.DataFrame()

        # Step 2: 批量获取K线数据
        stock_data = self._batch_get_kline(tradable, trade_date)
        print(f"[扫描] 获取K线数据: {len(stock_data)} 只")

        if len(stock_data) == 0:
            return pd.DataFrame()

        # Step 3: 获取基本面因子
        fundamental_panel = self._batch_get_fundamental_factors(tradable, trade_date)

        # Step 4: 计算技术因子
        tech_factors = self._calculate_technical_factors(stock_data)

        # Step 5: 合并因子面板
        factor_panel = self._merge_factors(tech_factors, fundamental_panel)

        if factor_panel.empty:
            return pd.DataFrame()

        print(f"[扫描] 因子面板: {factor_panel.shape}")

        # Step 6: 预处理
        processed_panel = self._preprocess_factor_panel(factor_panel)

        # Step 7: 批量打分
        scores = self._batch_score(processed_panel, weights)

        # Step 8: 排序并返回Top N
        scores.sort(key=lambda x: x.composite_score, reverse=True)
        top_scores = scores[:top_n]

        # Step 9: 转换为DataFrame
        result = self._scores_to_dataframe(top_scores, processed_panel)

        return result

    def _get_tradable_stocks(
        self,
        trade_date: str,
        exclude_st: bool,
        exclude_new_days: int,
        min_market_cap: float
    ) -> List[str]:
        """
        获取可交易股票列表

        Returns:
            股票代码列表
        """
        try:
            # 获取全市场股票列表
            stock_list = self.dm.get_stock_list(market='all')

            if stock_list.empty:
                return []

            symbols = []

            for _, row in stock_list.iterrows():
                symbol = row.get('symbol', '')

                # 过滤ST股票
                if exclude_st:
                    name = row.get('name', '')
                    if 'ST' in name or '*ST' in name:
                        continue

                # 过滤新股
                if exclude_new_days > 0:
                    list_date = row.get('list_date') or row.get('listDate')
                    if list_date:
                        try:
                            list_dt = pd.to_datetime(list_date)
                            days_since_list = (pd.to_datetime(trade_date) - list_dt).days
                            if days_since_list < exclude_new_days:
                                continue
                        except:
                            pass

                # 过滤低市值
                if min_market_cap > 0:
                    market_cap = row.get('market_cap', 0)
                    if market_cap and market_cap < min_market_cap:
                        continue

                symbols.append(symbol)

            return symbols

        except Exception as e:
            print(f"[警告] 获取可交易股票失败: {e}")
            return []

    def _batch_get_kline(
        self,
        symbols: List[str],
        trade_date: str,
        lookback_days: int = 60
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取K线数据

        Returns:
            {symbol: DataFrame} 字典
        """
        stock_data = {}
        end_date = trade_date
        start_date = pd.to_datetime(trade_date) - pd.Timedelta(days=lookback_days * 2)
        start_date = start_date.strftime('%Y-%m-%d')

        # 批量获取（使用已有的批量接口）
        for symbol in symbols:
            try:
                df = self.dm.get_daily_kline(symbol, start_date, end_date)
                if df is not None and not df.empty and len(df) >= 10:
                    stock_data[symbol] = df
            except Exception as e:
                continue

        return stock_data

    def _batch_get_fundamental_factors(
        self,
        symbols: List[str],
        trade_date: str
    ) -> pd.DataFrame:
        """
        批量获取基本面因子

        Returns:
            DataFrame(index=symbol, columns=因子名)
        """
        try:
            panel = self.ff.get_factor_panel(symbols, trade_date)
            return panel
        except Exception as e:
            print(f"[警告] 获取基本面因子失败: {e}")
            return pd.DataFrame()

    def _calculate_technical_factors(
        self,
        stock_data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        计算技术因子

        Args:
            stock_data: {symbol: DataFrame}

        Returns:
            DataFrame(index=symbol, columns=技术因子)
        """
        rows = []

        for symbol, df in stock_data.items():
            try:
                if df.empty or len(df) < 20:
                    continue

                row = {'symbol': symbol}

                close = df['close']

                # 动量因子
                row['momentum_5'] = (close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0
                row['momentum_20'] = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
                row['momentum_60'] = (close.iloc[-1] / close.iloc[-60] - 1) if len(close) >= 60 else 0

                # 波动率因子
                returns = close.pct_change().dropna()
                if len(returns) >= 20:
                    row['volatility_20'] = returns.iloc[-20:].std()
                    row['volatility_60'] = returns.iloc[-60:].std() if len(returns) >= 60 else returns.std()
                else:
                    row['volatility_20'] = returns.std() if len(returns) > 0 else 0
                    row['volatility_60'] = returns.std()

                # 成交量因子
                if 'volume' in df.columns:
                    vol = df['volume']
                    row['volume_ratio'] = vol.iloc[-5:].mean() / vol.iloc[-20:].mean() if len(vol) >= 20 else 1.0
                else:
                    row['volume_ratio'] = 1.0

                # 趋势因子
                if len(close) >= 20:
                    sma20 = close.iloc[-20:].mean()
                    row['trend_20'] = (close.iloc[-1] - sma20) / sma20 if sma20 > 0 else 0
                else:
                    row['trend_20'] = 0

                # 最新价格（用于后续计算）
                row['close'] = close.iloc[-1]

                rows.append(row)

            except Exception as e:
                continue

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows).set_index('symbol')

    def _merge_factors(
        self,
        tech_factors: pd.DataFrame,
        fundamental_factors: pd.DataFrame
    ) -> pd.DataFrame:
        """
        合并技术因子和基本面因子

        Returns:
            合并后的因子面板
        """
        if tech_factors.empty and fundamental_factors.empty:
            return pd.DataFrame()

        if tech_factors.empty:
            return fundamental_factors.copy()

        if fundamental_factors.empty:
            return tech_factors.copy()

        # 合并
        merged = tech_factors.join(fundamental_factors, how='outer')

        return merged

    def _preprocess_factor_panel(
        self,
        factor_panel: pd.DataFrame
    ) -> pd.DataFrame:
        """
        预处理因子面板

        1. 缺失值填充
        2. 异常值处理（Winsorization）
        3. 标准化
        """
        if factor_panel.empty:
            return factor_panel

        # 获取数值列
        factor_cols = [c for c in factor_panel.columns
                      if c not in ['symbol', 'trade_date', 'name', 'close']]

        if not factor_cols:
            return factor_panel

        # 使用预处理器
        try:
            processed = self.preprocessor.preprocess(
                factor_panel,
                factors=factor_cols,
                fill_method='median',
                winsorize=True,
                n_std=3.0
            )
            return processed
        except Exception as e:
            print(f"[警告] 预处理失败: {e}")
            return factor_panel

    def _batch_score(
        self,
        factor_panel: pd.DataFrame,
        weights: Dict[str, float] = None
    ) -> List[StockScore]:
        """
        批量打分

        Args:
            factor_panel: 预处理后的因子面板
            weights: 因子权重

        Returns:
            StockScore 列表
        """
        if factor_panel.empty:
            return []

        scores = []

        # 使用selector的批量打分
        # 需要构建stock_data字典
        stock_data = {}
        for symbol in factor_panel.index:
            try:
                df = self.dm.get_daily_kline(symbol, periods=60)
                if df is not None and not df.empty:
                    stock_data[symbol] = df
            except:
                continue

        if not stock_data:
            return []

        # 调用selector的打分
        try:
            raw_scores = self.selector.score_stocks(
                stock_data=stock_data,
                fundamental_factors=factor_panel
            )

            # 如果传了权重，重新计算综合得分
            if weights:
                self.selector.weights.update(weights)
                for score in raw_scores:
                    score.composite_score = (
                        score.momentum_score * self.selector.weights.get('momentum', 0.15) +
                        score.signal_score * self.selector.weights.get('signal', 0.15) +
                        score.volatility_score * self.selector.weights.get('volatility', 0.1) +
                        score.liquidity_score * self.selector.weights.get('liquidity', 0.1) +
                        score.valuation_score * self.selector.weights.get('valuation', 0.2) +
                        score.profitability_score * self.selector.weights.get('profitability', 0.15) +
                        score.growth_score * self.selector.weights.get('growth', 0.1) +
                        score.financial_quality_score * self.selector.weights.get('financial_quality', 0.05)
                    )

            scores = raw_scores

        except Exception as e:
            print(f"[警告] 批量打分失败: {e}")

        return scores

    def _scores_to_dataframe(
        self,
        scores: List[StockScore],
        factor_panel: pd.DataFrame
    ) -> pd.DataFrame:
        """
        将StockScore列表转换为DataFrame
        """
        if not scores:
            return pd.DataFrame()

        rows = []
        for score in scores:
            row = {
                'symbol': score.symbol,
                'name': score.name,
                'rank': score.rank,
                'composite_score': score.composite_score,
                'valuation_score': score.valuation_score,
                'profitability_score': score.profitability_score,
                'growth_score': score.growth_score,
                'momentum_score': score.momentum_score,
                'volatility_score': score.volatility_score,
                'liquidity_score': score.liquidity_score,
                'financial_quality_score': score.financial_quality_score,
                # 原始因子值
                'pe': score.pe,
                'pb': score.pb,
                'roe': score.roe,
                'revenue_growth': score.revenue_growth,
                'signal_type': score.signal_type,
                'signal_strength': score.signal_strength,
            }

            # 从factor_panel补充其他因子值
            if not factor_panel.empty and score.symbol in factor_panel.index:
                for col in factor_panel.columns:
                    if col not in row and col in factor_panel.loc[score.symbol]:
                        row[col] = factor_panel.loc[score.symbol, col]

            rows.append(row)

        df = pd.DataFrame(rows)
        df = df.sort_values('composite_score', ascending=False)
        df['rank'] = range(1, len(df) + 1)

        return df

    def save_scan_result(
        self,
        scan_df: pd.DataFrame,
        scan_date: str = None,
        table_name: str = 'scan_results'
    ) -> int:
        """
        保存扫描结果到数据库

        Args:
            scan_df: 扫描结果DataFrame
            scan_date: 扫描日期
            table_name: 表名

        Returns:
            保存记录数
        """
        if scan_df.empty:
            return 0

        if scan_date is None:
            scan_date = datetime.now().strftime('%Y-%m-%d')

        conn = self.dm.get_db_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in scan_df.iterrows():
            try:
                cursor.execute(f'''
                    INSERT OR REPLACE INTO {table_name}
                    (scan_date, symbol, symbol_name, rank, composite_score,
                     valuation_score, profitability_score, growth_score,
                     momentum_score, liquidity_score, pe, pb, roe, revenue_growth)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    scan_date,
                    row['symbol'],
                    row.get('name', ''),
                    row.get('rank', 0),
                    row.get('composite_score', 0),
                    row.get('valuation_score', 0),
                    row.get('profitability_score', 0),
                    row.get('growth_score', 0),
                    row.get('momentum_score', 0),
                    row.get('liquidity_score', 0),
                    row.get('pe', 0),
                    row.get('pb', 0),
                    row.get('roe', 0),
                    row.get('revenue_growth', 0),
                ))
                records += 1
            except Exception as e:
                continue

        conn.commit()
        return records

    def close(self):
        """关闭连接"""
        try:
            self.dm.close()
            self.ff.close()
        except:
            pass

    def __del__(self):
        try:
            self.close()
        except:
            pass


# ========== 便捷函数 ==========

def scan_market(
    trade_date: str = None,
    top_n: int = 100,
    weights: Dict[str, float] = None
) -> pd.DataFrame:
    """
    便捷的全市场扫描函数

    Args:
        trade_date: 交易日期
        top_n: 返回前N只
        weights: 因子权重

    Returns:
        DataFrame
    """
    scanner = MarketStockScanner()
    result = scanner.scan(trade_date, top_n, weights=weights)
    scanner.close()
    return result


if __name__ == "__main__":
    # 测试
    print("=" * 60)
    print("测试 MarketStockScanner")
    print("=" * 60)

    scanner = MarketStockScanner()

    # 简化测试：用自选股列表
    from portfolio.watchlist import WatchlistManager
    wm = WatchlistManager()
    watchlist = wm.get_all_stocks()

    if watchlist:
        symbols = [s['symbol'] for s in watchlist[:10]]  # 取前10只
        print(f"测试股票: {symbols}")

        # 获取K线数据
        stock_data = scanner._batch_get_kline(symbols, '2024-03-19')
        print(f"获取K线: {len(stock_data)} 只")

        # 计算技术因子
        tech_factors = scanner._calculate_technical_factors(stock_data)
        print(f"技术因子:\n{tech_factors.head()}")

        # 获取基本面因子
        fund_factors = scanner._batch_get_fundamental_factors(symbols, '2024-03-19')
        print(f"基本面因子: {fund_factors.shape}")

    scanner.close()
    print("\n测试完成")