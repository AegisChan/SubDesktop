import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QMessageBox,
    QSizePolicy,
)

from core.file_ops import FileOps
from core.profile_storage import ProfileStorage
from core.shortcut_helper import ShortcutHelper
from ui.profile_dialog import ProfileDialog
from ui.styles import MAIN_STYLE

class ElidedPathLabel(QLabel):
    """自适应中间截断路径标签，杜绝超长路径将卡片异常横向撑宽"""

    def __init__(self, full_path: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.full_path = full_path
        self.setToolTip(f"完整映射物理路径:\n{full_path}")
        self.setProperty("class", "CardPath")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(80)
        self._update_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()

    def _update_text(self):
        metrics = self.fontMetrics()
        prefix = "📁 物理映射: "
        prefix_w = metrics.horizontalAdvance(prefix)
        avail_w = self.width() - prefix_w - 6
        if avail_w > 40:
            elided = metrics.elidedText(self.full_path, Qt.ElideMiddle, avail_w)
            self.setText(prefix + elided)
        else:
            self.setText(prefix + self.full_path)

class ManagerWindow(QMainWindow):
    """
    SubDesktop 主管理控制中心
    提供 Profile 统一概览、独立进程启动、桌面快捷方式一键配置、安全解除映射管理
    """

    def __init__(self, parent: Optional[QMainWindow] = None):
        super().__init__(parent)
        self.setObjectName("ManagerWindow")
        self.setWindowTitle("SubDesktop - 子桌面管理控制台")
        # 默认尺寸增大至 960x600，保证横向充裕排布
        self.resize(960, 600)
        self.setMinimumSize(880, 500)

        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()
        self.refresh_profiles()

    def _setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. 顶部操作栏
        header_frame = QFrame(self)
        header_frame.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 14, 20, 14)

        title_vbox = QVBoxLayout()
        lbl_title = QLabel("SubDesktop 子桌面管理控制中心", header_frame)
        lbl_title.setObjectName("HeaderTitle")
        lbl_sub = QLabel("便携、轻量、高安全隔离的 Windows 虚拟子桌面", header_frame)
        lbl_sub.setObjectName("HeaderSubtitle")
        title_vbox.addWidget(lbl_title)
        title_vbox.addWidget(lbl_sub)
        header_layout.addLayout(title_vbox)

        header_layout.addStretch()

        btn_refresh = QPushButton("刷新列表", header_frame)
        btn_refresh.setObjectName("SecondaryButton")
        btn_refresh.clicked.connect(self.refresh_profiles)

        btn_new = QPushButton("+ 新建子桌面", header_frame)
        btn_new.setObjectName("PrimaryButton")
        btn_new.clicked.connect(self._create_new_profile)

        header_layout.addWidget(btn_refresh)
        header_layout.addWidget(btn_new)
        root_layout.addWidget(header_frame)

        # 2. 中间卡片滚动区（彻底禁用横向滚动条，内容强制自适应包裹）
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(20, 16, 20, 16)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.cards_container)
        root_layout.addWidget(self.scroll_area)

    def refresh_profiles(self):
        """扫描并刷新所有子桌面卡片"""
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        profiles = ProfileStorage.list_profiles()

        if not profiles:
            empty_frame = QFrame(self.cards_container)
            empty_layout = QVBoxLayout(empty_frame)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_layout.setContentsMargins(40, 60, 40, 60)

            lbl_empty = QLabel("📭 暂无子桌面配置", empty_frame)
            lbl_empty.setStyleSheet("font-size: 18px; font-weight: bold; color: #57606a;")
            lbl_empty_sub = QLabel(
                "请点击右上角的 “+ 新建子桌面” 按钮，映射任意现有文件夹开始使用。", empty_frame
            )
            lbl_empty_sub.setStyleSheet("font-size: 13px; color: #8c959f; margin-top: 8px;")

            btn_empty_new = QPushButton("立即创建第一个子桌面", empty_frame)
            btn_empty_new.setObjectName("PrimaryButton")
            btn_empty_new.clicked.connect(self._create_new_profile)
            btn_empty_new.setFixedWidth(200)

            empty_layout.addWidget(lbl_empty, alignment=Qt.AlignCenter)
            empty_layout.addWidget(lbl_empty_sub, alignment=Qt.AlignCenter)
            empty_layout.addSpacing(16)
            empty_layout.addWidget(btn_empty_new, alignment=Qt.AlignCenter)

            self.cards_layout.addWidget(empty_frame)
            return

        for p in profiles:
            card = self._create_profile_card(p)
            self.cards_layout.addWidget(card)

    def _create_profile_card(self, profile: dict) -> QFrame:
        """构建单个子桌面信息卡片控件（双层紧凑流式结构，彻底根除横向超宽）"""
        pid = profile["id"]
        pname = profile.get("name", "未命名桌面")
        target_path = profile.get("target_path", "未设置")
        rect = profile.get("window_rect", {})
        w = rect.get("width", 960)
        h = rect.get("height", 540)

        card = QFrame(self.cards_container)
        card.setProperty("class", "ProfileCard")
        card_vbox = QVBoxLayout(card)
        card_vbox.setContentsMargins(14, 12, 14, 12)
        card_vbox.setSpacing(8)

        # ========= 1. 上半行 (Top Row) =========
        # 壁纸/纯色缩略图 + 子桌面名称 + 分辨率徽章 + 快捷方式状态徽章
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        wall_preview = QLabel(card)
        wall_preview.setFixedSize(64, 40)
        wall_preview.setStyleSheet(
            "border: 1px solid #d0d7de; border-radius: 4px; background: #1c2532; color: #8c959f;"
        )
        wall_preview.setAlignment(Qt.AlignCenter)

        wall_path = ProfileStorage.get_wallpaper_path(pid)
        if wall_path and wall_path.exists():
            pix = QPixmap(str(wall_path)).scaled(
                64, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            wall_preview.setPixmap(pix)
        else:
            wall_preview.setText("纯色")
        top_row.addWidget(wall_preview)

        title_box = QHBoxLayout()
        title_box.setSpacing(8)

        lbl_card_title = QLabel(pname, card)
        lbl_card_title.setProperty("class", "CardTitle")
        title_box.addWidget(lbl_card_title)

        badge_res = QLabel(f"{w} × {h}", card)
        badge_res.setProperty("class", "Badge")
        title_box.addWidget(badge_res)

        has_lnk = ShortcutHelper.is_shortcut_exists(pname)
        if has_lnk:
            badge_lnk = QLabel("快捷方式: 已创建", card)
            badge_lnk.setProperty("class", "BadgeSuccess")
        else:
            badge_lnk = QLabel("快捷方式: 未创建", card)
            badge_lnk.setProperty("class", "Badge")
        title_box.addWidget(badge_lnk)

        title_box.addStretch()
        top_row.addLayout(title_box)
        card_vbox.addLayout(top_row)

        # ========= 分割线 (Subtle Divider) =========
        divider = QFrame(card)
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Plain)
        divider.setStyleSheet("background-color: #f0f2f5; max-height: 1px; border: none;")
        card_vbox.addWidget(divider)

        # ========= 2. 下半行 (Bottom Row) =========
        # 左侧物理路径 (自适应中间省略) + 右侧紧凑操作按钮组 (完整展示绝对不换行)
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(12)

        lbl_path = ElidedPathLabel(target_path, card)
        bottom_row.addWidget(lbl_path, stretch=1)

        # 右侧操作按钮组 (padding 4px 10px, 完整展示不挤压)
        act_box = QHBoxLayout()
        act_box.setSpacing(6)

        # 启动视窗
        btn_run = QPushButton("▶ 启动视窗", card)
        btn_run.setProperty("class", "CardBtnPrimary")
        btn_run.clicked.connect(lambda _, id=pid: self._launch_desktop(id))
        act_box.addWidget(btn_run)

        # 快捷方式切换
        btn_lnk = QPushButton("移除桌面" if has_lnk else "发送到桌面", card)
        btn_lnk.setProperty("class", "CardBtnSecondary")
        if has_lnk:
            btn_lnk.clicked.connect(lambda _, n=pname: self._remove_shortcut(n))
        else:
            btn_lnk.clicked.connect(lambda _, id=pid, n=pname: self._create_shortcut(id, n))
        act_box.addWidget(btn_lnk)

        # 编辑配置
        btn_edit = QPushButton("设置", card)
        btn_edit.setProperty("class", "CardBtnSecondary")
        btn_edit.clicked.connect(lambda _, p=profile: self._edit_profile(p))
        act_box.addWidget(btn_edit)

        # 打开真实文件夹
        btn_open_folder = QPushButton("打开目录", card)
        btn_open_folder.setProperty("class", "CardBtnSecondary")
        btn_open_folder.clicked.connect(lambda _, path=target_path: FileOps.show_in_explorer(path))
        act_box.addWidget(btn_open_folder)

        # 解除映射/删除 Profile（安全红线）
        btn_delete = QPushButton("解除映射", card)
        btn_delete.setProperty("class", "CardBtnDanger")
        btn_delete.clicked.connect(lambda _, id=pid, n=pname, t=target_path: self._safe_delete_profile(id, n, t))
        act_box.addWidget(btn_delete)

        bottom_row.addLayout(act_box)
        card_vbox.addLayout(bottom_row)

        return card

    def _create_new_profile(self):
        dialog = ProfileDialog(parent=self)
        if dialog.exec_() == ProfileDialog.Accepted:
            self.refresh_profiles()

    def _edit_profile(self, profile: dict):
        dialog = ProfileDialog(profile_data=profile, parent=self)
        if dialog.exec_() == ProfileDialog.Accepted:
            self.refresh_profiles()

    def _launch_desktop(self, profile_id: str):
        """以独立进程方式启动子桌面视窗"""
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable, "--profile", profile_id])
            else:
                py_dir = Path(sys.executable).parent
                pythonw = py_dir / "pythonw.exe"
                launcher = str(pythonw) if pythonw.exists() else sys.executable
                main_script = Path(__file__).resolve().parent.parent / "main.py"
                subprocess.Popen([launcher, str(main_script), "--profile", profile_id])
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"无法启动子桌面: {e}")

    def _create_shortcut(self, profile_id: str, profile_name: str):
        ok = ShortcutHelper.create_desktop_shortcut(profile_id, profile_name)
        if ok:
            QMessageBox.information(
                self, "快捷方式就绪", f"已在当前 Windows 桌面生成子桌面快捷方式：\n{profile_name}.lnk"
            )
            self.refresh_profiles()
        else:
            QMessageBox.warning(self, "生成失败", "无法创建桌面快捷方式，请检查桌面权限。")

    def _remove_shortcut(self, profile_name: str):
        ShortcutHelper.remove_desktop_shortcut(profile_name)
        self.refresh_profiles()

    def _safe_delete_profile(self, profile_id: str, profile_name: str, target_path: str):
        """
        【执行解除映射与安全删除】
        严格遵守红线：仅清除 profiles 内部元数据及快捷方式，物理目录 100% 完整保留！
        """
        msg = (
            f"确定要解除子桌面【{profile_name}】的映射并删除该配置吗？\n\n"
            f"🛡️【安全承诺】：\n"
            f"物理映射目录下的真实文件将 100% 完好保留，绝不进行任何删除：\n"
            f"📁 {target_path}\n\n"
            f"本次操作仅清理：\n"
            f"1. ./profiles/{profile_id}/ 配置元数据与固化壁纸\n"
            f"2. Windows 桌面的快捷方式（若已创建）"
        )
        reply = QMessageBox.warning(
            self,
            "确认解除子桌面映射",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            ShortcutHelper.remove_desktop_shortcut(profile_name)
            ProfileStorage.delete_profile(profile_id)
            self.refresh_profiles()
