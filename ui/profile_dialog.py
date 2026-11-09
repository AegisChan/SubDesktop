import os
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QFileDialog,
    QMessageBox,
    QFrame,
    QGroupBox,
)

from core.config import PRESET_RESOLUTIONS, DEFAULT_GRID_SIZE
from core.profile_storage import ProfileStorage

class ProfileDialog(QDialog):
    """
    子桌面配置/新建对话框
    支持：名称、物理映射路径、预设分辨率与自定义宽高、壁纸导入与预览、网格排布配置
    """

    def __init__(
        self,
        profile_data: Optional[Dict[str, Any]] = None,
        parent: Optional[QDialog] = None,
    ):
        super().__init__(parent)
        self.is_edit_mode = profile_data is not None
        self.profile_data = profile_data or {}
        self.selected_wallpaper_path: Optional[str] = None
        self.clear_wallpaper = False

        self.setWindowTitle("编辑子桌面属性" if self.is_edit_mode else "新建独立子桌面")
        self.setMinimumWidth(560)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 顶部提示栏（强调数据安全）
        notice_frame = QFrame(self)
        notice_frame.setStyleSheet(
            "background-color: #dafbe1; border: 1px solid #4ac26b; border-radius: 6px; padding: 8px 12px;"
        )
        notice_layout = QHBoxLayout(notice_frame)
        notice_layout.setContentsMargins(0, 0, 0, 0)
        notice_lbl = QLabel(
            "🛡️ <b>真实数据安全红线承诺</b>：物理映射目录仅用于内容展示与交互。<br>"
            "即便今后删除子桌面配置，<b>真实映射文件夹及其内部文件也将100%保留</b>，绝不会被删除。",
            notice_frame,
        )
        notice_lbl.setWordWrap(True)
        notice_lbl.setStyleSheet("color: #1a7f37; font-size: 12px;")
        notice_layout.addWidget(notice_lbl)
        main_layout.addWidget(notice_frame)

        form_group = QGroupBox("基础属性与映射设置", self)
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(12)

        # 1. 子桌面名称
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("例如: 工作日常、开发工作台、文档归档...")
        form_layout.addRow("子桌面名称(&N):", self.name_edit)

        # 2. 物理映射路径
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(self)
        self.path_edit.setPlaceholderText("选择或输入非系统盘的物理文件夹路径...")
        btn_browse = QPushButton("浏览(&B)...", self)
        btn_browse.clicked.connect(self._browse_target_folder)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(btn_browse)
        form_layout.addRow("物理映射路径(&P):", path_layout)

        main_layout.addWidget(form_group)

        # 3. 视窗分辨率设置
        res_group = QGroupBox("视窗尺寸与显示模式", self)
        res_v_layout = QVBoxLayout(res_group)
        res_h_layout = QHBoxLayout()

        self.res_combo = QComboBox(self)
        for label, w, h in PRESET_RESOLUTIONS:
            self.res_combo.addItem(label, (w, h))
        self.res_combo.currentIndexChanged.connect(self._on_preset_changed)

        self.spin_width = QSpinBox(self)
        self.spin_width.setRange(320, 7680)
        self.spin_width.setSuffix(" px")
        self.spin_width.valueChanged.connect(self._on_custom_size_changed)

        self.spin_height = QSpinBox(self)
        self.spin_height.setRange(240, 4320)
        self.spin_height.setSuffix(" px")
        self.spin_height.valueChanged.connect(self._on_custom_size_changed)

        res_h_layout.addWidget(QLabel("预设分辨率:"))
        res_h_layout.addWidget(self.res_combo, 2)
        res_h_layout.addWidget(QLabel("宽:"))
        res_h_layout.addWidget(self.spin_width, 1)
        res_h_layout.addWidget(QLabel("高:"))
        res_h_layout.addWidget(self.spin_height, 1)

        res_v_layout.addLayout(res_h_layout)
        main_layout.addWidget(res_group)

        # 4. 壁纸设置与固化
        wall_group = QGroupBox("壁纸与外观定制", self)
        wall_layout = QHBoxLayout(wall_group)

        # 壁纸缩略图
        self.wall_preview = QLabel(self)
        self.wall_preview.setFixedSize(120, 68)
        self.wall_preview.setStyleSheet("border: 1px dashed #d0d7de; border-radius: 4px; background: #222;")
        self.wall_preview.setAlignment(Qt.AlignCenter)
        self.wall_preview.setText("无壁纸")
        wall_layout.addWidget(self.wall_preview)

        wall_ctrl_layout = QVBoxLayout()
        wall_btn_layout = QHBoxLayout()
        btn_choose_wall = QPushButton("选择本地壁纸...", self)
        btn_choose_wall.clicked.connect(self._choose_wallpaper)
        btn_clear_wall = QPushButton("清除壁纸", self)
        btn_clear_wall.clicked.connect(self._on_clear_wallpaper)
        wall_btn_layout.addWidget(btn_choose_wall)
        wall_btn_layout.addWidget(btn_clear_wall)

        wall_tip = QLabel(
            "提示: 导入的壁纸将自动复制并隔离固化至当前 Profile 目录，源文件删除不影响展示。", self
        )
        wall_tip.setStyleSheet("color: #6a737d; font-size: 11px;")
        wall_tip.setWordWrap(True)

        wall_ctrl_layout.addLayout(wall_btn_layout)
        wall_ctrl_layout.addWidget(wall_tip)
        wall_layout.addLayout(wall_ctrl_layout)
        main_layout.addWidget(wall_group)

        # 5. 排布设置
        align_group = QGroupBox("排布与图标", self)
        align_layout = QHBoxLayout(align_group)

        self.chk_grid = QCheckBox("开启网格吸附对齐", self)
        self.chk_grid.setChecked(True)

        self.spin_grid_size = QSpinBox(self)
        self.spin_grid_size.setRange(40, 200)
        self.spin_grid_size.setValue(DEFAULT_GRID_SIZE)
        self.spin_grid_size.setSuffix(" px")

        self.combo_icon_size = QComboBox(self)
        self.combo_icon_size.addItem("中等图标 (推荐)", "medium")
        self.combo_icon_size.addItem("小图标", "small")
        self.combo_icon_size.addItem("大图标", "large")

        align_layout.addWidget(self.chk_grid)
        align_layout.addWidget(QLabel("网格步长:"))
        align_layout.addWidget(self.spin_grid_size)
        align_layout.addWidget(QLabel("图标尺寸:"))
        align_layout.addWidget(self.combo_icon_size)
        main_layout.addWidget(align_group)

        # 底部按钮栏
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("取消", self)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("保存配置" if self.is_edit_mode else "立即创建子桌面", self)
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setStyleSheet(
            "background-color: #0969da; color: #ffffff; padding: 7px 18px; border-radius: 6px; font-weight: 600;"
        )
        self.btn_save.clicked.connect(self._validate_and_save)

        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_save)
        main_layout.addLayout(btn_box)

    def _load_data(self):
        if not self.is_edit_mode:
            # 默认新建配置
            self.name_edit.setText("我的子桌面")
            # 默认 qHD 960x540
            self._select_resolution_in_combo(960, 540)
            return

        # 编辑已有数据
        p = self.profile_data
        self.name_edit.setText(p.get("name", ""))
        self.path_edit.setText(p.get("target_path", ""))

        rect = p.get("window_rect", {})
        w = rect.get("width", 960)
        h = rect.get("height", 540)
        self._select_resolution_in_combo(w, h)

        self.chk_grid.setChecked(p.get("grid_align", True))
        self.spin_grid_size.setValue(p.get("grid_size", DEFAULT_GRID_SIZE))

        # 图标尺寸
        idx = self.combo_icon_size.findData(p.get("icon_size", "medium"))
        if idx >= 0:
            self.combo_icon_size.setCurrentIndex(idx)

        # 现有壁纸展示
        profile_id = p.get("id")
        wall_path = ProfileStorage.get_wallpaper_path(profile_id)
        if wall_path and wall_path.exists():
            pix = QPixmap(str(wall_path))
            self._update_wall_preview(pix)

    def _select_resolution_in_combo(self, w: int, h: int):
        self.spin_width.blockSignals(True)
        self.spin_height.blockSignals(True)
        self.spin_width.setValue(w)
        self.spin_height.setValue(h)
        self.spin_width.blockSignals(False)
        self.spin_height.blockSignals(False)

        # 寻找预设匹配
        matched_idx = -1
        for i in range(self.res_combo.count()):
            pw, ph = self.res_combo.itemData(i)
            if pw == w and ph == h:
                matched_idx = i
                break

        self.res_combo.blockSignals(True)
        if matched_idx >= 0:
            self.res_combo.setCurrentIndex(matched_idx)
        else:
            self.res_combo.setCurrentIndex(self.res_combo.count() - 1)  # 自定义
        self.res_combo.blockSignals(False)

    def _on_preset_changed(self, index: int):
        w, h = self.res_combo.itemData(index)
        if w > 0 and h > 0:
            self.spin_width.blockSignals(True)
            self.spin_height.blockSignals(True)
            self.spin_width.setValue(w)
            self.spin_height.setValue(h)
            self.spin_width.blockSignals(False)
            self.spin_height.blockSignals(False)

    def _on_custom_size_changed(self):
        w = self.spin_width.value()
        h = self.spin_height.value()
        # 检查是否恰好命中某个预设
        matched_idx = -1
        for i in range(self.res_combo.count()):
            pw, ph = self.res_combo.itemData(i)
            if pw == w and ph == h:
                matched_idx = i
                break

        self.res_combo.blockSignals(True)
        if matched_idx >= 0:
            self.res_combo.setCurrentIndex(matched_idx)
        else:
            self.res_combo.setCurrentIndex(self.res_combo.count() - 1)  # 自定义
        self.res_combo.blockSignals(False)

    def _browse_target_folder(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "选择或指定物理映射文件夹", self.path_edit.text() or "D:\\"
        )
        if chosen:
            self.path_edit.setText(chosen)

    def _choose_wallpaper(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择壁纸图像",
            "",
            "图像文件 (*.jpg *.jpeg *.png *.bmp *.webp);;所有文件 (*.*)",
        )
        if path:
            self.selected_wallpaper_path = path
            self.clear_wallpaper = False
            pix = QPixmap(path)
            self._update_wall_preview(pix)

    def _on_clear_wallpaper(self):
        self.selected_wallpaper_path = None
        self.clear_wallpaper = True
        self.wall_preview.setPixmap(QPixmap())
        self.wall_preview.setText("无壁纸")

    def _update_wall_preview(self, pix: QPixmap):
        if not pix.isNull():
            scaled = pix.scaled(
                self.wall_preview.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self.wall_preview.setPixmap(scaled)
            self.wall_preview.setText("")

    def _validate_and_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "表单提示", "请输入子桌面名称！")
            self.name_edit.setFocus()
            return

        target_path_str = self.path_edit.text().strip()
        if not target_path_str:
            QMessageBox.warning(self, "表单提示", "请选择或指定一个有效的物理映射路径！")
            self.path_edit.setFocus()
            return

        target_path = Path(target_path_str)
        if not target_path.exists():
            create_reply = QMessageBox.question(
                self,
                "目录不存在",
                f"指定的物理映射目录不存在：\n{target_path}\n\n是否立即创建该文件夹？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if create_reply == QMessageBox.Yes:
                try:
                    target_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(self, "创建失败", f"无法创建目录: {e}")
                    return
            else:
                return

        # 整理数据
        w = self.spin_width.value()
        h = self.spin_height.value()
        grid_align = self.chk_grid.isChecked()
        grid_size = self.spin_grid_size.value()
        icon_size = self.combo_icon_size.currentData()

        if not self.is_edit_mode:
            # 创建新 profile
            profile = ProfileStorage.create_profile(
                name=name,
                target_path=str(target_path),
                width=w,
                height=h,
                wallpaper_src=self.selected_wallpaper_path,
                grid_align=grid_align,
                grid_size=grid_size,
                icon_size=icon_size,
            )
            self.profile_data = profile
        else:
            # 更新已有 profile
            pid = self.profile_data["id"]
            rect = self.profile_data.get("window_rect", {})
            rect["width"] = w
            rect["height"] = h

            updates = {
                "name": name,
                "target_path": str(target_path),
                "window_rect": rect,
                "grid_align": grid_align,
                "grid_size": grid_size,
                "icon_size": icon_size,
            }
            wall_src = "" if self.clear_wallpaper else self.selected_wallpaper_path
            updated = ProfileStorage.update_profile(pid, updates, new_wallpaper_src=wall_src)
            if updated:
                self.profile_data = updated

        self.accept()

