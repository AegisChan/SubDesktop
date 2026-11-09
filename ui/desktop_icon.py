import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QSize, QFileInfo, QDateTime
from PyQt5.QtGui import QIcon, QPixmap, QColor, QFont, QPainter, QBrush, QPen
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QLineEdit,
    QMenu,
    QAction,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QApplication,
)

from core.file_ops import FileOps
from core.shell_icon import ShellIconHelper
from core.config import ICON_SIZE_CONFIG

if TYPE_CHECKING:
    from ui.desktop_canvas import DesktopCanvas

class RenameLineEdit(QLineEdit):
    """
    支持失焦自动确认与 Esc 撤销的原地重命名编辑控件
    行为完全对齐 Windows 资源管理器原生体验
    """

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        parent = self.parent()
        if hasattr(parent, "_finish_rename"):
            parent._finish_rename()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            parent = self.parent()
            if hasattr(parent, "_cancel_rename"):
                parent._cancel_rename()
                return
        super().keyPressEvent(event)

class DesktopIconWidget(QWidget):
    """
    桌面独立图标控件
    支持：高精度系统图标渲染、Microsoft YaHei UI 9pt 文字与微阴影抗锯齿、
    自适应标准网格吸附、原地 F2 重命名、原生回收站安全删除
    """

    position_changed = pyqtSignal(str, int, int)  # filename, x, y
    item_renamed = pyqtSignal(str, str)           # old_name, new_name
    item_deleted = pyqtSignal(str)                # filename

    def __init__(
        self,
        file_path: Path,
        canvas: "DesktopCanvas",
        icon_size_mode: str = "medium",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.file_path = Path(file_path).resolve()
        self.filename = self.file_path.name
        self.canvas = canvas
        self.icon_size_mode = icon_size_mode

        # 状态变量
        self.is_selected = False
        self.is_hovered = False
        self.is_dragging = False
        self.drag_start_pos = QPoint()
        self.is_editing = False

        self._setup_ui()

    def _setup_ui(self):
        cfg = ICON_SIZE_CONFIG.get(self.icon_size_mode, ICON_SIZE_CONFIG["medium"])
        self.icon_pixel = cfg["icon"]
        self.cell_w = cfg.get("cell_w", 76)
        self.cell_h = cfg.get("cell_h", 90)
        self.setFixedSize(self.cell_w, self.cell_h)
        self.setStyleSheet("DesktopIconWidget { background: transparent; border: none; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 3, 2, 3)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)

        # 1. 图标展示 (强制 SmoothPixmapTransform 高精度渲染)
        self.icon_label = QLabel(self)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(self.icon_pixel, self.icon_pixel)
        self.update_icon()

        # 2. 文件名标签：采用 "Microsoft YaHei UI" 9pt、自然呼吸间距与微阴影
        self.text_label = QLabel(self.filename, self)
        self.text_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.text_label.setWordWrap(True)

        font = QFont("Microsoft YaHei UI", 9)
        font.setStyleStrategy(QFont.PreferAntialias)
        self.text_label.setFont(font)
        self.text_label.setStyleSheet("color: #ffffff; font-weight: 400; padding-top: 2px;")

        # Subtle Drop Shadow（微阴影: blur=2, offset=(1,1), rgba(0,0,0,180)），消除粗糙感
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(2)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(1, 1)
        self.text_label.setGraphicsEffect(shadow)

        # 3. 重命名就地编辑框（使用支持失焦自动确认的 RenameLineEdit）
        self.edit_line = RenameLineEdit(self.filename, self)
        self.edit_line.setAlignment(Qt.AlignCenter)
        self.edit_line.setFont(font)
        self.edit_line.setStyleSheet(
            "background-color: #ffffff; color: #1a1a1a; border: 1px solid #0969da; border-radius: 2px; padding: 1px;"
        )
        self.edit_line.returnPressed.connect(self._finish_rename)
        self.edit_line.hide()

        layout.addWidget(self.icon_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.text_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.edit_line, alignment=Qt.AlignCenter)

    def update_icon(self):
        """刷新图标渲染：采用高保真多分辨率平滑无锯齿贴图"""
        pix = ShellIconHelper.get_pixmap_for_path(str(self.file_path), self.icon_pixel)
        if not pix.isNull():
            self.icon_label.setPixmap(pix)

    def set_selected(self, selected: bool):
        """设置选中高亮状态"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.update()

    def paintEvent(self, event):
        """强制开启文本与几何抗锯齿，绘制通透微蓝背景与紧凑微框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 选框紧凑包裹图标与文字区域，去除大面积死板方块感
        content_box = self.rect().adjusted(3, 2, -3, -2)

        if self.is_selected:
            # 极通透 Windows 经典淡蓝微透效果: rgba(0, 120, 215, 0.2) 填充与 rgba(0, 120, 215, 0.5) 边框
            painter.setBrush(QBrush(QColor(0, 120, 215, 51)))
            painter.setPen(QPen(QColor(0, 120, 215, 128), 1))
            painter.drawRoundedRect(content_box, 4, 4)
        elif self.is_hovered:
            # 悬停轻微浅灰半透效果 (rgba(255, 255, 255, 0.08) 与 0.15 边框)
            painter.setBrush(QBrush(QColor(255, 255, 255, 20)))
            painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
            painter.drawRoundedRect(content_box, 4, 4)

        super().paintEvent(event)

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 多选与单选判定
            if not (event.modifiers() & Qt.ControlModifier):
                if not self.is_selected:
                    self.canvas.deselect_all_icons(exclude=self)
            self.set_selected(True)
            self.is_dragging = False
            self.drag_start_pos = event.pos()
        elif event.button() == Qt.RightButton:
            if not self.is_selected:
                self.canvas.deselect_all_icons(exclude=self)
                self.set_selected(True)
            self._show_context_menu(event.globalPos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if (event.pos() - self.drag_start_pos).manhattanLength() > QApplication.startDragDistance():
                self.is_dragging = True
                new_x = self.x() + (event.pos().x() - self.drag_start_pos.x())
                new_y = self.y() + (event.pos().y() - self.drag_start_pos.y())
                # 约束在画布可视范围内
                canvas_w = self.canvas.width()
                canvas_h = self.canvas.height()
                bounded_x = max(0, min(new_x, canvas_w - self.width()))
                bounded_y = max(0, min(new_y, canvas_h - self.height()))
                self.move(bounded_x, bounded_y)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            final_x = self.x()
            final_y = self.y()
            if self.canvas.grid_align:
                # 严禁图标重叠：网格防碰撞占位检测与曼哈顿就近吸附
                final_x, final_y = self.canvas.find_nearest_free_grid(
                    final_x, final_y, exclude_widget=self
                )
                self.move(final_x, final_y)

            clean_name = os.path.basename(self.filename)
            self.position_changed.emit(clean_name, final_x, final_y)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            FileOps.open_item(self.file_path)
        super().mouseDoubleClickEvent(event)

    def start_rename(self):
        """开启原地重命名模式"""
        self.is_editing = True
        self.text_label.hide()
        self.edit_line.setText(self.filename)
        self.edit_line.show()
        self.edit_line.setFocus()
        self.edit_line.selectAll()

    def _cancel_rename(self):
        """用户按 Esc 取消重命名，无条件隐藏输入框并恢复原名称显示"""
        if not self.is_editing:
            return
        self.is_editing = False
        self.edit_line.hide()
        self.text_label.show()

    def _finish_rename(self):
        """完成重命名提交：失焦或敲回车均自动确认，空值自动还原"""
        if not self.is_editing:
            return
        self.is_editing = False
        new_name = self.edit_line.text().strip()
        self.edit_line.hide()
        self.text_label.show()

        # 若未修改或输入为空，自动还原为当前文件名
        if not new_name or new_name == self.filename:
            return

        renamed_path = FileOps.safe_rename(self.file_path, new_name)
        if renamed_path:
            old_name = self.filename
            self.file_path = renamed_path
            self.filename = renamed_path.name
            self.text_label.setText(self.filename)
            self.update_icon()
            self.item_renamed.emit(old_name, self.filename)
        else:
            QMessageBox.warning(self, "重命名失败", "目标名称已存在或包含非法字符！")

    def _show_context_menu(self, global_pos: QPoint):
        """右键快捷上下文菜单"""
        menu = QMenu(self)

        act_open = QAction("打开(&O)", self)
        act_open.triggered.connect(lambda: FileOps.open_item(self.file_path))
        menu.addAction(act_open)

        act_show_dir = QAction("在资源管理器中定位(&E)", self)
        act_show_dir.triggered.connect(lambda: FileOps.show_in_explorer(self.file_path))
        menu.addAction(act_show_dir)

        menu.addSeparator()

        act_rename = QAction("重命名(&M)  [F2]", self)
        act_rename.triggered.connect(self.start_rename)
        menu.addAction(act_rename)

        act_delete = QAction("移至回收站(&D)  [Delete]", self)
        act_delete.triggered.connect(self._do_safe_delete)
        menu.addAction(act_delete)

        menu.addSeparator()

        act_props = QAction("属性(&R)", self)
        act_props.triggered.connect(self._show_properties)
        menu.addAction(act_props)

        menu.exec_(global_pos)

    def _do_safe_delete(self):
        """
        【严格回收站安全删除】
        调用 send2trash 移入回收站
        """
        confirm = QMessageBox.question(
            self,
            "确认删除",
            f"确定要将以下项目移入系统回收站吗？\n\n{self.filename}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            success = FileOps.send_to_recycle_bin(self.file_path)
            if success:
                self.item_deleted.emit(self.filename)
                self.deleteLater()
            else:
                QMessageBox.critical(self, "删除失败", "无法将文件移至回收站！")

    def _show_properties(self):
        """显示文件/目录基础属性对话框"""
        try:
            stat = self.file_path.stat()
            size_str = f"{stat.st_size:,} 字节"
            if stat.st_size > 1024 * 1024:
                size_str += f" ({stat.st_size / (1024*1024):.2f} MB)"
            elif stat.st_size > 1024:
                size_str += f" ({stat.st_size / 1024:.2f} KB)"

            mtime = QDateTime.fromSecsSinceEpoch(int(stat.st_mtime)).toString("yyyy-MM-dd hh:mm:ss")
            type_str = "文件夹" if self.file_path.is_dir() else f"{self.file_path.suffix or '未知'} 文件"

            info = (
                f"名称: {self.filename}\n"
                f"类型: {type_str}\n"
                f"位置: {self.file_path.parent}\n"
                f"大小: {size_str}\n"
                f"修改时间: {mtime}"
            )
            QMessageBox.information(self, f"属性 - {self.filename}", info)
        except Exception as e:
            QMessageBox.warning(self, "获取属性失败", str(e))
