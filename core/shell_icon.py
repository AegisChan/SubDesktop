import os
from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtCore import QFileInfo, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QFileIconProvider

class ShellIconHelper:
    """
    Windows 原生系统高保真图标提取与内存平滑缓存
    使用包含 16x16, 32x32, 48x48, 256x256 的多分辨率图标源，杜绝拉伸毛刺
    """

    _cache: Dict[str, QIcon] = {}
    _pix_cache: Dict[str, QPixmap] = {}
    _provider: Optional[QFileIconProvider] = None

    @classmethod
    def get_provider(cls) -> QFileIconProvider:
        if cls._provider is None:
            cls._provider = QFileIconProvider()
        return cls._provider

    @classmethod
    def get_icon_for_path(cls, path_str: str) -> QIcon:
        """获取文件或目录的 Windows 原生多分辨率图标"""
        path = Path(path_str)
        ext = path.suffix.lower() if not path.is_dir() else "__dir__"

        is_unique_icon = ext in [".exe", ".lnk", ".ico"]
        cache_key = str(path.resolve()) if is_unique_icon else ext

        if cache_key in cls._cache:
            return cls._cache[cache_key]

        icon = None
        try:
            qfi = QFileInfo(str(path))
            icon = cls.get_provider().icon(qfi)
        except Exception:
            icon = QIcon()

        if icon and not icon.isNull():
            cls._cache[cache_key] = icon
            return icon

        return QIcon()

    @classmethod
    def get_pixmap_for_path(cls, path_str: str, size: int = 48) -> QPixmap:
        """
        获取指定尺寸的高保真平滑贴图
        强制采用 Qt.KeepAspectRatio 与 Qt.SmoothTransformation，消除白底图标边缘锯齿毛边
        """
        cache_key = f"{path_str}_{size}"
        if cache_key in cls._pix_cache:
            return cls._pix_cache[cache_key]

        icon = cls.get_icon_for_path(path_str)
        if icon.isNull():
            return QPixmap()

        # 从多分辨率图标源（16/32/48/256）中提取与 size 最优匹配的贴图
        pix = icon.pixmap(size, size)
        if pix.isNull():
            return QPixmap()

        # 若提取出的尺寸与目标不一致，显式使用高质量双线性平滑插值进行无损重采样
        if pix.width() != size or pix.height() != size:
            pix = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        cls._pix_cache[cache_key] = pix
        return pix
