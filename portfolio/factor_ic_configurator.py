"""
因子 IC 动态配置器
根据因子 IC 统计动态调整因子权重
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import json
import sqlite3


class FactorICConfigurator:
    """
    因子 IC 动态配置器

    功能：
    - 加载因子 IC 历史统计
    - 根据 IC 判定规则调整因子权重
    - 生成因子配置报告
    """

    # IC 判定阈值
    IC_STRONG = 0.03   # 强有效因子 IC > 3%
    IR_STRONG = 0.5    # 稳定有效 IR > 0.5
    IC_WEAK = 0.01     # 弱有效 IC > 1%
    IR_WEAK = 0.2      # 基本稳定 IR > 0.2

    # 权重调整系数
    COEFF_STRONG = 1.5  # 强有效因子
    COEFF_NORMAL = 1.0  # 有效因子
    COEFF_WEAK = 0.5    # 弱有效因子
    COEFF_INVALID = 0.0  # 无效因子
    COEFF_UNSTABLE = 0.3  # 不稳定因子

    # 权重约束
    MAX_SINGLE_WEIGHT = 0.4  # 单一因子最大权重
    MIN_SINGLE_WEIGHT = 0.02  # 单一因子最小权重

    def __init__(
        self,
        db_path: str = None
    ):
        """
        初始化

        Args:
            db_path: 数据库路径
        """
        self.db_path = db_path or 'C:/Users/FY/WorkBuddy/Claw/quant_data.db'

    def load_ic_stats(
        self,
        factor_names: List[str],
        lookback_days: int = 252,
        conn=None
    ) -> Dict[str, Dict[str, float]]:
        """
        加载因子 IC 统计

        Args:
            factor_names: 因子列表
            lookback_days: 历史窗口天数
            conn: 数据库连接

        Returns:
            {factor_name: {'ic_mean': x, 'ic_std': y, 'ir': z, 'ic_positive_ratio': p}}
        """
        ic_stats = {}

        if conn is None:
            conn = sqlite3.connect(self.db_path)

        for factor in factor_names:
            try:
                # 从 ic_statistics 表读取
                query = """
                    SELECT ic_mean, ic_std, ir, ic_positive_ratio, latest_ic
                    FROM ic_statistics
                    WHERE factor_name = ?
                """
                df = pd.read_sql_query(query, conn, params=(factor,))

                if not df.empty:
                    row = df.iloc[0]
                    ic_stats[factor] = {
                        'ic_mean': row['ic_mean'] or 0.0,
                        'ic_std': row['ic_std'] or 1.0,
                        'ir': row['ir'] or 0.0,
                        'ic_positive_ratio': row['ic_positive_ratio'] or 0.5,
                        'latest_ic': row['latest_ic'] or 0.0
                    }
                else:
                    # 没有数据，返回默认
                    ic_stats[factor] = {
                        'ic_mean': 0.0,
                        'ic_std': 1.0,
                        'ir': 0.0,
                        'ic_positive_ratio': 0.5,
                        'latest_ic': 0.0
                    }
            except Exception as e:
                # 表不存在或其他错误
                ic_stats[factor] = {
                    'ic_mean': 0.0,
                    'ic_std': 1.0,
                    'ir': 0.0,
                    'ic_positive_ratio': 0.5,
                    'latest_ic': 0.0
                }

        if conn is not None:
            conn.close()

        return ic_stats

    def load_ic_series(
        self,
        factor_name: str,
        start_date: str = None,
        end_date: str = None,
        conn=None
    ) -> pd.Series:
        """
        加载因子 IC 时间序列

        Args:
            factor_name: 因子名称
            start_date: 开始日期
            end_date: 结束日期
            conn: 数据库连接

        Returns:
            Series(index=date, values=ic_value)
        """
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        query = """
            SELECT trade_date, ic_value
            FROM ic_analysis
            WHERE factor_name = ?
        """
        params = [factor_name]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date"

        df = pd.read_sql_query(query, conn, params=params)

        if conn is not None:
            conn.close()

        if df.empty:
            return pd.Series(dtype=float)

        df['trade_date'] = pd.to_datetime(df['trade_date'])
        return df.set_index('trade_date')['ic_value']

    def judge_factor_validity(
        self,
        ic_stats: Dict[str, float]
    ) -> str:
        """
        判定因子有效性

        Args:
            ic_stats: IC 统计字典

        Returns:
            判定结果: 'strong', 'normal', 'weak', 'unstable', 'invalid'
        """
        ic_mean = ic_stats.get('ic_mean', 0.0)
        ir = ic_stats.get('ir', 0.0)
        ic_positive_ratio = ic_stats.get('ic_positive_ratio', 0.5)

        # 无效：IC 均值为负
        if ic_mean < 0:
            return 'invalid'

        # 不稳定：IR 过低
        if ir < self.IR_WEAK:
            return 'unstable'

        # 强有效
        if ic_mean > self.IC_STRONG and ir > self.IR_STRONG:
            return 'strong'

        # 正常有效
        if ic_mean > self.IC_WEAK and ir > self.IR_WEAK:
            return 'normal'

        # 弱有效
        if ic_mean > 0:
            return 'weak'

        return 'invalid'

    def calculate_weights(
        self,
        base_weights: Dict[str, float],
        ic_stats: Dict[str, Dict[str, float]]
    ) -> Dict[str, float]:
        """
        根据 IC 调整权重

        Args:
            base_weights: 基础权重
            ic_stats: IC 统计

        Returns:
            调整后的权重
        """
        # 第一步：计算原始调整系数
        raw_adjusted = {}

        for factor, base_weight in base_weights.items():
            stats = ic_stats.get(factor, {
                'ic_mean': 0.0,
                'ir': 0.0,
                'ic_positive_ratio': 0.5
            })

            validity = self.judge_factor_validity(stats)

            # 根据有效性确定系数
            if validity == 'strong':
                coeff = self.COEFF_STRONG
            elif validity == 'normal':
                coeff = self.COEFF_NORMAL
            elif validity == 'weak':
                coeff = self.COEFF_WEAK
            elif validity == 'unstable':
                coeff = self.COEFF_UNSTABLE
            else:  # invalid
                coeff = self.COEFF_INVALID

            # 排除负 IC 因子
            if stats.get('ic_mean', 0) < 0:
                coeff = 0.0

            raw_adjusted[factor] = base_weight * coeff

        # 第二步：过滤掉权重为 0 的因子并归一化
        filtered = {k: v for k, v in raw_adjusted.items() if v > 0}

        if not filtered:
            return base_weights  # 回退到基础权重

        # 归一化使权重和为 1
        total = sum(filtered.values())
        normalized = {k: v / total for k, v in filtered.items()}

        # 第三步：应用单因子权重上限
        capped = {}
        excess = 0.0

        for factor, weight in normalized.items():
            if weight > self.MAX_SINGLE_WEIGHT:
                capped[factor] = self.MAX_SINGLE_WEIGHT
                excess += weight - self.MAX_SINGLE_WEIGHT
            else:
                capped[factor] = weight

        # 第四步：重新分配超出的权重
        if excess > 0:
            remaining = {k: v for k, v in capped.items() if v < self.MAX_SINGLE_WEIGHT}
            if remaining:
                remaining_total = sum(remaining.values())
                for factor in remaining:
                    # 按比例分配
                    capped[factor] += excess * (remaining[factor] / remaining_total)

        # 第五步：应用最小权重限制
        final = {k: max(v, self.MIN_SINGLE_WEIGHT) for k, v in capped.items()}

        # 再次归一化
        total_final = sum(final.values())
        if total_final > 0:
            final = {k: v / total_final for k, v in final.items()}

        return final

    def generate_config_report(
        self,
        factor_names: List[str],
        base_weights: Dict[str, float],
        ic_stats: Dict[str, Dict[str, float]] = None
    ) -> pd.DataFrame:
        """
        生成因子配置报告

        Args:
            factor_names: 因子列表
            base_weights: 基础权重
            ic_stats: IC 统计

        Returns:
            DataFrame(columns=[因子, 基础权重, IC均值, IR, IC>0比例, 判定, 调整后权重])
        """
        if ic_stats is None:
            ic_stats = self.load_ic_stats(factor_names)

        # 计算调整后权重
        adjusted_weights = self.calculate_weights(base_weights, ic_stats)

        # 生成报告
        records = []
        for factor in factor_names:
            stats = ic_stats.get(factor, {
                'ic_mean': 0.0,
                'ir': 0.0,
                'ic_positive_ratio': 0.5,
                'latest_ic': 0.0
            })
            validity = self.judge_factor_validity(stats)

            records.append({
                '因子': factor,
                '基础权重': base_weights.get(factor, 0.0),
                'IC均值': stats.get('ic_mean', 0.0),
                'IR': stats.get('ir', 0.0),
                'IC>0比例': stats.get('ic_positive_ratio', 0.0),
                '最新IC': stats.get('latest_ic', 0.0),
                '判定': validity,
                '调整后权重': adjusted_weights.get(factor, 0.0)
            })

        df = pd.DataFrame(records)

        # 添加描述列
        def get_description(validity):
            descriptions = {
                'strong': '强有效',
                'normal': '有效',
                'weak': '弱有效',
                'unstable': '不稳定',
                'invalid': '无效'
            }
            return descriptions.get(validity, '未知')

        df['描述'] = df['判定'].apply(get_description)

        return df

    def save_config(
        self,
        config_name: str,
        factor_weights: Dict[str, float],
        ic_weights: Dict[str, float],
        ic_stats: Dict[str, Dict[str, float]],
        conn=None
    ):
        """
        保存配置到数据库

        Args:
            config_name: 配置名称
            factor_weights: 基础权重
            ic_weights: IC 调整后权重
            ic_stats: IC 统计
            conn: 数据库连接
        """
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()

        # 转换为 JSON
        weights_json = json.dumps(factor_weights, ensure_ascii=False)
        ic_weights_json = json.dumps(ic_weights, ensure_ascii=False)
        ic_stats_json = json.dumps(ic_stats, ensure_ascii=False)

        cursor.execute("""
            INSERT OR REPLACE INTO backtest_config
            (config_name, factor_weights, ic_adjusted_weights, ic_stats, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (config_name, weights_json, ic_weights_json, ic_stats_json))

        conn.commit()
        conn.close()

    def load_config(
        self,
        config_name: str,
        conn=None
    ) -> Optional[Dict[str, Any]]:
        """
        从数据库加载配置

        Args:
            config_name: 配置名称
            conn: 数据库连接

        Returns:
            配置字典或 None
        """
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        query = """
            SELECT config_name, factor_weights, ic_adjusted_weights, ic_stats, updated_at
            FROM backtest_config
            WHERE config_name = ?
        """

        df = pd.read_sql_query(query, conn, params=(config_name,))

        if conn is not None:
            conn.close()

        if df.empty:
            return None

        row = df.iloc[0]

        return {
            'config_name': row['config_name'],
            'factor_weights': json.loads(row['factor_weights']),
            'ic_weights': json.loads(row['ic_adjusted_weights']),
            'ic_stats': json.loads(row['ic_stats']),
            'updated_at': row['updated_at']
        }


