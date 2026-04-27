"""
财务数据获取器 - Baostock 封装
用于获取A股财务报表数据（利润表、资产负债表、现金流量表等）
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sqlite3
import time
import warnings
import traceback
warnings.filterwarnings('ignore')


class FinancialDataSource:
    """
    Baostock 财务数据获取器

    支持的数据类型：
    - 利润表数据 (profit_data)
    - 资产负债表 (balance_data)
    - 现金流量表 (cash_flow_data)
    - 杜邦分析 (dupont_data)
    - 成长能力 (growth_data)
    - 营运能力 (operation_data)
    - 偿债能力 (debtpaying_data)
    - 实时估值 (valuation_data)
    """

    def __init__(self, db_path: str = None):
        """
        初始化财务数据获取器

        Args:
            db_path: SQLite数据库路径，默认使用 Claw 目录下的 quant_data.db
        """
        if db_path is None:
            from pathlib import Path
            # 与 DataManager 保持一致，使用 Claw 目录下的数据库
            db_path = Path(__file__).parent.parent.parent / "quant_data.db"
        self.db_path = str(db_path)

        # Baostock 登录状态
        self._logged_in = False
        self.bs = None
        self._init_baostock()

        # API 限流控制：每分钟最多60次
        self._min_interval = 1.0  # 秒
        self._last_call_time = {}

    def _init_baostock(self):
        """初始化 Baostock 连接"""
        try:
            import baostock as bs
            self.bs = bs
            lg = self.bs.login()
            if lg.error_code == '0':
                self._logged_in = True
                print(f"[OK] Baostock 登录成功")
            else:
                print(f"[!] Baostock 登录失败: {lg.error_msg}")
        except ImportError:
            print("[!] Baostock 未安装，请运行: pip install baostock")
            self.bs = None
        except Exception as e:
            print(f"[!] Baostock 初始化失败: {e}")
            self.bs = None

    def _rate_limit(self, api_name: str):
        """
        API 限流控制

        Args:
            api_name: API 名称，用于区分不同接口
        """
        if api_name not in self._last_call_time:
            self._last_call_time[api_name] = 0

        elapsed = time.time() - self._last_call_time[api_name]
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        self._last_call_time[api_name] = time.time()

    def _ensure_login(self):
        """确保已登录 Baostock"""
        if not self._logged_in:
            self._init_baostock()
        if not self._logged_in:
            raise ConnectionError("Baostock 未登录，请检查 Baostock 安装")

    # ========== 利润表数据 ==========

    def get_profit_data(self, symbol: str, start_year: int = None,
                       end_year: int = None) -> pd.DataFrame:
        """
        获取利润表数据

        Args:
            symbol: 股票代码，如 'sz.000001' 或 '000001.SZ'
            start_year: 起始年份，默认最近3年
            end_year: 结束年份，默认当前年份

        Returns:
            DataFrame with columns: [date, code, roe, npMargin, gpMargin,
                                     opMargin, eps, revenue, income, totalAsset, equity]
        """
        self._ensure_login()
        self._rate_limit('query_profit_data')

        if end_year is None:
            end_year = datetime.now().year
        if start_year is None:
            start_year = end_year - 3

        # 转换代码格式
        bs_code = self._convert_to_baostock_code(symbol)
        if bs_code is None:
            print(f"[!] 无效的股票代码: {symbol}")
            return pd.DataFrame()

        all_data = []
        for year in range(start_year, end_year + 1):
            for quarter in [1, 2, 3, 4]:
                try:
                    rs = self.bs.query_profit_data(
                        code=bs_code,
                        year=str(year),
                        quarter=str(quarter)
                    )

                    if rs.error_code == '0':
                        data_list = []
                        while rs.next():
                            data_list.append(rs.get_row_data())
                        if data_list:
                            df = pd.DataFrame(data_list, columns=rs.fields)
                            all_data.append(df)

                    time.sleep(0.1)  # 避免请求过快

                except Exception as e:
                    print(f"  获取 {symbol} {year}Q{quarter} 利润表失败: {e}")
                    continue

        if not all_data:
            print(f"  {symbol} 利润表数据为空")
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        print(f"  [OK] {symbol} 获取利润表 {len(result)} 条记录")
        return result

    # ========== 资产负债表 ==========

    def get_balance_data(self, symbol: str, start_year: int = None,
                         end_year: int = None) -> pd.DataFrame:
        """
        获取资产负债表数据

        Returns columns: [date, code, totalAsset, totalLiab, equity,
                         assetImpair, specialRisk, accumProfit]
        """
        self._ensure_login()
        self._rate_limit('query_balance_data')

        if end_year is None:
            end_year = datetime.now().year
        if start_year is None:
            start_year = end_year - 3

        bs_code = self._convert_to_baostock_code(symbol)
        if bs_code is None:
            return pd.DataFrame()

        all_data = []
        for year in range(start_year, end_year + 1):
            for quarter in [1, 2, 3, 4]:
                try:
                    rs = self.bs.query_balance_data(
                        code=bs_code,
                        year=str(year),
                        quarter=str(quarter)
                    )

                    if rs.error_code == '0':
                        data_list = []
                        while rs.next():
                            data_list.append(rs.get_row_data())
                        if data_list:
                            df = pd.DataFrame(data_list, columns=rs.fields)
                            all_data.append(df)

                    time.sleep(0.1)

                except Exception as e:
                    print(f"  获取 {symbol} {year}Q{quarter} 资产负债表失败: {e}")
                    continue

        if not all_data:
            print(f"  {symbol} 资产负债表数据为空")
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        print(f"  [OK] {symbol} 获取资产负债表 {len(result)} 条记录")
        return result

    # ========== 现金流量表 ==========

    def get_cash_flow_data(self, symbol: str, start_year: int = None,
                           end_year: int = None) -> pd.DataFrame:
        """
        获取现金流量表数据

        Returns columns: [date, code, operCashFlow, operCashFlowPS,
                         investCashFlow, financeCashFlow]
        """
        self._ensure_login()
        self._rate_limit('query_cash_flow_data')

        if end_year is None:
            end_year = datetime.now().year
        if start_year is None:
            start_year = end_year - 3

        bs_code = self._convert_to_baostock_code(symbol)
        if bs_code is None:
            return pd.DataFrame()

        all_data = []
        for year in range(start_year, end_year + 1):
            for quarter in [1, 2, 3, 4]:
                try:
                    rs = self.bs.query_cash_flow_data(
                        code=bs_code,
                        year=str(year),
                        quarter=str(quarter)
                    )

                    if rs.error_code == '0':
                        data_list = []
                        while rs.next():
                            data_list.append(rs.get_row_data())
                        if data_list:
                            df = pd.DataFrame(data_list, columns=rs.fields)
                            all_data.append(df)

                    time.sleep(0.1)

                except Exception as e:
                    print(f"  获取 {symbol} {year}Q{quarter} 现金流量表失败: {e}")
                    continue

        if not all_data:
            print(f"  {symbol} 现金流量表数据为空")
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        print(f"  [OK] {symbol} 获取现金流量表 {len(result)} 条记录")
        return result

    # ========== 杜邦分析 ==========

    def get_dupont_data(self, symbol: str, start_year: int = None,
                        end_year: int = None) -> pd.DataFrame:
        """
        获取杜邦分析数据

        Returns columns: [date, code, roe, assetStoTurn, equityMultipler,
                         profitToSales, salesToGross]
        """
        self._ensure_login()
        self._rate_limit('query_dupont_data')

        if end_year is None:
            end_year = datetime.now().year
        if start_year is None:
            start_year = end_year - 3

        bs_code = self._convert_to_baostock_code(symbol)
        if bs_code is None:
            return pd.DataFrame()

        all_data = []
        for year in range(start_year, end_year + 1):
            for quarter in [1, 2, 3, 4]:
                try:
                    rs = self.bs.query_dupont_data(
                        code=bs_code,
                        year=str(year),
                        quarter=str(quarter)
                    )

                    if rs.error_code == '0':
                        data_list = []
                        while rs.next():
                            data_list.append(rs.get_row_data())
                        if data_list:
                            df = pd.DataFrame(data_list, columns=rs.fields)
                            all_data.append(df)

                    time.sleep(0.1)

                except Exception as e:
                    print(f"  获取 {symbol} {year}Q{quarter} 杜邦分析失败: {e}")
                    continue

        if not all_data:
            print(f"  {symbol} 杜邦分析数据为空")
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        print(f"  [OK] {symbol} 获取杜邦分析 {len(result)} 条记录")
        return result

    # ========== 成长能力 ==========

    def get_growth_data(self, symbol: str, start_year: int = None,
                        end_year: int = None) -> pd.DataFrame:
        """
        获取成长能力数据

        Returns columns: [date, code, profitGrow, profitGrowRatio, assetToIncome]
        """
        self._ensure_login()
        self._rate_limit('query_growth_data')

        if end_year is None:
            end_year = datetime.now().year
        if start_year is None:
            start_year = end_year - 3

        bs_code = self._convert_to_baostock_code(symbol)
        if bs_code is None:
            return pd.DataFrame()

        all_data = []
        for year in range(start_year, end_year + 1):
            for quarter in [1, 2, 3, 4]:
                try:
                    rs = self.bs.query_growth_data(
                        code=bs_code,
                        year=str(year),
                        quarter=str(quarter)
                    )

                    if rs.error_code == '0':
                        data_list = []
                        while rs.next():
                            data_list.append(rs.get_row_data())
                        if data_list:
                            df = pd.DataFrame(data_list, columns=rs.fields)
                            all_data.append(df)

                    time.sleep(0.1)

                except Exception as e:
                    print(f"  获取 {symbol} {year}Q{quarter} 成长能力失败: {e}")
                    continue

        if not all_data:
            print(f"  {symbol} 成长能力数据为空")
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        print(f"  [OK] {symbol} 获取成长能力 {len(result)} 条记录")
        return result

    # ========== 营运能力 ==========

    def get_operation_data(self, symbol: str, start_year: int = None,
                           end_year: int = None) -> pd.DataFrame:
        """
        获取营运能力数据

        Returns columns: [date, code, invTurnover, arTurnover, apTurnover]
        """
        self._ensure_login()
        self._rate_limit('query_operation_data')

        if end_year is None:
            end_year = datetime.now().year
        if start_year is None:
            start_year = end_year - 3

        bs_code = self._convert_to_baostock_code(symbol)
        if bs_code is None:
            return pd.DataFrame()

        all_data = []
        for year in range(start_year, end_year + 1):
            for quarter in [1, 2, 3, 4]:
                try:
                    rs = self.bs.query_operation_data(
                        code=bs_code,
                        year=str(year),
                        quarter=str(quarter)
                    )

                    if rs.error_code == '0':
                        data_list = []
                        while rs.next():
                            data_list.append(rs.get_row_data())
                        if data_list:
                            df = pd.DataFrame(data_list, columns=rs.fields)
                            all_data.append(df)

                    time.sleep(0.1)

                except Exception as e:
                    print(f"  获取 {symbol} {year}Q{quarter} 营运能力失败: {e}")
                    continue

        if not all_data:
            print(f"  {symbol} 营运能力数据为空")
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        print(f"  [OK] {symbol} 获取营运能力 {len(result)} 条记录")
        return result

    # ========== 偿债能力 ==========
    # 注意：Baostock 没有独立的 query_debtpaying_data 接口
    # 偿债能力指标（流动比率、速动比率、现金比率）包含在 query_balance_data 中
    # 此处保留方法签名以兼容接口，但实际数据从资产负债表获取

    def get_debtpaying_data(self, symbol: str, start_year: int = None,
                            end_year: int = None) -> pd.DataFrame:
        """
        获取偿债能力数据
        
        注意：Baostock 无独立接口，此方法返回空 DataFrame
        偿债能力数据应从 balance_data 中提取
        """
        print(f"  [!] {symbol} 偿债能力数据：Baostock 无独立接口，请从资产负债表获取")
        return pd.DataFrame()

    # ========== 全市场股票列表 ==========

    def get_all_stocks(self) -> List[str]:
        """
        获取所有股票代码列表

        从本地文件加载（沪深300 + 中证500 成分股，共约800只）
        文件路径: quant_system/all_stocks.json

        Returns:
            股票代码列表，如 ['000001.SZ', '600000.SH', ...]
        """
        import json
        from pathlib import Path

        # 尝试从文件加载
        file_path = Path(__file__).parent.parent / "all_stocks.json"

        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    symbols = json.load(f)
                print(f"  [OK] 从文件加载 {len(symbols)} 只股票")
                return symbols
        except Exception as e:
            print(f"  加载股票列表文件失败: {e}")

        # 如果文件不存在或加载失败，尝试用 Baostock 获取
        self._ensure_login()
        self._rate_limit('query_all_stock')

        try:
            # 获取沪深300
            hs300 = self._query_index_stocks('hs300')
            # 获取中证500
            zz500 = self._query_index_stocks('zz500')
            # 获取上证50
            sz50 = self._query_index_stocks('sz50')

            symbols = list(set(hs300 + zz500 + sz50))
            print(f"  [OK] 获取全市场 {len(symbols)} 只股票（沪深300+中证500+上证50）")
            return symbols

        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []

    def _query_index_stocks(self, index: str) -> List[str]:
        """
        获取指数成分股

        Args:
            index: 'hs300', 'zz500', 'sz50'

        Returns:
            股票代码列表
        """
        query_funcs = {
            'hs300': self.bs.query_hs300_stocks,
            'zz500': self.bs.query_zz500_stocks,
            'sz50': self.bs.query_sz50_stocks,
        }

        if index not in query_funcs:
            return []

        rs = query_funcs[index]()
        if rs.error_code != '0':
            return []

        symbols = []
        while rs.next():
            data = rs.get_row_data()
            code = data[1]  # 格式如 'sh.600000'
            if code.startswith('sh.'):
                symbols.append(f"{code[3:]}.SH")
            elif code.startswith('sz.'):
                symbols.append(f"{code[3:]}.SZ")

        return symbols

    # ========== 全市场估值数据 ==========

    def get_all_stocks_valuation(self) -> pd.DataFrame:
        """
        获取所有股票的实时估值数据

        通过 query_history_k_data_plus 遍历获取单只股票数据
        由于是日频数据，每天只返回一条记录

        Returns columns: [symbol, trade_date, pe_ttm, pb, ps, pcf, close]
        """
        self._ensure_login()

        # 获取全市场股票列表
        symbols = self.get_all_stocks()
        if not symbols:
            print("股票列表为空")
            return pd.DataFrame()

        all_data = []
        today = datetime.now().strftime('%Y-%m-%d')

        for i, symbol in enumerate(symbols):
            self._rate_limit('query_history_k_data')

            try:
                bs_code = self._convert_to_baostock_code(symbol)
                if bs_code is None:
                    continue

                rs = self.bs.query_history_k_data_plus(
                    bs_code,
                    "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM",
                    start_date=today,
                    end_date=today,
                    frequency="d",
                    adjustflag="3"
                )

                if rs.error_code == '0':
                    data_list = []
                    while rs.next():
                        data_list.append(rs.get_row_data())

                    if data_list:
                        df = pd.DataFrame(data_list, columns=rs.fields)
                        df['symbol'] = symbol
                        df = df.rename(columns={
                            'peTTM': 'pe_ttm',
                            'pbMRQ': 'pb',
                            'psTTM': 'ps',
                            'pcfNcfTTM': 'pcf'
                        })
                        # 数值类型转换
                        for col in ['close', 'pe_ttm', 'pb', 'ps', 'pcf']:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        all_data.append(df)

                if (i + 1) % 100 == 0:
                    print(f"  进度: {i+1}/{len(symbols)}")

                time.sleep(0.1)  # 避免请求过快

            except Exception as e:
                continue

        if not all_data:
            print("未获取到任何估值数据")
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        print(f"  [OK] 获取全市场 {len(result)} 只股票估值数据")
        return result

    # ========== 单只股票历史估值数据 ==========

    def get_history_valuation(self, symbol: str,
                              start_date: str = None,
                              end_date: str = None) -> pd.DataFrame:
        """
        获取单只股票的历史估值数据

        Args:
            symbol: 股票代码，如 '600000.SH'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'

        Returns:
            DataFrame with columns: [trade_date, symbol, close, pe_ttm, pb, ps, pcf]
        """
        self._ensure_login()
        self._rate_limit('query_history_k_data')

        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if start_date is None:
            start_date = end_date

        bs_code = self._convert_to_baostock_code(symbol)
        if bs_code is None:
            return pd.DataFrame()

        try:
            rs = self.bs.query_history_k_data_plus(
                bs_code,
                "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"
            )

            if rs.error_code != '0':
                return pd.DataFrame()

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return pd.DataFrame()

            df = pd.DataFrame(data_list, columns=rs.fields)
            df['symbol'] = symbol

            # 重命名字段
            df = df.rename(columns={
                'date': 'trade_date',
                'peTTM': 'pe_ttm',
                'pbMRQ': 'pb',
                'psTTM': 'ps',
                'pcfNcfTTM': 'pcf'
            })

            # 数值类型转换
            for col in ['close', 'pe_ttm', 'pb', 'ps', 'pcf']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            return df

        except Exception as e:
            return pd.DataFrame()

    # ========== 股票基本信息 ==========

    def get_stock_info(self, symbol: str = None) -> pd.DataFrame:
        """
        获取股票基本信息

        Args:
            symbol: 股票代码，不传则获取全市场

        Returns columns: [baostock_code, name, ipoDate, outDate, stock_type, status, symbol]
        """
        self._ensure_login()
        self._rate_limit('query_stocks')

        try:
            rs = self.bs.query_stocks()

            if rs.error_code != '0':
                print(f"获取股票信息失败: {rs.error_msg}")
                return pd.DataFrame()

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return pd.DataFrame()

            df = pd.DataFrame(data_list, columns=rs.fields)

            # 转换代码格式
            df['symbol'] = df['code'].apply(self._convert_from_baostock_code)

            # 筛选指定股票
            if symbol:
                bs_code = self._convert_to_baostock_code(symbol)
                df = df[df['code'] == bs_code]

            df = df.rename(columns={
                'code': 'baostock_code',
                'code_name': 'name',
                'ipoDate': 'list_date',
                'outDate': 'delist_date',
                'stock_type': 'stock_type'
            })

            return df

        except Exception as e:
            print(f"获取股票信息失败: {e}")
            return pd.DataFrame()

    # ========== 辅助方法 ==========

    def _convert_to_baostock_code(self, symbol: str) -> Optional[str]:
        """
        将标准股票代码转换为 Baostock 格式

        Examples:
            '000001.SZ' -> 'sz.000001'
            '600000.SH' -> 'sh.600000'
            '000001.SZ' -> 'sz.000001'
        """
        if not symbol:
            return None

        symbol = symbol.upper()

        if symbol.endswith('.SZ'):
            return f"sz.{symbol[:-3]}"
        elif symbol.endswith('.SH'):
            return f"sh.{symbol[:-3]}"
        elif symbol.endswith('.BJ'):
            return f"bj.{symbol[:-3]}"
        elif symbol.startswith('6') or symbol.startswith('9'):
            return f"sh.{symbol}"
        else:
            return f"sz.{symbol}"

    def _convert_from_baostock_code(self, bs_code: str) -> str:
        """
        将 Baostock 代码转换为标准格式

        Examples:
            'sz.000001' -> '000001.SZ'
            'sh.600000' -> '600000.SH'
        """
        if not bs_code or '.' not in bs_code:
            return bs_code

        prefix, number = bs_code.split('.', 1)

        if prefix == 'sh':
            return f"{number}.SH"
        elif prefix == 'sz':
            return f"{number}.SZ"
        elif prefix == 'bj':
            return f"{number}.BJ"
        else:
            return bs_code

    def logout(self):
        """登出 Baostock"""
        if self._logged_in and self.bs:
            try:
                self.bs.logout()
                self._logged_in = False
                print("[OK] Baostock 已登出")
            except:
                pass

    def __del__(self):
        """析构时确保登出"""
        self.logout()


# ========== 便捷函数 ==========

def get_financial_data_simple(symbol: str, data_type: str = 'profit') -> pd.DataFrame:
    """
    便捷函数：获取单只股票的单类财务数据

    Args:
        symbol: 股票代码，如 '000001.SZ'
        data_type: 数据类型 ('profit'/'balance'/'cash'/'dupont'/'growth'/'operation'/'debtpaying')

    Returns:
        DataFrame
    """
    source = FinancialDataSource()

    if data_type == 'profit':
        return source.get_profit_data(symbol)
    elif data_type == 'balance':
        return source.get_balance_data(symbol)
    elif data_type == 'cash':
        return source.get_cash_flow_data(symbol)
    elif data_type == 'dupont':
        return source.get_dupont_data(symbol)
    elif data_type == 'growth':
        return source.get_growth_data(symbol)
    elif data_type == 'operation':
        return source.get_operation_data(symbol)
    elif data_type == 'debtpaying':
        return source.get_debtpaying_data(symbol)
    else:
        print(f"未知数据类型: {data_type}")
        return pd.DataFrame()


if __name__ == "__main__":
    # 测试 Baostock 连接和数据获取
    print("=" * 60)
    print("测试 Baostock 财务数据获取")
    print("=" * 60)

    source = FinancialDataSource()

    # 测试获取利润表
    print("\n[测试] 获取 000001.SZ 利润表数据...")
    df = source.get_profit_data('000001.SZ', start_year=2023, end_year=2024)
    if not df.empty:
        print(f"获取成功: {len(df)} 条记录")
        print(df.head())

    # 测试获取全市场估值
    print("\n[测试] 获取全市场估值数据...")
    df = source.get_all_stocks_valuation()
    if not df.empty:
        print(f"获取成功: {len(df)} 只股票")
        print(df.head())

    source.logout()
