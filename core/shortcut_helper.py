import os
import sys
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger("SubDesktop.ShortcutHelper")

class ShortcutHelper:
    """
    Windows 桌面快捷方式 (.lnk) 生成与清理助手
    使用 pywin32 WScript.Shell 接口
    采用 Windows 原生高质感系统图标库与纯净命名规则
    """

    @staticmethod
    def get_desktop_dir() -> Path:
        """获取当前用户的 Windows 桌面真实路径"""
        desktop = None
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            desktop = shell.SpecialFolders("Desktop")
        except Exception:
            pass

        if not desktop or not Path(desktop).exists():
            desktop = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Desktop")
        return Path(desktop)

    @classmethod
    def get_clean_name(cls, profile_name: str) -> str:
        """清洗名称中的文件名非法字符"""
        return "".join(c for c in profile_name if c not in r'\/:*?"<>|').strip()

    @classmethod
    def get_shortcut_path(cls, profile_name: str) -> Path:
        """获取指定子桌面的 .lnk 文件预期路径（纯净桌面名称命名）"""
        clean_name = cls.get_clean_name(profile_name)
        filename = f"{clean_name}.lnk"
        return cls.get_desktop_dir() / filename

    @classmethod
    def get_legacy_shortcut_path(cls, profile_name: str) -> Path:
        """获取旧版带前缀的 .lnk 路径（用于向下兼容查找与清理）"""
        clean_name = cls.get_clean_name(profile_name)
        filename = f"SubDesktop - {clean_name}.lnk"
        return cls.get_desktop_dir() / filename

    @classmethod
    def is_shortcut_exists(cls, profile_name: str) -> bool:
        """检查桌面是否已存在该子桌面的快捷方式（兼顾新纯净名与旧前缀名）"""
        return cls.get_shortcut_path(profile_name).exists() or cls.get_legacy_shortcut_path(profile_name).exists()

    @classmethod
    def get_default_icon_location(cls) -> str:
        """获取 Windows 原生高质感系统虚拟桌面图标库位置"""
        sys_root = os.environ.get("SystemRoot", "C:\\Windows")
        imageres = Path(sys_root) / "System32" / "imageres.dll"
        if imageres.exists():
            # 110: Windows 10/11 原生虚拟桌面 / 屏幕显示器图标
            return f"{imageres}, 110"
        shell32 = Path(sys_root) / "System32" / "shell32.dll"
        if shell32.exists():
            # 34: Windows 经典桌面图标
            return f"{shell32}, 34"
        return f"{sys.executable}, 0"

    @classmethod
    def create_desktop_shortcut(cls, profile_id: str, profile_name: str, icon_path: Optional[str] = None) -> bool:
        """
        在 Windows 桌面创建或更新指向该子桌面的纯净快捷方式
        """
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            lnk_path = cls.get_shortcut_path(profile_name)

            # 若存在旧版带前缀的快捷方式，先平滑升级移除旧文件
            legacy_lnk = cls.get_legacy_shortcut_path(profile_name)
            if legacy_lnk.exists() and legacy_lnk != lnk_path:
                try:
                    legacy_lnk.unlink()
                except Exception:
                    pass

            shortcut = shell.CreateShortCut(str(lnk_path))

            # 判断当前是 PyInstaller 冻结环境还是 Python 脚本直接运行
            if getattr(sys, "frozen", False):
                exe_path = sys.executable
                shortcut.TargetPath = exe_path
                shortcut.Arguments = f'--profile "{profile_id}"'
                shortcut.WorkingDirectory = str(Path(exe_path).parent)
            else:
                py_dir = Path(sys.executable).parent
                pythonw = py_dir / "pythonw.exe"
                launcher = str(pythonw) if pythonw.exists() else sys.executable

                main_script = Path(__file__).resolve().parent.parent / "main.py"
                shortcut.TargetPath = launcher
                shortcut.Arguments = f'"{main_script}" --profile "{profile_id}"'
                shortcut.WorkingDirectory = str(main_script.parent)

            shortcut.Description = f"SubDesktop 独立子桌面: {profile_name}"

            # 引用 Windows 原生系统图标库
            if icon_path and Path(icon_path).exists():
                shortcut.IconLocation = str(icon_path)
            else:
                shortcut.IconLocation = cls.get_default_icon_location()

            shortcut.Save()
            logger.info(f"桌面快捷方式创建成功: {lnk_path} (图标: {shortcut.IconLocation})")
            return True
        except Exception as e:
            logger.error(f"创建桌面快捷方式失败: {e}")
            return False

    @classmethod
    def remove_desktop_shortcut(cls, profile_name: str) -> bool:
        """从 Windows 桌面安全清理快捷方式（同时清理新纯净名与旧版前缀名）"""
        try:
            new_lnk = cls.get_shortcut_path(profile_name)
            if new_lnk.exists():
                new_lnk.unlink()
                logger.info(f"已清理桌面快捷方式: {new_lnk}")

            legacy_lnk = cls.get_legacy_shortcut_path(profile_name)
            if legacy_lnk.exists():
                legacy_lnk.unlink()
                logger.info(f"已清理旧版桌面快捷方式: {legacy_lnk}")
            return True
        except Exception as e:
            logger.error(f"清理桌面快捷方式失败: {profile_name}, 错误: {e}")
            return False
