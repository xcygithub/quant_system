# Phase 1 详细设计：Baostock 财务数据获取与存储

## 一、概述

Phase 1 的目标是建立完整的财务数据管道：
1. 从 Baostock 获取财务报表数据
2. 存储到本地 SQLite 数据库
3. 提供统一的数据访问接口

---

## 二、数据库 Schema 设计

### 2.1 扩展现有表结构

在 `data_manager.py` 的 `_init_database()` 方法中新增以下表：

```python
# ===== 1. 股票基础信息表（扩展）=====
cursor.execute('''
    CREATE TABLE IF NOT EXISTS stock_info (
        symbol TEXT PRIMARY KEY,
        name TEXT,
        industry TEXT,          -- 所属行业
        market TEXT,            -- 市场（SH/SZ/BJ）
        list_date TEXT,         -- 上市日期
        is_hs300 INTEGER DEFAULT 0,  -- 是否沪深300成分
        is_zz500 INTEGER DEFAULT 0,  -- 是否中证500成分
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# ===== 2. 盈利能力数据（利润表）=====
cursor.execute('''
    CREATE TABLE IF NOT EXISTS profit_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,     -- 报告期，如 2024-03-31
        report_type TEXT DEFAULT 'Q', -- 报表类型：Q=季报, M=中报, A=年报
        eps REAL,                      -- 每股收益（元）
        roe REAL,                      -- 净资产收益率（%）
        roe_avg REAL,                  -- 净资产收益率（摊薄，%）
        net_profit_ratio REAL,         -- 净利率（%）
        gross_profit_rate REAL,        -- 毛利率（%）
        business_income REAL,          -- 营业收入（万元）
        operating_profit REAL,        -- 营业利润（万元）
        net_profit REAL,               -- 净利润（万元）
        total_profit REAL,             -- 利润总额（万元）
        inv_net_profit REAL,          -- 扣除非经常性损益后净利润（万元）
        pub_date TEXT,                 -- 公报时间
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, report_date)
    )
''')

# ===== 3. 资产负债数据（资产负债表）=====
cursor.execute('''
    CREATE TABLE IF NOT EXISTS balance_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,
        report_type TEXT DEFAULT 'Q',
        total_assets REAL,             -- 总资产（万元）
        total_liabilities REAL,        -- 总负债（万元）
        total_equity REAL,             -- 所有者权益合计（万元）
        debt_ratio REAL,              -- 资产负债率（%）
        equity_ratio REAL,             -- 产权比率
        current_assets REAL,           -- 流动资产合计（万元）
        fixed_assets REAL,            -- 固定资产合计（万元）
        intangible_assets REAL,        -- 无形资产（万元）
        current_ratio REAL,            -- 流动比率
        quick_ratio REAL,              -- 速动比率
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, report_date)
    )
''')

# ===== 4. 现金流量数据（现金流量表）=====
cursor.execute('''
    CREATE TABLE IF NOT EXISTS cash_flow_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,
        report_type TEXT DEFAULT 'Q',
        oper_cash_flow REAL,           -- 经营活动现金流（万元）
        invest_cash_flow REAL,         -- 投资活动现金流（万元）
        finance_cash_flow REAL,        -- 筹资活动现金流（万元）
        cash_equil_change REAL,        -- 现金及等价物净增加额（万元）
        end_cash REAL,                 -- 期末现金（万元）
        oper_cash_flow_ps REAL,        -- 每股经营现金流（元）
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, report_date)
    )
''')

# ===== 5. 杜邦分析数据 ======
cursor.execute('''
    CREATE TABLE IF NOT EXISTS dupont_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,
        report_type TEXT DEFAULT 'Q',
        roe REAL,                      -- 净资产收益率（%）
        asset_turnover REAL,           -- 资产周转率（次）
        equity_multiplier REAL,        -- 权益乘数
        net_profit_margin REAL,        -- 销售净利率（%）
        sales_to_grs REAL,             -- 销售毛利率（%）
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, report_date)
    )
''')

# ===== 6. 成长能力数据 ======
cursor.execute('''
    CREATE TABLE IF NOT EXISTS growth_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,
        report_type TEXT DEFAULT 'Q',
        profit_grow REAL,              -- 利润总额增长率（%）
        profit_grow_ratio REAL,        -- 净利润增长率（%）
        asset_to_income REAL,          -- 资产驱动力（%）
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, report_date)
    )
''')

# ===== 7. 营运能力数据 ======
cursor.execute('''
    CREATE TABLE IF NOT EXISTS operation_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,
        report_type TEXT DEFAULT 'Q',
        inv_turnover REAL,             -- 存货周转率（次）
        ar_turnover REAL,              -- 应收账款周转率（次）
        ap_turnover REAL,              -- 应付账款周转率（次）
        total_asset_turnover REAL,     -- 总资产周转率（次）
        current_asset_turnover REAL,   -- 流动资产周转率（次）
        fixed_asset_turnover REAL,     -- 固定资产周转率（次）
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, report_date)
    )
''')

# ===== 8. 偿债能力数据 ======
cursor.execute('''
    CREATE TABLE IF NOT EXISTS debtpaying_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        report_date TEXT NOT NULL,
        report_type TEXT DEFAULT 'Q',
        current_ratio REAL,            -- 流动比率
        quick_ratio REAL,              -- 速动比率
        cash_ratio REAL,               -- 现金比率（%）
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, report_date)
    )
''')

# ===== 9. 估值数据（每日更新）=====
cursor.execute('''
    CREATE TABLE IF NOT EXISTS valuation_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        trade_date TEXT NOT NULL,      -- 交易日期
        pe REAL,                       -- 市盈率（TTM）
        pe_ttm REAL,                   -- 市盈率（TTM）
        pb REAL,                       -- 市净率
        ps REAL,                       -- 市销率（TTM）
        pcf REAL,                      -- 现金流倍率
        market_cap REAL,               -- 总市值（万元）
        float_market_cap REAL,          -- 流通市值（万元）
        total_shares REAL,             -- 总股本（万股）
        float_shares REAL,             -- 流通股本（万股）
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, trade_date)
    )
''')

# ===== 10. 财务因子缓存表 ======
cursor.execute('''
    CREATE TABLE IF NOT EXISTS factor_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        trade_date TEXT NOT NULL,      -- 计算日期
        factor_name TEXT NOT NULL,     -- 因子名称
        factor_value REAL,             -- 因子值
        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, trade_date, factor_name)
    )
''')

# ===== 11. 数据更新日志 ======
cursor.execute('''
    CREATE TABLE IF NOT EXISTS update_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        update_type TEXT NOT NULL,     -- 更新类型：profit/balance/cash/valuation
        symbol TEXT,                   -- 股票代码，NULL表示全量更新
        status TEXT DEFAULT 'running', -- running/success/failed
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        records_updated INTEGER DEFAULT 0,
        error_message TEXT
    )
''')
```

