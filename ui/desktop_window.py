import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QFileSystemWatcher, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMainWindow, QMessageBox

from core.profile_storage import ProfileStorage
from ui.desktop_canvas import DesktopCanvas
from ui.profile_dialog import ProfileDialog

logger = logging.getLogger("SubDesktop.DesktopWindow")

class SubDesktopWindow(QMainWindow):
    """
    独立子桌面主视窗
    具备高 DPI 适配、尺寸持久化、真实文件系统实时监听、全屏/窗口切换能力
    """

    def __init__(self, profile_id: str, parent: Optional[QMainWindow] = None):
        super().__init__(parent)
        self.profile_id = profile_id

        # 读取配置并初始化
        self.profile_data = ProfileStorage.get_profile(self.profile_id)
        if not self.profile_data:
            raise ValueError(f"未找到 Profile 配置: {profile_id}")

        self._init_window()
        self._init_canvas()
        self._init_watcher()

    def _init_window(self):
        name = self.profile_data.get("name", "子桌面")
        self.setWindowTitle(f"SubDesktop - {name}")

        rect = self.profile_data.get("window_rect", {})
        x = rect.get("x", 150)
        y = rect.get("y", 100)
        w = rect.get("width", 960)
        h = rect.get("height", 540)

        self.setGeometry(x, y, w, h)
        self.setMinimumSize(400, 300)

    def _init_canvas(self):
        self.canvas = DesktopCanvas(self.profile_id, self)
        self.canvas.open_settings_requested.connect(self._open_settings_dialog)
        self.setCentralWidget(self.canvas)

    def _init_watcher(self):
        """配置映射物理目录的实时动态变更监听"""
        self.watcher = QFileSystemWatcher(self)
        self._update_watched_dir()
        self.watcher.directoryChanged.connect(self._on_dir_changed)

    def _update_watched_dir(self):
        current_dirs = self.watcher.directories()
        if current_dirs:
            self.watcher.removePaths(current_dirs)

        target = self.profile_data.get("target_path")
        if target and Path(target).exists() and Path(target).is_dir():
            self.watcher.addPath(str(Path(target).resolve()))

    def _on_dir_changed(self, path: str):
        """物理目录发生外部改动时防抖刷新"""
        # 使用 QTimer 单次触发防抖，避免高频文件变动引起的重复计算
        QTimer.singleShot(150, self.canvas.sync_items_from_disk)

    def _open_settings_dialog(self):
        """打开子桌面配置修改对话框"""
        cur_profile = ProfileStorage.get_profile(self.profile_id)
        if not cur_profile:
            return

        dialog = ProfileDialog(cur_profile, self)
        if dialog.exec_() == ProfileDialog.Accepted:
            self.profile_data = dialog.profile_data
            self.setWindowTitle(f"SubDesktop - {self.profile_data.get('name', '子桌面')}")

            # 调整窗口尺寸
            rect = self.profile_data.get("window_rect", {})
            w = rect.get("width", self.width())
            h = rect.get("height", self.height())
            self.resize(w, h)

            # 重新加载画布与文件监听
            self.canvas.reload_config()
            self._update_watched_dir()

    def keyPressEvent(self, event):
        # F11 或 Alt+Enter 全屏切换
        if event.key() == Qt.Key_F11 or (
            event.key() == Qt.Key_Return and (event.modifiers() & Qt.AltModifier)
        ):
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            event.accept()
            return
        elif event.key() == Qt.Key_Comma and (event.modifiers() & Qt.ControlModifier):
            self._open_settings_dialog()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """窗口关闭时自动全量持久化所有图标坐标与当前几何状态"""
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.save_all_positions()
        if not self.isFullScreen() and not self.isMaximized():
            geo = self.geometry()
            ProfileStorage.update_window_rect(
                self.profile_id, geo.x(), geo.y(), geo.width(), geo.height()
            )
        super().closeEvent(event)

