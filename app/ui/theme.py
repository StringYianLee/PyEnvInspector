"""现代化主题(QSS)与色板 —— 支持浅色/深色两套。

主题在**应用启动时**确定(``use_dark()`` 在创建任何窗口之前调用),
因此各模块 ``Palette.xxx`` 的运行时读取都能拿到正确值;
切换主题后提示用户重启生效(避免运行中重建全部控件的复杂度)。
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QColor

_LIGHT = {
    "bg": "#eef1f6",
    "surface": "#ffffff",
    "surface_alt": "#f6f8fb",
    "border": "#e3e7ef",
    "border_strong": "#c9d1e0",
    "text": "#1f2533",
    "text_muted": "#5f6979",
    "text_faint": "#aab2c3",
    "primary": "#3d6df2",
    "primary_hover": "#2f5ae0",
    "primary_soft": "#e8eefe",
    "ok": "#18a058",
    "ok_soft": "#e6f6ee",
    "warn": "#e8850c",
    "warn_soft": "#fdf2e2",
    "error": "#dc3545",
    "error_soft": "#fdebec",
    "info": "#3d6df2",
    "info_soft": "#e8eefe",
    "neutral_soft": "#eef1f6",
    "graph_bg": "#fafbfd",
    "edge_normal": "#c4cbdb",
    "edge_ok": "#8fc7a8",
    "edge_conflict": "#e4404f",
    "edge_missing": "#ef9f3c",
    "node_normal_border": "#d4dae7",
    "node_ghost_border": "#e8b478",
    "tooltip_bg": "#2b3245",
    "row_alt": "#f6f8fb",
    "on_primary": "#ffffff",
    "danger_text": "#c8303e",
    "success_text": "#2f8f5b",
}

_DARK = {
    "bg": "#12161f",
    "surface": "#1a1f2b",
    "surface_alt": "#232936",
    "border": "#2f3749",
    "border_strong": "#414b60",
    # 深色下正文/次级文字整体提亮(此前 #e6e9f0/#98a1b3 在暗底上偏灰)
    "text": "#f2f5fa",
    "text_muted": "#b8c2d4",
    "text_faint": "#8b95a8",
    "primary": "#6b9bff",
    "primary_hover": "#8ab0ff",
    "primary_soft": "#22304f",
    "ok": "#4ed08a",
    "ok_soft": "#14301f",
    "warn": "#f5b25c",
    "warn_soft": "#3a2a13",
    "error": "#ff7b86",
    "error_soft": "#3d1a1f",
    "info": "#6b9bff",
    "info_soft": "#22304f",
    "neutral_soft": "#232936",
    "graph_bg": "#151a24",
    "edge_normal": "#4a5568",
    "edge_ok": "#4a8f6b",
    "edge_conflict": "#ff7b86",
    "edge_missing": "#f5b25c",
    "node_normal_border": "#414b60",
    "node_ghost_border": "#b98232",
    "tooltip_bg": "#0d1119",
    "row_alt": "#202633",
    "on_primary": "#0d1119",
    "danger_text": "#ff9aa3",
    "success_text": "#63d99b",
}


class Palette:
    """全局色板(浅色主题为默认值)。"""

    # 基础
    bg = "#eef1f6"          # 窗体背景
    surface = "#ffffff"     # 卡片/表面
    surface_alt = "#f6f8fb" # 次级表面(表头、悬浮)
    border = "#e3e7ef"
    border_strong = "#c9d1e0"
    text = "#1f2533"
    text_muted = "#5f6979"
    text_faint = "#aab2c3"

    # 品牌色
    primary = "#3d6df2"
    primary_hover = "#2f5ae0"
    primary_soft = "#e8eefe"

    # 语义色
    ok = "#18a058"
    ok_soft = "#e6f6ee"
    warn = "#e8850c"
    warn_soft = "#fdf2e2"
    error = "#dc3545"
    error_soft = "#fdebec"
    info = "#3d6df2"
    info_soft = "#e8eefe"
    neutral_soft = "#eef1f6"

    # 依赖图专用
    graph_bg = "#fafbfd"
    edge_normal = "#c4cbdb"
    edge_ok = "#8fc7a8"
    edge_conflict = "#e4404f"
    edge_missing = "#ef9f3c"
    node_normal_border = "#d4dae7"
    node_ghost_border = "#e8b478"

    # 细节
    tooltip_bg = "#2b3245"
    row_alt = "#f6f8fb"
    on_primary = "#ffffff"
    danger_text = "#c8303e"
    success_text = "#2f8f5b"

    is_dark = False


def use_dark(dark: bool) -> None:
    """切换色板(必须在创建任何窗口之前调用)。"""
    source = _DARK if dark else _LIGHT
    for key, value in source.items():
        setattr(Palette, key, value)
    Palette.is_dark = bool(dark)


def status_color(variant: str) -> str:
    """语义色(动态读取, 支持主题切换)。"""
    table = {
        "ok": Palette.ok,
        "warn": Palette.warn,
        "error": Palette.error,
        "info": Palette.info,
        "muted": Palette.text_muted,
    }
    return table.get(variant, Palette.text_muted)


def status_soft_color(variant: str) -> str:
    table = {
        "ok": Palette.ok_soft,
        "warn": Palette.warn_soft,
        "error": Palette.error_soft,
        "info": Palette.info_soft,
        "muted": Palette.neutral_soft,
    }
    return table.get(variant, Palette.neutral_soft)


def qcolor(hexstr: str) -> QColor:
    return QColor(hexstr)


def build_qss() -> str:
    p = Palette
    return f"""