### 2.2 索引设计

```python
# 加快查询速度的索引
cursor.execute('CREATE INDEX IF NOT EXISTS idx_profit_symbol_date ON profit_data(symbol, report_date)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_balance_symbol_date ON balance_data(symbol, report_date)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_cash_symbol_date ON cash_flow_data(symbol, report_date)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_dupont_symbol_date ON dupont_data(symbol, report_date)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_valuation_symbol_date ON valuation_data(symbol, trade_date)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_factor_cache_symbol_date ON factor_cache(symbol, trade_date)')
```

---

## 三、核心类设计

### 3.1 FinancialDataSource 类

```python
"""
财务数据获取器 - Baostock 封装
文件位置: data/financial_data_source.py
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
        if db_path is None:
            from pathlib import Path
            db_path = Path(__file__).parent.parent.parent / "quant_data.db"
        self.db_path = str(db_path)

        self._logged_in = False
        self._init_baostock()

        # API 限流控制
        self._min_interval = 1.0
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
        """API 限流控制"""
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
            raise ConnectionError("Baostock 未登录")

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
            DataFrame with columns: [date, code, roe, np_margin, gp_margin,
                                     op_margin, eps, revenue, income, totalAsset, equity]
        """
        self._ensure_login()
        self._rate_limit('query_profit_data')

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

                    time.sleep(0.1)

                except Exception as e:
                    print(f"  获取 {symbol} {year}Q{quarter} 利润表失败: {e}")
                    continue

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        return result

    # ========== 资产负债表 ==========

    def get_balance_data(self, symbol: str, start_year: int = None,
                         end_year: int = None) -> pd.DataFrame:
        """获取资产负债表数据"""
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
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        return result

    # ========== 现金流量表 ==========

    def get_cash_flow_data(self, symbol: str, start_year: int = None,
                           end_year: int = None) -> pd.DataFrame:
        """获取现金流量表数据"""
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
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        return result

    # ========== 杜邦分析 ==========

    def get_dupont_data(self, symbol: str, start_year: int = None,
                        end_year: int = None) -> pd.DataFrame:
        """获取杜邦分析数据"""
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
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        return result

    # ========== 成长能力 ==========

    def get_growth_data(self, symbol: str, start_year: int = None,
                        end_year: int = None) -> pd.DataFrame:
        """获取成长能力数据"""
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
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        return result

    # ========== 营运能力 ==========

    def get_operation_data(self, symbol: str, start_year: int = None,
                           end_year: int = None) -> pd.DataFrame:
        """获取营运能力数据"""
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
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        return result

    # ========== 偿债能力 ==========

    def get_debtpaying_data(self, symbol: str, start_year: int = None,
                            end_year: int = None) -> pd.DataFrame:
        """获取偿债能力数据"""
        self._ensure_login()
        self._rate_limit('query_debtpaying_data')

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
                    rs = self.bs.query_debtpaying_data(
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
                    print(f"  获取 {symbol} {year}Q{quarter} 偿债能力失败: {e}")
                    continue

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result['symbol'] = symbol
        return result

    # ========== 全市场估值数据 ==========

    def get_all_stocks_valuation(self) -> pd.DataFrame:
        """
        获取所有股票的实时估值数据

        用于批量更新估值表
        """
        self._ensure_login()
        self._rate_limit('query_stocks')

        try:
            rs = self.bs.query_stocks()

            if rs.error_code != '0':
                print(f"获取股票列表失败: {rs.error_msg}")
                return pd.DataFrame()

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return pd.DataFrame()

            df = pd.DataFrame(data_list, columns=rs.fields)

            # 转换代码格式
            df['symbol'] = df['code'].apply(self._convert_from_baostock_code)

            # 重命名列
            df = df.rename(columns={
                'code': 'baostock_code',
                'tradeDate': 'trade_date',
                'marketCap': 'market_cap',
                'floatMarketCap': 'float_market_cap',
                'totalShares': 'total_shares',
                'floatShares': 'float_shares'
            })

            return df

        except Exception as e:
            print(f"获取全市场估值数据失败: {e}")
            return pd.DataFrame()

    # ========== 辅助方法 ==========

    def _convert_to_baostock_code(self, symbol: str) -> Optional[str]:
        """
        将标准股票代码转换为 Baostock 格式

        Examples:
            '000001.SZ' -> 'sz.000001'
            '600000.SH' -> 'sh.600000'
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
```

