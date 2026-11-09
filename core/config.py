import os
import sys
from pathlib import Path

# 工程基础根目录 (相对当前文件解析，支持开发环境与 PyInstaller 打包便携环境)
def get_base_dir() -> Path:
    """获取程序运行基础根目录（兼容源码开发与打包运行）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
PROFILES_DIR = BASE_DIR / "profiles"

# 确保 profiles 基础目录就绪
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# 预设分辨率列表 (名称, 宽, 高)
PRESET_RESOLUTIONS = [
    ("640 × 480 (VGA 标清)", 640, 480),
    ("800 × 480 (WVGA 宽屏)", 800, 480),
    ("800 × 600 (SVGA)", 800, 600),
    ("960 × 540 (qHD 16:9)", 960, 540),
    ("1024 × 768 (XGA 经典)", 1024, 768),
    ("1280 × 720 (HD 720P)", 1280, 720),
    ("1366 × 768 (WXGA 笔记本)", 1366, 768),
    ("1600 × 900 (HD+ 16:9)", 1600, 900),
    ("1920 × 1080 (FHD 1080P)", 1920, 1080),
    ("自定义...", -1, -1),
]

# 图标尺寸与标准网格单元定义 (cell 宽, 高, 图标像素, 字体大小)
DEFAULT_CELL_WIDTH = 76
DEFAULT_CELL_HEIGHT = 90
GRID_MARGIN_X = 14
GRID_MARGIN_Y = 14

ICON_SIZE_CONFIG = {
    "small": {"icon": 32, "cell_w": 68, "cell_h": 80, "width": 68, "height": 80, "font_size": 9},
    "medium": {"icon": 48, "cell_w": 76, "cell_h": 90, "width": 76, "height": 90, "font_size": 9},
    "large": {"icon": 64, "cell_w": 90, "cell_h": 105, "width": 90, "height": 105, "font_size": 9},
}

# 默认网格步长
DEFAULT_GRID_SIZE = 90

# 默认子桌面配置骨架
DEFAULT_PROFILE_TEMPLATE = {
    "id": "profile_default",
    "name": "我的子桌面",
    "target_path": "",
    "window_rect": {"x": 150, "y": 100, "width": 960, "height": 540},
    "grid_align": True,
    "grid_size": DEFAULT_GRID_SIZE,
    "icon_size": "medium",
    "show_desktop_icons": True,
    "auto_arrange": False,
    "wallpaper_file": "",
    "items_pos": {},
}