* {{
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    outline: none;
}}
QMainWindow, QWidget#root, QDialog, QMessageBox {{ background: {p.bg}; }}
QDialog QLabel, QMessageBox QLabel {{ color: {p.text}; }}
QToolTip {{
    background: {p.tooltip_bg}; color: {p.text}; border: 1px solid {p.border_strong};
    padding: 6px 10px; border-radius: 6px; font-size: 12px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {p.surface}; color: {p.text};
    border: 1px solid {p.border_strong}; border-radius: 8px;
    padding: 7px 16px; font-size: 13px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {p.primary}; color: {p.primary}; }}
QPushButton:pressed {{ background: {p.surface_alt}; }}
QPushButton:disabled {{ color: {p.text_faint}; border-color: {p.border}; background: {p.surface_alt}; }}
QPushButton[variant="primary"] {{
    background: {p.primary}; color: #ffffff; border: none;
}}
QPushButton[variant="primary"]:hover {{ background: {p.primary_hover}; }}
QPushButton[variant="primary"]:disabled {{ background: #a9bdf5; }}
QPushButton[variant="ghost"] {{
    background: transparent; border: 1px dashed {p.border_strong};
}}
QPushButton:focus {{ border-color: {p.primary}; }}
QComboBox:focus {{ border-color: {p.primary}; }}
QTabBar::tab:focus {{ color: {p.text}; }}

/* ---------- 输入 ---------- */
QLineEdit {{
    background: {p.surface}; border: 1px solid {p.border_strong};
    border-radius: 8px; padding: 7px 12px; font-size: 13px; color: {p.text};
}}
QLineEdit:focus {{ border-color: {p.primary}; }}
QComboBox {{
    background: {p.surface}; border: 1px solid {p.border_strong};
    border-radius: 8px; padding: 6px 12px; font-size: 13px; color: {p.text};
}}
QComboBox:hover {{ border-color: {p.primary}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {p.surface}; border: 1px solid {p.border};
    border-radius: 8px; selection-background-color: {p.primary_soft};
    selection-color: {p.primary}; outline: none; padding: 4px;
}}

/* ---------- 表格 ---------- */
QTableView {{
    background: {p.surface}; border: 1px solid {p.border};
    border-radius: 10px; gridline-color: {p.border};
    alternate-background-color: {p.surface_alt};
}}
QTableView::item {{ padding: 6px 10px; border-bottom: 1px solid {p.border}; }}
QTableView::item:selected {{ background: {p.primary_soft}; color: {p.text}; }}
QHeaderView::section {{
    background: {p.surface_alt}; color: {p.text_muted};
    border: none; border-bottom: 1px solid {p.border};
    padding: 8px 10px; font-size: 12px; font-weight: 700;
}}
QTableCornerButton::section {{ background: {p.surface_alt}; border: none; }}

QTableWidget {{
    background: {p.surface}; border: 1px solid {p.border};
    border-radius: 10px; gridline-color: {p.border};
}}
QTableWidget::item {{ padding: 5px 8px; }}
QTableWidget::item:selected {{ background: {p.primary_soft}; color: {p.text}; }}
QTableWidget QHeaderView::section {{
    background: {p.surface_alt}; color: {p.text_muted};
    border: none; border-bottom: 1px solid {p.border};
    padding: 7px 8px; font-size: 12px; font-weight: 700;
}}

/* ---------- 标签页 ---------- */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {p.text_muted};
    padding: 9px 18px; margin-right: 6px; font-size: 13px; font-weight: 600;
    border: none; border-bottom: 3px solid transparent;
}}
QTabBar::tab:hover {{ color: {p.text}; }}
QTabBar::tab:selected {{ color: {p.primary}; border-bottom: 3px solid {p.primary}; }}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c9d1e0; border-radius: 5px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: #aeb9cf; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #c9d1e0; border-radius: 5px; min-width: 36px;
}}
QScrollBar::handle:horizontal:hover {{ background: #aeb9cf; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- 卡片 ---------- */
QFrame#card {{
    background: {p.surface}; border: 1px solid {p.border};
    border-radius: 12px;
}}

