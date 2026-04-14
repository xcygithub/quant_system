"""
财务数据持久化类
将财务数据保存到 SQLite 数据库
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
import sqlite3
import warnings
warnings.filterwarnings('ignore')


class FinancialDataSaver:
    """
    财务数据保存到数据库

    提供从 DataFrame 到 SQLite 的批量保存功能
    """

    def __init__(self, db_path: str = None):
        """
        初始化财务数据持久化器

        Args:
            db_path: SQLite数据库路径，默认使用 Claw 目录下的 quant_data.db
        """
        if db_path is None:
            from pathlib import Path
            # 与 DataManager 保持一致，使用 Claw 目录下的数据库
            db_path = Path(__file__).parent.parent.parent / "quant_data.db"
        self.db_path = str(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接

        Returns:
            sqlite3.Connection
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _to_float(value) -> float:
        """
        安全转换为浮点数

        Args:
            value: 待转换的值

        Returns:
            float，转换失败返回 0.0
        """
        if value is None or value == '' or value == '-' or str(value).strip() == '':
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _get_report_type(report_date: str) -> str:
        """
        根据报告期判断报表类型

        Args:
            report_date: 报告期，如 '2024-03-31'

        Returns:
            'A' = 年报, 'M' = 中报, 'Q' = 季报
        """
        if not report_date or len(report_date) < 5:
            return 'Q'
        if '-12-31' in report_date:
            return 'A'  # 年报
        elif '-06-30' in report_date:
            return 'M'  # 中报
        else:
            return 'Q'  # 季报

    # ========== 利润表保存 ==========

    def save_profit_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """
        保存利润表数据

        Args:
            df: DataFrame from FinancialDataSource.get_profit_data()
            symbol: 股票代码

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                # Baostock 返回的字段是 statDate（统计日期）而不是 date
                report_date = row.get('statDate', '') or row.get('date', '')
                if not report_date:
                    continue

                report_type = self._get_report_type(report_date)

                cursor.execute('''
                    INSERT OR REPLACE INTO profit_data
                    (symbol, report_date, report_type, eps, roe, roe_avg,
                     net_profit_ratio, gross_profit_rate, business_income,
                     operating_profit, net_profit, total_profit, inv_net_profit,
                     pub_date, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol or row.get('symbol', ''),
                    report_date,
                    report_type,
                    self._to_float(row.get('epsTTM', 0)),  # 每股收益TTM
                    self._to_float(row.get('roeAvg', 0)),    # 净资产收益率(平均)
                    self._to_float(row.get('roeAvg', 0)),    # 净资产收益率(摊薄)用平均代替
                    self._to_float(row.get('npMargin', 0)),  # 净利率
                    self._to_float(row.get('gpMargin', 0)), # 毛利率
                    self._to_float(row.get('MBRevenue', 0)),  # 营业收入(主营业务收入)
                    0,                                        # 营业利润
                    self._to_float(row.get('netProfit', 0)), # 净利润
                    0,                                        # 利润总额
                    0,                                        # 扣非净利润
                    row.get('pubDate', ''),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 资产负债表保存 ==========

    def save_balance_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """
        保存资产负债表数据

        Args:
            df: DataFrame from FinancialDataSource.get_balance_data()
            symbol: 股票代码

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                report_date = row.get('date', '')
                if not report_date:
                    continue

                report_type = self._get_report_type(report_date)

                cursor.execute('''
                    INSERT OR REPLACE INTO balance_data
                    (symbol, report_date, report_type, total_assets, total_liabilities,
                     total_equity, debt_ratio, equity_ratio, current_assets,
                     fixed_assets, intangible_assets, current_ratio, quick_ratio,
                     update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol or row.get('symbol', ''),
                    report_date,
                    report_type,
                    self._to_float(row.get('totalAsset', 0)),
                    self._to_float(row.get('totalLiab', 0)),
                    self._to_float(row.get('equity', 0)),
                    self._to_float(row.get('debtRatio', 0)),
                    self._to_float(row.get('equityRatio', 0)),
                    self._to_float(row.get('currAsset', 0)),
                    self._to_float(row.get('fixedAsset', 0)),
                    self._to_float(row.get('intangibleAsset', 0)),
                    self._to_float(row.get('currentRatio', 0)),
                    self._to_float(row.get('quickRatio', 0)),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 现金流量表保存 ==========

    def save_cash_flow_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """
        保存现金流量表数据

        Args:
            df: DataFrame from FinancialDataSource.get_cash_flow_data()
            symbol: 股票代码

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                report_date = row.get('date', '')
                if not report_date:
                    continue

                cursor.execute('''
                    INSERT OR REPLACE INTO cash_flow_data
                    (symbol, report_date, oper_cash_flow, invest_cash_flow,
                     finance_cash_flow, cash_equil_change, end_cash,
                     oper_cash_flow_ps, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol or row.get('symbol', ''),
                    report_date,
                    self._to_float(row.get('operCashFlow', 0)),
                    self._to_float(row.get('investCashFlow', 0)),
                    self._to_float(row.get('financeCashFlow', 0)),
                    self._to_float(row.get('cashEquilChange', 0)),
                    self._to_float(row.get('endCash', 0)),
                    self._to_float(row.get('operCashFlowPS', 0)),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 杜邦分析保存 ==========

    def save_dupont_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """
        保存杜邦分析数据

        Args:
            df: DataFrame from FinancialDataSource.get_dupont_data()
            symbol: 股票代码

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                report_date = row.get('date', '')
                if not report_date:
                    continue

                cursor.execute('''
                    INSERT OR REPLACE INTO dupont_data
                    (symbol, report_date, roe, asset_turnover, equity_multiplier,
                     net_profit_margin, sales_to_grs, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol or row.get('symbol', ''),
                    report_date,
                    self._to_float(row.get('roe', 0)),
                    self._to_float(row.get('assetStoTurn', 0)),
                    self._to_float(row.get('equityMultipler', 0)),
                    self._to_float(row.get('profitToSales', 0)),
                    self._to_float(row.get('salesToGross', 0)),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 成长能力保存 ==========

    def save_growth_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """
        保存成长能力数据

        Args:
            df: DataFrame from FinancialDataSource.get_growth_data()
            symbol: 股票代码

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                report_date = row.get('date', '')
                if not report_date:
                    continue

                report_type = self._get_report_type(report_date)

                cursor.execute('''
                    INSERT OR REPLACE INTO growth_data
                    (symbol, report_date, report_type, profit_grow,
                     profit_grow_ratio, asset_to_income, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol or row.get('symbol', ''),
                    report_date,
                    report_type,
                    self._to_float(row.get('profitGrow', 0)),
                    self._to_float(row.get('profitGrowRatio', 0)),
                    self._to_float(row.get('assetToIncome', 0)),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 营运能力保存 ==========

    def save_operation_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """
        保存营运能力数据

        Args:
            df: DataFrame from FinancialDataSource.get_operation_data()
            symbol: 股票代码

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                report_date = row.get('date', '')
                if not report_date:
                    continue

                report_type = self._get_report_type(report_date)

                cursor.execute('''
                    INSERT OR REPLACE INTO operation_data
                    (symbol, report_date, report_type, inv_turnover,
                     ar_turnover, ap_turnover, total_asset_turnover,
                     current_asset_turnover, fixed_asset_turnover, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol or row.get('symbol', ''),
                    report_date,
                    report_type,
                    self._to_float(row.get('invTurnover', 0)),
                    self._to_float(row.get('arTurnover', 0)),
                    self._to_float(row.get('apTurnover', 0)),
                    self._to_float(row.get('totalAssetTurnover', 0)),
                    self._to_float(row.get('currAssetTurnover', 0)),
                    self._to_float(row.get('fixedAssetTurnover', 0)),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 偿债能力保存 ==========

    def save_debtpaying_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """
        保存偿债能力数据

        Args:
            df: DataFrame from FinancialDataSource.get_debtpaying_data()
            symbol: 股票代码

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                report_date = row.get('date', '')
                if not report_date:
                    continue

                report_type = self._get_report_type(report_date)

                cursor.execute('''
                    INSERT OR REPLACE INTO debtpaying_data
                    (symbol, report_date, report_type, current_ratio,
                     quick_ratio, cash_ratio, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol or row.get('symbol', ''),
                    report_date,
                    report_type,
                    self._to_float(row.get('currentRatio', 0)),
                    self._to_float(row.get('quickRatio', 0)),
                    self._to_float(row.get('cashRatio', 0)),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 估值数据批量保存 ==========

    def save_valuation_data(self, df: pd.DataFrame, trade_date: str = None) -> int:
        """
        批量保存估值数据

        Args:
            df: DataFrame from FinancialDataSource.get_all_stocks_valuation()
            trade_date: 交易日期

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                symbol = row.get('symbol', '')
                if not symbol:
                    continue

                cursor.execute('''
                    INSERT OR REPLACE INTO valuation_data
                    (symbol, trade_date, pe, pe_ttm, pb, ps, pcf,
                     market_cap, float_market_cap, total_shares, float_shares,
                     update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol,
                    trade_date,
                    self._to_float(row.get('pe', 0)),
                    self._to_float(row.get('pe_ttm', 0)),
                    self._to_float(row.get('pb', 0)),
                    self._to_float(row.get('ps', 0)),
                    self._to_float(row.get('pcf', 0)),
                    self._to_float(row.get('market_cap', 0)),
                    self._to_float(row.get('float_market_cap', 0)),
                    self._to_float(row.get('total_shares', 0)),
                    self._to_float(row.get('float_shares', 0)),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 股票信息保存 ==========

    def save_stock_info(self, df: pd.DataFrame) -> int:
        """
        保存股票基本信息

        Args:
            df: DataFrame from FinancialDataSource.get_stock_info()

        Returns:
            保存的记录数
        """
        if df.empty:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        records = 0
        for _, row in df.iterrows():
            try:
                symbol = row.get('symbol', '')
                if not symbol:
                    continue

                cursor.execute('''
                    INSERT OR REPLACE INTO stock_info
                    (symbol, name, industry, market, list_date, update_time)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    symbol,
                    row.get('name', ''),
                    '',  # industry 需要从其他接口获取
                    row.get('stock_type', ''),
                    row.get('list_date', ''),
                ))
                records += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()
        return records

    # ========== 批量保存（统一入口）==========

    def save_all(self, data_dict: Dict[str, pd.DataFrame], symbol: str = None) -> Dict[str, int]:
        """
        批量保存多种财务数据

        Args:
            data_dict: 字典，key 为数据类型，value 为 DataFrame
                       如 {'profit': df1, 'balance': df2, 'cash': df3}
            symbol: 股票代码

        Returns:
            每种类型的保存记录数
        """
        results = {}

        for data_type, df in data_dict.items():
            if df.empty:
                results[data_type] = 0
                continue

            if data_type == 'profit':
                results[data_type] = self.save_profit_data(df, symbol)
            elif data_type == 'balance':
                results[data_type] = self.save_balance_data(df, symbol)
            elif data_type == 'cash':
                results[data_type] = self.save_cash_flow_data(df, symbol)
            elif data_type == 'dupont':
                results[data_type] = self.save_dupont_data(df, symbol)
            elif data_type == 'growth':
                results[data_type] = self.save_growth_data(df, symbol)
            elif data_type == 'operation':
                results[data_type] = self.save_operation_data(df, symbol)
            elif data_type == 'debtpaying':
                results[data_type] = self.save_debtpaying_data(df, symbol)
            elif data_type == 'valuation':
                results[data_type] = self.save_valuation_data(df)
            elif data_type == 'stock_info':
                results[data_type] = self.save_stock_info(df)
            else:
                results[data_type] = 0

        return results


if __name__ == "__main__":
    # 测试数据保存
    from pathlib import Path

    db_path = Path(__file__).parent.parent / "quant_data.db"
    saver = FinancialDataSaver(str(db_path))

    print(f"数据库路径: {saver.db_path}")
    print("FinancialDataSaver 初始化成功")
