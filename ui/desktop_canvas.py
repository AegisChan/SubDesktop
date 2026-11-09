import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap, QColor, QLinearGradient, QKeyEvent
from PyQt5.QtWidgets import (
    QWidget,
    QRubberBand,
    QMenu,
    QAction,
    QActionGroup,
    QMessageBox,
    QApplication,
)

from core.config import (
    DEFAULT_CELL_WIDTH,
    DEFAULT_CELL_HEIGHT,
    GRID_MARGIN_X,
    GRID_MARGIN_Y,
    DEFAULT_GRID_SIZE,
    ICON_SIZE_CONFIG,
)
from core.file_ops import FileOps
from core.profile_storage import ProfileStorage
from ui.desktop_icon import DesktopIconWidget

class DesktopCanvas(QWidget):
    """
    独立子桌面主画布
    支持：壁纸绘制、框选多选、自适应网格对齐、外部文件安全移动拖入、动态排序与新建
    """

    open_settings_requested = pyqtSignal()

    def __init__(self, profile_id: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile_id = profile_id
        self.setObjectName("DesktopCanvas")

        # 核心参数
        self.target_path: Optional[Path] = None
        self.grid_align = True
        self.grid_size = DEFAULT_GRID_SIZE
        self.icon_size_mode = "medium"
        self.auto_arrange = False
        self.wallpaper_pixmap: Optional[QPixmap] = None

        # 标准网格单元系统
        self.cell_width = DEFAULT_CELL_WIDTH
        self.cell_height = DEFAULT_CELL_HEIGHT
        self.margin_x = GRID_MARGIN_X
        self.margin_y = GRID_MARGIN_Y

        # 图标字典：{filename: DesktopIconWidget}
        self.icon_widgets: Dict[str, DesktopIconWidget] = {}

        # 框选交互
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.rubber_band_origin = QPoint()
        self.is_rubber_banding = False

        # 外部拖入文件支持
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.reload_config()

    def reload_config(self):
        """重新载入 Profile 配置并刷新界面与壁纸"""
        profile = ProfileStorage.get_profile(self.profile_id)
        if not profile:
            return

        target_str = profile.get("target_path", "")
        self.target_path = Path(target_str).resolve() if target_str else None
        self.grid_align = bool(profile.get("grid_align", True))
        self.icon_size_mode = profile.get("icon_size", "medium")
        self.auto_arrange = bool(profile.get("auto_arrange", False))

        # 更新标准自适应网格尺寸
        cfg = ICON_SIZE_CONFIG.get(self.icon_size_mode, ICON_SIZE_CONFIG["medium"])
        self.cell_width = cfg.get("cell_w", DEFAULT_CELL_WIDTH)
        self.cell_height = cfg.get("cell_h", DEFAULT_CELL_HEIGHT)
        self.grid_size = self.cell_height

        # 加载固化壁纸
        wall_path = ProfileStorage.get_wallpaper_path(self.profile_id)
        if wall_path and wall_path.exists():
            self.wallpaper_pixmap = QPixmap(str(wall_path))
        else:
            self.wallpaper_pixmap = None

        self.update()
        self.sync_items_from_disk()

    def snap_to_grid(self, x: int, y: int, clamp: bool = False) -> Tuple[int, int]:
        """
        【自适应网格对齐】
        使用精准矩阵算法：margin + round((pos - margin) / cell) * cell
        当 clamp=True 时，仅在画布已完全布局展开的前提下才执行边界防溢出，
        在初始化载入时绝不截断存盘坐标。
        """
        col = max(0, round((x - self.margin_x) / self.cell_width))
        row = max(0, round((y - self.margin_y) / self.cell_height))
        snapped_x = self.margin_x + col * self.cell_width
        snapped_y = self.margin_y + row * self.cell_height

        if clamp and self.width() > 200 and self.height() > 200:
            max_x = max(self.margin_x, self.width() - self.cell_width)
            max_y = max(self.margin_y, self.height() - self.cell_height)
            return min(snapped_x, max_x), min(snapped_y, max_y)
        return snapped_x, snapped_y

    def find_nearest_free_grid(
        self,
        target_x: int,
        target_y: int,
        exclude_widget: Optional[DesktopIconWidget] = None,
        occupied: Optional[set] = None,
    ) -> Tuple[int, int]:
        """
        【严禁图标重叠：网格防碰撞占位机制】
        1. 目标网格若为空，直接落入；
        2. 若目标网格已被其他图标占据，以曼哈顿距离为核心、同列向下就近顺延搜索最近的空闲网格槽位。
        保证每个网格永远仅存在一个图标，严禁坐标重叠遮挡。
        """
        col = max(0, round((target_x - self.margin_x) / self.cell_width))
        row = max(0, round((target_y - self.margin_y) / self.cell_height))
        cand_x = self.margin_x + col * self.cell_width
        cand_y = self.margin_y + row * self.cell_height

        # 收集当前所有已占用的网格坐标
        if occupied is not None:
            occupied_slots = set(occupied)
        else:
            occupied_slots = set(
                (w.x(), w.y()) for w in self.icon_widgets.values() if w != exclude_widget
            )

        # 目标网格为空，直接返回
        if (cand_x, cand_y) not in occupied_slots:
            return cand_x, cand_y

        # 目标已被占用：搜索曼哈顿距离最近的空闲槽位
        profile = ProfileStorage.get_profile(self.profile_id) or {}
        expected_h = profile.get("window_rect", {}).get("height", 540)
        canvas_h = max(self.height(), expected_h, 400)
        max_rows = max(1, (canvas_h - self.margin_y) // self.cell_height)

        best_slot = None
        for max_d in range(1, 60):
            candidates = []
            for r_diff in range(0, max_d + 1):
                c_diff = max_d - r_diff
                # 遍历可能的四个方向
                for dc, dr in [
                    (0, r_diff), (0, -r_diff),
                    (c_diff, 0), (-c_diff, 0),
                    (c_diff, r_diff), (-c_diff, r_diff),
                    (c_diff, -r_diff), (-c_diff, -r_diff),
                ]:
                    c = col + dc
                    r = row + dr
                    if c >= 0 and 0 <= r < max_rows:
                        slot = (self.margin_x + c * self.cell_width, self.margin_y + r * self.cell_height)
                        if slot not in occupied_slots:
                            # 曼哈顿优先，同列顺延优先 (abs(dc))，欧几里得距离次优
                            cost = (max_d, abs(dc), dc**2 + dr**2, c, r)
                            candidates.append((cost, slot))
            if candidates:
                candidates.sort(key=lambda item: item[0])
                best_slot = candidates[0][1]
                break

        return best_slot if best_slot else self._find_next_free_slot(occupied_slots)

    def sync_items_from_disk(self):
        """从真实映射磁盘同步文件列表，更新图标控件（统一纯文件名 Key 并防止重叠）"""
        if not self.target_path or not self.target_path.exists() or not self.target_path.is_dir():
            for widget in list(self.icon_widgets.values()):
                widget.deleteLater()
            self.icon_widgets.clear()
            return

        profile = ProfileStorage.get_profile(self.profile_id) or {}
        raw_saved = profile.get("items_pos", {})
        saved_positions = {os.path.basename(k): v for k, v in raw_saved.items()}

        try:
            entries = list(self.target_path.iterdir())
        except Exception:
            entries = []

        current_filenames = {os.path.basename(e.name): e for e in entries if not e.name.startswith("~$")}

        # 移除磁盘中已被删除的文件控件
        for fname in list(self.icon_widgets.keys()):
            clean_name = os.path.basename(fname)
            if clean_name not in current_filenames:
                self.icon_widgets[fname].deleteLater()
                del self.icon_widgets[fname]
                ProfileStorage.remove_item_position(self.profile_id, clean_name)

        # 针对新增文件创建图标控件
        occupied_slots = set()
        for fname, widget in self.icon_widgets.items():
            occupied_slots.add((widget.x(), widget.y()))

        for clean_name, fpath in current_filenames.items():
            if clean_name not in self.icon_widgets:
                widget = DesktopIconWidget(
                    fpath,
                    canvas=self,
                    icon_size_mode=self.icon_size_mode,
                    parent=self,
                )
                widget.position_changed.connect(self._on_item_position_changed)
                widget.item_renamed.connect(self._on_item_renamed)
                widget.item_deleted.connect(self._on_item_deleted)

                # 确定摆放位置：精准防重叠
                if clean_name in saved_positions and not self.auto_arrange:
                    pos = saved_positions[clean_name]
                    raw_x, raw_y = int(pos.get("x", self.margin_x)), int(pos.get("y", self.margin_y))
                    if self.grid_align:
                        cand_x, cand_y = self.snap_to_grid(raw_x, raw_y, clamp=False)
                        if (cand_x, cand_y) in occupied_slots:
                            x, y = self.find_nearest_free_grid(cand_x, cand_y, occupied=occupied_slots)
                        else:
                            x, y = cand_x, cand_y
                    else:
                        x, y = raw_x, raw_y
                else:
                    x, y = self.find_nearest_free_grid(self.margin_x, self.margin_y, occupied=occupied_slots)
                    ProfileStorage.update_item_position(self.profile_id, clean_name, x, y)

                widget.move(x, y)
                widget.show()
                occupied_slots.add((x, y))
                self.icon_widgets[clean_name] = widget
            else:
                widget = self.icon_widgets[clean_name]
                widget.file_path = fpath

        if self.auto_arrange:
            self.rearrange_icons()

    def _find_next_free_slot(self, occupied: set) -> Tuple[int, int]:
        """按 Windows 经典桌面由上至下、由左至右寻找标准网格空槽位（高度以预期分辨率兜底）"""
        profile = ProfileStorage.get_profile(self.profile_id) or {}
        expected_h = profile.get("window_rect", {}).get("height", 540)
        canvas_h = max(self.height(), expected_h, 400)
        col = 0
        while True:
            x = self.margin_x + col * self.cell_width
            row = 0
            while True:
                y = self.margin_y + row * self.cell_height
                if y + self.cell_height > canvas_h - self.margin_y:
                    break
                if (x, y) not in occupied:
                    return (x, y)
                row += 1
            col += 1
            if col > 150:
                return (self.margin_x, self.margin_y)

    def save_all_positions(self):
        """
        【全量坐标持久化兜底】
        在窗口关闭（closeEvent）或重大操作时，将画布上所有控件的实际坐标写入 config.json
        """
        profile = ProfileStorage.get_profile(self.profile_id)
        if not profile:
            return
        if "items_pos" not in profile:
            profile["items_pos"] = {}

        for fname, widget in self.icon_widgets.items():
            clean_name = os.path.basename(fname)
            profile["items_pos"][clean_name] = {"x": int(widget.x()), "y": int(widget.y())}

        ProfileStorage.save_profile(profile)

    def rearrange_icons(self, sort_by: str = "name"):
        """对所有桌面图标按规则自动重排"""
        if not self.icon_widgets:
            return

        items = list(self.icon_widgets.values())
        if sort_by == "name":
            items.sort(key=lambda w: (not w.file_path.is_dir(), w.filename.lower()))
        elif sort_by == "time":
            items.sort(key=lambda w: (not w.file_path.is_dir(), -w.file_path.stat().st_mtime if w.file_path.exists() else 0))
        elif sort_by == "size":
            items.sort(key=lambda w: (not w.file_path.is_dir(), -w.file_path.stat().st_size if w.file_path.is_file() else 0))
        elif sort_by == "type":
            items.sort(key=lambda w: (not w.file_path.is_dir(), w.file_path.suffix.lower()))

        canvas_h = max(self.height(), 400)
        cur_x = self.margin_x
        cur_y = self.margin_y

        for w in items:
            if cur_y + self.cell_height > canvas_h - self.margin_y:
                cur_y = self.margin_y
                cur_x += self.cell_width
            w.move(cur_x, cur_y)
            clean_name = os.path.basename(w.filename)
            ProfileStorage.update_item_position(self.profile_id, clean_name, cur_x, cur_y)
            cur_y += self.cell_height

    def deselect_all_icons(self, exclude: Optional[DesktopIconWidget] = None):
        """取消所有图标选中状态"""
        for w in self.icon_widgets.values():
            if w != exclude:
                w.set_selected(False)

    def get_selected_icons(self) -> List[DesktopIconWidget]:
        """获取当前被选中的图标控件列表"""
        return [w for w in self.icon_widgets.values() if w.is_selected]

    def _on_item_position_changed(self, filename: str, x: int, y: int):
        clean_name = os.path.basename(filename)
        ProfileStorage.update_item_position(self.profile_id, clean_name, x, y)

    def _on_item_renamed(self, old_name: str, new_name: str):
        old_clean = os.path.basename(old_name)
        new_clean = os.path.basename(new_name)
        if old_clean in self.icon_widgets:
            w = self.icon_widgets.pop(old_clean)
            self.icon_widgets[new_clean] = w
            ProfileStorage.remove_item_position(self.profile_id, old_clean)
            ProfileStorage.update_item_position(self.profile_id, new_clean, w.x(), w.y())

    def _on_item_deleted(self, filename: str):
        clean_name = os.path.basename(filename)
        if clean_name in self.icon_widgets:
            del self.icon_widgets[clean_name]
            ProfileStorage.remove_item_position(self.profile_id, clean_name)

    # ================= 绘制与鼠标事件 =================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if self.wallpaper_pixmap and not self.wallpaper_pixmap.isNull():
            scaled = self.wallpaper_pixmap.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            offset_x = (scaled.width() - self.width()) // 2
            offset_y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(0, 0, scaled, offset_x, offset_y, self.width(), self.height())
        else:
            grad = QLinearGradient(0, 0, self.width(), self.height())
            grad.setColorAt(0.0, QColor(28, 37, 50))
            grad.setColorAt(1.0, QColor(16, 22, 31))
            painter.fillRect(self.rect(), grad)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.deselect_all_icons()
            self.rubber_band_origin = event.pos()
            self.rubber_band.setGeometry(QRect(self.rubber_band_origin, QSize()))
            self.rubber_band.show()
            self.is_rubber_banding = True
        elif event.button() == Qt.RightButton:
            self.deselect_all_icons()
            self._show_canvas_context_menu(event.globalPos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_rubber_banding:
            rect = QRect(self.rubber_band_origin, event.pos()).normalized()
            self.rubber_band.setGeometry(rect)
            for w in self.icon_widgets.values():
                w.set_selected(rect.intersects(w.geometry()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_rubber_banding:
            self.is_rubber_banding = False
            self.rubber_band.hide()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Delete:
            selected = self.get_selected_icons()
            if selected:
                names = "\n".join([w.filename for w in selected[:5]])
                if len(selected) > 5:
                    names += f"\n... 等共 {len(selected)} 项"
                reply = QMessageBox.question(
                    self,
                    "确认移入回收站",
                    f"确定要将以下项目移入系统回收站吗？\n\n{names}",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    for w in selected:
                        FileOps.send_to_recycle_bin(w.file_path)
                        w.deleteLater()
                        if w.filename in self.icon_widgets:
                            del self.icon_widgets[w.filename]
                            ProfileStorage.remove_item_position(self.profile_id, w.filename)
        elif event.key() == Qt.Key_F2:
            selected = self.get_selected_icons()
            if len(selected) == 1:
                selected[0].start_rename()
        elif event.key() == Qt.Key_F5:
            self.sync_items_from_disk()
        elif event.key() == Qt.Key_A and (event.modifiers() & Qt.ControlModifier):
            for w in self.icon_widgets.values():
                w.set_selected(True)
        super().keyPressEvent(event)

    # ================= 外部文件拖放 (安全移动 Drag & Drop) =================

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls() and self.target_path:
            urls = event.mimeData().urls()
            paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if paths:
                # 执行【安全移动】：先流写入校验大小一致，再由 send2trash 安全清理源文件
                moved_items = FileOps.safe_move_into_folder(paths, self.target_path)
                if moved_items:
                    drop_pos = event.pos()
                    occupied = set((w.x(), w.y()) for w in self.icon_widgets.values())

                    for item in moved_items:
                        clean_name = os.path.basename(item.name)
                        if self.grid_align:
                            free_x, free_y = self.find_nearest_free_grid(
                                drop_pos.x(), drop_pos.y(), occupied=occupied
                            )
                        else:
                            free_x, free_y = drop_pos.x(), drop_pos.y()

                        occupied.add((free_x, free_y))
                        ProfileStorage.update_item_position(
                            self.profile_id, clean_name, free_x, free_y
                        )

                    self.sync_items_from_disk()
                    self.save_all_positions()
            event.acceptProposedAction()
        else:
            event.ignore()

    # ================= 空白区域右键菜单 =================

    def _show_canvas_context_menu(self, global_pos: QPoint):
        menu = QMenu(self)

        # 1. 查看子菜单
        view_menu = menu.addMenu("查看(&V)")
        size_group = QActionGroup(view_menu)
        for label, mode in [("大图标(&L)", "large"), ("中等图标(&M)", "medium"), ("小图标(&S)", "small")]:
            act = QAction(label, view_menu, checkable=True)
            act.setChecked(self.icon_size_mode == mode)
            act.triggered.connect(lambda chk, m=mode: self._change_icon_size(m))
            size_group.addAction(act)
            view_menu.addAction(act)

        view_menu.addSeparator()

        act_grid = QAction("将图标与网格对齐(&G)", view_menu, checkable=True)
        act_grid.setChecked(self.grid_align)
        act_grid.triggered.connect(self._toggle_grid_align)
        view_menu.addAction(act_grid)

        act_auto = QAction("自动排列图标(&A)", view_menu, checkable=True)
        act_auto.setChecked(self.auto_arrange)
        act_auto.triggered.connect(self._toggle_auto_arrange)
        view_menu.addAction(act_auto)

        # 2. 排序子菜单
        sort_menu = menu.addMenu("排序方式(&O)")
        act_s_name = QAction("名称(&N)", sort_menu)
        act_s_name.triggered.connect(lambda: self.rearrange_icons("name"))
        sort_menu.addAction(act_s_name)

        act_s_time = QAction("修改日期(&D)", sort_menu)
        act_s_time.triggered.connect(lambda: self.rearrange_icons("time"))
        sort_menu.addAction(act_s_time)

        act_s_type = QAction("项目类型(&T)", sort_menu)
        act_s_type.triggered.connect(lambda: self.rearrange_icons("type"))
        sort_menu.addAction(act_s_type)

        act_s_size = QAction("大小(&S)", sort_menu)
        act_s_size.triggered.connect(lambda: self.rearrange_icons("size"))
        sort_menu.addAction(act_s_size)

        # 3. 刷新
        act_refresh = QAction("刷新(&E)  [F5]", menu)
        act_refresh.triggered.connect(self.sync_items_from_disk)
        menu.addAction(act_refresh)

        menu.addSeparator()

        # 4. 新建
        new_menu = menu.addMenu("新建(&W)")
        act_new_folder = QAction("新建文件夹(&F)", new_menu)
        act_new_folder.triggered.connect(self._create_new_folder)
        new_menu.addAction(act_new_folder)

        act_new_text = QAction("新建文本文档(&T)", new_menu)
        act_new_text.triggered.connect(self._create_new_text_file)
        new_menu.addAction(act_new_text)

        menu.addSeparator()

        # 5. 打开映射目录
        act_open_dir = QAction("打开映射文件夹(&F)...", menu)
        act_open_dir.triggered.connect(lambda: FileOps.show_in_explorer(self.target_path) if self.target_path else None)
        menu.addAction(act_open_dir)

        # 6. 设置
        act_settings = QAction("子桌面属性与设置(&P)...", menu)
        act_settings.triggered.connect(self.open_settings_requested.emit)
        menu.addAction(act_settings)

        menu.exec_(global_pos)

    def _change_icon_size(self, mode: str):
        self.icon_size_mode = mode
        ProfileStorage.update_profile(self.profile_id, {"icon_size": mode})
        self.reload_config()

    def _toggle_grid_align(self):
        self.grid_align = not self.grid_align
        ProfileStorage.update_profile(self.profile_id, {"grid_align": self.grid_align})

    def _toggle_auto_arrange(self):
        self.auto_arrange = not self.auto_arrange
        ProfileStorage.update_profile(self.profile_id, {"auto_arrange": self.auto_arrange})
        if self.auto_arrange:
            self.rearrange_icons()

    def _create_new_folder(self):
        if self.target_path:
            created = FileOps.create_new_folder(self.target_path)
            if created:
                self.sync_items_from_disk()
                if created.name in self.icon_widgets:
                    self.icon_widgets[created.name].start_rename()

    def _create_new_text_file(self):
        if self.target_path:
            created = FileOps.create_new_file(self.target_path)
            if created:
                self.sync_items_from_disk()
                if created.name in self.icon_widgets:
                    self.icon_widgets[created.name].start_rename()