### 3.2 FinancialDataSaver 类

```python
"""
财务数据持久化类
文件位置: data/financial_data_saver.py
"""


class FinancialDataSaver:
    """
    财务数据保存到数据库

    提供从 DataFrame 到 SQLite 的批量保存功能
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            from pathlib import Path
            db_path = Path(__file__).parent.parent.parent / "quant_data.db"
        self.db_path = str(db_path)

    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _to_float(self, value) -> float:
        """安全转换为浮点数"""
        if value is None or value == '' or value == '-':
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    # ========== 利润表保存 ==========

    def save_profit_data(self, df: pd.DataFrame, symbol: str = None) -> int:
        """保存利润表数据"""
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

                report_type = 'Q'
                if '-12-31' in report_date:
                    report_type = 'A'
                elif '-06-30' in report_date:
                    report_type = 'M'

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
                    self._to_float(row.get('eps', 0)),
                    self._to_float(row.get('roe', 0)),
                    self._to_float(row.get('roeAvg', 0)),
                    self._to_float(row.get('npMargin', 0)),
                    self._to_float(row.get('gpMargin', 0)),
                    self._to_float(row.get('revenue', 0)),
                    self._to_float(row.get('income', 0)),
                    self._to_float(row.get('totalAsset', 0)),
                    self._to_float(row.get('equity', 0)),
                    self._to_float(row.get('invNetProfit', 0)),
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
        """保存资产负债表数据"""
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

                report_type = 'Q'
                if '-12-31' in report_date:
                    report_type = 'A'
                elif '-06-30' in report_date:
                    report_type = 'M'

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
        """保存现金流量表数据"""
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
        """保存杜邦分析数据"""
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

    # ========== 估值数据批量保存 ==========

    def save_valuation_data(self, df: pd.DataFrame, trade_date: str = None) -> int:
        """
        批量保存估值数据

        Args:
            df: DataFrame from get_all_stocks_valuation()
            trade_date: 交易日期
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
```

