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
import logging
warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

try:
    from data.financial_data_manager import FinancialDataManager
    from data.factor_manager import FactorManager
except ImportError:
    # 如果是相对导入失败，尝试绝对导入
    from quant_system.data.financial_data_manager import FinancialDataManager
    from quant_system.data.factor_manager import FactorManager


class FundamentalFactors:
    """
    基本面因子计算器

    从数据库财务数据计算各类基本面因子：
    - 估值因子：PE、PB、PS、PCF
    - 盈利因子：ROE、毛利率、净利率
    - 成长因子：利润增长率、净资产增长率
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
        'gross_margin': {'category': 'profitability', 'direction': 'positive', 'description': '毛利率'},
        'net_margin': {'category': 'profitability', 'direction': 'positive', 'description': '净利率'},
        'np_margin': {'category': 'profitability', 'direction': 'positive', 'description': '销售净利率'},
        'gp_margin': {'category': 'profitability', 'direction': 'positive', 'description': '销售毛利率'},
        'eps_ttm': {'category': 'profitability', 'direction': 'positive', 'description': '每股收益TTM'},
        'roa': {'category': 'profitability', 'direction': 'positive', 'description': '总资产收益率'},
        'net_profit': {'category': 'profitability', 'direction': 'positive', 'description': '净利润'},
        'mb_revenue': {'category': 'profitability', 'direction': 'positive', 'description': '主营业务收入'},
        'total_share': {'category': 'profitability', 'direction': 'neutral', 'description': '总股本'},
        'liqa_share': {'category': 'profitability', 'direction': 'neutral', 'description': '流通股本'},

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

    def _get_disclosure_cutoff_date(self, trade_date: str) -> str:
        """
        根据交易日推断理论可用的财报截止日期。

        口径（A股）：
        - 1~4 月：上年 Q3
        - 5~8 月：当年 Q1
        - 9~10 月：当年 Q2
        - 11~12 月：当年 Q3
        """
        trade_dt = pd.to_datetime(trade_date)
        year = trade_dt.year
        month = trade_dt.month
        if month <= 4:
            return f"{year - 1}-09-30"
        if month <= 8:
            return f"{year}-03-31"
        if month <= 10:
            return f"{year}-06-30"
        return f"{year}-09-30"

    def _clip_financial_df_by_report_date(self, df: pd.DataFrame, report_date: str) -> pd.DataFrame:
        """按 report_date 截断财务 DataFrame。"""
        if df is None or df.empty:
            return pd.DataFrame()
        if "report_date" not in df.columns:
            return df
        clipped = df.copy()
        clipped["report_date"] = pd.to_datetime(clipped["report_date"], errors="coerce")
        cutoff = pd.to_datetime(report_date, errors="coerce")
        clipped = clipped[clipped["report_date"] <= cutoff]
        if clipped.empty:
            return pd.DataFrame()
        return clipped.sort_values("report_date", ascending=False).reset_index(drop=True)

    def _previous_quarter_end(self, report_date: str) -> str:
        """获取上一季度报告期。"""
        report_dt = pd.to_datetime(report_date)
        month_map = {
            3: (report_dt.year - 1, 12, 31),
            6: (report_dt.year, 3, 31),
            9: (report_dt.year, 6, 30),
            12: (report_dt.year, 9, 30),
        }
        year, month, day = month_map.get(report_dt.month, (report_dt.year - 1, 12, 31))
        return f"{year:04d}-{month:02d}-{day:02d}"

    def get_report_publish_date(self, symbol: str, report_date: str, lag_days: int = 45) -> str:
        """
        获取报告期对应的可用发布日期。

        优先使用 profit_data.pub_date；若无，则退化为 report_date + lag_days。
        """
        # 注意：必须用 try/finally 关闭连接。
        # 早期写法把 conn.close() 放在 try 内部、异常被 except 吞掉，
        # 一旦查询失败（例如老库缺少 pub_date 列）就会泄漏一个 sqlite 连接，
        # 在长驻的桌面客户端里会持续累积，Windows 下还会锁住 db 文件。
        conn = None
        try:
            conn = sqlite3.connect(self.fdm.db_path)
            row = conn.execute(
                """
                SELECT pub_date FROM profit_data
                WHERE symbol = ? AND report_date = ? AND pub_date IS NOT NULL AND TRIM(pub_date) != ''
                ORDER BY pub_date DESC
                LIMIT 1
                """,
                (symbol, report_date),
            ).fetchone()
            if row and row[0]:
                pub_dt = pd.to_datetime(str(row[0]), errors="coerce")
                if pd.notna(pub_dt):
                    return pub_dt.strftime("%Y-%m-%d")
        except Exception:
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        fallback_dt = pd.to_datetime(report_date, errors="coerce")
        if pd.isna(fallback_dt):
            fallback_dt = pd.to_datetime("2015-03-31")
        return (fallback_dt + pd.Timedelta(days=lag_days)).strftime("%Y-%m-%d")

    def _get_latest_report_date_from_db(self, trade_date: str, symbol: str = None) -> Optional[str]:
        """
        从数据库中获取查询日期之前最新可用的财报截止日期。

        Args:
            trade_date: 查询日期，格式 YYYY-MM-DD
            symbol: 股票代码，None 表示不限制股票

        Returns:
            财报截止日期或 None
        """
        conn = sqlite3.connect(self.fdm.db_path)
        cursor = conn.cursor()
        tables = ['profit_data', 'balance_data', 'cash_flow_data', 'dupont_data']
        latest_dates: List[str] = []
        try:
            for table_name in tables:
                if symbol:
                    query = f'''
                        SELECT MAX(report_date) FROM {table_name}
                        WHERE symbol = ? AND report_date <= ?
                    '''
                    row = cursor.execute(query, (symbol, trade_date)).fetchone()
                else:
                    query = f'''
                        SELECT MAX(report_date) FROM {table_name}
                        WHERE report_date <= ?
                    '''
                    row = cursor.execute(query, (trade_date,)).fetchone()
                if row and row[0]:
                    latest_dates.append(str(row[0]))
        finally:
            conn.close()

        if not latest_dates:
            return None
        return max(latest_dates)

    def get_report_date(self, trade_date: str, symbol: str = None, lag_days: int = 45) -> str:
        """
        根据查询日期返回最近可用财报截止日期。

        Args:
            trade_date: 查询日期，格式 YYYY-MM-DD
            symbol: 股票代码，优先按该股票在数据库中的可用财报日期判断
            lag_days: 财报可用滞后天数，默认 45 天

        Returns:
            财报截止日期，格式 YYYY-MM-DD
        """
        # 1) 优先按披露窗口推断截止日，再在库里找 <= 截止日的最近财报
        #    重点：1~4月默认优先上年Q3，避免年报未披露时因子大面积为0。
        cutoff_date = self._get_disclosure_cutoff_date(trade_date)
        latest_report_date = self._get_latest_report_date_from_db(cutoff_date, symbol)
        if latest_report_date:
            # 严格防止前视：若该报告尚未披露，回退到上一季度
            if symbol:
                trade_dt = pd.to_datetime(trade_date)
                guard = 0
                while latest_report_date and guard < 16:
                    pub_date = self.get_report_publish_date(symbol, latest_report_date, lag_days=lag_days)
                    pub_dt = pd.to_datetime(pub_date, errors="coerce")
                    if pd.notna(pub_dt) and pub_dt <= trade_dt:
                        break
                    latest_report_date = self._previous_quarter_end(latest_report_date)
                    guard += 1
            return latest_report_date

        # 2) 若该股票无数据，再尝试全市场维度
        if symbol:
            latest_report_date = self._get_latest_report_date_from_db(cutoff_date, None)
            if latest_report_date:
                return latest_report_date

        # 3) 再放宽到“交易日前最近财报”
        latest_report_date = self._get_latest_report_date_from_db(trade_date, symbol)
        if latest_report_date:
            return latest_report_date
        if symbol:
            latest_report_date = self._get_latest_report_date_from_db(trade_date, None)
            if latest_report_date:
                return latest_report_date

        # 4) 最后兜底：使用固定滞后规则推断
        trade_dt = pd.to_datetime(trade_date)
        earliest_year = 2015
        latest_year = trade_dt.year + 1
        report_dates: List[pd.Timestamp] = []

        for year in range(earliest_year, latest_year + 1):
            report_dates.extend([
                pd.Timestamp(f"{year}-03-31"),
                pd.Timestamp(f"{year}-06-30"),
                pd.Timestamp(f"{year}-09-30"),
                pd.Timestamp(f"{year}-12-31"),
            ])

        available_reports = [
            report_dt for report_dt in report_dates
            if report_dt + pd.Timedelta(days=lag_days) <= trade_dt
        ]

        if not available_reports:
            # 数据不足时兜底到最早可用季度，避免返回未来日期
            return f"{earliest_year}-03-31"

        return max(available_reports).strftime('%Y-%m-%d')

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
        report_date = self.get_report_date(trade_date, symbol)

        factors = {}

        # 1. 获取财务数据（只使用指定财报截止日期及之前的数据）
        profit = self.fdm.get_financial_data(symbol, data_type='profit', end_date=report_date)
        balance = self.fdm.get_financial_data(symbol, data_type='balance', end_date=report_date)
        cash_flow = self.fdm.get_financial_data(symbol, data_type='cash', end_date=report_date)
        dupont = self.fdm.get_financial_data(symbol, data_type='dupont', end_date=report_date)
        growth = self.fdm.get_financial_data(symbol, data_type='growth', end_date=report_date)
        valuation = self.fdm.get_valuation(symbol, trade_date)

        # 2. 获取最新价格（用于计算估值因子）
        price = self._get_price(symbol, trade_date)

        # 3. 计算各类因子
        factors.update(self._calc_valuation_factors(price, valuation, profit))
        factors.update(self._calc_profitability_factors(profit, balance, dupont))
        factors.update(self._calc_growth_factors(profit, balance, growth))
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
            logger.warning(
                "读取价格失败: symbol=%s trade_date=%s error_type=%s error=%s",
                symbol, trade_date, type(e).__name__, e
            )

        # 如果没有K线数据，尝试从估值数据估算
        valuation = self.fdm.get_valuation(symbol)
        if valuation and valuation.get('market_cap') and valuation.get('total_shares'):
            try:
                shares = float(valuation['total_shares'])
                if shares > 0:
                    market_cap = float(valuation['market_cap'])
                    return market_cap / shares
            except Exception as e:
                logger.debug(
                    "估值换算价格失败: symbol=%s error_type=%s error=%s",
                    symbol, type(e).__name__, e
                )

        return 0.0

    def _fetch_table_by_symbols(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        symbols: List[str],
        date_col: str,
        end_date: str
    ) -> Dict[str, pd.DataFrame]:
        """批量读取某张表在指定日期前的数据，并按 symbol 分组。"""
        if not symbols:
            return {}

        placeholders = ','.join(['?' for _ in symbols])
        query = f"""
            SELECT * FROM {table_name}
            WHERE symbol IN ({placeholders}) AND {date_col} <= ?
            ORDER BY symbol, {date_col} DESC
        """
        params = symbols + [end_date]
        df = pd.read_sql_query(query, conn, params=params)
        if df.empty:
            return {}
        return {symbol: group.copy() for symbol, group in df.groupby('symbol')}

    def _fetch_latest_valuation_by_symbols(
        self,
        conn: sqlite3.Connection,
        symbols: List[str],
        trade_date: str
    ) -> Dict[str, Dict]:
        """批量读取估值表在指定交易日前的最新一条记录。"""
        if not symbols:
            return {}
        placeholders = ','.join(['?' for _ in symbols])
        query = f"""
            SELECT v1.*
            FROM valuation_data v1
            WHERE v1.symbol IN ({placeholders})
              AND v1.trade_date = (
                  SELECT MAX(v2.trade_date)
                  FROM valuation_data v2
                  WHERE v2.symbol = v1.symbol AND v2.trade_date <= ?
              )
        """
        params = symbols + [trade_date]
        df = pd.read_sql_query(query, conn, params=params)
        if df.empty:
            return {}
        return {row['symbol']: row.to_dict() for _, row in df.iterrows()}

    def _fetch_latest_price_by_symbols(
        self,
        conn: sqlite3.Connection,
        symbols: List[str],
        trade_date: str
    ) -> Dict[str, float]:
        """批量读取 K 线在指定交易日前的最新收盘价。"""
        if not symbols:
            return {}
        placeholders = ','.join(['?' for _ in symbols])
        query = f"""
            SELECT k1.symbol, k1.close
            FROM daily_kline k1
            WHERE k1.symbol IN ({placeholders})
              AND k1.date = (
                  SELECT MAX(k2.date)
                  FROM daily_kline k2
                  WHERE k2.symbol = k1.symbol AND k2.date <= ?
              )
        """
        params = symbols + [trade_date]
        df = pd.read_sql_query(query, conn, params=params)
        if df.empty:
            return {}
        return {row['symbol']: float(row['close']) for _, row in df.iterrows()}

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

        # 严格按“去年同期”计算，不再误用“上一期”。
        # 若最新一期字段为空/为0，则向前寻找最近可计算的季度。
        if 'report_date' not in df.columns:
            return 0.0

        try:
            work_df = df.copy()
            work_df['report_date'] = pd.to_datetime(work_df['report_date'], errors='coerce')
            work_df = work_df.dropna(subset=['report_date']).sort_values('report_date', ascending=False)
            if work_df.empty:
                return 0.0

            for _, current_row in work_df.iterrows():
                current = float(current_row[col]) if pd.notna(current_row[col]) else 0.0
                if current == 0 or np.isnan(current):
                    continue

                current_date = current_row['report_date']
                prior_date = current_date - pd.DateOffset(years=1)
                prior_row = work_df[work_df['report_date'] == prior_date]
                if prior_row.empty:
                    continue
                prior = float(prior_row.iloc[0][col]) if pd.notna(prior_row.iloc[0][col]) else 0.0

                if prior != 0 and not np.isnan(prior):
                    return (current / prior) - 1.0
        except Exception as e:
            logger.debug(
                "同比增长率计算失败: col=%s error_type=%s error=%s",
                col, type(e).__name__, e
            )

        return 0.0

    def _get_latest_non_zero(self, df: pd.DataFrame, col: str) -> float:
        """
        获取最近一期非零值（按 report_date 倒序）。
        """
        if df.empty or col not in df.columns:
            return 0.0
        try:
            work_df = df.copy()
            if 'report_date' in work_df.columns:
                work_df['report_date'] = pd.to_datetime(work_df['report_date'], errors='coerce')
                work_df = work_df.dropna(subset=['report_date']).sort_values('report_date', ascending=False)
            series = pd.to_numeric(work_df[col], errors='coerce').dropna()
            for value in series:
                value = float(value)
                if value != 0 and not np.isnan(value):
                    return value
        except Exception as e:
            logger.debug(
                "最新非零值计算失败: col=%s error_type=%s error=%s",
                col, type(e).__name__, e
            )
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

        factors['pe'] = float(pe) if pe and not np.isnan(float(pe)) else 0.0
        pe_ttm = valuation.get('pe_ttm')
        factors['pe_ttm'] = float(pe_ttm) if pe_ttm and not np.isnan(float(pe_ttm)) else factors['pe']
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
        dupont_roe = 0.0
        if not dupont.empty and 'roe' in dupont.columns:
            dupont_roe = self._get_latest_value(dupont, 'roe', 4)

        # 杜邦 ROE 为 0 时，回退利润表 ROE，避免“有数据却显示无数据”
        if dupont_roe != 0:
            factors['roe'] = dupont_roe
            factors['roe_avg'] = dupont_roe
        elif not profit.empty and 'roe' in profit.columns:
            roe_profit = self._get_latest_value(profit, 'roe', 4)
            factors['roe'] = roe_profit
            factors['roe_avg'] = roe_profit
        elif not profit.empty and not balance.empty:
            try:
                net_profit = self._get_latest_value(profit, 'net_profit', 4)
                equity = self._get_latest_value(balance, 'total_equity', 4)
                if equity and equity > 0:
                    factors['roe'] = net_profit / equity
                    factors['roe_avg'] = factors['roe']
            except Exception as e:
                logger.warning(
                    "盈利因子计算失败: factor=roe error_type=%s error=%s",
                    type(e).__name__, e
                )
                factors['roe'] = 0.0
                factors['roe_avg'] = 0.0
        else:
            factors['roe'] = 0.0
            factors['roe_avg'] = 0.0

        # 毛利率
        if not profit.empty:
            factors['gross_margin'] = self._get_latest_value(profit, 'gross_profit_rate', 4)
            factors['net_margin'] = self._get_latest_value(profit, 'net_profit_ratio', 4)
            # 与 Baostock 字段命名保持一致的别名
            factors['np_margin'] = factors['net_margin']
            factors['gp_margin'] = factors['gross_margin']
            factors['eps_ttm'] = self._get_latest_value(profit, 'eps', 4)
            factors['net_profit'] = self._get_latest_value(profit, 'net_profit', 4)
            factors['mb_revenue'] = self._get_latest_value(profit, 'business_income', 4)
            factors['total_share'] = self._get_latest_value(profit, 'total_share', 1)
            factors['liqa_share'] = self._get_latest_value(profit, 'liqa_share', 1)

            # ROA = 净利润 / 总资产
            total_assets = self._get_latest_value(balance, 'total_assets', 4) if not balance.empty else 0.0
            if total_assets > 0:
                factors['roa'] = self._get_latest_value(profit, 'net_profit', 4) / total_assets
            else:
                factors['roa'] = 0.0
        else:
            factors['gross_margin'] = 0.0
            factors['net_margin'] = 0.0
            factors['np_margin'] = 0.0
            factors['gp_margin'] = 0.0
            factors['eps_ttm'] = 0.0
            factors['roa'] = 0.0
            factors['net_profit'] = 0.0
            factors['mb_revenue'] = 0.0
            factors['total_share'] = 0.0
            factors['liqa_share'] = 0.0

        # 资产周转率（杜邦分析）
        if not dupont.empty and 'asset_turnover' in dupont.columns:
            factors['asset_turnover'] = self._get_latest_value(dupont, 'asset_turnover', 4)
        else:
            factors['asset_turnover'] = 0.0

        return factors

    def _calc_growth_factors(self, profit: pd.DataFrame = None,
                            balance: pd.DataFrame = None,
                            growth: pd.DataFrame = None) -> Dict[str, float]:
        """计算成长因子"""
        factors = {}

        if profit is None:
            profit = pd.DataFrame()
        if balance is None:
            balance = pd.DataFrame()
        if growth is None:
            growth = pd.DataFrame()

        # 利润增长率（优先使用 growth_data 的净利润同比，取最新可用）
        if not growth.empty and 'profit_grow' in growth.columns:
            factors['profit_growth'] = self._get_latest_non_zero(growth, 'profit_grow')
        elif not profit.empty and 'net_profit' in profit.columns:
            factors['profit_growth'] = self._get_yoy_growth(profit, 'net_profit')
        else:
            factors['profit_growth'] = 0.0

        # 营收增长率（优先使用利润表营业收入同比）
        if not profit.empty and 'business_income' in profit.columns:
            factors['revenue_growth'] = self._get_yoy_growth(profit, 'business_income')
        elif not growth.empty and 'profit_grow_ratio' in growth.columns:
            # 保底：无收入字段时，用 growth_data 的辅助同比字段
            factors['revenue_growth'] = self._get_latest_non_zero(growth, 'profit_grow_ratio')
        else:
            factors['revenue_growth'] = 0.0

        # 净资产增长率（优先使用 growth_data 的净资产同比，取最新可用）
        if not growth.empty and 'asset_to_income' in growth.columns:
            factors['equity_growth'] = self._get_latest_non_zero(growth, 'asset_to_income')
        elif not balance.empty and 'total_equity' in balance.columns:
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
        except Exception as e:
            logger.debug(
                "CAGR 计算失败: col=%s error_type=%s error=%s",
                col, type(e).__name__, e
            )

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
            cfo_to_np = self._get_latest_value(cash_flow, 'cfo_to_np', 4) if 'cfo_to_np' in cash_flow.columns else 0.0

            # 经营现金流/净利润（优先使用接口直接返回的 CFOToNP 比率）
            if cfo_to_np and cfo_to_np != 0:
                factors['cash_to_profit'] = cfo_to_np
            else:
                try:
                    oper_cf = self._get_latest_value(cash_flow, 'oper_cash_flow', 4)
                    net_profit = self._get_latest_value(profit, 'net_profit', 4)
                    if net_profit and net_profit > 0:
                        factors['cash_to_profit'] = oper_cf / net_profit
                    else:
                        factors['cash_to_profit'] = 0.0
                except Exception as e:
                    logger.warning(
                        "现金流因子计算失败: factor=cash_to_profit error_type=%s error=%s",
                        type(e).__name__, e
                    )
                    factors['cash_to_profit'] = 0.0
        else:
            factors['cash_to_profit'] = 0.0

        return factors

    def _calc_derived_factors(self, factors: Dict[str, float],
                             dupont: pd.DataFrame = None) -> Dict[str, float]:
        """计算衍生因子"""
        derived = {}

        # PB/ROE/ROE
        if factors.get('roe') and factors['roe'] > 0 and factors.get('pb'):
            roe_pct = factors['roe'] * 100.0
            derived['pb_roe_roe'] = factors['pb'] / (roe_pct * roe_pct)
        else:
            derived['pb_roe_roe'] = 0.0

        # PE/ROE
        if factors.get('roe') and factors['roe'] > 0 and factors.get('pe'):
            roe_pct = factors['roe'] * 100.0
            derived['pe_roe'] = factors['pe'] / roe_pct
        else:
            derived['pe_roe'] = 0.0

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
        return self.calculate_factor_panel(symbols, trade_date)

    def calculate_factor_panel(self, symbols: List[str], trade_date: str = None) -> pd.DataFrame:
        """
        批量计算因子面板（按 symbols + 日期批量读取，避免逐股 N+1 查询）。
        """
        if not symbols:
            return pd.DataFrame()
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(self.fdm.db_path)
        try:
            # 先拉取到 trade_date，再按股票逐只按 report_date 截断
            profit_map = self._fetch_table_by_symbols(conn, 'profit_data', symbols, 'report_date', trade_date)
            balance_map = self._fetch_table_by_symbols(conn, 'balance_data', symbols, 'report_date', trade_date)
            cash_map = self._fetch_table_by_symbols(conn, 'cash_flow_data', symbols, 'report_date', trade_date)
            dupont_map = self._fetch_table_by_symbols(conn, 'dupont_data', symbols, 'report_date', trade_date)
            growth_map = self._fetch_table_by_symbols(conn, 'growth_data', symbols, 'report_date', trade_date)
            valuation_map = self._fetch_latest_valuation_by_symbols(conn, symbols, trade_date)
            price_map = self._fetch_latest_price_by_symbols(conn, symbols, trade_date)
        finally:
            conn.close()

        rows = []
        empty_df = pd.DataFrame()
        for symbol in symbols:
            report_date = self.get_report_date(trade_date, symbol)
            profit = self._clip_financial_df_by_report_date(profit_map.get(symbol, empty_df), report_date)
            balance = self._clip_financial_df_by_report_date(balance_map.get(symbol, empty_df), report_date)
            cash_flow = self._clip_financial_df_by_report_date(cash_map.get(symbol, empty_df), report_date)
            dupont = self._clip_financial_df_by_report_date(dupont_map.get(symbol, empty_df), report_date)
            growth = self._clip_financial_df_by_report_date(growth_map.get(symbol, empty_df), report_date)
            valuation = valuation_map.get(symbol, {})
            price = price_map.get(symbol, 0.0)

            factors: Dict[str, float] = {}
            factors.update(self._calc_valuation_factors(price, valuation, profit))
            factors.update(self._calc_profitability_factors(profit, balance, dupont))
            factors.update(self._calc_growth_factors(profit, balance, growth))
            factors.update(self._calc_structure_factors(balance))
            factors.update(self._calc_cashflow_factors(cash_flow, profit, valuation))
            factors.update(self._calc_derived_factors(factors, dupont))
            factors['symbol'] = symbol
            factors['trade_date'] = trade_date
            rows.append(factors)

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
            return df
        except Exception as e:
            logger.warning(
                "读取因子缓存失败: symbols_count=%s factor_names_count=%s trade_date=%s error_type=%s error=%s",
                len(symbols) if symbols else 0,
                len(factor_names) if factor_names else 0,
                trade_date,
                type(e).__name__,
                e
            )
            return pd.DataFrame()
        finally:
            conn.close()

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

        work_df = df.copy()
        if "trade_date" not in work_df.columns:
            work_df["trade_date"] = trade_date
        if "factor_name" not in work_df.columns and "factor" in work_df.columns:
            work_df["factor_name"] = work_df["factor"]
        if "factor_value" not in work_df.columns and "value" in work_df.columns:
            work_df["factor_value"] = work_df["value"]
        if "factor_value" in work_df.columns:
            work_df["factor_value"] = pd.to_numeric(work_df["factor_value"], errors="coerce")

        manager = FactorManager(self.fdm.db_path)
        return manager.save_factor_values(work_df)

    def close(self):
        """关闭连接"""
        self.fdm.close()

    def __del__(self):
        """析构时确保关闭"""
        try:
            self.close()
        except Exception:
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
        print(panel[['pe', 'pb', 'roe', 'profit_growth']].head())

    ff.close()
    print("\n测试完成")