class ICStatsCalculator:
    """
    IC 统计计算器
    用于批量计算和更新因子 IC 统计
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or 'C:/Users/FY/WorkBuddy/Claw/quant_data.db'

    def calculate_and_save_ic_stats(
        self,
        factor_names: List[str],
        ic_series_dict: Dict[str, pd.Series] = None,
        lookback_days: int = 252,
        conn=None
    ):
        """
        计算并保存 IC 统计

        Args:
            factor_names: 因子列表
            ic_series_dict: IC 时间序列字典 {factor: ic_series}
            lookback_days: 历史窗口
            conn: 数据库连接
        """
        if conn is None:
            conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()

        for factor in factor_names:
            # 获取 IC 序列
            if ic_series_dict and factor in ic_series_dict:
                ic_series = ic_series_dict[factor]
            else:
                # 从数据库读取
                query = """
                    SELECT trade_date, ic_value
                    FROM ic_analysis
                    WHERE factor_name = ?
                    ORDER BY trade_date DESC
                    LIMIT ?
                """
                df = pd.read_sql_query(query, conn, params=(factor, lookback_days))
                if df.empty:
                    continue
                ic_series = df.set_index('trade_date')['ic_value']

            if len(ic_series) < 10:
                continue

            # 计算统计
            ic_mean = ic_series.mean()
            ic_std = ic_series.std()
            ir = ic_mean / ic_std if ic_std > 0 else 0.0
            ic_positive_ratio = (ic_series > 0).sum() / len(ic_series)
            latest_ic = ic_series.iloc[0] if len(ic_series) > 0 else 0.0

            # 保存到 ic_statistics 表
            cursor.execute("""
                INSERT OR REPLACE INTO ic_statistics
                (factor_name, ic_mean, ic_std, ir, ic_positive_ratio, latest_ic, update_date)
                VALUES (?, ?, ?, ?, ?, ?, date('now'))
            """, (factor, ic_mean, ic_std, ir, ic_positive_ratio, latest_ic))

        conn.commit()
        conn.close()


if __name__ == "__main__":
    # 测试
    configurator = FactorICConfigurator()

    # 模拟 IC 统计
    ic_stats = {
        'roe': {'ic_mean': 0.052, 'ic_std': 0.076, 'ir': 0.68, 'ic_positive_ratio': 0.72, 'latest_ic': 0.045},
        'pe': {'ic_mean': -0.005, 'ic_std': 0.08, 'ir': -0.06, 'ic_positive_ratio': 0.45, 'latest_ic': -0.010},
        'momentum_20': {'ic_mean': 0.031, 'ic_std': 0.074, 'ir': 0.42, 'ic_positive_ratio': 0.65, 'latest_ic': 0.028},
        'revenue_growth': {'ic_mean': 0.018, 'ic_std': 0.072, 'ir': 0.25, 'ic_positive_ratio': 0.58, 'latest_ic': 0.015},
        'debt_ratio': {'ic_mean': 0.008, 'ic_std': 0.065, 'ir': 0.12, 'ic_positive_ratio': 0.52, 'latest_ic': 0.005}
    }

    # 基础权重
    base_weights = {
        'roe': 0.25,
        'pe': 0.15,
        'momentum_20': 0.20,
        'revenue_growth': 0.15,
        'debt_ratio': 0.15,
        'liquidity': 0.10
    }

    # 生成配置报告
    report = configurator.generate_config_report(
        factor_names=list(base_weights.keys()),
        base_weights=base_weights,
        ic_stats=ic_stats
    )

    print("因子配置报告:")
    print(report.to_string(index=False))

    # 计算调整后权重
    adjusted = configurator.calculate_weights(base_weights, ic_stats)
    print(f"\n调整后权重: {adjusted}")
