"""SubDesktop UI 样式与主题定义"""

MAIN_STYLE = """
/* 全局基础设置：统一采用 Microsoft YaHei UI */
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 9pt;
    color: #2b2b2b;
}

/* 主管理器窗口背景 */
QMainWindow#ManagerWindow {
    background-color: #f4f6f9;
}

/* 顶部操作横栏 */
QFrame#HeaderBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e1e4e8;
    padding: 12px 20px;
}

QLabel#HeaderTitle {
    font-size: 18px;
    font-weight: bold;
    color: #1a1a1a;
}

QLabel#HeaderSubtitle {
    font-size: 12px;
    color: #6a737d;
}

/* 核心主按钮 */
QPushButton#PrimaryButton {
    background-color: #0969da;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover {
    background-color: #0856b3;
}
QPushButton#PrimaryButton:pressed {
    background-color: #06438a;
}

/* 次要/常规按钮 */
QPushButton#SecondaryButton {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 7px 14px;
}
QPushButton#SecondaryButton:hover {
    background-color: #f3f4f6;
    border-color: #bbc0c5;
}
QPushButton#SecondaryButton:pressed {
    background-color: #ebecf0;
}

/* 危险操作按钮 (解除映射) */
QPushButton#DangerButton {
    background-color: #ffffff;
    color: #cf222e;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton#DangerButton:hover {
    background-color: #ffebe9;
    border-color: #fd8c73;
}
QPushButton#DangerButton:pressed {
    background-color: #ffcecb;
}

/* 卡片操作按钮专用紧凑排布样式 (收紧 padding 与字体，确保不换行) */
QPushButton.CardBtnPrimary {
    background-color: #0969da;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton.CardBtnPrimary:hover {
    background-color: #0856b3;
}
QPushButton.CardBtnPrimary:pressed {
    background-color: #06438a;
}

QPushButton.CardBtnSecondary {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
}
QPushButton.CardBtnSecondary:hover {
    background-color: #f3f4f6;
    border-color: #bbc0c5;
}
QPushButton.CardBtnSecondary:pressed {
    background-color: #ebecf0;
}

QPushButton.CardBtnDanger {
    background-color: #ffffff;
    color: #cf222e;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
}
QPushButton.CardBtnDanger:hover {
    background-color: #ffebe9;
    border-color: #fd8c73;
}
QPushButton.CardBtnDanger:pressed {
    background-color: #ffcecb;
}

/* 滚动区背景 */
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* Profile 卡片样式 */
QFrame.ProfileCard {
    background-color: #ffffff;
    border: 1px solid #e1e4e8;
    border-radius: 8px;
    padding: 16px;
}
QFrame.ProfileCard:hover {
    border-color: #0969da;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

QLabel.CardTitle {
    font-size: 16px;
    font-weight: bold;
    color: #24292f;
}

QLabel.CardPath {
    font-size: 12px;
    color: #57606a;
}

QLabel.Badge {
    background-color: #eef2f6;
    color: #0969da;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
}

QLabel.BadgeSuccess {
    background-color: #dafbe1;
    color: #1a7f37;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
}

/* 表单输入框与下拉列表 */
QLineEdit, QComboBox, QSpinBox {
    background-color: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 6px 10px;
    color: #24292f;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #0969da;
    outline: none;
}

/* 右键上下文菜单 */
QMenu {
    background-color: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #eef2f6;
    color: #0969da;
}
QMenu::separator {
    height: 1px;
    background-color: #e1e4e8;
    margin: 4px 6px;
}
"""

DESKTOP_CANVAS_STYLE = """
/* 子桌面画布暗调优雅底色 */
QWidget#DesktopCanvas {
    background-color: #1e2530;
}
"""

