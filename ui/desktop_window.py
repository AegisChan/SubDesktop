import ctypes
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QEvent, QFileSystemWatcher, QTimer, QPoint, QRect
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox

from core.profile_storage import ProfileStorage
from ui.desktop_canvas import DesktopCanvas
from ui.profile_dialog import ProfileDialog

logger = logging.getLogger("SubDesktop.DesktopWindow")

class SubDesktopWindow(QMainWindow):
    """
    独立子桌面主视窗
    具备高 DPI 适配、尺寸持久化、真实文件系统实时监听、全屏/窗口切换能力
    """

    def __init__(
        self,
        profile_id: str,
        parent: Optional[QMainWindow] = None,
        dpr_override: Optional[float] = None,
    ):
        super().__init__(parent)
        self.profile_id = profile_id
        self._dpr_override = dpr_override
        self._active_dpr: float = 1.0
        self._dpi_hooks_installed: bool = False
        self._connected_screen = None
        self._clamping_pos: bool = False

        # 读取配置并初始化
        self.profile_data = ProfileStorage.get_profile(self.profile_id)
        if not self.profile_data:
            raise ValueError(f"未找到 Profile 配置: {profile_id}")

        self._init_window()
        self._init_canvas()
        self._init_watcher()
        self._active_dpr = self._get_current_dpr()

    def _init_window(self):
        name = self.profile_data.get("name", "子桌面")
        self.setWindowTitle(f"SubDesktop - {name}")

        rect = self.profile_data.get("window_rect", {})
        x = rect.get("x", 150)
        y = rect.get("y", 100)
        w = rect.get("width", 960)
        h = rect.get("height", 540)

        self._apply_dpi_safe_geometry(x, y, w, h)

    def _get_current_dpr(self, x: Optional[int] = None, y: Optional[int] = None) -> float:
        """获取指定坐标或当前窗口所在屏幕的 devicePixelRatio"""
        if self._dpr_override is not None and self._dpr_override > 0:
            return float(self._dpr_override)
        screen = None
        if x is not None and y is not None:
            screen = QApplication.screenAt(QPoint(x, y))
        if screen is None and hasattr(self, "windowHandle") and self.windowHandle() is not None:
            screen = self.windowHandle().screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            val = float(screen.devicePixelRatio())
            if val > 0:
                return val
        return 1.0

    def _apply_dpi_safe_geometry(self, x: int, y: int, target_w: int, target_h: int):
        """
        将配置的物理像素分辨率 (target_w × target_h) 按 1 / dpr 换算为 Qt 逻辑像素尺寸，
        确保不同系统 DPI 缩放下屏幕物理占地面积 1:1 恒定；
        仅在超出当前屏幕 availableGeometry() 时做安全钳制，越界则自动居中。
        """
        dpr = self._get_current_dpr(x, y)
        screen = QApplication.screenAt(QPoint(x, y)) or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
        else:
            avail = QRect(0, 0, 1280, 720)

        logical_w = max(200, int(round(target_w / dpr)))
        logical_h = max(150, int(round(target_h / dpr)))

        # 仅在超出当前屏幕可用区域时做最大值安全钳制
        logical_w = min(logical_w, max(200, avail.width()))
        logical_h = min(logical_h, max(150, avail.height()))

        self.setMinimumSize(min(int(round(400 / dpr)), logical_w), min(int(round(300 / dpr)), logical_h))
        self.resize(logical_w, logical_h)
        self.move(x, y)
        self.clamp_window_to_screen()

    def clamp_window_to_screen(self):
        """
        屏幕边界安全保护（基于包含标题栏和外边框的 frameGeometry()）：
        1. 计算边框偏移量 top_offset / left_offset；
        2. 严格保证 fg.left() >= avail.left()、fg.right() <= avail.right()、
           fg.top() >= avail.top()、fg.bottom() <= avail.bottom()；
        3. 绝不允许标题栏或关闭按钮跑出屏幕可视区域之外。
        """
        if self._clamping_pos or self.isFullScreen() or self.isMaximized():
            return

        g = self.geometry()
        fg = self.frameGeometry()
        screen = (
            QApplication.screenAt(fg.center())
            or QApplication.screenAt(fg.topLeft())
            or QApplication.primaryScreen()
        )
        avail = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)

        top_offset = max(0, g.top() - fg.top())
        left_offset = max(0, g.left() - fg.left())
        fw = max(g.width(), fg.width())
        fh = max(g.height(), fg.height())

        target_fg_left = fg.left()
        target_fg_top = fg.top()

        if fw >= avail.width():
            target_fg_left = avail.left()
        else:
            target_fg_left = max(avail.left(), min(target_fg_left, avail.right() - fw + 1))

        if fh >= avail.height():
            target_fg_top = avail.top()
        else:
            target_fg_top = max(avail.top(), min(target_fg_top, avail.bottom() - fh + 1))

        # 绝对红线：外框顶部与左边绝不允许小于 avail.top() / avail.left()
        target_fg_left = max(avail.left(), target_fg_left)
        target_fg_top = max(avail.top(), target_fg_top)

        if target_fg_left != fg.left() or target_fg_top != fg.top():
            self._clamping_pos = True
            try:
                self.move(target_fg_left, target_fg_top)
                # 兜底核验：若 move() 在部分窗口管理器下作用于客户区导致外框仍偏上，则补偿偏移量
                after_fg = self.frameGeometry()
                if after_fg.top() < avail.top() or after_fg.left() < avail.left():
                    self.move(target_fg_left + left_offset, target_fg_top + top_offset)
            finally:
                self._clamping_pos = False

    def _init_canvas(self):
        self.canvas = DesktopCanvas(self.profile_id, self, dpr_override=self._dpr_override)
        self.canvas.open_settings_requested.connect(self._open_settings_dialog)
        self.setCentralWidget(self.canvas)

    def _connect_screen_dpi_signals(self, screen):
        """绑定屏幕 DPI 变更信号（支持 Windows 显示设置动态调整缩放比例）"""
        if screen is None or screen is self._connected_screen:
            return
        if self._connected_screen is not None:
            try:
                self._connected_screen.logicalDotsPerInchChanged.disconnect(self._on_dpi_signal)
                self._connected_screen.physicalDotsPerInchChanged.disconnect(self._on_dpi_signal)
            except Exception:
                pass
        self._connected_screen = screen
        try:
            screen.logicalDotsPerInchChanged.connect(self._on_dpi_signal)
            screen.physicalDotsPerInchChanged.connect(self._on_dpi_signal)
        except Exception:
            pass

    def _on_screen_changed(self, screen):
        self._connect_screen_dpi_signals(screen)
        QTimer.singleShot(0, self._check_and_reapply_dpi)
        QTimer.singleShot(80, self.clamp_window_to_screen)

    def _on_dpi_signal(self, *_args):
        QTimer.singleShot(0, self._check_and_reapply_dpi)
        QTimer.singleShot(80, self.clamp_window_to_screen)

    def _check_and_reapply_dpi(self):
        new_dpr = self._get_current_dpr()
        if abs(new_dpr - self._active_dpr) > 0.01:
            self.apply_physical_metrics()

    def apply_physical_metrics(self, new_dpr: Optional[float] = None):
        """
        运行期实时重算子桌面物理像素度量（无需关闭重启）：
        1. 按最新 dpr 重算窗口逻辑宽高（保持物理占地面积恒定）；
        2. 同步刷新画布网格步长、所有图标尺寸、物理像素贴图、像素字体及坐标映射；
        3. 立即并延迟 80ms 二次执行 frameGeometry 边界钳制，防止 Windows 缩放重排将标题栏顶出屏幕。
        """
        if new_dpr is not None and new_dpr > 0:
            self._dpr_override = float(new_dpr)
            if hasattr(self, "canvas") and self.canvas is not None:
                self.canvas._dpr_override = float(new_dpr)

        dpr = self._get_current_dpr()
        self._active_dpr = dpr

        cur_profile = ProfileStorage.get_profile(self.profile_id) or self.profile_data
        rect = cur_profile.get("window_rect", {})
        phys_w = rect.get("width", 960)
        phys_h = rect.get("height", 540)
        self._apply_dpi_safe_geometry(self.x(), self.y(), phys_w, phys_h)

        if hasattr(self, "canvas") and self.canvas is not None:
            self.canvas.apply_physical_metrics()
        self.clamp_window_to_screen()
        QTimer.singleShot(80, self.clamp_window_to_screen)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._dpi_hooks_installed and self.windowHandle() is not None:
            self._dpi_hooks_installed = True
            try:
                self.windowHandle().screenChanged.connect(self._on_screen_changed)
            except Exception:
                pass
            self._connect_screen_dpi_signals(self.windowHandle().screen() or QApplication.primaryScreen())
        self._check_and_reapply_dpi()
        self.clamp_window_to_screen()
        QTimer.singleShot(80, self.clamp_window_to_screen)

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self._clamping_pos and not self.isFullScreen() and not self.isMaximized():
            fg = self.frameGeometry()
            screen = QApplication.screenAt(fg.center()) or QApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                if fg.top() < avail.top() or fg.left() < avail.left():
                    QTimer.singleShot(0, self.clamp_window_to_screen)

    def changeEvent(self, event):
        super().changeEvent(event)
        # QEvent.ScreenChangeInternal == 214 (部分 PyQt5 版本未暴露该枚举属性)
        screen_change_evt = getattr(QEvent, "ScreenChangeInternal", 214)
        if event.type() in (screen_change_evt, QEvent.FontChange):
            QTimer.singleShot(0, self._check_and_reapply_dpi)
            QTimer.singleShot(80, self.clamp_window_to_screen)

    def nativeEvent(self, eventType, message):
        """捕获 Windows 原生 WM_DPICHANGED (0x02E0) 消息，立即重算并在系统重排后延迟兜底钳制"""
        try:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG") and message is not None:
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x02E0:  # WM_DPICHANGED
                    QTimer.singleShot(0, self.apply_physical_metrics)
                    QTimer.singleShot(80, self.clamp_window_to_screen)
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

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

            # 调整窗口尺寸（按当前屏幕 DPR 进行物理->逻辑换算与边界钳制）
            rect = self.profile_data.get("window_rect", {})
            w = rect.get("width", 960)
            h = rect.get("height", 540)
            self._apply_dpi_safe_geometry(self.x(), self.y(), w, h)

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
        """窗口关闭时保存图标坐标与安全钳制后的窗口位置 (x, y)，严禁覆盖预设宽高 (width, height)"""
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.save_all_positions()
        if not self.isFullScreen() and not self.isMaximized():
            self.clamp_window_to_screen()
            cur_profile = ProfileStorage.get_profile(self.profile_id) or self.profile_data
            preset_rect = cur_profile.get("window_rect", {})
            preset_w = preset_rect.get("width", 960)
            preset_h = preset_rect.get("height", 540)
            ProfileStorage.update_window_rect(
                self.profile_id, self.x(), self.y(), preset_w, preset_h
            )
        super().closeEvent(event)