/* ---------- 侧边栏导航 ---------- */
QToolButton#navButton {{
    background: transparent; border: none; border-radius: 10px;
    padding: 10px 0; font-size: 12px; font-weight: 600; color: {p.text_muted};
}}
QToolButton#navButton:hover {{ background: #e4e9f4; color: {p.text}; }}
QToolButton#navButton:checked {{ background: {p.primary}; color: #ffffff; }}

/* ---------- 徽章 ---------- */
QLabel[variant="ok"], QLabel[variant="warn"], QLabel[variant="error"],
QLabel[variant="info"], QLabel[variant="muted"] {{
    border-radius: 7px; padding: 2px 9px; font-size: 11px; font-weight: 700;
}}
QLabel[variant="ok"] {{ background: {p.ok_soft}; color: {p.ok}; }}
QLabel[variant="warn"] {{ background: {p.warn_soft}; color: {p.warn}; }}
QLabel[variant="error"] {{ background: {p.error_soft}; color: {p.error}; }}
QLabel[variant="info"] {{ background: {p.info_soft}; color: {p.info}; }}
QLabel[variant="muted"] {{ background: {p.neutral_soft}; color: {p.text_muted}; }}

/* ---------- 分割器 ---------- */
QSplitter::handle {{ background: transparent; width: 6px; }}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background: {p.surface_alt}; border: none; border-radius: 4px;
    min-height: 8px; max-height: 8px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {p.primary}; border-radius: 4px; }}

/* ---------- 状态栏 ---------- */
QStatusBar {{ background: transparent; color: {p.text_muted}; font-size: 12px; }}
"""


def build_palette():
    """根据当前色板构造完整 QPalette。

    QSS 只覆盖显式声明的控件; 滚动区视口、表格空白区、对话框底色等
    由 QPalette 决定 —— 深色主题下若不更新它, 会出现"深色文字 +
    浅色底"的不可读组合。
    """
    from PySide6.QtGui import QPalette

    p = QPalette()
    role = QPalette.ColorRole
    p.setColor(role.Window, QColor(Palette.bg))
    p.setColor(role.WindowText, QColor(Palette.text))
    p.setColor(role.Base, QColor(Palette.surface))
    p.setColor(role.AlternateBase, QColor(Palette.row_alt))
    p.setColor(role.Text, QColor(Palette.text))
    p.setColor(role.Button, QColor(Palette.surface))
    p.setColor(role.ButtonText, QColor(Palette.text))
    p.setColor(role.BrightText, QColor("#ffffff"))
    p.setColor(role.Highlight, QColor(Palette.primary))
    p.setColor(role.HighlightedText, QColor(Palette.on_primary))
    p.setColor(role.ToolTipBase, QColor(Palette.tooltip_bg))
    p.setColor(role.ToolTipText, QColor(Palette.text))
    p.setColor(role.PlaceholderText, QColor(Palette.text_faint))
    p.setColor(role.Link, QColor(Palette.primary))
    # 禁用态: 弱化但仍可辨识
    for r in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, r, QColor(Palette.text_faint))
    return p


def apply_theme(app) -> None:
    """应用全局主题与默认字体(支持运行中重新调用以实现实时换肤)。"""
    font = QFont()
    font.setFamilies(["Segoe UI", "Microsoft YaHei UI", "SimHei", "PingFang SC"])
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(build_qss())
    app.setPalette(build_palette())
