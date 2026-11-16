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
from core.shell_icon import ShellIconHelper
from ui.desktop_icon import DesktopIconWidget

class DesktopCanvas(QWidget):
    """
    独立子桌面主画布
    支持：壁纸绘制、框选多选、自适应网格对齐、外部文件安全移动拖入、动态排序与新建
    """

    open_settings_requested = pyqtSignal()

    def __init__(
        self,
        profile_id: str,
        parent: Optional[QWidget] = None,
        dpr_override: Optional[float] = None,
    ):
        super().__init__(parent)
        self.profile_id = profile_id
        self._dpr_override = dpr_override
        self.setObjectName("DesktopCanvas")

        # 核心参数
        self.target_path: Optional[Path] = None
        self.grid_align = True
        self.grid_size = DEFAULT_GRID_SIZE
        self.icon_size_mode = "medium"
        self.auto_arrange = False
        self.wallpaper_pixmap: Optional[QPixmap] = None

        # 标准网格单元系统（逻辑像素，按 1 / dpr 由物理基准换算）
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

    def get_dpr(self) -> float:
        """获取画布当前所在屏幕的 devicePixelRatio（支持测试注入覆盖）"""
        if self._dpr_override is not None and self._dpr_override > 0:
            return float(self._dpr_override)
        win = self.window()
        if win is not None and hasattr(win, "_get_current_dpr"):
            return float(win._get_current_dpr())
        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        if dpr > 0:
            return dpr
        screen = QApplication.primaryScreen()
        return float(screen.devicePixelRatio()) if screen and screen.devicePixelRatio() > 0 else 1.0

    def to_logical(self, phys_val: float) -> int:
        """物理像素 -> Qt 逻辑像素"""
        return int(round(phys_val / self.get_dpr()))

    def to_physical(self, logical_val: float) -> int:
        """Qt 逻辑像素 -> 物理像素"""
        return int(round(logical_val * self.get_dpr()))

    def _update_grid_metrics(self):
        """将物理网格步长与边距按 1 / dpr 换算为逻辑尺寸，抵消 Qt 高 DPI 缩放"""
        cfg = ICON_SIZE_CONFIG.get(self.icon_size_mode, ICON_SIZE_CONFIG["medium"])
        phys_w = cfg.get("cell_w", DEFAULT_CELL_WIDTH)
        phys_h = cfg.get("cell_h", DEFAULT_CELL_HEIGHT)
        self.cell_width = max(24, self.to_logical(phys_w))
        self.cell_height = max(28, self.to_logical(phys_h))
        self.margin_x = max(4, self.to_logical(GRID_MARGIN_X))
        self.margin_y = max(4, self.to_logical(GRID_MARGIN_Y))
        self.grid_size = phys_h

    def apply_physical_metrics(self):
        """
        运行期动态 DPI 变化时实时重算画布所有物理度量：
        重新计算网格步长、清缓存、按最新 DPR 刷新所有图标控件与贴图，
        并将持久化的物理坐标重新映射为当前 DPR 下的逻辑坐标（绝不洗牌）。
        """
        self._update_grid_metrics()
        ShellIconHelper.clear_pixmap_cache()

        profile = ProfileStorage.get_profile(self.profile_id) or {}
        raw_saved = profile.get("items_pos", {})
        saved_positions = {os.path.basename(k): v for k, v in raw_saved.items()}

        for clean_name, widget in self.icon_widgets.items():
            widget.refresh_dpi_scale()
            if clean_name in saved_positions:
                pos = saved_positions[clean_name]
                lx = self.to_logical(int(pos.get("x", GRID_MARGIN_X)))
                ly = self.to_logical(int(pos.get("y", GRID_MARGIN_Y)))
                if self.grid_align:
                    lx, ly = self.snap_to_grid(lx, ly, clamp=True)
                widget.move(lx, ly)

        self.update()

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

        # 更新标准自适应网格尺寸（按 1/dpr 换算）
        self._update_grid_metrics()

        # 加载固化壁纸
        wall_path = ProfileStorage.get_wallpaper_path(self.profile_id)
        if wall_path and wall_path.exists():
            self.wallpaper_pixmap = QPixmap(str(wall_path))
        else:
            self.wallpaper_pixmap = None

        self.update()
        self.sync_items_from_disk()

    def _get_canvas_bounds(self) -> Tuple[int, int]:
        """获取当前子桌面可视画布有效逻辑宽高（未显示前按物理预设尺寸 / dpr 兜底）"""
        if self.width() > 150 and self.height() > 150:
            return self.width(), self.height()
        profile = ProfileStorage.get_profile(self.profile_id) or {}
        rect = profile.get("window_rect", {})
        phys_w = max(320, int(rect.get("width", 960)))
        phys_h = max(240, int(rect.get("height", 540)))
        return max(200, self.to_logical(phys_w)), max(150, self.to_logical(phys_h))

    def _get_max_grid_dims(self) -> Tuple[int, int]:
        """计算当前可视画布可容纳的最大网格列数与行数"""
        canvas_w, canvas_h = self._get_canvas_bounds()
        max_cols = max(1, (canvas_w - self.margin_x) // self.cell_width)
        max_rows = max(1, (canvas_h - self.margin_y) // self.cell_height)
        return max_cols, max_rows

    def _is_within_bounds(self, x: int, y: int) -> bool:
        """判断给定图标左上角坐标是否完整落在可视画布边界内"""
        canvas_w, canvas_h = self._get_canvas_bounds()
        return (
            self.margin_x <= x
            and x + self.cell_width <= canvas_w
            and self.margin_y <= y
            and y + self.cell_height <= canvas_h
        )

    def snap_to_grid(self, x: int, y: int, clamp: bool = False) -> Tuple[int, int]:
        """
        【自适应网格对齐】
        使用精准矩阵算法：margin + round((pos - margin) / cell) * cell
        """
        col = max(0, round((x - self.margin_x) / self.cell_width))
        row = max(0, round((y - self.margin_y) / self.cell_height))

        if clamp:
            max_cols, max_rows = self._get_max_grid_dims()
            col = min(col, max_cols - 1)
            row = min(row, max_rows - 1)

        snapped_x = self.margin_x + col * self.cell_width
        snapped_y = self.margin_y + row * self.cell_height
        return snapped_x, snapped_y

    def find_nearest_free_grid(
        self,
        target_x: int,
        target_y: int,
        exclude_widget: Optional[DesktopIconWidget] = None,
        occupied: Optional[set] = None,
    ) -> Tuple[int, int]:
        """
        【严禁图标重叠与视窗防越界：网格防碰撞占位机制】
        1. 先将目标网格限定在当前可视画布的合法行列范围 (max_cols, max_rows) 内；
        2. 目标网格若为空，直接落入；
        3. 若已被占用，以曼哈顿距离为核心在可视区内就近寻找空闲网格，确保不重叠、不越界。
        """
        max_cols, max_rows = self._get_max_grid_dims()
        col = min(max(0, round((target_x - self.margin_x) / self.cell_width)), max_cols - 1)
        row = min(max(0, round((target_y - self.margin_y) / self.cell_height)), max_rows - 1)
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

        # 目标已被占用：在可视画布内搜索曼哈顿距离最近的空闲槽位
        best_slot = None
        max_search = max_cols + max_rows + 10
        for max_d in range(1, max_search):
            candidates = []
            for r_diff in range(0, max_d + 1):
                c_diff = max_d - r_diff
                for dc, dr in [
                    (0, r_diff), (0, -r_diff),
                    (c_diff, 0), (-c_diff, 0),
                    (c_diff, r_diff), (-c_diff, r_diff),
                    (c_diff, -r_diff), (-c_diff, -r_diff),
                ]:
                    c = col + dc
                    r = row + dr
                    if 0 <= c < max_cols and 0 <= r < max_rows:
                        slot = (self.margin_x + c * self.cell_width, self.margin_y + r * self.cell_height)
                        if slot not in occupied_slots:
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

        any_size_changed = False
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

                # 确定摆放位置：Config 内为物理坐标，需换算为逻辑坐标后再做对齐与防重叠
                if clean_name in saved_positions and not self.auto_arrange:
                    pos = saved_positions[clean_name]
                    raw_x = self.to_logical(int(pos.get("x", GRID_MARGIN_X)))
                    raw_y = self.to_logical(int(pos.get("y", GRID_MARGIN_Y)))
                    if self.grid_align:
                        cand_x, cand_y = self.snap_to_grid(raw_x, raw_y, clamp=False)
                        if (cand_x, cand_y) in occupied_slots or not self._is_within_bounds(cand_x, cand_y):
                            x, y = self.find_nearest_free_grid(cand_x, cand_y, occupied=occupied_slots)
                            ProfileStorage.update_item_position(
                                self.profile_id, clean_name, self.to_physical(x), self.to_physical(y)
                            )
                        else:
                            x, y = cand_x, cand_y
                    else:
                        if not self._is_within_bounds(raw_x, raw_y):
                            x, y = self.find_nearest_free_grid(raw_x, raw_y, occupied=occupied_slots)
                            ProfileStorage.update_item_position(
                                self.profile_id, clean_name, self.to_physical(x), self.to_physical(y)
                            )
                        else:
                            x, y = raw_x, raw_y
                else:
                    x, y = self.find_nearest_free_grid(self.margin_x, self.margin_y, occupied=occupied_slots)
                    ProfileStorage.update_item_position(
                        self.profile_id, clean_name, self.to_physical(x), self.to_physical(y)
                    )

                widget.move(x, y)
                widget.show()
                occupied_slots.add((x, y))
                self.icon_widgets[clean_name] = widget
            else:
                widget = self.icon_widgets[clean_name]
                widget.file_path = fpath
                if widget.icon_size_mode != self.icon_size_mode:
                    widget.set_icon_size_mode(self.icon_size_mode)
                    any_size_changed = True

        if self.auto_arrange:
            self.rearrange_icons()
        elif any_size_changed:
            self._repack_grid_no_overlap()

    def _find_next_free_slot(self, occupied: set) -> Tuple[int, int]:
        """按 Windows 经典桌面由上至下、由左至右寻找标准网格空槽位"""
        _, canvas_h = self._get_canvas_bounds()
        col = 0
        while True:
            x = self.margin_x + col * self.cell_width
            row = 0
            while True:
                y = self.margin_y + row * self.cell_height
                if y + self.cell_height > canvas_h - self.margin_y and row > 0:
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
        将画布上所有控件的逻辑坐标换算为物理像素坐标写入 config.json
        """
        profile = ProfileStorage.get_profile(self.profile_id)
        if not profile:
            return
        if "items_pos" not in profile:
            profile["items_pos"] = {}

        for fname, widget in self.icon_widgets.items():
            clean_name = os.path.basename(fname)
            profile["items_pos"][clean_name] = {
                "x": self.to_physical(widget.x()),
                "y": self.to_physical(widget.y()),
            }

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

        _, canvas_h = self._get_canvas_bounds()
        cur_x = self.margin_x
        cur_y = self.margin_y

        for w in items:
            if cur_y + self.cell_height > canvas_h - self.margin_y and cur_y > self.margin_y:
                cur_y = self.margin_y
                cur_x += self.cell_width
            w.move(cur_x, cur_y)
            clean_name = os.path.basename(w.filename)
            ProfileStorage.update_item_position(
                self.profile_id, clean_name, self.to_physical(cur_x), self.to_physical(cur_y)
            )
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
        ProfileStorage.update_item_position(
            self.profile_id, clean_name, self.to_physical(x), self.to_physical(y)
        )

    def _on_item_renamed(self, old_name: str, new_name: str):
        old_clean = os.path.basename(old_name)
        new_clean = os.path.basename(new_name)
        if old_clean in self.icon_widgets:
            w = self.icon_widgets.pop(old_clean)
            self.icon_widgets[new_clean] = w
            ProfileStorage.remove_item_position(self.profile_id, old_clean)
            ProfileStorage.update_item_position(
                self.profile_id, new_clean, self.to_physical(w.x()), self.to_physical(w.y())
            )

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
                            self.profile_id,
                            clean_name,
                            self.to_physical(free_x),
                            self.to_physical(free_y),
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

    def _repack_grid_no_overlap(self):
        """
        【局部防重叠微调（Lazy Anti-Collision）】
        切换图标尺寸后，优先保留每个图标原有的物理 (x, y) 坐标（仅做当前新网格下的就近吸附对齐）：
        - 若未发生网格碰撞且在视窗可视边界内，原封不动保留原位，禁止全局重新洗牌；
        - 仅对发生碰撞重叠或超出边界的图标，就近寻找最近的空闲网格放置。
        """
        if not self.icon_widgets:
            return

        profile = ProfileStorage.get_profile(self.profile_id) or {}
        raw_saved = profile.get("items_pos", {})
        saved_positions = {os.path.basename(k): v for k, v in raw_saved.items()}

        # 第一轮：按原位置就近吸附，不冲突且在边界内的图标直接保留原位
        occupied = set()
        conflicts = []
        for clean_name, widget in self.icon_widgets.items():
            if clean_name in saved_positions:
                pos = saved_positions[clean_name]
                raw_x = self.to_logical(int(pos.get("x", GRID_MARGIN_X)))
                raw_y = self.to_logical(int(pos.get("y", GRID_MARGIN_Y)))
            else:
                raw_x, raw_y = widget.x(), widget.y()

            sx, sy = self.snap_to_grid(raw_x, raw_y, clamp=True)
            if (sx, sy) not in occupied and self._is_within_bounds(sx, sy):
                widget.move(sx, sy)
                occupied.add((sx, sy))
            else:
                conflicts.append((widget, sx, sy))

        # 第二轮：仅对真正发生碰撞或越界的图标做局部顺延微调
        for widget, sx, sy in conflicts:
            free_x, free_y = self.find_nearest_free_grid(
                sx, sy, exclude_widget=widget, occupied=occupied
            )
            widget.move(free_x, free_y)
            occupied.add((free_x, free_y))

        self.save_all_positions()

    def _change_icon_size(self, mode: str):
        """切换视图图标尺寸（大/中/小图标）：持久化配置、清缓存、更新控件与网格并强制防碰撞重排"""
        if mode not in ICON_SIZE_CONFIG:
            return

        self.icon_size_mode = mode
        self._update_grid_metrics()

        # 1. 更新并持久化 Profile 配置
        ProfileStorage.update_profile(
            self.profile_id,
            {"icon_size": mode, "grid_size": self.grid_size},
        )

        # 2. 清空贴图缓存，确保按新尺寸与当前 DPR 重新提取
        ShellIconHelper.clear_pixmap_cache()

        # 3. 实时更新画布上所有已存在图标控件的尺寸与贴图
        for widget in self.icon_widgets.values():
            widget.set_icon_size_mode(mode)

        # 4. 强制触发全局防碰撞网格重排，确保两两不重叠且不超出视窗边界
        if self.auto_arrange:
            self.rearrange_icons()
        else:
            self._repack_grid_no_overlap()

        self.sync_items_from_disk()
        self.update()

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
