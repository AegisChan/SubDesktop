import argparse
import logging
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SubDesktop")

def main():
    # 显式开启 PyQt5 高 DPI 缩放适配，确保在 Win10/Win11 高分屏下界面与文字清晰不模糊
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("SubDesktop")
    app.setOrganizationName("SubDesktopOpenSource")

    parser = argparse.ArgumentParser(description="SubDesktop - Windows 独立子桌面增强工具")
    parser.add_argument("--manager", action="store_true", help="启动主管理控制台")
    parser.add_argument("--profile", type=str, default="", help="直接启动指定的子桌面 Profile ID")

    args, unknown = parser.parse_known_args()

    # 路由启动
    if args.profile:
        # 直接启动子桌面独立视窗
        from core.profile_storage import ProfileStorage
        from ui.desktop_window import SubDesktopWindow

        profile = ProfileStorage.get_profile(args.profile)
        if not profile:
            QMessageBox.critical(
                None,
                "错误",
                f"未找到指定的子桌面配置: {args.profile}\n请打开管理中心重新配置或检查路径。",
            )
            return 1

        window = SubDesktopWindow(args.profile)
        window.show()
    else:
        # 默认启动管理控制台
        from ui.manager_window import ManagerWindow

        window = ManagerWindow()
        window.show()

    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())