### 3.3 FinancialDataManager 类

```python
"""
财务数据管理器 - 对外统一接口
文件位置: data/financial_data_manager.py
"""


class FinancialDataManager:
    """
    财务数据管理器

    整合数据获取和持久化，提供统一的数据访问接口
    支持增量更新和全量更新
    """

    def __init__(self, db_path: str = None):
        from .financial_data_source import FinancialDataSource
        from .financial_data_saver import FinancialDataSaver

        self.source = FinancialDataSource(db_path)
        self.saver = FinancialDataSaver(db_path)
        self.db_path = self.source.db_path

    # ========== 单股票操作 ==========

    def update_single_stock(self, symbol: str,
                            data_types: List[str] = None) -> Dict[str, int]:
        """
        更新单只股票的财务数据

        Args:
            symbol: 股票代码，如 '000001.SZ'
            data_types: 要更新的数据类型，如 ['profit', 'balance', 'cash', 'dupont']

        Returns:
            Dict[str, int]: 每种类型的更新记录数
        """
        if data_types is None:
            data_types = ['profit', 'balance', 'cash', 'dupont',
                         'growth', 'operation', 'debtpaying']

        results = {}

        print(f"\n更新 {symbol} 财务数据...")

        if 'profit' in data_types:
            print(f"  获取利润表数据...")
            df = self.source.get_profit_data(symbol)
            count = self.saver.save_profit_data(df, symbol)
            results['profit'] = count
            print(f"    保存 {count} 条记录")

        if 'balance' in data_types:
            print(f"  获取资产负债表...")
            df = self.source.get_balance_data(symbol)
            count = self.saver.save_balance_data(df, symbol)
            results['balance'] = count
            print(f"    保存 {count} 条记录")

        if 'cash' in data_types:
            print(f"  获取现金流量表...")
            df = self.source.get_cash_flow_data(symbol)
            count = self.saver.save_cash_flow_data(df, symbol)
            results['cash'] = count
            print(f"    保存 {count} 条记录")

        if 'dupont' in data_types:
            print(f"  获取杜邦分析数据...")
            df = self.source.get_dupont_data(symbol)
            count = self.saver.save_dupont_data(df, symbol)
            results['dupont'] = count
            print(f"    保存 {count} 条记录")

        if 'growth' in data_types:
            print(f"  获取成长能力数据...")
            df = self.source.get_growth_data(symbol)
            # 需要添加 save_growth_data 方法到 FinancialDataSaver
            results['growth'] = 0

        if 'operation' in data_types:
            print(f"  获取营运能力数据...")
            df = self.source.get_operation_data(symbol)
            # 需要添加 save_operation_data 方法
            results['operation'] = 0

        if 'debtpaying' in data_types:
            print(f"  获取偿债能力数据...")
            df = self.source.get_debtpaying_data(symbol)
            # 需要添加 save_debtpaying_data 方法
            results['debtpaying'] = 0

        return results

    # ========== 批量更新 ==========

    def batch_update(self, symbols: List[str],
                     data_types: List[str] = None,
                     progress_callback=None) -> Dict[str, int]:
        """
        批量更新多只股票的财务数据

        Args:
            symbols: 股票代码列表
            data_types: 要更新的数据类型
            progress_callback: 进度回调函数 callback(current, total, symbol)

        Returns:
            Dict[str, int]: 每种类型的总更新记录数
        """
        if data_types is None:
            data_types = ['profit', 'balance', 'cash', 'dupont']

        total_results = {dt: 0 for dt in data_types}
        total = len(symbols)

        for i, symbol in enumerate(symbols):
            try:
                results = self.update_single_stock(symbol, data_types)
                for dt, count in results.items():
                    total_results[dt] = total_results.get(dt, 0) + count

                if progress_callback:
                    progress_callback(i + 1, total, symbol)

            except Exception as e:
                print(f"  更新 {symbol} 失败: {e}")
                continue

            # Baostock 限流
            time.sleep(1.1)

        return total_results

    # ========== 数据查询 ==========

    def get_financial_data(self, symbol: str,
                          data_type: str = 'profit',
                          start_date: str = None) -> pd.DataFrame:
        """
        从数据库读取财务数据

        Args:
            symbol: 股票代码
            data_type: 数据类型 ('profit'/'balance'/'cash'/'dupont')
            start_date: 起始日期

        Returns:
            DataFrame
        """
        conn = sqlite3.connect(self.db_path)

        table_map = {
            'profit': 'profit_data',
            'balance': 'balance_data',
            'cash': 'cash_flow_data',
            'dupont': 'dupont_data',
            'growth': 'growth_data',
            'operation': 'operation_data',
            'debtpaying': 'debtpaying_data',
        }

        table = table_map.get(data_type, 'profit_data')

        query = f"SELECT * FROM {table} WHERE symbol = ?"
        params = [symbol]

        if start_date:
            query += " AND report_date >= ?"
            params.append(start_date)

        query += " ORDER BY report_date DESC"

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        return df

    def get_latest_financial(self, symbol: str,
                             data_type: str = 'profit') -> Optional[Dict]:
        """获取最新的财务数据"""
        df = self.get_financial_data(symbol, data_type)
        if not df.empty:
            return df.iloc[0].to_dict()
        return None

    def get_valuation(self, symbol: str,
                      trade_date: str = None) -> Optional[Dict]:
        """获取估值数据"""
        conn = sqlite3.connect(self.db_path)

        if trade_date:
            query = '''
                SELECT * FROM valuation_data
                WHERE symbol = ? AND trade_date = ?
                ORDER BY trade_date DESC LIMIT 1
            '''
            df = pd.read_sql_query(query, conn, params=(symbol, trade_date))
        else:
            query = '''
                SELECT * FROM valuation_data
                WHERE symbol = ?
                ORDER BY trade_date DESC LIMIT 1
            '''
            df = pd.read_sql_query(query, conn, params=(symbol,))

        conn.close()

        if not df.empty:
            return df.iloc[0].to_dict()
        return None

    # ========== 估值全量更新 ==========

    def update_all_valuations(self, trade_date: str = None) -> int:
        """更新所有股票的估值数据"""
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        print(f"获取全市场估值数据 ({trade_date})...")
        df = self.source.get_all_stocks_valuation()

        if df.empty:
            print("  获取失败")
            return 0

        print(f"  获取到 {len(df)} 只股票的估值数据")
        print("  保存到数据库...")

        count = self.saver.save_valuation_data(df, trade_date)
        print(f"  保存 {count} 条记录")

        return count

    # ========== 资源清理 ==========

    def close(self):
        """关闭连接"""
        self.source.logout()
```

