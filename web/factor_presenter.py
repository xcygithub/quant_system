"""
因子展示服务
负责因子数据的格式化、查询和展示
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import sqlite3

from strategy.fundamental_factors import FundamentalFactors


class FactorPresenter:
    """
    因子展示服务

    职责：
    - 获取并格式化因子数据
    - 提供单股/多股的因子查询接口
    - 因子数据缓存管理
    """

    # 因子中文名称映射
    FACTOR_NAMES_CN = {
        # 估值因子
        'pe': '市盈率(PE)',
        'pe_ttm': '滚动市盈率(PE TTM)',
        'pb': '市净率(PB)',
        'ps': '市销率(PS)',
        'pcf': '市现率(PCF)',
        # 盈利因子
        'roe': '净资产收益率(ROE)',
        'roe_avg': '平均净资产收益率',
        'roa': '资产收益率(ROA)',
        'gross_margin': '毛利率',
        'net_margin': '净利率',
        'eps_ttm': '每股收益(TTM)',
        'asset_turnover': '资产周转率',
        # 成长因子
        'revenue_growth': '营收增长率',
        'profit_growth': '利润增长率',
        'equity_growth': '净资产增长率',
        'profit_cagr': '净利润复合增长率',
        # 财务结构
        'debt_ratio': '资产负债率',
        'current_ratio': '流动比率',
        'quick_ratio': '速动比率',
        'equity_multiplier': '权益乘数',
        # 现金流
        'cash_to_profit': '经营现金流/净利润',
        'fcf': '自由现金流',
        'cash_yield': '现金市值比',
        # 衍生
        'pb_roe': 'PB/ROE',
        'pe_growth': 'PE/增长率',
        'altman_z': 'Altman Z指数',
    }

    # 因子方向说明
    FACTOR_DIRECTIONS = {
        'positive': '正向（越高越好）',
        'negative': '负向（越低越好）',
        'neutral': '中性（适中为佳）',
    }

    # 因子类别（英文key -> 中文名称）
    FACTOR_CATEGORIES = {
        'valuation': '估值因子',
        'profitability': '盈利因子',
        'growth': '成长因子',
        'structure': '财务结构',
        'cashflow': '现金流因子',
        'derived': '衍生因子',
    }

    # 中文类别名 -> 英文key 的反向映射
    CATEGORY_CN_TO_EN = {v: k for k, v in FACTOR_CATEGORIES.items()}

    def __init__(self, db_path: str = None):
        """
        初始化因子展示服务

        Args:
            db_path: 数据库路径
        """
        self.ff = FundamentalFactors(db_path)

    def get_single_stock_factors(self, symbol: str,
                                  trade_date: str = None,
                                  include_zero: bool = False) -> pd.DataFrame:
        """
        获取单只股票的所有因子值

        Args:
            symbol: 股票代码
            trade_date: 交易日期
            include_zero: 是否包含零值因子

        Returns:
            DataFrame，包含因子名称、因子值、类别、方向等
        """
        # 计算因子
        factors = self.ff.calculate_all_factors(symbol, trade_date)

        # 获取因子元数据
        metadata = self._get_factor_metadata()

        # 构建结果DataFrame
        rows = []
        for factor_name, factor_value in factors.items():
            if not include_zero and factor_value == 0:
                continue

            meta = metadata.get(factor_name, {})
            rows.append({
                '因子代码': factor_name,
                '因子名称': self.FACTOR_NAMES_CN.get(factor_name, factor_name),
                '因子值': factor_value,
                '类别': self.FACTOR_CATEGORIES.get(meta.get('category', ''), meta.get('category', '')),
                '方向': self.FACTOR_DIRECTIONS.get(meta.get('direction', ''), ''),
                '描述': meta.get('description', ''),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df

    def get_multi_stock_single_factor(self, symbols: List[str],
                                      factor_name: str,
                                      trade_date: str = None) -> pd.DataFrame:
        """
        获取多只股票的单个因子值并排序

        Args:
            symbols: 股票列表
            factor_name: 因子名称
            trade_date: 交易日期

        Returns:
            DataFrame，包含股票代码、因子值、排名
        """
        rows = []
        metadata = self._get_factor_metadata()
        meta = metadata.get(factor_name, {})
        direction = meta.get('direction', 'positive')

        for symbol in symbols:
            try:
                factors = self.ff.calculate_all_factors(symbol, trade_date)
                value = factors.get(factor_name, 0)

                if value != 0:  # 只保留非零值
                    rows.append({
                        '股票代码': symbol,
                        '因子值': value,
                    })
            except Exception as e:
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # 排序
        ascending = (direction == 'negative')  # 负向因子越低越好
        df = df.sort_values('因子值', ascending=ascending).reset_index(drop=True)

        # 添加排名
        df['排名'] = range(1, len(df) + 1)

        return df

    def get_multi_stock_multi_factors(self, symbols: List[str],
                                       factor_names: List[str],
                                       trade_date: str = None) -> pd.DataFrame:
        """
        获取多只股票的多个因子值

        Args:
            symbols: 股票列表
            factor_names: 因子名称列表
            trade_date: 交易日期

        Returns:
            DataFrame，宽表格式
        """
        rows = []
        for symbol in symbols:
            try:
                factors = self.ff.calculate_all_factors(symbol, trade_date)
                row = {'股票代码': symbol}
                for fname in factor_names:
                    row[fname] = factors.get(fname, 0)
                rows.append(row)
            except Exception as e:
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df

    def format_factor_value(self, factor_name: str, value: float) -> str:
        """
        格式化因子值为字符串

        Args:
            factor_name: 因子名称
            value: 因子值

        Returns:
            格式化后的字符串
        """
        if value == 0:
            return '-'

        # 估值类因子保留2位小数
        valuation_factors = {'pe', 'pe_ttm', 'pb', 'ps', 'pcf'}
        if factor_name in valuation_factors:
            return f"{value:.2f}"

        # 比率类因子转为百分比
        ratio_factors = {
            'roe', 'roe_avg', 'roa', 'gross_margin', 'net_margin',
            'revenue_growth', 'profit_growth', 'equity_growth', 'profit_cagr',
            'debt_ratio', 'current_ratio', 'quick_ratio', 'cash_to_profit',
            'cash_yield', 'asset_turnover', 'equity_multiplier'
        }
        if factor_name in ratio_factors:
            return f"{value * 100:.2f}%"

        # 金额类因子
        amount_factors = {'fcf'}
        if factor_name in amount_factors:
            if abs(value) >= 1e8:
                return f"{value / 1e8:.2f}亿"
            elif abs(value) >= 1e4:
                return f"{value / 1e4:.2f}万"
            else:
                return f"{value:.2f}"

        # 其他保留4位小数
        return f"{value:.4f}"

    def _get_factor_metadata(self) -> Dict[str, Dict]:
        """
        获取因子元数据

        Returns:
            {因子名: {category, direction, description, formula}}
        """
        conn = sqlite3.connect(self.ff.fdm.db_path)
        try:
            df = pd.read_sql_query('SELECT * FROM factor_metadata', conn)
            if df.empty:
                return {}
            # 转换为短key
            df = df.rename(columns={
                'factor_category': 'category',
                'factor_direction': 'direction',
                'factor_value': 'value'
            })
            return df.set_index('factor_name').to_dict('index')
        except Exception as e:
            return {}
        finally:
            conn.close()

    def get_factor_list_by_category(self) -> Dict[str, List[Tuple[str, str]]]:
        """
        按类别获取因子列表

        Returns:
            {类别名: [(因子代码, 因子名称), ...]}
        """
        metadata = self._get_factor_metadata()
        result = {}

        for factor_name, meta in metadata.items():
            # meta.get('category') 返回英文如 'valuation'
            # 转换为中文类别名
            category_en = meta.get('category', '')
            category = self.FACTOR_CATEGORIES.get(category_en, '其他')
            if category not in result:
                result[category] = []
            result[category].append((
                factor_name,
                self.FACTOR_NAMES_CN.get(factor_name, factor_name)
            ))

        return result

    def get_all_factors_for_ui(self, symbol: str, trade_date: str = None) -> Dict[str, Dict]:
        """
        获取用于UI展示的因子数据

        Returns:
            {类别: {因子名: {value, formatted, direction, name}}}
        """
        factors = self.ff.calculate_all_factors(symbol, trade_date)
        metadata = self._get_factor_metadata()
        result = {}

        for factor_name, value in factors.items():
            if value == 0:
                continue

            meta = metadata.get(factor_name, {})
            category_en = meta.get('category', '')
            category = self.FACTOR_CATEGORIES.get(category_en, '其他')

            if category not in result:
                result[category] = {}

            result[category][factor_name] = {
                'value': value,
                'formatted': self.format_factor_value(factor_name, value),
                'direction': meta.get('direction', 'neutral'),
                'name': self.FACTOR_NAMES_CN.get(factor_name, factor_name),
                'description': meta.get('description', ''),
            }

        return result

    def calculate_watchlist_factors(self, symbols: List[str],
                                     trade_date: str = None,
                                     progress_callback=None) -> Dict[str, Dict]:
        """
        批量计算自选股的因子值

        Args:
            symbols: 股票列表
            trade_date: 交易日期
            progress_callback: 进度回调函数

        Returns:
            {股票代码: {因子名: 因子值, ...}, ...}
        """
        results = {}
        total = len(symbols)

        for i, symbol in enumerate(symbols):
            try:
                factors = self.ff.calculate_all_factors(symbol, trade_date)
                results[symbol] = factors

                if progress_callback:
                    progress_callback(i + 1, total)
            except Exception as e:
                results[symbol] = {}
                if progress_callback:
                    progress_callback(i + 1, total)

        return results

    def close(self):
        """关闭连接"""
        self.ff.close()

    def __del__(self):
        """析构时确保关闭"""
        try:
            self.close()
        except:
            pass


# ========== 便捷函数 ==========

def get_stock_factors(symbol: str, trade_date: str = None) -> pd.DataFrame:
    """获取单只股票的所有因子"""
    fp = FactorPresenter()
    df = fp.get_single_stock_factors(symbol, trade_date)
    fp.close()
    return df


def get_factor_ranking(symbols: List[str], factor_name: str,
                        trade_date: str = None) -> pd.DataFrame:
    """获取多只股票的因子排名"""
    fp = FactorPresenter()
    df = fp.get_multi_stock_single_factor(symbols, factor_name, trade_date)
    fp.close()
    return df


if __name__ == "__main__":
    print("=" * 60)
    print("FactorPresenter 测试")
    print("=" * 60)

    fp = FactorPresenter()

    # 测试1: 获取单只股票因子
    print("\n[测试1] 获取 000001.SZ 的因子")
    df = fp.get_single_stock_factors('000001.SZ')
    if not df.empty:
        print(df.to_string())
    else:
        print("  无因子数据（可能缺少财务数据）")

    # 测试2: 获取因子列表
    print("\n[测试2] 按类别获取因子列表")
    factor_list = fp.get_factor_list_by_category()
    for category, factors in factor_list.items():
        print(f"  {category}: {[f[0] for f in factors]}")

    # 测试3: 格式化因子值
    print("\n[测试3] 格式化因子值测试")
    test_values = [('pe', 25.678), ('roe', 0.1567), ('fcf', 1234567890)]
    for fname, val in test_values:
        print(f"  {fname} = {val} -> {fp.format_factor_value(fname, val)}")

    fp.close()
    print("\n测试完成")
