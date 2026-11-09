import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Union

import send2trash

logger = logging.getLogger("SubDesktop.FileOps")

class FileOps:
    """
    文件操作安全门禁
    严格遵守安全铁律：
    1. 任何删除操作必须经由 send2trash 进入 Windows 原生回收站，严禁物理硬删除！
    2. 新建/重命名做好合法性校验与同名自动递增规避。
    """

    @staticmethod
    def send_to_recycle_bin(path: Union[str, Path]) -> bool:
        """
        【安全删除】将文件或目录放入 Windows 原生回收站
        严禁使用 os.remove / shutil.rmtree
        """
        target = Path(path).resolve()
        if not target.exists():
            logger.warning(f"目标不存在，无需删除: {target}")
            return True

        try:
            # 严格调用 send2trash
            send2trash.send2trash(str(target))
            logger.info(f"已安全移入系统回收站: {target}")
            return True
        except Exception as e:
            logger.error(f"移入回收站失败: {target}, 错误: {e}")
            return False

    @staticmethod
    def open_item(path: Union[str, Path]) -> bool:
        """使用 Windows 系统关联的默认应用打开文件或文件夹"""
        target = Path(path).resolve()
        if not target.exists():
            return False
        try:
            os.startfile(str(target))
            return True
        except Exception as e:
            logger.error(f"打开文件失败: {target}, 错误: {e}")
            return False

    @staticmethod
    def show_in_explorer(path: Union[str, Path]) -> bool:
        """在 Windows 文件资源管理器中高亮选中文件或打开目录"""
        target = Path(path).resolve()
        if not target.exists():
            return False
        try:
            if target.is_dir():
                subprocess.Popen(["explorer.exe", str(target)])
            else:
                subprocess.Popen(["explorer.exe", f"/select,{str(target)}"])
            return True
        except Exception as e:
            logger.error(f"在资源管理器中显示失败: {target}, 错误: {e}")
            return False

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名中的非法字符"""
        return re.sub(r'[\\/:*?"<>|]', "", filename).strip()

    @classmethod
    def create_new_folder(cls, parent_dir: Union[str, Path], base_name: str = "新建文件夹") -> Optional[Path]:
        """在映射目录下新建文件夹，自动处理重名后缀递增"""
        parent = Path(parent_dir).resolve()
        if not parent.exists() or not parent.is_dir():
            return None

        clean_base = cls.sanitize_filename(base_name) or "新建文件夹"
        target = parent / clean_base
        counter = 2
        while target.exists():
            target = parent / f"{clean_base} ({counter})"
            counter += 1

        try:
            target.mkdir(parents=True, exist_ok=False)
            return target
        except Exception as e:
            logger.error(f"新建文件夹失败: {target}, 错误: {e}")
            return None

    @classmethod
    def create_new_file(cls, parent_dir: Union[str, Path], filename: str = "新建文本文档.txt") -> Optional[Path]:
        """在映射目录下新建空白文件，自动处理重名递增"""
        parent = Path(parent_dir).resolve()
        if not parent.exists() or not parent.is_dir():
            return None

        p = Path(filename)
        stem = cls.sanitize_filename(p.stem) or "新建文本文档"
        suffix = p.suffix or ".txt"

        target = parent / f"{stem}{suffix}"
        counter = 2
        while target.exists():
            target = parent / f"{stem} ({counter}){suffix}"
            counter += 1

        try:
            target.write_text("", encoding="utf-8")
            return target
        except Exception as e:
            logger.error(f"新建文件失败: {target}, 错误: {e}")
            return None

    @classmethod
    def safe_rename(cls, src_path: Union[str, Path], new_name: str) -> Optional[Path]:
        """在同一目录下安全重命名文件或文件夹"""
        src = Path(src_path).resolve()
        if not src.exists():
            return None

        clean_name = cls.sanitize_filename(new_name)
        if not clean_name or clean_name == src.name:
            return src

        dst = src.parent / clean_name
        if dst.exists():
            logger.warning(f"目标文件已存在，无法重命名: {dst}")
            return None

        try:
            src.rename(dst)
            return dst
        except Exception as e:
            logger.error(f"重命名失败: {src} -> {dst}, 错误: {e}")
            return None

    @classmethod
    def copy_into_folder(cls, src_paths: List[Union[str, Path]], target_dir: Union[str, Path]) -> List[Path]:
        """将外部文件或目录复制到目标映射目录中"""
        target = Path(target_dir).resolve()
        if not target.exists() or not target.is_dir():
            return []

        copied = []
        for src in src_paths:
            src_p = Path(src).resolve()
            if not src_p.exists():
                continue
            dst = target / src_p.name
            # 同名处理
            counter = 2
            while dst.exists():
                if src_p.is_dir():
                    dst = target / f"{src_p.name} ({counter})"
                else:
                    dst = target / f"{src_p.stem} ({counter}){src_p.suffix}"
                counter += 1

            try:
                if src_p.is_dir():
                    shutil.copytree(src_p, dst)
                else:
                    shutil.copy2(src_p, dst)
                copied.append(dst)
            except Exception as e:
                logger.error(f"复制文件失败: {src_p} -> {dst}, 错误: {e}")
        return copied

    @classmethod
    def safe_move_into_folder(cls, src_paths: List[Union[str, Path]], target_dir: Union[str, Path]) -> List[Path]:
        """
        【安全移动】执行严谨的“先流写入校验大小 -> 后回收站清理源文件”安全移动协议：
        1. 先将文件/目录流写入目标物理映射目录；
        2. 严格校验目标与源文件大小（st_size）或文件项数是否完全一致；
        3. 校验通过后，调用 send2trash 将源文件移入系统回收站（绝非不可逆硬删除）；
        4. 若校验不通过，绝对不删除源文件，确保零意外数据丢失且不留冗余副本。
        """
        target = Path(target_dir).resolve()
        if not target.exists() or not target.is_dir():
            logger.error(f"目标目录不存在: {target_dir}")
            return []

        moved_items = []
        for src in src_paths:
            src_p = Path(src).resolve()
            if not src_p.exists():
                continue

            # 若源路径已在目标目录中，无需重复移动
            if src_p.parent == target:
                continue

            # 处理同名规避
            dst = target / src_p.name
            counter = 2
            while dst.exists():
                if src_p.is_dir():
                    dst = target / f"{src_p.name} ({counter})"
                else:
                    dst = target / f"{src_p.stem} ({counter}){src_p.suffix}"
                counter += 1

            try:
                # 步骤 1: 写入目标流
                if src_p.is_dir():
                    shutil.copytree(src_p, dst)
                    # 步骤 2: 校验目录文件数量与总大小
                    src_files = list(src_p.rglob("*"))
                    dst_files = list(dst.rglob("*"))
                    src_size = sum(f.stat().st_size for f in src_files if f.is_file())
                    dst_size = sum(f.stat().st_size for f in dst_files if f.is_file())
                    is_valid = (len(src_files) == len(dst_files)) and (src_size == dst_size)
                else:
                    shutil.copy2(src_p, dst)
                    # 步骤 2: 校验单文件字节大小完全一致
                    is_valid = dst.exists() and (dst.stat().st_size == src_p.stat().st_size)

                # 步骤 3: 校验完全一致后安全清理源文件至回收站
                if is_valid:
                    send2trash.send2trash(str(src_p))
                    moved_items.append(dst)
                    logger.info(f"安全移动成功: {src_p} -> {dst}")
                else:
                    logger.error(f"安全校验失败（大小不匹配），已保留源文件: {src_p}")
                    if dst.exists():
                        send2trash.send2trash(str(dst))
            except Exception as e:
                logger.error(f"安全移动过程异常: {src_p} -> {dst}, 错误: {e}")

        return moved_items

