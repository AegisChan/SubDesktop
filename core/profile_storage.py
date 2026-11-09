import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

from core.config import PROFILES_DIR, DEFAULT_PROFILE_TEMPLATE

logger = logging.getLogger("SubDesktop.ProfileStorage")

class ProfileStorage:
    """
    Profile 隔离存储引擎
    负责管理 ./profiles/<profile_id>/ 下的配置与壁纸
    严格遵守安全铁律：删除 Profile 仅清理元数据与快捷方式，绝不删除映射目录真实文件！
    """

    @classmethod
    def get_profile_dir(cls, profile_id: str) -> Path:
        """获取指定 Profile 的目录路径"""
        return PROFILES_DIR / profile_id

    @classmethod
    def get_config_path(cls, profile_id: str) -> Path:
        """获取指定 Profile 的 config.json 路径"""
        return cls.get_profile_dir(profile_id) / "config.json"

    @classmethod
    def list_profiles(cls) -> List[Dict[str, Any]]:
        """列出所有已存在的有效 Profile 配置"""
        profiles = []
        if not PROFILES_DIR.exists():
            return profiles

        for entry in PROFILES_DIR.iterdir():
            if entry.is_dir():
                cfg_file = entry / "config.json"
                if cfg_file.exists() and cfg_file.is_file():
                    try:
                        with open(cfg_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            # 补全缺失键
                            for k, v in DEFAULT_PROFILE_TEMPLATE.items():
                                if k not in data:
                                    data[k] = v
                            profiles.append(data)
                    except Exception as e:
                        logger.warning(f"读取 Profile 失败: {cfg_file}, 错误: {e}")
        return profiles

    @classmethod
    def get_profile(cls, profile_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 Profile 配置数据"""
        cfg_file = cls.get_config_path(profile_id)
        if not cfg_file.exists():
            return None
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULT_PROFILE_TEMPLATE.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            logger.error(f"读取 Profile 配置异常: {cfg_file}, 错误: {e}")
            return None

    @classmethod
    def save_profile(cls, profile_data: Dict[str, Any]) -> bool:
        """保存 Profile 数据到 config.json"""
        profile_id = profile_data.get("id")
        if not profile_id:
            logger.error("保存失败: 缺少 profile_id")
            return False

        profile_dir = cls.get_profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = profile_dir / "config.json"

        try:
            temp_file = profile_dir / "config.json.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)
            temp_file.replace(cfg_file)
            return True
        except Exception as e:
            logger.error(f"写入 Profile 配置失败: {cfg_file}, 错误: {e}")
            return False

    @classmethod
    def generate_profile_id(cls, name: str) -> str:
        """
        生成规范、简洁、整齐的 Profile ID / 文件夹名称：
        优先以 profile_{safe_name} 命名；若重名则后置自增数字 profile_{safe_name}_1；
        若名称无效则统一回退至纯时间戳 profile_%Y%m%d_%H%M%S。
        彻底废弃带随机散列码的冗长命名。
        """
        clean = re.sub(r'[^\w\u4e00-\u9fa5]', '_', (name or "").strip())
        clean = re.sub(r'_+', '_', clean).strip('_')

        if not clean:
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            candidate = f"profile_{timestamp_str}"
        else:
            candidate = f"profile_{clean}"

        final_id = candidate
        counter = 1
        while cls.get_profile_dir(final_id).exists():
            final_id = f"{candidate}_{counter}"
            counter += 1

        return final_id

    @classmethod
    def create_profile(
        cls,
        name: str,
        target_path: str,
        width: int = 960,
        height: int = 540,
        wallpaper_src: Optional[str] = None,
        grid_align: bool = True,
        grid_size: int = 85,
        icon_size: str = "medium",
    ) -> Dict[str, Any]:
        """
        创建新的 Profile 并固化壁纸（采用规范、整齐的 ID 与目录命名）
        """
        profile_id = cls.generate_profile_id(name)
        profile_dir = cls.get_profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)

        wallpaper_filename = ""
        if wallpaper_src and Path(wallpaper_src).exists():
            wallpaper_filename = cls._copy_wallpaper(profile_dir, wallpaper_src)

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        data = {
            "id": profile_id,
            "name": name.strip() or f"桌面_{timestamp_str}",
            "target_path": str(Path(target_path).resolve()) if target_path else "",
            "window_rect": {"x": 150, "y": 100, "width": width, "height": height},
            "grid_align": grid_align,
            "grid_size": grid_size,
            "icon_size": icon_size,
            "show_desktop_icons": True,
            "auto_arrange": False,
            "wallpaper_file": wallpaper_filename,
            "items_pos": {},
        }
        cls.save_profile(data)
        return data

    @classmethod
    def update_profile(
        cls,
        profile_id: str,
        updates: Dict[str, Any],
        new_wallpaper_src: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新已有 Profile 配置"""
        current = cls.get_profile(profile_id)
        if not current:
            logger.error(f"未找到目标 Profile: {profile_id}")
            return None

        profile_dir = cls.get_profile_dir(profile_id)

        # 处理壁纸更新
        if new_wallpaper_src is not None:
            if new_wallpaper_src == "":
                # 清除壁纸
                old_wall = current.get("wallpaper_file")
                if old_wall and (profile_dir / old_wall).exists():
                    try:
                        (profile_dir / old_wall).unlink()
                    except Exception:
                        pass
                current["wallpaper_file"] = ""
            elif Path(new_wallpaper_src).exists():
                # 复制并固化新壁纸
                wallpaper_filename = cls._copy_wallpaper(profile_dir, new_wallpaper_src)
                current["wallpaper_file"] = wallpaper_filename

        # 更新其他字段
        for k, v in updates.items():
            if k not in ("id", "wallpaper_file"):
                current[k] = v

        if "target_path" in current and current["target_path"]:
            current["target_path"] = str(Path(current["target_path"]).resolve())

        if cls.save_profile(current):
            return current
        return None

    @classmethod
    def _copy_wallpaper(cls, profile_dir: Path, src_path: str) -> str:
        """安全复制固化壁纸到 profile 目录"""
        src = Path(src_path)
        ext = src.suffix.lower() if src.suffix else ".jpg"
        target_name = f"wallpaper{ext}"
        dst = profile_dir / target_name
        try:
            shutil.copy2(src, dst)
            return target_name
        except Exception as e:
            logger.error(f"固化壁纸失败: {src} -> {dst}, 错误: {e}")
            return ""

    @classmethod
    def get_wallpaper_path(cls, profile_id: str) -> Optional[Path]:
        """获取壁纸的绝对路径，若无或不存在返回 None"""
        profile = cls.get_profile(profile_id)
        if not profile:
            return None
        wall_file = profile.get("wallpaper_file")
        if not wall_file:
            return None
        path = cls.get_profile_dir(profile_id) / wall_file
        return path if path.exists() else None

    @classmethod
    def delete_profile(cls, profile_id: str) -> bool:
        """
        【最高安全红线保护核心方法】
        删除子桌面实质为【解除映射关系】。
        仅删除 ./profiles/<profile_id>/ 内的元数据与固化壁纸！
        严禁、绝对禁止以任何形式触碰、修改或删除映射的 target_path 物理真实目录！
        """
        profile_dir = cls.get_profile_dir(profile_id)
        if not profile_dir.exists():
            logger.warning(f"Profile 目录不存在，无需删除: {profile_dir}")
            return True

        # 二次核查：确保删除的目标必须位于 PROFILES_DIR 内部，防止任何路径穿越
        try:
            resolved_profile_dir = profile_dir.resolve()
            resolved_root = PROFILES_DIR.resolve()
            if resolved_root not in resolved_profile_dir.parents and resolved_root != resolved_profile_dir:
                raise ValueError(f"安全警报：拒绝删除非 profiles 内部路径: {resolved_profile_dir}")
            
            # 仅删除 profile 目录自身元数据
            shutil.rmtree(resolved_profile_dir)
            logger.info(f"已安全解除映射并清除 Profile 元数据: {profile_id}")
            return True
        except Exception as e:
            logger.error(f"删除 Profile 目录失败: {profile_dir}, 错误: {e}")
            return False

    @classmethod
    def update_item_position(cls, profile_id: str, item_name: str, x: int, y: int):
        """记录图标在画布上的绝对坐标（统一使用纯文件名作为 Key）"""
        profile = cls.get_profile(profile_id)
        if not profile:
            return
        if "items_pos" not in profile:
            profile["items_pos"] = {}
        clean_key = os.path.basename(item_name)
        profile["items_pos"][clean_key] = {"x": int(x), "y": int(y)}
        cls.save_profile(profile)

    @classmethod
    def remove_item_position(cls, profile_id: str, item_name: str):
        """移除已不存在文件的坐标记录"""
        profile = cls.get_profile(profile_id)
        if not profile or "items_pos" not in profile:
            return
        clean_key = os.path.basename(item_name)
        if clean_key in profile["items_pos"]:
            del profile["items_pos"][clean_key]
            cls.save_profile(profile)

    @classmethod
    def update_window_rect(cls, profile_id: str, x: int, y: int, width: int, height: int):
        """记录窗口位置与尺寸"""
        profile = cls.get_profile(profile_id)
        if not profile:
            return
        profile["window_rect"] = {
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
        }
        cls.save_profile(profile)

