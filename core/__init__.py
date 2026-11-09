"""
SubDesktop 核心业务层包定义
纯本地轻量运行架构，无任何外部数据库或 Redis 依赖
"""

from core.config import (
    BASE_DIR,
    PROFILES_DIR,
    PRESET_RESOLUTIONS,
    DEFAULT_GRID_SIZE,
    DEFAULT_CELL_WIDTH,
    DEFAULT_CELL_HEIGHT,
    GRID_MARGIN_X,
    GRID_MARGIN_Y,
    ICON_SIZE_CONFIG,
    DEFAULT_PROFILE_TEMPLATE,
)
from core.profile_storage import ProfileStorage
from core.file_ops import FileOps
from core.shortcut_helper import ShortcutHelper
from core.shell_icon import ShellIconHelper

__all__ = [
    "BASE_DIR",
    "PROFILES_DIR",
    "PRESET_RESOLUTIONS",
    "DEFAULT_GRID_SIZE",
    "DEFAULT_CELL_WIDTH",
    "DEFAULT_CELL_HEIGHT",
    "GRID_MARGIN_X",
    "GRID_MARGIN_Y",
    "ICON_SIZE_CONFIG",
    "DEFAULT_PROFILE_TEMPLATE",
    "ProfileStorage",
    "FileOps",
    "ShortcutHelper",
    "ShellIconHelper",
]