---

## 四、使用示例

```python
# ===== 1. 更新单只股票的财务数据 =====
from data import FinancialDataManager

fdm = FinancialDataManager()

# 更新所有类型的财务数据
results = fdm.update_single_stock('000001.SZ')
# {'profit': 16, 'balance': 16, 'cash': 16, 'dupont': 16, ...}

# 只更新特定类型
results = fdm.update_single_stock('000001.SZ', ['profit', 'balance'])

# ===== 2. 读取财务数据 =====
df = fdm.get_financial_data('000001.SZ', 'profit')
print(df.head())

latest = fdm.get_latest_financial('000001.SZ', 'dupont')
print(latest)

# ===== 3. 获取估值数据 =====
valuation = fdm.get_valuation('000001.SZ')
print(f"PE: {valuation['pe']}, PB: {valuation['pb']}")

# ===== 4. 批量更新股票列表 =====
watchlist = ['000001.SZ', '600000.SH', '000002.SZ']

def progress_callback(current, total, symbol):
    print(f"进度: {current}/{total} - {symbol}")

results = fdm.batch_update(watchlist, progress_callback=progress_callback)

# ===== 5. 更新全市场估值 =====
count = fdm.update_all_valuations()
print(f"更新了 {count} 只股票的估值")

fdm.close()
```

---

## 五、数据更新策略

### 5.1 更新频率

| 数据类型 | 更新频率 | 说明 |
|---------|---------|------|
| 估值数据 | 每日 | 从 Baostock 获取全市场快照 |
| 财务数据 | 季度 | 财报公布后（4/7/10月后） |
| 杜邦数据 | 季度 | 与财务数据同步更新 |

### 5.2 增量更新判断

