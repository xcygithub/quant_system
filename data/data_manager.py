"""
数据管理器 - 统一的数据获取和缓存管理

职责划分（重构后）：
- DataManager：只负责数据库初始化和连接管理
- KlineManager：日线/分钟线数据管理（纯读写）
- FactorManager：因子数据管理（读写）
- FinancialDataManager：财务数据管理（已有）
- MarketDataService：市场数据（股票列表、分钟线、指数）
- CachePolicy：缓存策略（完整性检查）

使用示例：
```python
from data import DataManager

dm = DataManager()

# 委托给 KlineManager
df = dm.get_daily_kline("000001.SZ", "2024-01-01", "2024-03-19")

# 委托给 FinancialDataManager
profit = dm.get_profit("000001.SZ")

# 委托给 FactorManager
ic_stats = dm.get_ic_statistics()
```
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
import sqlite3
import os
import json
from pathlib import Path
import time
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_PATH, CACHE_DIR

from .data_sources import MultiDataSource
from .kline_manager import KlineManager
from .factor_manager import FactorManager
from .market_data_service import MarketDataService
from .financial_data_manager import FinancialDataManager


class DataManager:
    """
    数据管理器 - 负责数据的统一入口

    重构后职责：
    1. 数据库连接和表初始化
    2. 委托数据操作给专业管理器
    3. 提供便捷的代理方法（向后兼容）
    """

    def __init__(self, db_path: str = None):
        """
        初始化数据管理器

        Args:
            db_path: SQLite数据库路径，默认使用配置文件中的路径
        """
        if db_path is None:
            db_path = DATABASE_PATH
        self.db_path = str(db_path)
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(exist_ok=True)

        # 初始化子管理器
        self._kline_mgr = KlineManager(self.db_path)
        self._factor_mgr = FactorManager(self.db_path)
        self._financial_mgr = FinancialDataManager(self.db_path)
        self._data_source = MultiDataSource()
        self._kline_mgr.set_data_source(self._data_source)
        self._market_data = MarketDataService()

        # 初始化数据库
        self._init_database()

    # ========== 数据库初始化 ==========

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

        # ========== 财务数据表（新版）==========

        # 1. 盈利能力数据（利润表）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                eps REAL,
                roe REAL,
                roe_avg REAL,
                net_profit_ratio REAL,
                gross_profit_rate REAL,
                business_income REAL,
                total_share REAL,
                liqa_share REAL,
                operating_profit REAL,
                net_profit REAL,
                total_profit REAL,
                inv_net_profit REAL,
                pub_date TEXT,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')
        # 兼容历史库：补齐新增字段
        self._ensure_column_exists(cursor, 'profit_data', 'total_share', 'REAL')
        self._ensure_column_exists(cursor, 'profit_data', 'liqa_share', 'REAL')
        # 兼容历史数据：统一 debt_ratio 口径为负债/资产（小数）
        self._normalize_debt_ratio(cursor)

        # 2. 资产负债数据（资产负债表）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS balance_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                total_assets REAL,
                total_liabilities REAL,
                total_equity REAL,
                debt_ratio REAL,
                equity_ratio REAL,
                current_assets REAL,
                fixed_assets REAL,
                intangible_assets REAL,
                current_ratio REAL,
                quick_ratio REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 3. 现金流量数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cash_flow_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                oper_cash_flow REAL,
                invest_cash_flow REAL,
                finance_cash_flow REAL,
                cash_equil_change REAL,
                end_cash REAL,
                oper_cash_flow_ps REAL,
                cfo_to_or REAL,
                cfo_to_np REAL,
                cfo_to_gr REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')
        self._ensure_column_exists(cursor, 'cash_flow_data', 'cfo_to_or', 'REAL')
        self._ensure_column_exists(cursor, 'cash_flow_data', 'cfo_to_np', 'REAL')
        self._ensure_column_exists(cursor, 'cash_flow_data', 'cfo_to_gr', 'REAL')

        # 4. 杜邦分析数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dupont_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                roe REAL,
                asset_turnover REAL,
                equity_multiplier REAL,
                net_profit_margin REAL,
                sales_to_grs REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 5. 成长能力数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS growth_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                profit_grow REAL,
                profit_grow_ratio REAL,
                asset_to_income REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 6. 营运能力数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                inv_turnover REAL,
                ar_turnover REAL,
                ap_turnover REAL,
                total_asset_turnover REAL,
                current_asset_turnover REAL,
                fixed_asset_turnover REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 7. 偿债能力数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debtpaying_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                report_type TEXT DEFAULT 'Q',
                current_ratio REAL,
                quick_ratio REAL,
                cash_ratio REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, report_date)
            )
        ''')

        # 8. 估值数据
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS valuation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                pe REAL,
                pe_ttm REAL,
                pb REAL,
                ps REAL,
                pcf REAL,
                market_cap REAL,
                float_market_cap REAL,
                total_shares REAL,
                float_shares REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date)
            )
        ''')

        # 8.1 历史估值数据（日频）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history_valuation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL,
                pe_ttm REAL,
                pb REAL,
                ps REAL,
                pcf REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date)
            )
        ''')

        # 8.2 财务原始数据（接口全字段留存）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_data_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                data_type TEXT NOT NULL,
                report_date TEXT DEFAULT '',
                trade_date TEXT DEFAULT '',
                baostock_code TEXT DEFAULT '',
                raw_json TEXT NOT NULL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, data_type, report_date, trade_date)
            )
        ''')

        # 9. 财务因子缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                factor_value REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date, factor_name)
            )
        ''')

        # 10. 数据更新日志
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS update_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_type TEXT NOT NULL,
                symbol TEXT,
                status TEXT DEFAULT 'running',
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                records_updated INTEGER DEFAULT 0,
                error_message TEXT
            )
        ''')

        # ========== 创建索引 ==========
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_profit_symbol_date ON profit_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_balance_symbol_date ON balance_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cash_symbol_date ON cash_flow_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_dupont_symbol_date ON dupont_data(symbol, report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_valuation_symbol_date ON valuation_data(symbol, trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_factor_cache_symbol_date ON factor_cache(symbol, trade_date)')

        # ========== 因子数据表 ==========

        # 1. 每日因子值缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                factor_value REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date, factor_name)
            )
        ''')

        # 2. 因子元数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL UNIQUE,
                factor_category TEXT,
                factor_direction TEXT,
                description TEXT,
                formula TEXT,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 插入默认因子元数据
        default_factors = [
            ('pe', 'valuation', 'negative', '市盈率', 'price / eps'),
            ('pe_ttm', 'valuation', 'negative', '滚动市盈率', 'price / eps_ttm'),
            ('pb', 'valuation', 'negative', '市净率', 'price / book_value_per_share'),
            ('ps', 'valuation', 'negative', '市销率', 'price / revenue_per_share'),
            ('pcf', 'valuation', 'negative', '市现率', 'price / cash_flow_per_share'),
            ('roe', 'profitability', 'positive', '净资产收益率', 'net_profit / equity'),
            ('roe_avg', 'profitability', 'positive', '平均净资产收益率', 'roe_avg'),
            ('gross_margin', 'profitability', 'positive', '毛利率', 'gross_profit / revenue'),
            ('net_margin', 'profitability', 'positive', '净利率', 'net_profit / revenue'),
            ('profit_growth', 'growth', 'positive', '利润增长率', '(profit_now - profit_prev) / profit_prev'),
            ('equity_growth', 'growth', 'positive', '净资产增长率', '(equity_now - equity_prev) / equity_prev'),
            ('debt_ratio', 'structure', 'neutral', '资产负债率', 'total_liabilities / total_assets'),
            ('current_ratio', 'structure', 'positive', '流动比率', 'current_assets / current_liabilities'),
            ('quick_ratio', 'structure', 'positive', '速动比率', '(current_assets - inventory) / current_liabilities'),
            ('cash_to_profit', 'cashflow', 'positive', '经营现金流/净利润', 'oper_cash_flow / net_profit'),
            ('fcf', 'cashflow', 'positive', '自由现金流', 'oper_cash_flow - capex'),
            ('cash_yield', 'cashflow', 'positive', '现金市值比', 'oper_cash_flow / market_cap'),
            ('asset_turnover', 'profitability', 'positive', '资产周转率', 'revenue / total_assets'),
            ('equity_multiplier', 'structure', 'neutral', '权益乘数', 'total_assets / equity'),
            ('pb_roe', 'derived', 'positive', 'PB/ROE因子', 'pb / roe'),
            ('pe_growth', 'derived', 'positive', 'PE增长因子', 'pe / profit_growth'),
            ('altman_z', 'derived', 'positive', 'Altman Z-Score', 'Z-Score破产预警模型'),
        ]

        cursor.executemany('''
            INSERT OR IGNORE INTO factor_metadata
            (factor_name, factor_category, factor_direction, description, formula)
            VALUES (?, ?, ?, ?, ?)
        ''', default_factors)

        # ========== 选股扫描表 ==========

        # 1. 选股扫描结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                symbol_name TEXT,
                rank INTEGER,
                composite_score REAL,
                valuation_score REAL,
                profitability_score REAL,
                growth_score REAL,
                momentum_score REAL,
                volatility_score REAL,
                liquidity_score REAL,
                financial_quality_score REAL,
                pe REAL, pb REAL, roe REAL, revenue_growth REAL,
                is_selected INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(scan_date, symbol)
            )
        ''')

        # 2. IC分析结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ic_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                ic_value REAL,
                ic_rank REAL,
                forward_return REAL,
                sample_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(factor_name, trade_date)
            )
        ''')

        # 3. IC统计表（定期计算）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ic_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL UNIQUE,
                ic_mean REAL,
                ic_std REAL,
                ir REAL,
                ic_positive_ratio REAL,
                latest_ic REAL,
                update_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scan_results_date ON scan_results(scan_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ic_analysis_factor ON ic_analysis(factor_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ic_analysis_date ON ic_analysis(trade_date)')

        # ========== Phase 4: 多因子回测表 ==========

        # 4. 因子暴露度记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_exposure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                exposure REAL,
                portfolio_value REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, factor_name)
            )
        ''')

        # 5. 因子收益归因表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_attribution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                factor_return REAL,
                portfolio_exposure REAL,
                attribution REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, factor_name)
            )
        ''')

        # 6. 多因子回测配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_name TEXT NOT NULL UNIQUE,
                factor_weights TEXT,
                ic_adjusted_weights TEXT,
                ic_stats TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 7. 回测期间记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_name TEXT,
                start_date TEXT,
                end_date TEXT,
                symbols_count INTEGER,
                total_return REAL,
                annual_return REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                config_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_factor_exposure_date ON factor_exposure(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_factor_attribution_date ON factor_attribution(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_backtest_runs_date ON backtest_runs(start_date, end_date)')

        # 历史数据兼容修正
        self._backfill_cashflow_ratio_from_raw(cursor)

        conn.commit()
        conn.close()

    def _ensure_column_exists(self, cursor, table_name: str, column_name: str, column_type: str):
        """确保表字段存在（用于历史库升级）"""
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def _normalize_debt_ratio(self, cursor):
        """
        统一历史 debt_ratio 口径，避免出现 0.4 与 0.004 混用。

        优先使用 total_liabilities / total_assets 重算。
        """
        try:
            cursor.execute(
                '''
                UPDATE balance_data
                SET debt_ratio = (total_liabilities * 1.0 / total_assets)
                WHERE total_assets > 0 AND total_liabilities >= 0
                '''
            )
            # 第二步：修正已落库的千分位/万分位口径异常值（如 0.0042 应为 0.42）
            cursor.execute(
                '''
                UPDATE balance_data
                SET debt_ratio = debt_ratio * 100.0
                WHERE debt_ratio > 0
                  AND debt_ratio < 0.02
                  AND current_ratio > 0.2
                '''
            )
        except Exception:
            # 历史库异常时不阻塞初始化
            pass

    def _backfill_cashflow_ratio_from_raw(self, cursor):
        """从 raw_json 回填 cash_flow_data 的 CFO 比率字段。"""
        try:
            cursor.execute(
                '''
                SELECT symbol, report_date, raw_json
                FROM financial_data_raw
                WHERE data_type = 'cash'
                  AND raw_json IS NOT NULL
                '''
            )
            rows = cursor.fetchall()
            if not rows:
                return

            import json
            updates = []

            for symbol, report_date, raw_json in rows:
                try:
                    raw = json.loads(raw_json)
                except Exception:
                    continue

                def to_float(value):
                    try:
                        if value is None or str(value).strip() == '':
                            return 0.0
                        return float(value)
                    except Exception:
                        return 0.0

                updates.append((
                    to_float(raw.get('CFOToOR', 0)),
                    to_float(raw.get('CFOToNP', 0)),
                    to_float(raw.get('CFOToGr', 0)),
                    symbol,
                    report_date
                ))

            if updates:
                cursor.executemany(
                    '''
                    UPDATE cash_flow_data
                    SET cfo_to_or = ?, cfo_to_np = ?, cfo_to_gr = ?
                    WHERE symbol = ? AND report_date = ?
                    ''',
                    updates
                )
        except Exception:
            pass

    # ========== 子管理器访问 ==========

    @property
    def kline_manager(self) -> KlineManager:
        """获取 K线管理器"""
        return self._kline_mgr

    @property
    def factor_manager(self) -> FactorManager:
        """获取因子管理器"""
        return self._factor_mgr

    # ========== K线数据代理方法（委托给 KlineManager）==========

    def get_daily_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取日线数据（带完整性检查和在线获取）

        委托给 KlineManager.fetch_daily_kline() 处理完整的获取-检查-保存逻辑

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame 包含 OHLCV 数据
        """
        # 委托给 KlineManager 处理完整的获取流程
        return self._kline_mgr.fetch_daily_kline(symbol, start_date, end_date)

    def get_minute_kline(self, symbol: str, period: str = "1") -> pd.DataFrame:
        """获取分钟线数据（委托给 MarketDataService）。"""
        return self._market_data.get_minute_kline(symbol, period)

    def _get_kline_from_db(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从数据库读取K线数据（内部方法）"""
        return self._kline_mgr.get_daily_kline(symbol, start_date, end_date)

    def _save_kline_to_db(self, df: pd.DataFrame):
        """保存K线数据到数据库（内部方法）"""
        return self._kline_mgr.save_daily_kline(df)

    # ========== 数据更新方法 ==========

    def update_recent_data(self, symbols: list, days: int = 10):
        """
        更新指定股票列表的最近N天数据（委托给 KlineManager）。
        """
        return self._kline_mgr.update_recent_data(symbols, days)

    def update_all_data(self):
        """更新所有市场数据（委托给 MarketDataService）。"""
        self._market_data.update_all_data()

    # ========== 其他数据获取方法（保留原有实现）==========

    def get_stock_list(self, market: str = "all") -> pd.DataFrame:
        """获取股票列表（委托给 MarketDataService）。"""
        return self._market_data.get_stock_list(market)

    def get_index_list(self) -> pd.DataFrame:
        """获取指数列表（委托给 MarketDataService）。"""
        return self._market_data.get_index_list()

    def get_index_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取指数K线数据（委托给 MarketDataService）。"""
        return self._market_data.get_index_kline(symbol, start_date, end_date)

    # ========== 财务数据便捷方法（委托给 FinancialDataManager）==========

    def get_financial_manager(self):
        """获取财务数据管理器（复用实例）。"""
        return self._financial_mgr

    def update_financial_data(self, symbol: str,
                             data_types: List[str] = None) -> Dict[str, int]:
        """更新财务数据（便捷方法）"""
        return self._financial_mgr.update_single_stock(symbol, data_types)

    def get_financial_data(self, symbol: str,
                          data_type: str = 'profit',
                          start_date: str = None) -> pd.DataFrame:
        """获取财务数据（便捷方法）"""
        return self._financial_mgr.get_financial_data(symbol, data_type, start_date)

    def get_valuation(self, symbol: str,
                      trade_date: str = None) -> Optional[Dict]:
        """获取估值数据（便捷方法）"""
        return self._financial_mgr.get_valuation(symbol, trade_date)

    def close(self):
        """关闭 DataManager 持有的外部连接。"""
        try:
            self._financial_mgr.close()
        except Exception:
            pass

    def get_profit(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取利润表数据"""
        return self.get_financial_data(symbol, 'profit', start_date)

    def get_balance(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取资产负债表数据"""
        return self.get_financial_data(symbol, 'balance', start_date)

    def get_cash_flow(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取现金流量表数据"""
        return self.get_financial_data(symbol, 'cash', start_date)

    def get_dupont(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """获取杜邦分析数据"""
        return self.get_financial_data(symbol, 'dupont', start_date)

    # ========== IC分析便捷方法（委托给 FactorManager）==========

    def get_ic_statistics(self, factor_name: str = None) -> pd.DataFrame:
        """获取 IC 统计信息"""
        return self._factor_mgr.get_ic_statistics(factor_name)

    def get_ic_series(self, factor_name: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取 IC 时间序列"""
        return self._factor_mgr.get_ic_series(factor_name, start_date, end_date)

    def save_ic_result(self, factor_name: str, trade_date: str, ic_value: float, **kwargs) -> bool:
        """保存 IC 分析结果"""
        return self._factor_mgr.save_ic_result(factor_name, trade_date, ic_value, **kwargs)


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

    # 测试子管理器
    print(f"\nK线管理器: {dm.kline_manager}")
    print(f"因子管理器: {dm.factor_manager}")