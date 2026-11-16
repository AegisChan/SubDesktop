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
        import core.profile_storage as ps_mod
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        if QApplication.instance() is None:
            cls.app = QApplication([""])
        cls.sandbox_dir = BASE_DIR / "test_sandbox"
        cls.sandbox_dir.mkdir(parents=True, exist_ok=True)
        # 隔离测试用 Profile 存储目录，防止污染真实 ./profiles/
        cls._orig_profiles_dir = ps_mod.PROFILES_DIR
        cls.test_profiles_dir = cls.sandbox_dir / "test_profiles"
        cls.test_profiles_dir.mkdir(parents=True, exist_ok=True)
        ps_mod.PROFILES_DIR = cls.test_profiles_dir

    @classmethod
    def tearDownClass(cls):
        import core.profile_storage as ps_mod
        ps_mod.PROFILES_DIR = cls._orig_profiles_dir
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

    def test_10_high_dpi_dialog_and_icon_dpr(self):
        """
        【高 DPI 弹窗自适应与图标 DPR 缩放测试】
        1. 验证 ProfileDialog 使用 QScrollArea 且最大高度受限、底部按钮常驻可见；
        2. 验证 ShellIconHelper 按 dpr=1.5 提取 48px 逻辑图标时生成 72x72 物理像素且 devicePixelRatio=1.5。
        """
        from PyQt5.QtWidgets import QApplication
        from core.shell_icon import ShellIconHelper
        from ui.profile_dialog import ProfileDialog

        dlg = ProfileDialog()
        self.assertTrue(hasattr(dlg, "scroll_area"))
        self.assertTrue(dlg.scroll_area.widgetResizable())
        self.assertLessEqual(dlg.minimumHeight(), 620)
        screen = QApplication.primaryScreen()
        if screen:
            avail_h = screen.availableGeometry().height()
            self.assertLessEqual(dlg.maximumHeight(), int(avail_h * 0.88) + 1)
        self.assertFalse(dlg.btn_save.isHidden())
        dlg.close()

        # 验证高 DPI 图标提取 (150% DPR = 1.5 -> 72x72 物理像素)
        sample_file = self.case_dir / "sample_dpi.txt"
        sample_file.write_text("dpi test", encoding="utf-8")
        ShellIconHelper.clear_pixmap_cache()
        pix = ShellIconHelper.get_pixmap_for_path(str(sample_file), size=48, dpr=1.5)
        self.assertFalse(pix.isNull())
        self.assertEqual(pix.width(), 72)
        self.assertEqual(pix.height(), 72)
        self.assertAlmostEqual(pix.devicePixelRatio(), 1.5, places=2)

    def test_11_context_menu_change_icon_size(self):
        """
        【右键切换图标尺寸实时闭环测试】
        验证：点击大图标/小图标后，Profile 配置保存、画布网格尺寸、已存在控件尺寸同步实时更新
        """
        from ui.desktop_canvas import DesktopCanvas
        from core.config import ICON_SIZE_CONFIG

        data_dir = self.case_dir / "icon_size_switch"
        data_dir.mkdir(parents=True, exist_ok=True)
        for i in range(6):
            (data_dir / f"item{i}.txt").write_text(str(i), encoding="utf-8")

        p = ProfileStorage.create_profile("IconSizeTest", str(data_dir), width=900, height=600)
        pid = p["id"]

        canvas = DesktopCanvas(pid)
        canvas.resize(900, 600)
        canvas.show()

        w1 = canvas.icon_widgets["item0.txt"]
        self.assertEqual(w1.icon_size_mode, "medium")
        self.assertEqual(w1.icon_pixel, ICON_SIZE_CONFIG["medium"]["icon"])

        # 切换为大图标，验证所有 6 个图标两两不重叠且完全在视窗边界内
        canvas._change_icon_size("large")
        self.assertEqual(canvas.icon_size_mode, "large")
        self.assertEqual(w1.icon_size_mode, "large")
        self.assertEqual(w1.icon_pixel, ICON_SIZE_CONFIG["large"]["icon"])
        self.assertEqual(w1.width(), ICON_SIZE_CONFIG["large"]["cell_w"])
        self.assertEqual(w1.height(), ICON_SIZE_CONFIG["large"]["cell_h"])

        large_coords = [(w.x(), w.y()) for w in canvas.icon_widgets.values()]
        self.assertEqual(len(large_coords), len(set(large_coords)), "切换大图标后出现图标重叠！")
        for wx, wy in large_coords:
            self.assertGreaterEqual(wx, canvas.margin_x)
            self.assertGreaterEqual(wy, canvas.margin_y)
            self.assertLessEqual(wx + ICON_SIZE_CONFIG["large"]["cell_w"], canvas.width())
            self.assertLessEqual(wy + ICON_SIZE_CONFIG["large"]["cell_h"], canvas.height())

        saved_large = ProfileStorage.get_profile(pid)
        self.assertEqual(saved_large["icon_size"], "large")

        # 切换为小图标
        canvas._change_icon_size("small")
        self.assertEqual(canvas.icon_size_mode, "small")
        self.assertEqual(w1.icon_size_mode, "small")
        self.assertEqual(w1.icon_pixel, ICON_SIZE_CONFIG["small"]["icon"])
        self.assertEqual(w1.width(), ICON_SIZE_CONFIG["small"]["cell_w"])
        self.assertEqual(w1.height(), ICON_SIZE_CONFIG["small"]["cell_h"])

        saved_small = ProfileStorage.get_profile(pid)
        self.assertEqual(saved_small["icon_size"], "small")

        canvas.close()
        ProfileStorage.delete_profile(pid)

    def test_12_window_dpi_scaling_and_screen_clamp(self):
        """
        【子桌面视窗高 DPI 尺寸换算与屏幕边界自动居中钳制测试】
        验证：即使保存的坐标越界（如 x=-100, y=5000），打开时也能自动钳制在可用屏幕 92% 内并居中显示
        """
        from PyQt5.QtWidgets import QApplication
        from ui.desktop_window import SubDesktopWindow

        data_dir = self.case_dir / "win_clamp"
        data_dir.mkdir(parents=True, exist_ok=True)

        p = ProfileStorage.create_profile("ClampTest", str(data_dir), width=960, height=540)
        pid = p["id"]
        # 写入一个越界的坐标（模拟之前测试遗留的 -73 越界场景）
        ProfileStorage.update_window_rect(pid, -100, 5000, 960, 540)

        win = SubDesktopWindow(pid)
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.assertLessEqual(win.width(), avail.width())
            self.assertLessEqual(win.height(), avail.height())
            self.assertGreaterEqual(win.x(), avail.left())
            self.assertGreaterEqual(win.y(), avail.top())
            self.assertLessEqual(win.x() + win.width(), avail.right() + 1)
            self.assertLessEqual(win.y() + win.height(), avail.bottom() + 1)
        win.close()
        ProfileStorage.delete_profile(pid)

    def test_13_preset_resolution_locked_on_resize_and_close(self):
        """
        【锁定预设分辨率测试】
        验证：用户在运行期临时拖拽改变子桌面大小并关闭窗口后，
        Profile 中保存的预设 width/height 绝对不会被覆盖；下次重新打开仍严格恢复预设尺寸。
        """
        from ui.desktop_window import SubDesktopWindow

        data_dir = self.case_dir / "locked_res"
        data_dir.mkdir(parents=True, exist_ok=True)

        p = ProfileStorage.create_profile("LockedResTest", str(data_dir), width=800, height=480)
        pid = p["id"]

        win = SubDesktopWindow(pid)
        win.show()
        self.assertEqual(win.width(), 800)
        self.assertEqual(win.height(), 480)

        # 模拟用户临时拖拽放大窗口并关闭
        win.resize(1100, 650)
        win.close()

        saved = ProfileStorage.get_profile(pid)
        self.assertEqual(saved["window_rect"]["width"], 800, "预设宽度被临时拖拽改写！")
        self.assertEqual(saved["window_rect"]["height"], 480, "预设高度被临时拖拽改写！")

        # 重新打开必须恢复 800x480
        win2 = SubDesktopWindow(pid)
        self.assertEqual(win2.width(), 800)
        self.assertEqual(win2.height(), 480)
        win2.close()
        ProfileStorage.delete_profile(pid)

    def test_14_physical_pixel_1to1_under_dpr_150(self):
        """
        【物理像素 1:1 渲染（dpr = 1.5 模拟环境）验证测试】
        验证：
        1. 960x540 子桌面在 dpr=1.5 下逻辑窗口严格为 640x360（物理尺寸 960x540）；
        2. 中等图标逻辑像素 32x32、贴图物理像素 48x48 (dpr=1.5)、字体 pixelSize=8；
        3. 20 个图标全部完整落在可视区域内、两两不重叠且无任何溢出；
        4. 保存物理坐标后，切换回 dpr=1.0 仍能 1:1 完整对齐。
        """
        from ui.desktop_window import SubDesktopWindow

        data_dir = self.case_dir / "dpr_150_files"
        data_dir.mkdir(parents=True, exist_ok=True)
        for i in range(20):
            (data_dir / f"doc_{i:02d}.txt").write_text(str(i), encoding="utf-8")

        p = ProfileStorage.create_profile("Dpr150Test", str(data_dir), width=960, height=540)
        pid = p["id"]

        # 模拟 150% 高 DPI 环境
        win_150 = SubDesktopWindow(pid, dpr_override=1.5)
        win_150.show()

        # 1. 验证逻辑窗口 640x360 -> 物理 960x540
        self.assertEqual(win_150.width(), 640)
        self.assertEqual(win_150.height(), 360)
        self.assertEqual(round(win_150.width() * 1.5), 960)
        self.assertEqual(round(win_150.height() * 1.5), 540)

        canvas = win_150.canvas
        self.assertEqual(len(canvas.icon_widgets), 20)

        # 2. 验证图标、单元格、字体与贴图 DPR 精确换算
        sample_w = canvas.icon_widgets["doc_00.txt"]
        self.assertEqual(sample_w.icon_pixel, 32)
        self.assertEqual(sample_w.text_label.font().pixelSize(), 8)
        pix = sample_w.icon_label.pixmap()
        self.assertIsNotNone(pix)
        self.assertEqual(pix.width(), 48)
        self.assertEqual(pix.height(), 48)
        self.assertAlmostEqual(pix.devicePixelRatio(), 1.5, places=2)

        # 3. 验证所有 20 个图标完整落在 640x360 可视区域内且互不重叠
        coords = []
        for w in canvas.icon_widgets.values():
            coords.append((w.x(), w.y()))
            self.assertGreaterEqual(w.x(), 0)
            self.assertGreaterEqual(w.y(), 0)
            self.assertLessEqual(w.x() + w.width(), win_150.width())
            self.assertLessEqual(w.y() + w.height(), win_150.height())
        self.assertEqual(len(coords), len(set(coords)))

        win_150.close()

        # 4. 切换回 100% (dpr=1.0) 打开同一个子桌面，验证物理尺寸与图标无溢出
        win_100 = SubDesktopWindow(pid, dpr_override=1.0)
        # 在 offscreen (800x600) 下宽度钳制为 800，高度 540 完整保留
        self.assertEqual(win_100.height(), 540)
        for w in win_100.canvas.icon_widgets.values():
            self.assertLessEqual(w.x() + w.width(), win_100.width())
            self.assertLessEqual(w.y() + w.height(), win_100.height())
        win_100.close()

        ProfileStorage.delete_profile(pid)

    def test_15_dynamic_runtime_dpr_change(self):
        """
        【运行期动态 DPR 切换（1.0 -> 1.5 -> 1.2）实时重算测试】
        验证：窗口不关闭重启时动态调整 DPR，窗口物理宽高与图标物理像素始终保持恒定。
        """
        from ui.desktop_window import SubDesktopWindow

        data_dir = self.case_dir / "dyn_dpr"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "alpha.txt").write_text("a", encoding="utf-8")
        (data_dir / "beta.txt").write_text("b", encoding="utf-8")

        p = ProfileStorage.create_profile("DynDprTest", str(data_dir), width=800, height=480)
        pid = p["id"]

        win = SubDesktopWindow(pid, dpr_override=1.0)
        win.show()
        self.assertEqual((win.width(), win.height()), (800, 480))
        w_alpha = win.canvas.icon_widgets["alpha.txt"]
        self.assertEqual(w_alpha.icon_pixel, 48)
        self.assertEqual(w_alpha.text_label.font().pixelSize(), 12)

        # 动态切换为 150% (dpr=1.5)
        win.apply_physical_metrics(new_dpr=1.5)
        self.assertEqual((win.width(), win.height()), (533, 320))
        self.assertEqual(w_alpha.icon_pixel, 32)
        self.assertEqual(w_alpha.text_label.font().pixelSize(), 8)
        pix_15 = w_alpha.icon_label.pixmap()
        self.assertEqual((pix_15.width(), pix_15.height()), (48, 48))
        self.assertAlmostEqual(pix_15.devicePixelRatio(), 1.5, places=2)

        # 动态切换为 120% (dpr=1.2)
        win.apply_physical_metrics(new_dpr=1.2)
        self.assertEqual((win.width(), win.height()), (667, 400))
        self.assertEqual(w_alpha.icon_pixel, 40)
        self.assertEqual(w_alpha.text_label.font().pixelSize(), 10)
        pix_12 = w_alpha.icon_label.pixmap()
        self.assertEqual((pix_12.width(), pix_12.height()), (48, 48))
        self.assertAlmostEqual(pix_12.devicePixelRatio(), 1.2, places=2)

        win.close()
        ProfileStorage.delete_profile(pid)

    def test_16_lazy_anti_collision_preserves_non_overlapping_positions(self):
        """
        【切换图标大小禁止全局洗牌（局部防重叠微调）测试】
        验证：互不重叠且在边界内的图标保留原有相对网格位置不变，仅对冲突项局部顺延。
        """
        from ui.desktop_canvas import DesktopCanvas

        data_dir = self.case_dir / "lazy_anticoll"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "far_right.txt").write_text("1", encoding="utf-8")
        (data_dir / "c1.txt").write_text("2", encoding="utf-8")
        (data_dir / "c2.txt").write_text("3", encoding="utf-8")

        p = ProfileStorage.create_profile("LazyTest", str(data_dir), width=900, height=600)
        pid = p["id"]
        # far_right 放在远处独立格 (col=4, row=2 -> 14+4*92=382, 14+2*98=210)
        # c1 与 c2 故意设为非常接近，在切换到 large (112x120) 时会吸附到同一个格导致冲突
        ProfileStorage.update_item_position(pid, "far_right.txt", 462, 254)
        ProfileStorage.update_item_position(pid, "c1.txt", 14, 14)
        ProfileStorage.update_item_position(pid, "c2.txt", 40, 20)

        canvas = DesktopCanvas(pid, dpr_override=1.0)
        canvas.resize(900, 600)
        canvas.show()

        # 切换到大图标 (112x120)
        canvas._change_icon_size("large")

        w_far = canvas.icon_widgets["far_right.txt"]
        w_c1 = canvas.icon_widgets["c1.txt"]
        w_c2 = canvas.icon_widgets["c2.txt"]

        # far_right 原本 (462, 254) 就近吸附到大图标网格 col=round((462-14)/112)=4 -> 462, row=round((254-14)/120)=2 -> 254，原封不动保留！
        self.assertEqual((w_far.x(), w_far.y()), (462, 254))
        # c1 与 c2 均已解开碰撞，两两不重叠
        coords = {(w_far.x(), w_far.y()), (w_c1.x(), w_c1.y()), (w_c2.x(), w_c2.y())}
        self.assertEqual(len(coords), 3)

        canvas.close()
        ProfileStorage.delete_profile(pid)

    def test_17_clamp_window_to_screen_prevents_titlebar_overflow(self):
        """
        【窗口屏幕边界安全保护测试】
        验证：无论初始化或运行时移动到负坐标 (y=-120) 还是右下越界 (4000, 3000)，
        clamp_window_to_screen() 均严格将窗口钳制在 availableGeometry() 内，绝不让顶部标题栏跑出屏幕。
        """
        from PyQt5.QtWidgets import QApplication
        from ui.desktop_window import SubDesktopWindow

        data_dir = self.case_dir / "clamp_titlebar"
        data_dir.mkdir(parents=True, exist_ok=True)
        p = ProfileStorage.create_profile("ClampTitleTest", str(data_dir), width=640, height=400)
        pid = p["id"]

        win = SubDesktopWindow(pid, dpr_override=1.0)
        win.show()

        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry()

        # 模拟顶部标题栏跑出屏幕上边缘 (y=-120) 及左侧越界 (-80)
        win.move(-80, -120)
        win.clamp_window_to_screen()
        fg = win.frameGeometry()
        self.assertGreaterEqual(fg.left(), avail.left())
        self.assertGreaterEqual(fg.top(), avail.top())

        # 模拟右下角越界
        win.move(4000, 3000)
        win.clamp_window_to_screen()
        fg2 = win.frameGeometry()
        self.assertLessEqual(fg2.right(), avail.right())
        self.assertLessEqual(fg2.bottom(), avail.bottom())

        # 关闭后保存的坐标也不得越界
        win.close()
        saved = ProfileStorage.get_profile(pid)
        self.assertGreaterEqual(saved["window_rect"]["y"], avail.top())

        ProfileStorage.delete_profile(pid)

    def test_18_small_icon_two_line_label_no_clipping(self):
        """
        【小图标双行文件名完整展示测试】
        验证：small 模式下文本区域净高度 >= 36/dpr（物理>=36px）且控件总物理高度 >= 86px，
        两行文件名不被底部截断。
        """
        from core.config import ICON_SIZE_CONFIG
        from ui.desktop_canvas import DesktopCanvas

        self.assertGreaterEqual(ICON_SIZE_CONFIG["small"]["cell_h"], 86)

        data_dir = self.case_dir / "small_two_line"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "新建文件夹 (2)").mkdir(parents=True, exist_ok=True)

        p = ProfileStorage.create_profile("SmallLabelTest", str(data_dir), icon_size="small")
        pid = p["id"]

        for dpr in (1.0, 1.5):
            canvas = DesktopCanvas(pid, dpr_override=dpr)
            canvas.resize(600, 400)
            canvas.show()
            w = canvas.icon_widgets["新建文件夹 (2)"]

            # 1. 验证文本净高度 >= int(round(36 / dpr))
            self.assertGreaterEqual(w.text_label.minimumHeight(), int(round(36 / dpr)))
            # 2. 验证物理总高度 >= 86px
            self.assertGreaterEqual(round(w.height() * dpr), 86)

            # 3. 验证两行文本渲染所需高度 + 图标 + 边距 <= 单元格总高度
            margins = w.main_layout.contentsMargins()
            spacing = w.main_layout.spacing()
            text_h = w.text_label.heightForWidth(w.cell_w - margins.left() - margins.right())
            if text_h <= 0:
                text_h = w.text_label.sizeHint().height()
            required_h = margins.top() + w.icon_pixel + spacing + max(text_h, w.text_label.minimumHeight()) + margins.bottom()
            self.assertLessEqual(required_h, w.height(), f"dpr={dpr} 时 small 模式高度不足以容纳两行文字！")
            canvas.close()

        ProfileStorage.delete_profile(pid)

if __name__ == "__main__":
    unittest.main()
