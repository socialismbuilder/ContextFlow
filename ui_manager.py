import aqt
from aqt.qt import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QScrollArea, QMessageBox
)
from .config_manager import get_config, save_config
from .basic_settings_ui import add_api_setting, add_Preferences_setting, add_othersetting, save_basic_settings, NoWheelComboBox
from .prompt_editor_ui import setup_prompt_template_tab, load_selected_prompt, delete_selected_prompt, save_custom_prompt, test_prompt_template

class ConfigDialog(QDialog):
    """配置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI例句配置")
        self.setMinimumWidth(650)
        self.setMinimumHeight(780)

        main_layout = QVBoxLayout(self)
        current_config = get_config()

        self.cached_models = [] # 缓存API返回的模型列表

        self.tab_widget = QTabWidget()

        self.basic_tab = QWidget()
        basic_layout = QVBoxLayout(self.basic_tab)

        self.prompt_tab = QWidget()
        prompt_layout = QVBoxLayout(self.prompt_tab)

        self.tab_widget.addTab(self.basic_tab, "基本设置")
        self.tab_widget.addTab(self.prompt_tab, "提示词编辑器")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.tab_widget)
        main_layout.addWidget(scroll_area)

        # --- API配置设置组 ---
        add_api_setting(self, basic_layout, current_config)

        # --- 句子生成偏好设置组 ---
        add_Preferences_setting(self, basic_layout, current_config)

        # --- 其他设置 ---
        add_othersetting(self, basic_layout, current_config)

        # --- 添加提示词编辑区域---
        setup_prompt_template_tab(self, prompt_layout, current_config)

    def save_and_close(self):
        save_basic_settings(self)
        QMessageBox.information(self, "成功", "配置已保存。")
        self.accept()

# --- 全局函数 ---
_dialog_instance = None

def show_config_dialog():
    global _dialog_instance
    parent = aqt.mw
    if _dialog_instance is None or _dialog_instance.parent() != parent:
        _dialog_instance = ConfigDialog(parent)

    _dialog_instance.show()
    _dialog_instance.raise_()
    _dialog_instance.activateWindow()

def register_menu_item():
    action = aqt.QAction("AI例句配置...", aqt.mw)
    action.triggered.connect(show_config_dialog)
    aqt.mw.form.menuTools.addAction(action)
