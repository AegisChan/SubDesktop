import os
from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtCore import QFileInfo, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QFileIconProvider

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
    def clear_pixmap_cache(cls):
        """清空贴图缓存（切换图标尺寸或屏幕 DPR 变化时调用）"""
        cls._pix_cache.clear()

    @classmethod
    def _resolve_dpr(cls, dpr: Optional[float]) -> float:
        if dpr is not None and dpr > 0:
            return float(dpr)
        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                val = screen.devicePixelRatio()
                if val > 0:
                    return float(val)
        return 1.0

    @classmethod
    def get_pixmap_for_path(
        cls,
        path_str: str,
        size: int = 48,
        dpr: Optional[float] = None,
        phys_size: Optional[int] = None,
    ) -> QPixmap:
        """
        获取指定尺寸与屏幕缩放比（DPR）的高保真平滑贴图：
        - 若显式传入 phys_size（如物理 48px），则严格输出 phys_size×phys_size 物理像素并绑定 DPR；
        - 否则按 round(size * dpr) 计算目标物理像素。
        """
        actual_dpr = cls._resolve_dpr(dpr)
        target_phys = max(1, int(phys_size)) if phys_size and phys_size > 0 else max(1, int(round(size * actual_dpr)))
        cache_key = f"{path_str}_{target_phys}_{actual_dpr:.2f}"
        if cache_key in cls._pix_cache:
            return cls._pix_cache[cache_key]

        icon = cls.get_icon_for_path(path_str)
        if icon.isNull():
            return QPixmap()

        # 优先尝试按物理像素尺寸提取；若提取尺寸不足 target_phys，则请求 256px 原图降采样
        pix = icon.pixmap(target_phys, target_phys)
        if not pix.isNull():
            pix.setDevicePixelRatio(1.0)
        if pix.isNull() or max(pix.width(), pix.height()) < target_phys:
            hi_pix = icon.pixmap(256, 256)
            if not hi_pix.isNull():
                hi_pix.setDevicePixelRatio(1.0)
                if max(hi_pix.width(), hi_pix.height()) > max(pix.width() if not pix.isNull() else 0, 0):
                    pix = hi_pix

        if pix.isNull():
            return QPixmap()

        # 精确缩放到目标物理像素尺寸，并应用高质量双线性平滑插值
        if pix.width() != target_phys or pix.height() != target_phys:
            pix = pix.scaled(target_phys, target_phys, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        pix.setDevicePixelRatio(actual_dpr)
        cls._pix_cache[cache_key] = pix
        return pix
