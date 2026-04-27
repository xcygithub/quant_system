"""
缓存策略模块 - 数据完整性检查逻辑

包含：
- 数据完整性检查（条数 + 时效性）
- 缓存策略判断
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


class CachePolicy:
    """
    缓存策略 - 判断数据是否完整且足够新鲜

    完整性判断标准：
    1. 数据条数足够（>= 估算交易日 * 85%）
    2. 最新数据日期足够新（>= 参考日期）

    只有同时满足两者，才认为数据完整。
    """

    # 交易日数量估算比例（日历天 -> 交易日）
    TRADING_DAY_RATIO = 0.4

    # 数据条数最低比例
    MIN_COMPLETE_RATIO = 0.85

    @classmethod
    def check_data_complete(
        cls,
        df: pd.DataFrame,
        start_date: str,
        end_date: str,
        ref_date: datetime = None
    ) -> bool:
        """
        检查数据是否完整

        Args:
            df: 待检查的数据
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            ref_date: 参考日期（用于判断时效性），默认使用 end_date 或今天

        Returns:
            bool: 数据是否完整
        """
        if df.empty:
            return False

        # 计算估算交易日数量
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end - start).days

        if total_days <= 0:
            return True

        # 粗略估算交易日数量
        estimated_trading_days = int(total_days * cls.TRADING_DAY_RATIO)

        # 检查1：数据条数是否足够
        if len(df) < estimated_trading_days * cls.MIN_COMPLETE_RATIO:
            return False

        # 检查2：最新数据日期是否足够新
        if ref_date is None:
            ref_date = cls._calculate_ref_date(end_date)

        latest_date = pd.to_datetime(df['date']).max().date()

        if latest_date < ref_date.date():
            return False

        return True

    @classmethod
    def _calculate_ref_date(cls, end_date: str) -> datetime:
        """
        计算参考日期（用于判断数据时效性）

        关键逻辑：
        - 如果 end_date 是历史日期（过去），用 end_date 作为参考
        - 如果 end_date 是今天或未来，用当前日期逻辑（考虑周末）

        Args:
            end_date: 结束日期

        Returns:
            datetime: 参考日期
        """
        today = datetime.now()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        if end_dt.date() < today.date():
            # 回测历史区间：用 end_date 作为参考
            return end_dt
        else:
            # 实时/未来区间：考虑周末
            # - 周一(0)：最近交易日是上周五（3天前）
            # - 周日(6)：最近交易日是上周五（2天前）
            # - 其他工作日：最近交易日是昨天（1天前）
            weekday = today.weekday()

            if weekday == 0:  # 周一
                days_back = 3  # 上周五
            elif weekday == 6:  # 周日
                days_back = 2  # 上周五
            else:  # 周二~周六
                days_back = 1  # 昨天

            return today - timedelta(days=days_back)

    @classmethod
    def estimate_trading_days(cls, start_date: str, end_date: str) -> int:
        """
        估算交易日数量

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            int: 估算的交易日数量
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end - start).days
        return int(total_days * cls.TRADING_DAY_RATIO)

    @classmethod
    def get_latest_date(cls, df: pd.DataFrame) -> Optional[str]:
        """
        获取数据的最新日期

        Args:
            df: 数据

        Returns:
            str or None: 最新日期 (YYYY-MM-DD) 或 None
        """
        if df.empty:
            return None
        return pd.to_datetime(df['date']).max().strftime('%Y-%m-%d')

    @classmethod
    def is_data_fresh(
        cls,
        df: pd.DataFrame,
        max_age_days: int = 1,
        ref_date: datetime = None
    ) -> bool:
        """
        检查数据是否新鲜（时效性）

        Args:
            df: 待检查的数据
            max_age_days: 最大允许天数
            ref_date: 参考日期，默认今天

        Returns:
            bool: 数据是否新鲜
        """
        if df.empty:
            return False

        if ref_date is None:
            ref_date = datetime.now()

        latest_date = pd.to_datetime(df['date']).max()
        age_days = (ref_date - latest_date).days

        return age_days <= max_age_days


if __name__ == "__main__":
    # 简单测试
    import pandas as pd
    from datetime import datetime, timedelta

    # 模拟数据
    dates = pd.date_range("2024-01-01", "2024-01-31", freq='B')
    df = pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'close': range(len(dates))
    })

    print("测试 CachePolicy:")
    print(f"  数据条数: {len(df)}")
    print(f"  日期范围: {df['date'].min()} ~ {df['date'].max()}")

    # 检查完整性
    is_complete = CachePolicy.check_data_complete(df, "2024-01-01", "2024-01-31")
    print(f"  完整性检查: {is_complete}")

    # 估算交易日
    est_days = CachePolicy.estimate_trading_days("2024-01-01", "2024-01-31")
    print(f"  估算交易日: {est_days}")

    # 时效性检查
    is_fresh = CachePolicy.is_data_fresh(df, max_age_days=1)
    print(f"  时效性检查 (1天): {is_fresh}")