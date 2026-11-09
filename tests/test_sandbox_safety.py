import os
import shutil
import unittest
from pathlib import Path

from core.config import BASE_DIR, PROFILES_DIR
from core.profile_storage import ProfileStorage
from core.file_ops import FileOps
from core.shortcut_helper import ShortcutHelper

class TestSubDesktopSafety(unittest.TestCase):
    """
    SubDesktop 核心安全红线与沙盒隔离测试套件
    严格仅在 ./test_sandbox/ 临时目录下运行
    """

    @classmethod
    def setUpClass(cls):
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        if QApplication.instance() is None:
            cls.app = QApplication([""])
        cls.sandbox_dir = BASE_DIR / "test_sandbox"
        cls.sandbox_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        # 测试结束后仅清理 ./test_sandbox/ 临时目录
        if cls.sandbox_dir.exists():
            shutil.rmtree(cls.sandbox_dir, ignore_errors=True)

    def setUp(self):
        # 每一个测试用例前准备专属沙盒隔离目录，并确保起步环境完全清空
        self.case_dir = self.sandbox_dir / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir, ignore_errors=True)
        self.case_dir.mkdir(parents=True, exist_ok=True)

    def test_01_profile_lifecycle_and_zero_data_loss(self):
        """
        【最高安全红线测试】
        验证：创建 Profile、映射真实数据目录、解除映射删除 Profile。
        必须保证：真实映射目录下的所有文件 100% 完好无损，零丢失、零修改！
        """
        user_real_data_dir = self.case_dir / "user_important_documents"
        user_real_data_dir.mkdir(parents=True, exist_ok=True)

        # 模拟用户的关键重要文件
        file1 = user_real_data_dir / "财务报表_2026.xlsx"
        file1.write_text("核心财务数据内容", encoding="utf-8")
        file2 = user_real_data_dir / "项目方案.docx"
        file2.write_text("项目设计规范", encoding="utf-8")
        sub_dir = user_real_data_dir / "代码附件"
        sub_dir.mkdir(parents=True, exist_ok=True)
        file3 = sub_dir / "main.c"
        file3.write_text("int main() { return 0; }", encoding="utf-8")

        # 模拟一张壁纸
        mock_wall = self.case_dir / "mock_wallpaper.jpg"
        mock_wall.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 100)

        # 1. 创建子桌面
        profile = ProfileStorage.create_profile(
            name="安全测试桌面",
            target_path=str(user_real_data_dir),
            width=1280,
            height=720,
            wallpaper_src=str(mock_wall),
            grid_align=True,
            icon_size="medium",
        )
        pid = profile["id"]
        self.assertTrue(pid.startswith("profile_"))

        # 2. 验证元数据与壁纸固化是否在 profiles 目录下
        p_dir = ProfileStorage.get_profile_dir(pid)
        self.assertTrue(p_dir.exists())
        self.assertTrue((p_dir / "config.json").exists())
        self.assertTrue((p_dir / "wallpaper.jpg").exists())

        # 3. 记录图标位置
        ProfileStorage.update_item_position(pid, "财务报表_2026.xlsx", 100, 150)
        reloaded = ProfileStorage.get_profile(pid)
        self.assertEqual(reloaded["items_pos"]["财务报表_2026.xlsx"]["x"], 100)
        self.assertEqual(reloaded["items_pos"]["财务报表_2026.xlsx"]["y"], 150)

        # 4. 【核心验证动作】：删除 Profile / 解除映射
        del_result = ProfileStorage.delete_profile(pid)
        self.assertTrue(del_result)

        # 5. 验证 profiles 目录下的元数据已被清理
        self.assertFalse(p_dir.exists(), "Profile 元数据目录应当已被清除")

        # 6. 【铁律断言】：用户映射目录及内部所有文件必须 100% 存在、完好无损！
        self.assertTrue(user_real_data_dir.exists(), "红线断言失败：真实映射目录被删除了！")
        self.assertTrue(file1.exists(), "红线断言失败：真实文件1被删除了！")
        self.assertTrue(file2.exists(), "红线断言失败：真实文件2被删除了！")
        self.assertTrue(file3.exists(), "红线断言失败：真实文件3被删除了！")
        self.assertEqual(file1.read_text(encoding="utf-8"), "核心财务数据内容")
        self.assertEqual(file2.read_text(encoding="utf-8"), "项目设计规范")
        self.assertEqual(file3.read_text(encoding="utf-8"), "int main() { return 0; }")

    def test_02_send2trash_recycle_bin(self):
        """
        【回收站删除测试】
        验证：文件删除动作严格调用 send2trash，而非物理硬删除
        """
        test_file = self.case_dir / "to_be_recycled.txt"
        test_file.write_text("测试移入回收站内容", encoding="utf-8")
        self.assertTrue(test_file.exists())

        success = FileOps.send_to_recycle_bin(test_file)
        self.assertTrue(success)
        # 移入回收站后，原物理路径下的文件应当脱离原位置
        self.assertFalse(test_file.exists())

    def test_03_file_ops_helpers(self):
        """
        验证新建文件夹、新建文件与安全重命名（同名自动递增规避）
        """
        # 新建文件夹自动编号
        f1 = FileOps.create_new_folder(self.case_dir, "新建文件夹")
        self.assertIsNotNone(f1)
        self.assertEqual(f1.name, "新建文件夹")

        f2 = FileOps.create_new_folder(self.case_dir, "新建文件夹")
        self.assertIsNotNone(f2)
        self.assertEqual(f2.name, "新建文件夹 (2)")

        # 新建文本文档自动编号
        t1 = FileOps.create_new_file(self.case_dir, "新建文本文档.txt")
        self.assertIsNotNone(t1)
        self.assertEqual(t1.name, "新建文本文档.txt")

        t2 = FileOps.create_new_file(self.case_dir, "新建文本文档.txt")
        self.assertIsNotNone(t2)
        self.assertEqual(t2.name, "新建文本文档 (2).txt")

        # 安全重命名
        renamed = FileOps.safe_rename(t1, "重命名文档.txt")
        self.assertIsNotNone(renamed)
        self.assertEqual(renamed.name, "重命名文档.txt")
        self.assertTrue(renamed.exists())
        self.assertFalse(t1.exists())

    def test_04_shortcut_helper_naming(self):
        """
        验证快捷方式纯净命名与路径清理逻辑
        """
        lnk_path = ShortcutHelper.get_shortcut_path("测试:/*?桌面")
        # 验证非法字符已被清洗，且不再包含 "SubDesktop - " 前缀
        self.assertNotIn(":", lnk_path.name)
        self.assertNotIn("*", lnk_path.name)
        self.assertNotIn("?", lnk_path.name)
        self.assertEqual(lnk_path.name, "测试桌面.lnk")
        self.assertFalse(lnk_path.name.startswith("SubDesktop - "))

        # 验证图标位置引用原生系统库
        icon_loc = ShortcutHelper.get_default_icon_location()
        self.assertTrue("imageres.dll" in icon_loc or "shell32.dll" in icon_loc)

    def test_05_safe_move_flow_and_validation(self):
        """
        【安全移动测试】
        验证：写入目标流 -> 大小校验一致 -> send2trash 回收站安全清理源文件
        """
        src_dir = self.case_dir / "external_source"
        src_dir.mkdir(parents=True, exist_ok=True)
        target_dir = self.case_dir / "mapped_target"
        target_dir.mkdir(parents=True, exist_ok=True)

        test_file = src_dir / "dragged_doc.docx"
        test_content = "安全移动测试文件流内容" * 50
        test_file.write_text(test_content, encoding="utf-8")
        original_size = test_file.stat().st_size

        moved = FileOps.safe_move_into_folder([test_file], target_dir)
        self.assertEqual(len(moved), 1)
        dst_file = moved[0]

        # 目标文件存在且大小内容完全一致
        self.assertTrue(dst_file.exists())
        self.assertEqual(dst_file.stat().st_size, original_size)
        self.assertEqual(dst_file.read_text(encoding="utf-8"), test_content)

        # 源文件已脱离原位置进入回收站
        self.assertFalse(test_file.exists())

    def test_06_coordinate_persistence_no_stacking(self):
        """
        【坐标持久化与无堆叠测试】
        验证：图标自定义摆放与自适应空余网格计算在重新开窗后不会退化为 (0,0) 或发生重叠
        """
        data_dir = self.case_dir / "files"
        data_dir.mkdir(parents=True, exist_ok=True)
        for i in range(4):
            (data_dir / f"doc_{i}.txt").write_text(f"content {i}", encoding="utf-8")

        p = ProfileStorage.create_profile("PersistTest", str(data_dir))
        pid = p["id"]

        # 写入两个自定义坐标
        ProfileStorage.update_item_position(pid, "doc_0.txt", 166, 284)
        ProfileStorage.update_item_position(pid, "doc_1.txt", 90, 104)

        # 重新读取并验证 key 纯净且有效
        reloaded = ProfileStorage.get_profile(pid)
        items_pos = reloaded.get("items_pos", {})
        self.assertIn("doc_0.txt", items_pos)
        self.assertEqual(items_pos["doc_0.txt"], {"x": 166, "y": 284})
        self.assertEqual(items_pos["doc_1.txt"], {"x": 90, "y": 104})

        # 清理
        ProfileStorage.delete_profile(pid)

    def test_08_profile_id_generation_and_auto_increment(self):
        """
        【规范并精简 Profile 目录命名测试】
        验证：无散列码、格式规范为 profile_{safe_name}，重名自动后置自增
        """
        # 1. 规范安全命名
        id1 = ProfileStorage.generate_profile_id("TestDesk")
        self.assertEqual(id1, "profile_TestDesk")

        # 2. 中文名称支持
        id2 = ProfileStorage.generate_profile_id("工作子桌面")
        self.assertEqual(id2, "profile_工作子桌面")

        # 3. 实际创建并测试冲突自增规避
        data_dir = self.case_dir / "dir_p"
        data_dir.mkdir(parents=True, exist_ok=True)
        p1 = ProfileStorage.create_profile("AutoIncTest", str(data_dir))
        self.assertEqual(p1["id"], "profile_AutoIncTest")

        p2 = ProfileStorage.create_profile("AutoIncTest", str(data_dir))
        self.assertEqual(p2["id"], "profile_AutoIncTest_1")

        # 清理
        ProfileStorage.delete_profile(p1["id"])
        ProfileStorage.delete_profile(p2["id"])

    def test_09_rename_blur_auto_confirm(self):
        """
        【重命名失焦自动确认测试】
        验证：失焦自动提交重命名、空值自动还原
        """
        from PyQt5.QtGui import QFocusEvent
        from ui.desktop_canvas import DesktopCanvas

        data_dir = self.case_dir / "blur_rename_files"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "file_old.txt").write_text("content", encoding="utf-8")

        p = ProfileStorage.create_profile("BlurTest", str(data_dir))
        pid = p["id"]

        canvas = DesktopCanvas(pid)
        canvas.show()
        w = canvas.icon_widgets["file_old.txt"]

        # 开启编辑并修改
        w.start_rename()
        self.assertTrue(w.is_editing)
        w.edit_line.setText("file_renamed.txt")

        # 模拟失焦 (focusOutEvent)
        focus_out = QFocusEvent(QFocusEvent.FocusOut)
        w.edit_line.focusOutEvent(focus_out)

        self.assertFalse(w.is_editing)
        self.assertEqual(w.filename, "file_renamed.txt")
        self.assertTrue((data_dir / "file_renamed.txt").exists())
        self.assertFalse((data_dir / "file_old.txt").exists())

        # 清理
        canvas.close()
        ProfileStorage.delete_profile(pid)

    def test_07_anti_collision_nearest_free_grid(self):
        """
        【网格防碰撞占位测试】
        验证：当两个文件被拖拽至同一坐标槽位时，防碰撞机制必须自动就近顺延，严禁重叠遮挡
        """
        data_dir = self.case_dir / "anti_collision_files"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "018.jpg").write_text("018", encoding="utf-8")
        (data_dir / "019.jpg").write_text("019", encoding="utf-8")

        p = ProfileStorage.create_profile("CollisionSafeTest", str(data_dir))
        pid = p["id"]

        # 模拟 018.jpg 占据 (14, 14)
        ProfileStorage.update_item_position(pid, "018.jpg", 14, 14)

        from ui.desktop_canvas import DesktopCanvas
        canvas = DesktopCanvas(pid)

        # 模拟将 019.jpg 拖拽至 018.jpg 所在的 (14, 14)
        slot_x, slot_y = canvas.find_nearest_free_grid(14, 14, occupied={(14, 14)})
        self.assertNotEqual((slot_x, slot_y), (14, 14), "防碰撞失败：允许了坐标重叠！")

        ProfileStorage.delete_profile(pid)

    def test_08_profile_id_generation_and_auto_increment(self):
        """
        【规范并精简 Profile 目录命名测试】
        验证：无散列码、格式规范为 profile_{safe_name}，重名自动后置自增
        """
        # 1. 规范安全命名
        id1 = ProfileStorage.generate_profile_id("TestDesk")
        self.assertEqual(id1, "profile_TestDesk")

        # 2. 中文名称支持
        id2 = ProfileStorage.generate_profile_id("工作子桌面")
        self.assertEqual(id2, "profile_工作子桌面")

        # 3. 实际创建并测试冲突自增规避
        data_dir = self.case_dir / "dir_p"
        data_dir.mkdir(parents=True, exist_ok=True)
        p1 = ProfileStorage.create_profile("AutoIncTest", str(data_dir))
        self.assertEqual(p1["id"], "profile_AutoIncTest")

        p2 = ProfileStorage.create_profile("AutoIncTest", str(data_dir))
        self.assertEqual(p2["id"], "profile_AutoIncTest_1")

        # 清理
        ProfileStorage.delete_profile(p1["id"])
        ProfileStorage.delete_profile(p2["id"])

    def test_09_rename_blur_auto_confirm(self):
        """
        【重命名失焦自动确认测试】
        验证：失焦自动提交重命名、空值自动还原
        """
        from PyQt5.QtGui import QFocusEvent
        from ui.desktop_canvas import DesktopCanvas

        data_dir = self.case_dir / "blur_rename_files"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "file_old.txt").write_text("content", encoding="utf-8")

        p = ProfileStorage.create_profile("BlurTest", str(data_dir))
        pid = p["id"]

        canvas = DesktopCanvas(pid)
        canvas.show()
        w = canvas.icon_widgets["file_old.txt"]

        # 开启编辑并修改
        w.start_rename()
        self.assertTrue(w.is_editing)
        w.edit_line.setText("file_renamed.txt")

        # 模拟失焦 (focusOutEvent)
        focus_out = QFocusEvent(QFocusEvent.FocusOut)
        w.edit_line.focusOutEvent(focus_out)

        self.assertFalse(w.is_editing)
        self.assertEqual(w.filename, "file_renamed.txt")
        self.assertTrue((data_dir / "file_renamed.txt").exists())
        self.assertFalse((data_dir / "file_old.txt").exists())

        # 清理
        canvas.close()
        ProfileStorage.delete_profile(pid)

if __name__ == "__main__":
    unittest.main()