```python
def is_data_fresh(self, symbol: str, table: str, max_age_days: int = 120) -> bool:
    """
    检查数据是否足够新鲜

    Args:
        symbol: 股票代码
        table: 表名
        max_age_days: 最大允许天数（默认120天=约2个季度）
    """
    conn = sqlite3.connect(self.db_path)

    query = f'''
        SELECT MAX(report_date) FROM {table}
        WHERE symbol = ?
    '''
    df = pd.read_sql_query(query, conn, params=(symbol,))

    if df.empty or df.iloc[0, 0] is None:
        conn.close()
        return False

    latest_date = datetime.strptime(df.iloc[0, 0], '%Y-%m-%d')
    age_days = (datetime.now() - latest_date).days

    conn.close()
    return age_days <= max_age_days
```

---

## 六、与现有 DataManager 集成

### 6.1 扩展 DataManager

在 `data_manager.py` 中添加方法：

```python
class DataManager:
    # ... 现有代码 ...

    def get_financial_manager(self) -> FinancialDataManager:
        """获取财务数据管理器"""
        if not hasattr(self, '_financial_manager'):
            self._financial_manager = FinancialDataManager(self.db_path)
        return self._financial_manager

    def update_financial_data(self, symbol: str,
                             data_types: List[str] = None) -> Dict:
        """更新财务数据（便捷方法）"""
        fdm = self.get_financial_manager()
        return fdm.update_single_stock(symbol, data_types)

    def get_financial_data(self, symbol: str,
                          data_type: str = 'profit',
                          start_date: str = None) -> pd.DataFrame:
        """获取财务数据（便捷方法）"""
        fdm = self.get_financial_manager()
        return fdm.get_financial_data(symbol, data_type, start_date)

    def get_valuation(self, symbol: str,
                      trade_date: str = None) -> Optional[Dict]:
        """获取估值数据（便捷方法）"""
        fdm = self.get_financial_manager()
        return fdm.get_valuation(symbol, trade_date)
```

### 6.2 使用方式

```python
from data import DataManager

dm = DataManager()

# 便捷调用
dm.update_financial_data('000001.SZ')

df = dm.get_financial_data('000001.SZ', 'profit')
valuation = dm.get_valuation('000001.SZ')
```

---

## 七、文件清单

Phase 1 需要创建/修改的文件：

| 文件 | 操作 | 说明 |
|------|------|------|
| `data/financial_data_source.py` | 新建 | Baostock 财务数据获取器 |
| `data/financial_data_saver.py` | 新建 | 财务数据持久化类 |
| `data/financial_data_manager.py` | 新建 | 财务数据管理器（统一接口） |
| `data/__init__.py` | 修改 | 导出新类 |
| `data/data_manager.py` | 修改 | 扩展数据库 Schema，添加便捷方法 |
| `scripts/update_financial_data.py` | 新建 | 命令行更新脚本（可选） |
| `tests/test_financial_data.py` | 新建 | 单元测试（可选） |

---

## 八、Baostock API 速查表

| 接口函数 | 返回字段 | 说明 |
|---------|---------|------|
| `query_profit_data` | date, code, roe, npMargin, gpMargin, opMargin, eps, revenue, income, totalAsset, equity | 利润表 |
| `query_balance_data` | date, code, totalAsset, totalLiab, equity, assetImpair, specialRisk, accumProfit | 资产负债表 |
| `query_cash_flow_data` | date, code, operCashFlow, operCashFlowPS, investCashFlow, financeCashFlow | 现金流量表 |
| `query_dupont_data` | date, code, roe, assetStoTurn, equityMultipler, profitToSales, salesToGross | 杜邦分析 |
| `query_growth_data` | date, code, profitGrow, profitGrowRatio, assetToIncome | 成长能力 |
| `query_operation_data` | date, code, invTurnover, arTurnover, apTurnover | 营运能力 |
| `query_debtpaying_data` | date, code, currentRatio, quickRatio, cashRatio | 偿债能力 |
| `query_stocks` | code, code_name, ipoDate, outDate, stock_type, status | 全市场股票列表 |

---

## 九、注意事项

1. **Baostock API 限制**
   - 每分钟最多60次调用
   - 建议添加 1 秒间隔
   - 免费接口数据可能有延迟

2. **数据类型转换**
   - Baostock 返回的字符串 '-' 表示空值
   - 需要处理为 0 或 None

3. **报表类型判断**
   - 年报: 报告期为 YYYY-12-31
   - 中报: 报告期为 YYYY-06-30
   - 季报: 其他日期

4. **线程安全**
   - FinancialDataSource 包含登录状态，**不建议多线程共享实例**
   - 建议每个线程创建独立实例
