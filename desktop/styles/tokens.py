"""
设计令牌 (Design Tokens) — 全桌面端唯一样式事实来源

所有颜色/间距/字体/圆角/阴影只允许从这里取。
theme.qss 与本文件保持一致（QSS 不支持变量，色值同步硬编码，
修改时必须双改）。

规范依据：docs/ui_polish_plan.md（Phase 1 已批准）
"""

# ============ 色板 ============
# 主色
PRIMARY = "#378ADD"
PRIMARY_HOVER = "#185FA5"
PRIMARY_PRESSED = "#042C53"
PRIMARY_100 = "#B5D4F4"
PRIMARY_50 = "#E6F1FB"

# 涨跌（A股惯例：涨红跌绿）
UP = "#E24B4A"
DOWN = "#639922"
WARNING = "#EF9F27"
ERROR = UP
SUCCESS = DOWN

# 文字
TEXT_1 = "#212529"   # 主标题/数值
TEXT_2 = "#343A40"   # 正文
TEXT_3 = "#6C757D"   # 辅助说明
TEXT_4 = "#ADB5BD"   # 禁用/占位

# 背景与边框
BG_PAGE = "#F5F6F8"        # 页面底色（略深，衬托白卡）
BG_CARD = "#FFFFFF"        # 卡片
BG_SUBTLE = "#F8F9FA"      # 表头/输入禁用
BG_MUTED = "#F1F3F5"       # hover 弱反馈
BORDER = "#E9ECEF"         # 卡片/控件边框
DIVIDER = "#F1F3F5"        # 行分隔线
HOVER_BG = "#F1F6FC"       # 行 hover
SELECT_BG = "#E6F1FB"      # 行选中（轻）+ 左侧竖线指示

# ============ 间距（4px 基栅） ============
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 20
SPACE_6 = 24
SPACE_8 = 32

# 页面边距（全局唯一）：左右 24，上下 20
PAGE_MARGIN = (24, 20, 24, 20)
SECTION_GAP = 16      # 区块（卡片）间距唯一值
CONTROL_GAP = 8       # 控件间距唯一值
CARD_PADDING = 16     # 卡片内边距

# ============ 字体阶梯 ============
FONT_H1 = 20          # 页面标题 / weight 600
FONT_H2 = 16          # 区块标题 / weight 600
FONT_H3 = 14          # 卡片标题 / weight 600
FONT_BODY = 14        # 正文 / weight 400
FONT_BODY_MED = 14    # 正文强调 / weight 500
FONT_CAPTION = 12     # 辅助说明 / weight 400
FONT_METRIC = 24      # MetricCard 数值 / weight 700

# 数字等宽字体族（表格数值列、指标数值、涨跌幅）
FONT_NUMERIC_FAMILY = '"DIN Alternate", "Roboto Mono", "Consolas", "Courier New", monospace'
FONT_FAMILY = '"PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif'

# ============ 圆角（语义化） ============
RADIUS_SM = 4    # 控件（按钮/输入框/下拉）
RADIUS_MD = 8    # 容器（卡片/表格/弹窗/菜单）
RADIUS_LG = 12   # 仅 Hero

# ============ 控件尺寸 ============
CONTROL_HEIGHT = 32     # 所有可交互控件统一高度
ROW_HEIGHT = 40         # 表格行高
HEADER_HEIGHT = 40      # 表头高
NAV_WIDTH = 200         # 侧边导航宽
WINDOW_MIN_WIDTH = 1080
WINDOW_MIN_HEIGHT = 700

# ============ 阴影（QSS 仅支持有限阴影，记录在案供 QGraphicsDropShadowEffect 使用） ============
SHADOW_CARD = (0, 1, 2, "rgba(16,24,40,0.05)")    # x, y, blur, color
SHADOW_POP = (0, 4, 12, "rgba(16,24,40,0.10)")    # 浮层/菜单/批量操作栏
