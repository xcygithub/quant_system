"""
数据库 Schema 初始化脚本
用于创建因子分析相关的数据库表

运行方式:
    python -m data.database_schema
"""
import sqlite3
from pathlib import Path


def get_db_path():
    """获取数据库路径"""
    return Path(__file__).parent.parent / "quant_data.db"


def init_factor_tables(db_path: str = None):
    """
    初始化因子分析相关的数据库表

    表结构:
    - factor_values: 因子值缓存表
    - factor_metadata: 因子元数据表
    - factor_calc_log: 因子计算日志表
    """
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ========== 1. 因子值缓存表 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS factor_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            factor_name TEXT NOT NULL,
            factor_value REAL,
            source_pub_date TEXT,
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, trade_date, factor_name)
        )
    ''')
    cursor.execute("PRAGMA table_info(factor_values)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "source_pub_date" not in existing_cols:
        cursor.execute("ALTER TABLE factor_values ADD COLUMN source_pub_date TEXT")

    # 创建索引
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_factor_values_date
        ON factor_values(trade_date)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_factor_values_symbol
        ON factor_values(symbol)
    ''')

    # ========== 2. 因子元数据表 ==========
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

    # ========== 3. 因子计算日志表 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS factor_calc_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calc_type TEXT NOT NULL,
            stock_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            calc_time INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print(f"[OK] 因子分析数据库表初始化完成: {db_path}")


def init_factor_metadata(db_path: str = None):
    """
    初始化因子元数据

    插入所有因子的元数据信息
    """
    if db_path is None:
        db_path = get_db_path()

    # 因子元数据定义
    metadata = [
        # 估值因子（低估值买入）
        ('pe', 'valuation', 'negative', '市盈率', 'price / eps'),
        ('pe_ttm', 'valuation', 'negative', '滚动市盈率', 'price / eps_ttm'),
        ('pb', 'valuation', 'negative', '市净率', 'price / book_value_per_share'),
        ('ps', 'valuation', 'negative', '市销率', 'price / revenue_per_share'),
        ('pcf', 'valuation', 'negative', '市现率', 'price / cash_flow_per_share'),

        # 盈利因子（高盈利买入）
        ('roe', 'profitability', 'positive', '净资产收益率', 'net_profit / total_equity'),
        ('roe_avg', 'profitability', 'positive', '平均净资产收益率', 'avg(net_profit / total_equity)'),
        ('gross_margin', 'profitability', 'positive', '毛利率', 'gross_profit / revenue'),
        ('net_margin', 'profitability', 'positive', '净利率', 'net_profit / revenue'),
        ('np_margin', 'profitability', 'positive', '销售净利率', 'net_profit / revenue'),
        ('gp_margin', 'profitability', 'positive', '销售毛利率', '(revenue-cost)/revenue'),
        ('eps_ttm', 'profitability', 'positive', '每股收益(TTM)', 'net_profit_ttm / total_shares'),
        ('roa', 'profitability', 'positive', '总资产收益率', 'net_profit / total_assets'),
        ('net_profit', 'profitability', 'positive', '净利润', 'profit_data.net_profit'),
        ('mb_revenue', 'profitability', 'positive', '主营业务收入', 'profit_data.business_income'),
        ('total_share', 'profitability', 'neutral', '总股本', 'profit_data.total_share'),
        ('liqa_share', 'profitability', 'neutral', '流通股本', 'profit_data.liqa_share'),
        ('asset_turnover', 'profitability', 'positive', '资产周转率', 'revenue / total_assets'),

        # 成长因子（高成长买入）
        ('revenue_growth', 'growth', 'positive', '营收增长率', '(revenue_now - revenue_prev) / revenue_prev'),
        ('profit_growth', 'growth', 'positive', '利润增长率', '(profit_now - profit_prev) / profit_prev'),
        ('equity_growth', 'growth', 'positive', '净资产增长率', '(equity_now - equity_prev) / equity_prev'),
        ('profit_cagr', 'growth', 'positive', '净利润复合增长率', 'CAGR(net_profit, 3年)'),

        # 财务结构因子（适中偏好）
        ('debt_ratio', 'structure', 'neutral', '资产负债率', 'total_liabilities / total_assets'),
        ('current_ratio', 'structure', 'positive', '流动比率', 'current_assets / current_liabilities'),
        ('quick_ratio', 'structure', 'positive', '速动比率', '(current_assets - inventory) / current_liabilities'),
        ('equity_multiplier', 'structure', 'neutral', '权益乘数', 'total_assets / total_equity'),

        # 现金流因子（现金流优良买入）
        ('cash_to_profit', 'cashflow', 'positive', '经营现金流/净利润', 'oper_cash_flow / net_profit'),

        # 衍生因子
        ('pb_roe_roe', 'derived', 'negative', 'PB/ROE/ROE', 'PB / ((ROE*100) * (ROE*100))'),
        ('pe_roe', 'derived', 'negative', 'PE/ROE', 'PE / (ROE*100)'),
    ]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 持续增量写入，确保新增因子元数据能够自动补齐
    for factor_name, category, direction, description, formula in metadata:
        cursor.execute('''
            INSERT OR IGNORE INTO factor_metadata
            (factor_name, factor_category, factor_direction, description, formula)
            VALUES (?, ?, ?, ?, ?)
        ''', (factor_name, category, direction, description, formula))
        cursor.execute('''
            UPDATE factor_metadata
            SET factor_category = ?, factor_direction = ?, description = ?, formula = ?
            WHERE factor_name = ?
        ''', (category, direction, description, formula, factor_name))

    # 清理已废弃的估算型因子
    cursor.execute(
        "DELETE FROM factor_metadata WHERE factor_name IN ('fcf', 'cash_yield', 'pb_roe', 'pe_growth', 'altman_z')"
    )

    conn.commit()
    cursor.execute('SELECT COUNT(*) FROM factor_metadata')
    count = cursor.fetchone()[0]
    print(f"[OK] 因子元数据初始化完成，当前共 {count} 个因子")

    conn.close()


def check_tables(db_path: str = None):
    """检查数据库表是否存在"""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]

    # 检查关键列
    print("\n数据库表检查:")
    print("=" * 50)

    for table in ['factor_values', 'factor_metadata', 'factor_calc_log']:
        if table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [col[1] for col in cursor.fetchall()]
            print(f"  [OK] {table}: {', '.join(cols)}")
        else:
            print(f"  [MISSING] {table}")

    conn.close()


if __name__ == "__main__":
    import sys

    print("因子分析数据库 Schema 初始化")
    print("=" * 50)

    db_path = get_db_path()
    print(f"数据库路径: {db_path}")
    print(f"数据库存在: {db_path.exists()}")
    print()

    # 初始化表
    init_factor_tables()

    # 初始化元数据
    init_factor_metadata()

    # 检查表
    check_tables()

    print()
    print("=" * 50)
    print("初始化完成！")
