# -*- coding: utf-8 -*-
"""
量化系统配置文件
所有配置项集中在此文件管理
"""

from pathlib import Path

# ============ 项目路径 ============
# 项目根目录（config.py 所在目录）
PROJECT_ROOT = Path(__file__).parent.resolve()

# ============ 数据库配置 ============
# 主数据库路径（行情数据）
DATABASE_PATH = PROJECT_ROOT / "quant_data.db"

# 缓存目录
CACHE_DIR = PROJECT_ROOT / "data_cache"

# ============ 数据源配置 ============
# Baostock API 限流（每秒请求数）
BAOSTOCK_RATE_LIMIT = 1

# 数据更新策略
DATA_UPDATE_STRATEGY = {
    "daily_kline": "baostock",      # 日线数据使用 Baostock
    "financial": "baostock",        # 财务数据使用 Baostock
    "fundamentals": "baostock",     # 基本面数据使用 Baostock
}

# ============ 回测配置 ============
BACKTEST_CONFIG = {
    # 默认初始资金
    "default_initial_cash": 1000000,
    # 默认手续费率
    "default_commission": 0.0003,
    # 默认印花税率
    "default_stamp_tax": 0.001,
    # 最大持仓数
    "default_max_positions": 5,
    # 单只股票最大仓位
    "default_max_single_position": 0.2,
}

# ============ Streamlit 配置 ============
STREAMLIT_CONFIG = {
    # 默认回测时间范围（天）
    "default_backtest_days": 365,
    # 每页显示条数
    "page_size": 20,
}
