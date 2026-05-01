"""
基本面因子计算模块
从财务数据计算估值、盈利、成长、财务结构、现金流等因子
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import sqlite3
import warnings
warnings.filterwarnings('ignore')

try:
    from data.financial_data_manager import FinancialDataManager
except ImportError:
    # 如果是相对导入失败，尝试绝对导入
    from quant_system.data.financial_data_manager import FinancialDataManager


class FundamentalFactors:
    """
    基本面因子计算器

    从数据库财务数据计算各类基本面因子：
    - 估值因子：PE、PB、PS、PCF
    - 盈利因子：ROE、ROA、毛利率、净利率
    - 成长因子：营收增长率、利润增长率
    - 财务结构因子：资产负债率、流动比率
    - 现金流因子：经营现金流/净利润
    """

    # 因子元数据：类别、方向、计算公式说明
    FACTOR_METADATA = {
        # 估值因子（低估值买入）
        'pe': {'category': 'valuation', 'direction': 'negative', 'description': '市盈率'},
        'pe_ttm': {'category': 'valuation', 'direction': 'negative', 'description': '滚动市盈率'},
        'pb': {'category': 'valuation', 'direction': 'negative', 'description': '市净率'},
        'ps': {'category': 'valuation', 'direction': 'negative', 'description': '市销率'},
        'pcf': {'category': 'valuation', 'direction': 'negative', 'description': '市现率'},

        # 盈利因子（高盈利买入）
        'roe': {'category': 'profitability', 'direction': 'positive', 'description': '净资产收益率'},
        'roe_avg': {'category': 'profitability', 'direction': 'positive', 'description': '平均净资产收益率'},
        'roa': {'category': 'profitability', 'direction': 'positive', 'description': '资产收益率'},
        'gross_margin': {'category': 'profitability', 'direction': 'positive', 'description': '毛利率'},
        'net_margin': {'category': 'profitability', 'direction': 'positive', 'description': '净利率'},
        'eps_ttm': {'category': 'profitability', 'direction': 'positive', 'description': '每股收益TTM'},

        # 成长因子（高成长买入）
        'revenue_growth': {'category': 'growth', 'direction': 'positive', 'description': '营收增长率'},
        'profit_growth': {'category': 'growth', 'direction': 'positive', 'description': '利润增长率'},
        'equity_growth': {'category': 'growth', 'direction': 'positive', 'description': '净资产增长率'},
        'profit_cagr': {'category': 'growth', 'direction': 'positive', 'description': '净利润复合增长率'},

        # 财务结构因子（适中偏好）
        'debt_ratio': {'category': 'structure', 'direction': 'neutral', 'description': '资产负债率'},
        'current_ratio': {'category': 'structure', 'direction': 'positive', 'description': '流动比率'},
        'quick_ratio': {'category': 'structure', 'direction': 'positive', 'description': '速动比率'},

        # 现金流因子（现金流优良买入）
        'cash_to_profit': {'category': 'cashflow', 'direction': 'positive', 'description': '经营现金流/净利润'},
        'fcf': {'category': 'cashflow', 'direction': 'positive', 'description': '自由现金流'},
        'cash_yield': {'category': 'cashflow', 'direction': 'positive', 'description': '现金市值比'},

        # 杜邦分析因子
        'asset_turnover': {'category': 'profitability', 'direction': 'positive', 'description': '资产周转率'},
        'equity_multiplier': {'category': 'structure', 'direction': 'neutral', 'description': '权益乘数'},
    }

    def __init__(self, db_path: str = None):
        """
        初始化基本面因子计算器

        Args:
            db_path: 数据库路径，默认使用项目根目录下的 quant_data.db
        """
        self.fdm = FinancialDataManager(db_path)

    def calculate_all_factors(self, symbol: str, trade_date: str = None) -> Dict[str, float]:
        """
        计算某只股票的所有基本面因子

        Args:
            symbol: 股票代码，如 '000001.SZ'
            trade_date: 交易日期，默认今天

        Returns:
            {因子名: 因子值} 字典
        """
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        factors = {}

        # 1. 获取财务数据（按报告期降序，取最新可用）
        profit = self.fdm.get_profit(symbol)
        balance = self.fdm.get_balance(symbol)
        cash_flow = self.fdm.get_cash_flow(symbol)
        dupont = self.fdm.get_dupont(symbol)
        valuation = self.fdm.get_valuation(symbol)

        # 2. 获取最新价格（用于计算估值因子）
        price = self._get_price(symbol, trade_date)

        # 3. 计算各类因子
        factors.update(self._calc_valuation_factors(price, valuation, profit))
        factors.update(self._calc_profitability_factors(profit, balance, dupont))
        factors.update(self._calc_growth_factors(profit, balance))
        factors.update(self._calc_structure_factors(balance))
        factors.update(self._calc_cashflow_factors(cash_flow, profit, valuation))

        # 4. 计算衍生因子
        factors.update(self._calc_derived_factors(factors, dupont))

        return factors

    def _get_price(self, symbol: str, trade_date: str) -> float:
        """获取指定日期的收盘价"""
        conn = sqlite3.connect(self.fdm.db_path)
        query = '''
            SELECT close FROM daily_kline
            WHERE symbol = ? AND date <= ?
            ORDER BY date DESC LIMIT 1
        '''
        try:
            df = pd.read_sql_query(query, conn, params=(symbol, trade_date))
            conn.close()
            if not df.empty:
                return float(df['close'].iloc[0])
        except Exception as e:
            conn.close()

        # 如果没有K线数据，尝试从估值数据估算
        valuation = self.fdm.get_valuation(symbol)
        if valuation and valuation.get('market_cap') and valuation.get('total_shares'):
            try:
                shares = float(valuation['total_shares'])
                if shares > 0:
                    market_cap = float(valuation['market_cap'])
                    return market_cap / shares
            except:
                pass

        return 0.0

    def _get_latest_value(self, df: pd.DataFrame, col: str, periods: int = 4) -> float:
        """
        获取最近N期数据的中位数（更稳健）

        Args:
            df: 财务数据DataFrame
            col: 列名
            periods: 期数

        Returns:
            中位数或0
        """
        if df.empty or col not in df.columns:
            return 0.0

        values = df[col].dropna().head(periods)
        if len(values) == 0:
            return 0.0
        return float(values.median())

    def _get_yoy_growth(self, df: pd.DataFrame, col: str) -> float:
        """
        计算同比增长率

        Args:
            df: 财务数据DataFrame（按日期降序）
            col: 列名

        Returns:
            同比增长率（今年/去年-1）
        """
        if df.empty or col not in df.columns:
            return 0.0

        values = df[col].dropna().head(4)  # 最近4期
        if len(values) < 2:
            return 0.0

        try:
            current = float(values.iloc[0])  # 最新一期
            prior = float(values.iloc[1])   # 去年同期

            if prior != 0 and not np.isnan(prior):
                return (current / prior) - 1.0
        except:
            pass

        return 0.0

    def _calc_valuation_factors(self, price: float, valuation: Dict = None,
                                profit: pd.DataFrame = None) -> Dict[str, float]:
        """计算估值因子"""
        factors = {}

        if valuation is None:
            valuation = {}

        # 从估值表获取
        pe = valuation.get('pe') or valuation.get('pe_ttm')
        pb = valuation.get('pb')
        ps = valuation.get('ps')
        pcf = valuation.get('pcf')
        market_cap = valuation.get('market_cap')

        # EPS（从利润表计算）
        eps = 0.0
        if profit is not None and not profit.empty:
            try:
                net_profit = self._get_latest_value(profit, 'net_profit', 4)
                # 需要总股本，这里用估值表的
                if valuation and valuation.get('total_shares'):
                    total_shares = float(valuation['total_shares'])
                    if total_shares > 0:
                        eps = net_profit / total_shares
            except:
                pass

        # 如果有价格但没有估值数据，尝试从利润表计算
        if price > 0:
            if eps == 0.0 and profit is not None:
                try:
                    net_profit_ttm = self._get_latest_value(profit, 'net_profit', 4)
                    if valuation and valuation.get('total_shares'):
                        total_shares = float(valuation['total_shares'])
                        if total_shares > 0:
                            eps = net_profit_ttm / total_shares
                except:
                    pass

            # 用价格和EPS计算PE
            if pe is None and eps > 0:
                pe = price / eps

        factors['pe'] = float(pe) if pe and not np.isnan(float(pe)) else 0.0
        factors['pe_ttm'] = factors['pe']
        factors['pb'] = float(pb) if pb and not np.isnan(float(pb)) else 0.0
        factors['ps'] = float(ps) if ps and not np.isnan(float(ps)) else 0.0
        factors['pcf'] = float(pcf) if pcf and not np.isnan(float(pcf)) else 0.0

        return factors

    def _calc_profitability_factors(self, profit: pd.DataFrame = None,
                                    balance: pd.DataFrame = None,
                                    dupont: pd.DataFrame = None) -> Dict[str, float]:
        """计算盈利因子"""
        factors = {}

        if profit is None:
            profit = pd.DataFrame()
        if balance is None:
            balance = pd.DataFrame()
        if dupont is None:
            dupont = pd.DataFrame()

        # ROE（净资产收益率）
        if not dupont.empty and 'roe' in dupont.columns:
            factors['roe'] = self._get_latest_value(dupont, 'roe', 4)
            factors['roe_avg'] = self._get_latest_value(dupont, 'roe', 4)
        elif not profit.empty and not balance.empty:
            try:
                net_profit = self._get_latest_value(profit, 'net_profit', 4)
                equity = self._get_latest_value(balance, 'total_equity', 4)
                if equity and equity > 0:
                    factors['roe'] = net_profit / equity
                    factors['roe_avg'] = factors['roe']
            except:
                factors['roe'] = 0.0
                factors['roe_avg'] = 0.0
        else:
            factors['roe'] = 0.0
            factors['roe_avg'] = 0.0

        # ROA（资产收益率）
        if not profit.empty and not balance.empty:
            try:
                net_profit = self._get_latest_value(profit, 'net_profit', 4)
                total_assets = self._get_latest_value(balance, 'total_assets', 4)
                if total_assets and total_assets > 0:
                    factors['roa'] = net_profit / total_assets
                else:
                    factors['roa'] = 0.0
            except:
                factors['roa'] = 0.0
        else:
            factors['roa'] = 0.0

        # 毛利率
        if not profit.empty:
            factors['gross_margin'] = self._get_latest_value(profit, 'gross_profit_rate', 4)
            factors['net_margin'] = self._get_latest_value(profit, 'net_profit_ratio', 4)
            factors['eps_ttm'] = self._get_latest_value(profit, 'eps', 4)
        else:
            factors['gross_margin'] = 0.0
            factors['net_margin'] = 0.0
            factors['eps_ttm'] = 0.0

        # 资产周转率（杜邦分析）
        if not dupont.empty and 'asset_turnover' in dupont.columns:
            factors['asset_turnover'] = self._get_latest_value(dupont, 'asset_turnover', 4)
        else:
            factors['asset_turnover'] = 0.0

        return factors

    def _calc_growth_factors(self, profit: pd.DataFrame = None,
                            balance: pd.DataFrame = None) -> Dict[str, float]:
        """计算成长因子"""
        factors = {}

        if profit is None:
            profit = pd.DataFrame()
        if balance is None:
            balance = pd.DataFrame()

        # 营收增长率
        if not profit.empty and 'business_income' in profit.columns:
            factors['revenue_growth'] = self._get_yoy_growth(profit, 'business_income')
        else:
            factors['revenue_growth'] = 0.0

        # 利润增长率
        if not profit.empty and 'net_profit' in profit.columns:
            factors['profit_growth'] = self._get_yoy_growth(profit, 'net_profit')
        else:
            factors['profit_growth'] = 0.0

        # 净资产增长率
        if not balance.empty and 'total_equity' in balance.columns:
            factors['equity_growth'] = self._get_yoy_growth(balance, 'total_equity')
        else:
            factors['equity_growth'] = 0.0

        # 净利润复合增长率（CAGR 3年）
        if not profit.empty and 'net_profit' in profit.columns:
            factors['profit_cagr'] = self._calc_cagr(profit, 'net_profit', 4)  # 约4期=1年
        else:
            factors['profit_cagr'] = 0.0

        return factors

    def _calc_cagr(self, df: pd.DataFrame, col: str, periods: int = 4) -> float:
        """
        计算复合年增长率

        Args:
            df: DataFrame
            col: 列名
            periods: 期数

        Returns:
            CAGR
        """
        if df.empty or col not in df.columns:
            return 0.0

        values = df[col].dropna().head(periods * 3)  # 最多3年数据
        if len(values) < 2:
            return 0.0

        try:
            start_value = float(values.iloc[-1])  # 最早
            end_value = float(values.iloc[0])    # 最新
            n_years = len(values) / 4  # 假设每年4期

            if start_value > 0 and end_value > 0 and n_years > 0:
                cagr = (end_value / start_value) ** (1 / n_years) - 1
                return float(cagr)
        except:
            pass

        return 0.0

    def _calc_structure_factors(self, balance: pd.DataFrame = None) -> Dict[str, float]:
        """计算财务结构因子"""
        factors = {}

        if balance is None:
            balance = pd.DataFrame()

        if not balance.empty:
            # 资产负债率
            factors['debt_ratio'] = self._get_latest_value(balance, 'debt_ratio', 4)

            # 流动比率
            factors['current_ratio'] = self._get_latest_value(balance, 'current_ratio', 4)

            # 速动比率
            factors['quick_ratio'] = self._get_latest_value(balance, 'quick_ratio', 4)

            # 权益乘数（杜邦数据）
            # 从balance_data的equity_ratio反推
            equity_ratio = self._get_latest_value(balance, 'equity_ratio', 4)
            if equity_ratio and equity_ratio > 0:
                factors['equity_multiplier'] = 1.0 / equity_ratio
            else:
                factors['equity_multiplier'] = 0.0
        else:
            factors['debt_ratio'] = 0.0
            factors['current_ratio'] = 0.0
            factors['quick_ratio'] = 0.0
            factors['equity_multiplier'] = 0.0

        return factors

    def _calc_cashflow_factors(self, cash_flow: pd.DataFrame = None,
                               profit: pd.DataFrame = None,
                               valuation: Dict = None) -> Dict[str, float]:
        """计算现金流因子"""
        factors = {}

        if cash_flow is None:
            cash_flow = pd.DataFrame()
        if profit is None:
            profit = pd.DataFrame()
        if valuation is None:
            valuation = {}

        if not cash_flow.empty:
            # 经营现金流/净利润（盈利质量）
            try:
                oper_cf = self._get_latest_value(cash_flow, 'oper_cash_flow', 4)
                net_profit = self._get_latest_value(profit, 'net_profit', 4)
                if net_profit and net_profit > 0:
                    factors['cash_to_profit'] = oper_cf / net_profit
                else:
                    factors['cash_to_profit'] = 0.0
            except:
                factors['cash_to_profit'] = 0.0

            # 自由现金流（简化：经营现金流）
            factors['fcf'] = self._get_latest_value(cash_flow, 'oper_cash_flow', 4)
        else:
            factors['cash_to_profit'] = 0.0
            factors['fcf'] = 0.0

        # 现金市值比
        if valuation and valuation.get('market_cap'):
            try:
                market_cap = float(valuation['market_cap'])
                if market_cap > 0 and factors['fcf'] != 0:
                    factors['cash_yield'] = factors['fcf'] / market_cap
                else:
                    factors['cash_yield'] = 0.0
            except:
                factors['cash_yield'] = 0.0
        else:
            factors['cash_yield'] = 0.0

        return factors

    def _calc_derived_factors(self, factors: Dict[str, float],
                             dupont: pd.DataFrame = None) -> Dict[str, float]:
        """计算衍生因子"""
        derived = {}

        # PB_ROE = PB / ROE（成长价值因子）
        if factors.get('roe') and factors['roe'] > 0 and factors.get('pb'):
            derived['pb_roe'] = factors['pb'] / factors['roe']
        else:
            derived['pb_roe'] = 0.0

        # PE_Growth = PE / 利润增长率（PEG的倒数）
        if factors.get('profit_growth') and factors['profit_growth'] > -0.99:
            derived['pe_growth'] = factors.get('pe', 0) / (factors['profit_growth'] + 1)
        else:
            derived['pe_growth'] = 0.0

        # Altman Z-Score（简化版）
        # Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
        # X1 = 营运资本/总资产 = (current_assets - current_liabilities) / total_assets
        # X2 = 留存收益/总资产
        # X3 = EBIT/总资产 ≈ ROA
        # X4 = 股权市值/总负债
        # X5 = 销售收入/总资产 = asset_turnover
        try:
            if dupont is not None and not dupont.empty:
                asset_turnover = self._get_latest_value(dupont, 'asset_turnover', 4)
            else:
                asset_turnover = factors.get('asset_turnover', 0)

            roa = factors.get('roa', 0)
            equity_multiplier = factors.get('equity_multiplier', 0)
            debt_ratio = factors.get('debt_ratio', 0)

            x1 = 0  # 简化
            x2 = 0  # 简化
            x3 = roa
            x4 = equity_multiplier if debt_ratio > 0 else 0
            x5 = asset_turnover

            derived['altman_z'] = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
        except:
            derived['altman_z'] = 0.0

        return derived

    def get_factor_panel(self, symbols: List[str],
                         trade_date: str = None) -> pd.DataFrame:
        """
        获取多只股票在某日期的因子面板数据

        Args:
            symbols: 股票列表
            trade_date: 交易日期

        Returns:
            DataFrame(index=symbol, columns=因子名)
        """
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        rows = []
        for symbol in symbols:
            try:
                factors = self.calculate_all_factors(symbol, trade_date)
                factors['symbol'] = symbol
                factors['trade_date'] = trade_date
                rows.append(factors)
            except Exception as e:
                print(f"计算 {symbol} 因子失败: {e}")
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df.set_index('symbol', inplace=True)
        return df

    def get_factor_values(self, symbols: List[str] = None,
                         factor_names: List[str] = None,
                         trade_date: str = None) -> pd.DataFrame:
        """
        从数据库缓存读取因子值

        Args:
            symbols: 股票列表，None表示全部
            factor_names: 因子名列表，None表示全部
            trade_date: 交易日期

        Returns:
            DataFrame
        """
        conn = sqlite3.connect(self.fdm.db_path)

        query = 'SELECT * FROM factor_values WHERE 1=1'
        params = []

        if trade_date:
            query += ' AND trade_date = ?'
            params.append(trade_date)

        if symbols:
            placeholders = ','.join(['?' for _ in symbols])
            query += f' AND symbol IN ({placeholders})'
            params.extend(symbols)

        if factor_names:
            placeholders = ','.join(['?' for _ in factor_names])
            query += f' AND factor_name IN ({placeholders})'
            params.extend(factor_names)

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            print(f"读取因子缓存失败: {e}")
            df = pd.DataFrame()

        conn.close()
        return df

    def save_factor_values(self, df: pd.DataFrame, trade_date: str = None) -> int:
        """
        保存因子值到数据库缓存

        Args:
            df: DataFrame，包含 symbol, factor_name, factor_value 列
            trade_date: 交易日期

        Returns:
            保存记录数
        """
        if df.empty:
            return 0

        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(self.fdm.db_path)
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO factor_values
                    (symbol, trade_date, factor_name, factor_value, update_time)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    row.get('symbol', ''),
                    trade_date,
                    row.get('factor_name', row.get('factor', '')),
                    row.get('factor_value', row.get('value', 0)),
                ))
                records += 1
            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    def close(self):
        """关闭连接"""
        self.fdm.close()

    def __del__(self):
        """析构时确保关闭"""
        try:
            self.close()
        except:
            pass


# ========== 便捷函数 ==========

def calculate_factors(symbol: str, trade_date: str = None) -> Dict[str, float]:
    """
    计算单只股票的基本面因子

    Args:
        symbol: 股票代码
        trade_date: 交易日期

    Returns:
        {因子名: 因子值} 字典
    """
    ff = FundamentalFactors()
    factors = ff.calculate_all_factors(symbol, trade_date)
    ff.close()
    return factors


def get_factor_panel(symbols: List[str], trade_date: str = None) -> pd.DataFrame:
    """
    获取多只股票的基本面因子面板

    Args:
        symbols: 股票列表
        trade_date: 交易日期

    Returns:
        DataFrame
    """
    ff = FundamentalFactors()
    df = ff.get_factor_panel(symbols, trade_date)
    ff.close()
    return df


if __name__ == "__main__":
    print("=" * 60)
    print("测试 FundamentalFactors")
    print("=" * 60)

    ff = FundamentalFactors()

    # 测试1: 计算单只股票因子
    print("\n[测试1] 计算 000001.SZ 基本面因子...")
    factors = ff.calculate_all_factors('000001.SZ')
    print("因子结果:")
    for name, value in factors.items():
        if value != 0:
            print(f"  {name}: {value:.4f}")

    # 测试2: 批量获取因子面板
    print("\n[测试2] 获取多只股票因子面板...")
    symbols = ['000001.SZ', '600000.SH', '600519.SH']
    panel = ff.get_factor_panel(symbols)
    if not panel.empty:
        print(panel[['pe', 'pb', 'roe', 'revenue_growth']].head())

    ff.close()
    print("\n测试完成")