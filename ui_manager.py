import time # 用于超时控制
import traceback # 用于打印更详细的错误信息
import os
import json

import aqt
from aqt.qt import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QGroupBox, QHBoxLayout, QWidget, QDialogButtonBox, QMessageBox, QApplication,
    QTabWidget, QTextEdit, QSplitter, Qt,QGridLayout
)
from .config_manager import get_config, save_config # 使用相对导入
from .cache_manager import clear_cache
from . import api_client # 导入 api_client 以便调用测试函数


class ConfigDialog(QDialog):
    """配置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI例句配置")
        #self.setMinimumWidth(650) # 增加宽度以容纳提示词模板编辑区域
        #self.setMinimumHeight(600) #高度自适应，不做限制

        main_layout = QVBoxLayout(self)
        current_config = get_config()

        # 创建选项卡控件
        self.tab_widget = QTabWidget()

        # 创建基本设置选项卡
        self.basic_tab = QWidget()
        basic_layout = QVBoxLayout(self.basic_tab)

        # 创建提示词模板选项卡
        self.prompt_tab = QWidget()
        prompt_layout = QVBoxLayout(self.prompt_tab)

        # 添加选项卡到选项卡控件
        self.tab_widget.addTab(self.basic_tab, "基本设置")
        self.tab_widget.addTab(self.prompt_tab, "提示词模板")

        # 将选项卡控件添加到主布局
        main_layout.addWidget(self.tab_widget)
        

        # --- API配置设置组 ---
        self.add_api_setting(basic_layout,current_config)

        # --- 句子生成偏好设置组 ---
        self.add_Preferences_setting(basic_layout,current_config)

        # --- 其他设置 ---
        self.add_othersetting(basic_layout,current_config)

        # --- 添加提示词模板编辑区域---
        self.setup_prompt_template_tab(prompt_layout, current_config)



        # --- 保存取消按钮 ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.save_and_close)
        self.button_box.rejected.connect(self.reject)
        button_layout = QHBoxLayout() # 水平布局放按钮
        button_layout.addWidget(self.button_box)
        main_layout.addLayout(button_layout)


    def add_api_setting(self,basic_layout,current_config):
        api_group = QGroupBox("API 设置")
        api_layout = QFormLayout()
        # 添加API设置组件

        #api供应商与url组件
        PRESET_API_URLS = current_config.get("preset_api_urls")
        self.api_provider_combo = QComboBox()
        self.api_provider_combo.addItems(PRESET_API_URLS.keys())
        api_layout.addRow("API 提供商:", self.api_provider_combo)

        self.api_url = QLineEdit() # 初始化时不清空，由 _on_api_provider_changed 处理
        api_layout.addRow("API 接口地址:", self.api_url)

        # 初始化 API Provider 和 URL
        saved_api_url = current_config.get("api_url", "")
        provider_match = False
        for provider, url in PRESET_API_URLS.items():
            if url == saved_api_url and provider != "自定义":
                self.api_provider_combo.setCurrentText(provider)
                provider_match = True
                break
        if not provider_match and saved_api_url: # 如果URL存在但不在预设中，则认为是自定义
            self.api_provider_combo.setCurrentText("自定义")
        elif not saved_api_url and "火山/豆包/字节（推荐）" in PRESET_API_URLS: # 默认选择OpenAI如果配置为空
             self.api_provider_combo.setCurrentText("火山/豆包/字节（推荐）")

        self._on_api_provider_changed() # 根据 combo 初始化 URL 状态
        self.api_url.setText(saved_api_url) # 确保加载已保存的URL，即使是自定义的
        self.api_provider_combo.currentTextChanged.connect(self._on_api_provider_changed)

        #API密钥填写框
        self.api_key = QLineEdit(current_config.get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("API 密钥:", self.api_key)

        #模型名称填写框
        self.model_name = QLineEdit(current_config.get("model_name", ""))
        api_layout.addRow("模型名称:", self.model_name)

        #测试连接按钮
        self.test_connection_button = QPushButton("测试 API 连接")
        self.test_connection_button.clicked.connect(self._test_api_connection)
        self.test_status_label = QLabel("点击按钮测试连接状态")
        self.test_status_label.setWordWrap(True)

        #文本框
        test_layout = QHBoxLayout()
        test_layout.addWidget(self.test_connection_button)
        test_layout.addWidget(self.test_status_label)
        api_layout.addRow(test_layout) # 将按钮和标签添加到表单布局的一行

        # 设置组件生效
        api_group.setLayout(api_layout)
        basic_layout.addWidget(api_group)

    def add_Preferences_setting(self,basic_layout,current_config):
        prefs_group = QGroupBox("句子生成偏好")
        prefs_layout = QFormLayout()

        # 词汇量等级选择
        self.vocab_level_combo = QComboBox()

        PRESET_VOCAB_LEVELS = current_config.get("preset_vocab_levels")
        self.vocab_level_combo.addItems(PRESET_VOCAB_LEVELS)
        current_vocab = current_config.get("vocab_level", "大学英语四级 CET-4 (4000词)")
        self.vocab_level_custom = None # 初始化为 None
        if current_vocab not in PRESET_VOCAB_LEVELS[:-1]:
            self.vocab_level_combo.setCurrentText("自定义")
            self.vocab_level_custom = QLineEdit(current_vocab)
        else:
            self.vocab_level_combo.setCurrentText(current_vocab)
        prefs_layout.addRow("词汇量等级:", self.vocab_level_combo)
        if self.vocab_level_custom:
            prefs_layout.addRow("", self.vocab_level_custom) # 自定义输入框放在下一行
        self.vocab_level_combo.currentIndexChanged.connect(self.on_vocab_level_changed)
        self._toggle_custom_widget(self.vocab_level_combo, self.vocab_level_custom, prefs_layout) # 初始化可见性

        # 学习目标选择
        self.learning_goal_combo = QComboBox()

        PRESET_LEARNING_GOALS = current_config.get("preset_learning_goals")
        self.learning_goal_combo.addItems(PRESET_LEARNING_GOALS)
        current_goal = current_config.get("learning_goal", "提升日常浏览英文网页与资料的流畅度")
        self.learning_goal_custom = None
        if current_goal not in PRESET_LEARNING_GOALS[:-1]:
            self.learning_goal_combo.setCurrentText("自定义")
            self.learning_goal_custom = QLineEdit(current_goal)
        else:
            self.learning_goal_combo.setCurrentText(current_goal)
        prefs_layout.addRow("学习目标:", self.learning_goal_combo)
        if self.learning_goal_custom:
            prefs_layout.addRow("", self.learning_goal_custom)
        self.learning_goal_combo.currentIndexChanged.connect(self.on_learning_goal_changed)
        self._toggle_custom_widget(self.learning_goal_combo, self.learning_goal_custom, prefs_layout)

        # 句子难度选择
        self.difficulty_combo = QComboBox()


        PRESET_DIFFICULTIES = current_config.get("preset_difficulties")
        self.difficulty_combo.addItems(PRESET_DIFFICULTIES)
        current_diff = current_config.get("difficulty_level", "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围") # 修正默认值以匹配列表
        self.difficulty_custom = None
        if current_diff not in PRESET_DIFFICULTIES[:-1]:
            self.difficulty_combo.setCurrentText("自定义")
            self.difficulty_custom = QLineEdit(current_diff)
        else:
            self.difficulty_combo.setCurrentText(current_diff)
        prefs_layout.addRow("句子难度:", self.difficulty_combo)
        if self.difficulty_custom:
            prefs_layout.addRow("", self.difficulty_custom)
        self.difficulty_combo.currentIndexChanged.connect(self.on_difficulty_changed)
        self._toggle_custom_widget(self.difficulty_combo, self.difficulty_custom, prefs_layout)


        PRESET_LENGTHS = current_config.get("preset_lengths")
        self.length_combo = QComboBox()
        self.length_combo.addItems(PRESET_LENGTHS)
        current_length = current_config.get("sentence_length_desc", "中等长度句 (约25-40词): 通用对话及文章常用长度") # 修正默认值
        self.length_custom = None
        if current_length not in PRESET_LENGTHS[:-1]:
            self.length_combo.setCurrentText("自定义")
            self.length_custom = QLineEdit(current_length)
        else:
            self.length_combo.setCurrentText(current_length)
        prefs_layout.addRow("句子长度:", self.length_combo)
        if self.length_custom:
            prefs_layout.addRow("", self.length_custom)
        self.length_combo.currentIndexChanged.connect(self.on_length_changed)
        self._toggle_custom_widget(self.length_combo, self.length_custom, prefs_layout)

        prefs_group.setLayout(prefs_layout)
        basic_layout.addWidget(prefs_group)

    def add_othersetting(self,basic_layout,current_config):
        other_group = QGroupBox("其他")
        other_layout = QFormLayout()

        self.deck_name = QLineEdit(current_config.get("deck_name", ""))
        other_layout.addRow("目标牌组名称:", self.deck_name)

        # 学习语言下拉选框
        self.learning_language_combo = QComboBox()
        # 常见语言列表，可以根据需要扩展
        languages = ["英语", "法语", "日语", "西班牙语", "德语", "韩语", "俄语", "意大利语", "葡萄牙语", "阿拉伯语", "印地语"]
        self.learning_language_combo.addItems(languages)
        saved_language = current_config.get("learning_language", "英语")
        if saved_language in languages:
            self.learning_language_combo.setCurrentText(saved_language)
        else: # 如果保存的语言不在列表中，默认选择英语
            self.learning_language_combo.setCurrentText("英语")

        # 是否标出目标词下拉选框
        self.highlight_target_word_combo = QComboBox()
        self.highlight_target_word_combo.addItems(["否", "是"]) # 存储时 "是" -> True, "否" -> False
        saved_highlight = current_config.get("highlight_target_word", False) # 默认为 False
        self.highlight_target_word_combo.setCurrentText("是" if saved_highlight else "否")

        # 创建一个水平布局来放置这两个下拉框
        learning_options_layout = QHBoxLayout()
        learning_options_layout.addWidget(QLabel("学习语言:")) # 添加标签
        learning_options_layout.addWidget(self.learning_language_combo)
        learning_options_layout.addSpacing(20) # 添加一些间距
        learning_options_layout.addWidget(QLabel("标出目标词:")) # 添加标签
        learning_options_layout.addWidget(self.highlight_target_word_combo)
        learning_options_layout.addStretch() # 确保控件靠左

        # 将水平布局添加到表单布局中
        # QFormLayout 通常期望一个标签和一个字段。为了将 QHBoxLayout 作为“字段”部分，
        # 我们可以直接添加它，或者如果需要一个总标签，可以这样做：
        # other_layout.addRow("学习选项:", learning_options_layout)
        # 但如果希望这两个控件在同一行且 QFormLayout 的标签栏为空或用于其他目的，
        # 我们可以将 QHBoxLayout 添加到一个 QWidget 中，然后将该 QWidget 添加。
        # 或者，更简单地，如果 QFormLayout 的该行不需要左侧标签，可以直接添加布局。
        # 但为了保持 QFormLayout 的结构，我们还是给它一个总的标签。
        other_layout.addRow("学习选项:", learning_options_layout)


        other_group.setLayout(other_layout)
        basic_layout.addWidget(other_group)

        # 删除缓存按钮
        del_cache_btn = QPushButton("删除缓存")
        del_cache_btn.clicked.connect(self.clear_cache_and_notify)
        button_layout = QHBoxLayout() # 水平布局放按钮
        button_layout.addWidget(del_cache_btn)
        button_layout.addStretch() # 推到右边
        basic_layout.addLayout(button_layout) # 添加按钮布局

    def setup_prompt_template_tab(self, layout, config):
        """设置提示词模板编辑选项卡"""
        # 提示词模板编辑区域
        prompt_group = QGroupBox("提示词编辑")
        prompt_layout = QVBoxLayout()

        # 提示词模板说明
        help_label = QLabel("提示词模板用于生成AI例句。可以使用以下占位符：")
        help_label.setWordWrap(True)
        prompt_layout.addWidget(help_label)

        grid_layout  = QGridLayout()
        grid_layout.addWidget(QLabel("{world}:关键词"),0,0)
        grid_layout.addWidget(QLabel("{language}:学习语言"),0,1)
        grid_layout.addWidget(QLabel("{vocab_level}:词汇量等级"),0,2)

        grid_layout.addWidget(QLabel("{learning_goal}:学习目标"),1,0)
        grid_layout.addWidget(QLabel("{difficulty_level}:句子难度"),1,1)
        grid_layout.addWidget(QLabel("{sentence_length_desc}:句子长度"),1,2)

        prompt_layout.addLayout(grid_layout)

        # 主提示词模板编辑区
        edit_prompt_layout = QHBoxLayout()
        edit_prompt = QLabel("提示词编辑:")
        edit_prompt_layout.addWidget(edit_prompt)

        # 提示词来源选择框（含存储的提示词）
        self.prompt_source_combo = QComboBox()
        current_config = get_config()
        custom_prompts = current_config.get("custom_prompts", {})
        self.prompt_source_combo.addItems(["默认-不标记目标词", "默认-标记目标词", "空"] + list(custom_prompts.keys()))
        edit_prompt_layout.addWidget(self.prompt_source_combo)

        # 删除存储提示词按钮
        self.delete_prompt_btn = QPushButton("删除")
        self.delete_prompt_btn.clicked.connect(self.delete_selected_prompt)
        edit_prompt_layout.addWidget(self.delete_prompt_btn)
        prompt_layout.addLayout(edit_prompt_layout)

        self.prompt_template_edit = QTextEdit()
        self.prompt_template_edit.setMinimumHeight(200)
        prompt_layout.addWidget(self.prompt_template_edit)

        # 存储名输入框和保存按钮
        save_layout = QHBoxLayout()
        save_layout.addWidget(QLabel("存储名:"))
        self.prompt_name_edit = QLineEdit()
        save_layout.addWidget(self.prompt_name_edit)
        self.save_prompt_btn = QPushButton("保存")
        self.save_prompt_btn.clicked.connect(self.save_custom_prompt)
        save_layout.addWidget(self.save_prompt_btn)
        prompt_layout.addLayout(save_layout)

        # 初始化提示词内容
        self.prompt_source_combo.currentTextChanged.connect(self.load_selected_prompt)
        self.load_selected_prompt(self.prompt_source_combo.currentText())

        # 测试区域（保持原有逻辑）
        test_group = QGroupBox("提示词测试")
        test_layout = QVBoxLayout()
        test_input_layout = QHBoxLayout()
        keyword_layout = QVBoxLayout()
        keyword_label = QLabel("测试关键词:")
        keyword_layout.addWidget(keyword_label)
        self.test_keyword_edit = QLineEdit()
        self.test_keyword_edit.setText("example")
        keyword_layout.addWidget(self.test_keyword_edit)
        test_mode_layout = QHBoxLayout()
        test_mode_label = QLabel("测试模式:")
        test_mode_layout.addWidget(test_mode_label)
        self.test_mode_combo = QComboBox()
        self.test_mode_combo.addItems(["生成例句", "查看提示词"])
        test_mode_layout.addWidget(self.test_mode_combo)
        keyword_layout.addLayout(test_mode_layout)
        self.test_prompt_button = QPushButton("测试")
        self.test_prompt_button.clicked.connect(self.test_prompt_template)
        keyword_layout.addWidget(self.test_prompt_button)
        test_input_layout.addLayout(keyword_layout)
        test_result_label = QLabel("测试结果:")
        test_layout.addWidget(test_result_label)
        self.test_result_edit = QTextEdit()
        self.test_result_edit.setReadOnly(True)
        self.test_result_edit.setMinimumHeight(150)
        test_layout.addWidget(self.test_result_edit)
        test_layout.addLayout(test_input_layout)
        test_group.setLayout(test_layout)
        prompt_group.setLayout(prompt_layout)
        layout.addWidget(prompt_group)
        layout.addWidget(test_group)

    def load_selected_prompt(self, source):
        """根据选择的提示词来源加载内容到编辑框，并设置存储名输入框"""
        config = get_config()
        custom_prompts = config.get("custom_prompts", {})
        
        if source == "默认-不标记目标词":
            content = api_client.DEFAULT_PROMPT_TEMPLATE + api_client.DEFAULT_FORMAT_NORMAL
            self.prompt_name_edit.setText("自定义提示词")
        elif source == "默认-标记目标词":
            content = api_client.DEFAULT_PROMPT_TEMPLATE + api_client.DEFAULT_FORMAT_HIGHLIGHT
            self.prompt_name_edit.setText("自定义提示词")
        elif source == "空":
            content = ""
            self.prompt_name_edit.setText("空")
        else:  # 存储的提示词
            content = custom_prompts.get(source, "")
            self.prompt_name_edit.setText(source)
        
        self.prompt_template_edit.setPlainText(content)

    def delete_selected_prompt(self):
        """删除选中的存储提示词"""
        selected = self.prompt_source_combo.currentText()
        
        # 检查是否为不可删除项
        if selected in ["默认-不标记目标词", "默认-标记目标词", "空"]:
            QMessageBox.warning(self, "错误", f"不能删除 {selected} 提示词")
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除提示词 '{selected}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 执行删除
        config = get_config()
        custom_prompts = config.get("custom_prompts", {})
        if selected in custom_prompts:
            del custom_prompts[selected]
            config["custom_prompts"] = custom_prompts
            save_config(config)
            
            # 更新选择框
            self.prompt_source_combo.removeItem(self.prompt_source_combo.findText(selected))
            self.prompt_source_combo.setCurrentText("默认-不标记目标词")
            self.load_selected_prompt("默认-不标记目标词")
            QMessageBox.information(self, "成功", "提示词删除完成")
        else:
            QMessageBox.warning(self, "错误", "未找到该存储提示词")

    def save_custom_prompt(self):
        """保存自定义提示词"""
        prompt_name = self.prompt_name_edit.text().strip()
        prompt_content = self.prompt_template_edit.toPlainText()
        
        # 校验名称
        if not prompt_name:
            QMessageBox.warning(self, "错误", "存储名不能为空")
            return
            
        # 处理默认名称冲突
        if prompt_name in ["默认-不标记目标词", "默认-标记目标词"]:
            prompt_name = "自定义提示词"
            self.prompt_name_edit.setText(prompt_name)
        
        # 保存到配置
        config = get_config()
        custom_prompts = config.get("custom_prompts", {})
        custom_prompts[prompt_name] = prompt_content
        config["custom_prompts"] = custom_prompts
        save_config(config)
        
        # 更新选择框
        current_items = ["默认-不标记目标词", "默认-标记目标词", "空"] + list(custom_prompts.keys())
        self.prompt_source_combo.clear()
        self.prompt_source_combo.addItems(current_items)
        self.prompt_source_combo.setCurrentText(prompt_name)
        self.load_selected_prompt(prompt_name)
        QMessageBox.information(self, "成功", "提示词保存完成")

    def test_prompt_template(self):
        """测试提示词模板"""
        keyword = self.test_keyword_edit.text()
        if not keyword:
            self.test_result_edit.setText("请输入测试关键词")
            return

        # 获取当前编辑的提示词模板
        prompt_template = self.prompt_template_edit.toPlainText()
        normal_format = self.normal_format_edit.toPlainText()
        highlight_format = self.highlight_format_edit.toPlainText()

        # 获取当前配置
        config = get_config()

        # 创建临时配置用于测试
        test_config = {
            "api_url": config.get("api_url", ""),
            "api_key": config.get("api_key", ""),
            "model_name": config.get("model_name", ""),
            "vocab_level": config.get("vocab_level", "大学英语四级 CET-4 (4000词)"),
            "learning_goal": config.get("learning_goal", "提升日常浏览英文网页与资料的流畅度"),
            "difficulty_level": config.get("difficulty_level", "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围"),
            "sentence_length_desc": config.get("sentence_length_desc", "中等长度句 (约25-40词): 通用对话及文章常用长度"),
            "learning_language": config.get("learning_language", "英语"),
            "highlight_target_word": config.get("highlight_target_word", False),
            "prompt_template": prompt_template,
            "prompt_format_normal": normal_format,
            "prompt_format_highlight": highlight_format
        }

        # 获取测试模式
        test_mode = self.test_mode_combo.currentText()

        # 如果是查看提示词模式
        if test_mode == "查看提示词":
            try:
                # 根据是否高亮目标词选择不同的格式示例
                if test_config["highlight_target_word"]:
                    prompt = prompt_template + highlight_format
                else:
                    prompt = prompt_template + normal_format

                # 格式化提示词
                formatted_prompt = prompt.format(
                    world=keyword,
                    vocab_level=test_config["vocab_level"],
                    learning_goal=test_config["learning_goal"],
                    difficulty_level=test_config["difficulty_level"],
                    sentence_length_desc=test_config["sentence_length_desc"],
                    language=test_config["learning_language"]
                )

                # 显示格式化后的提示词
                self.test_result_edit.setText(formatted_prompt)
            except Exception as e:
                self.test_result_edit.setText(f"提示词格式化错误: {str(e)}")
            return

        # 如果是生成例句模式，需要检查API配置
        if not test_config["api_url"] or not test_config["api_key"] or not test_config["model_name"]:
            self.test_result_edit.setText("错误: 请先在基本设置中配置API信息（URL、密钥和模型名称）")
            return

        # 显示正在测试的提示
        self.test_result_edit.setText("正在生成例句，请稍候...")
        self.test_prompt_button.setEnabled(False)
        QApplication.processEvents() # 确保UI更新

        try:
            # 调用API生成例句
            sentence_pairs = api_client.generate_ai_sentence(test_config, keyword)

            if not sentence_pairs:
                self.test_result_edit.setText("未能生成例句，请检查API配置和提示词模板")
                self.test_prompt_button.setEnabled(True)
                return

            # 格式化结果显示
            result_text = f"关键词 '{keyword}' 的例句测试结果：\n\n"

            for i, (sentence, translation) in enumerate(sentence_pairs, 1):
                result_text += f"例句 {i}:\n{sentence}\n\n翻译:\n{translation}\n\n"

            # 显示结果
            self.test_result_edit.setText(result_text)

        except Exception as e:
            self.test_result_edit.setText(f"测试错误: {str(e)}")
            traceback.print_exc() # 打印详细错误信息到控制台
        finally:
            self.test_prompt_button.setEnabled(True)
            QApplication.processEvents() # 确保UI更新

    def _on_api_provider_changed(self):
        """当API提供商选择变化时调用"""
        provider = self.api_provider_combo.currentText()
        if provider == "自定义":
            self.api_url.setReadOnly(False)
            # self.api_url.clear() # 用户可能想保留或修改已有的自定义URL
            self.api_url.setPlaceholderText("请输入自定义 API URL")
        else:
            PRESET_API_URLS =  get_config().get("preset_api_urls")
            self.api_url.setText(PRESET_API_URLS.get(provider, ""))
            self.api_url.setReadOnly(True)

    def _prompt_change(self):
        pass
    def _test_api_connection(self):
        """处理测试API连接按钮点击事件（现在是同步的）"""
        api_url = self.api_url.text()
        api_key = self.api_key.text()
        model_name = self.model_name.text()

        if not api_url or not api_key: # model_name can be optional for some APIs, but good to have
            self.test_status_label.setText("<font color='red'>错误: API URL 和 API Key 不能为空。</font>")
            return

        self.test_status_label.setText("测试中，请稍候...")
        self.test_connection_button.setEnabled(False)
        QApplication.processEvents() # 确保UI更新

        start_time = time.time()
        try:
            # 调用 api_client.py 中的同步测试函数
            # test_api_sync(api_url, api_key, model_name, timeout_seconds)
            result_text, error_message = api_client.test_api_sync(
                api_url, api_key, model_name, timeout_seconds=30
            )
            #输出result_text
            print("输出结果：", result_text)

            elapsed_time = time.time() - start_time

            if error_message:
                # 检查是否因为<think>标签导致的问题
                if "<think>" in error_message.lower() or "inference model not supported" in error_message.lower():
                     error_message += " (提示: 部分模型可能不支持以 <think> 开头的指令或特定推理模式)"
                self.test_status_label.setText(f"<font color='red'>测试失败 ({elapsed_time:.2f}s): {error_message}</font>")
            elif result_text:
                self.test_status_label.setText(f"<font color='green'>测试成功 ({elapsed_time:.2f}s)! 收到: '{result_text[:50]}...'</font>")
            else: # 无结果也无错误，可能是API返回空内容
                self.test_status_label.setText(f"<font color='orange'>测试完成但未收到明确内容 ({elapsed_time:.2f}s).</font>")

        except requests.exceptions.Timeout: # Catching specific requests timeout
            elapsed_time = time.time() - start_time
            self.test_status_label.setText(f"<font color='red'>测试失败: 超时 ({elapsed_time:.2f}s)。请检查网络或API端点。</font>")
        except requests.exceptions.RequestException as e: # Catching other requests errors
            elapsed_time = time.time() - start_time
            self.test_status_label.setText(f"<font color='red'>测试失败: 请求错误 ({elapsed_time:.2f}s): {str(e)}</font>")
        except Exception as e: # 捕获其他意外错误
            elapsed_time = time.time() - start_time
            # traceback.print_exc() # 打印详细错误到控制台，便于调试
            error_detail = str(e)
            if "<think>" in error_detail.lower(): # 再次检查
                 error_detail += " (提示: 部分模型可能不支持以 <think> 开头的指令)"
            self.test_status_label.setText(f"<font color='red'>测试失败 ({elapsed_time:.2f}s): {error_detail}</font>")
        finally:
            self.test_connection_button.setEnabled(True)
            QApplication.processEvents() # 确保UI在按钮重新启用后更新


    def _get_form_layout(self, widget):
        """辅助函数：获取包含组合框的 QFormLayout"""
        # 遍历父级查找 QFormLayout
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent.layout(), QFormLayout):
                return parent.layout()
            parent = parent.parentWidget()
        return None # 或引发错误

    def _toggle_custom_widget(self, combo_box, custom_widget, form_layout_ref):
        """通用函数：切换自定义输入框的可见性，并处理其在布局中的添加/移除"""
        is_custom = (combo_box.currentText() == "自定义")
        # 获取包含组合框的 QFormLayout (现在作为参数传入)
        form_layout = form_layout_ref

        if not form_layout: # 安全检查
            if custom_widget: custom_widget.setVisible(is_custom)
            return

        # 查找组合框在布局中的行索引
        combo_row = -1
        for i in range(form_layout.rowCount()):
            item = form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if item and item.widget() == combo_box:
                combo_row = i
                break

        custom_widget_current_row = -1
        if custom_widget: # 检查 custom_widget 是否已在布局中
            for i in range(form_layout.rowCount()):
                # 检查 FieldRole 是否为 custom_widget
                field_item = form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
                if field_item and field_item.widget() == custom_widget:
                    custom_widget_current_row = i
                    break

        if is_custom:
            if custom_widget:
                custom_widget.setVisible(True)
                if custom_widget_current_row == -1 and combo_row != -1: # 不在布局中，且找到了combo
                    # 插入到 QComboBox 下一行, 标签为空
                    form_layout.insertRow(combo_row + 1, QLabel(""), custom_widget)
                elif custom_widget_current_row != -1: # 已在布局中，确保标签也可见
                    label_item = form_layout.itemAt(custom_widget_current_row, QFormLayout.ItemRole.LabelRole)
                    if label_item and label_item.widget():
                        label_item.widget().setVisible(True) # 自定义行标签通常为空，但以防万一
        else: # 不是自定义
            if custom_widget and custom_widget_current_row != -1: # 存在且在布局中
                custom_widget.setVisible(False)
                # 同时隐藏该行的标签
                label_item = form_layout.itemAt(custom_widget_current_row, QFormLayout.ItemRole.LabelRole)
                if label_item and label_item.widget():
                    label_item.widget().setVisible(False)
                # 注意：这里只是隐藏，而不是从布局中移除。如果需要移除，逻辑会更复杂。


    def _handle_custom_change(self, combo_box, custom_attr_name, form_layout_ref):
        """通用处理函数：处理下拉框变化，创建或显示/隐藏自定义输入框"""
        is_custom_selected = (combo_box.currentText() == "自定义")
        custom_widget = getattr(self, custom_attr_name, None)

        if is_custom_selected:
            if custom_widget is None: # 首次选择自定义，创建输入框
                custom_widget = QLineEdit()
                setattr(self, custom_attr_name, custom_widget)
                # _toggle_custom_widget 会处理添加到布局和可见性
            # else: # 已有输入框，确保它可见
                # custom_widget.setVisible(True) # 由 _toggle_custom_widget 处理
        # else: # 非自定义选项
            # if custom_widget is not None: # 如果存在自定义输入框，则隐藏
                # custom_widget.setVisible(False) # 由 _toggle_custom_widget 处理

        # 统一调用 _toggle_custom_widget 来处理布局和可见性
        self._toggle_custom_widget(combo_box, custom_widget, form_layout_ref)


    def on_vocab_level_changed(self):
        self._handle_custom_change(self.vocab_level_combo, 'vocab_level_custom', self._get_form_layout(self.vocab_level_combo))

    def on_learning_goal_changed(self):
        self._handle_custom_change(self.learning_goal_combo, 'learning_goal_custom', self._get_form_layout(self.learning_goal_combo))

    def on_difficulty_changed(self):
        self._handle_custom_change(self.difficulty_combo, 'difficulty_custom', self._get_form_layout(self.difficulty_combo))

    def on_length_changed(self):
        self._handle_custom_change(self.length_combo, 'length_custom', self._get_form_layout(self.length_combo))

    def clear_cache_and_notify(self):
        """清除缓存并显示提示"""
        try:
            clear_cache()
            #QMessageBox.information(self, "成功", "缓存已成功清除。")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"清除缓存时出错: {e}")

    def _get_combo_value(self, combo_box, custom_widget):
        """辅助函数：获取下拉框或自定义输入框的值"""
        value = combo_box.currentText()
        if value == "自定义" and custom_widget is not None:
            # 确保 custom_widget 存在且可见才读取
            if custom_widget.isVisible(): # 检查 custom_widget 是否真的可见
                 return custom_widget.text()
            else: # 如果自定义框不可见（例如，用户切换回非自定义选项后），
                  # 即使组合框仍显示“自定义”（理论上不应发生，因UI会同步），
                  # 也应返回空或一个标记值，表示自定义值未被激活。
                  # 或者，更安全的是，依赖于 custom_widget 是否被创建和填充。
                  # 如果 custom_widget.text() 为空，也返回空。
                 return custom_widget.text() if custom_widget.text() else "" # 返回文本或空
        return value

    def save_and_close(self):
        """保存配置并关闭对话框"""
        # API URL 根据 provider combo 和 api_url line edit 决定
        # api_url_to_save = ""
        # selected_provider = self.api_provider_combo.currentText()
        # if selected_provider == "自定义":
        #     api_url_to_save = self.api_url.text()
        # else:
        #     api_url_to_save = PRESET_API_URLS.get(selected_provider, "")
        # 直接读取 self.api_url.text() 即可，因为 _on_api_provider_changed 已经更新了它

        new_config = {
            "api_url": self.api_url.text(), # api_url 文本框的值在选择预设时已更新或在自定义时可编辑
            "api_key": self.api_key.text(),
            "model_name": self.model_name.text(),
            "deck_name": self.deck_name.text(),
            "vocab_level": self._get_combo_value(self.vocab_level_combo, getattr(self, 'vocab_level_custom', None)),
            "learning_goal": self._get_combo_value(self.learning_goal_combo, getattr(self, 'learning_goal_custom', None)),
            "difficulty_level": self._get_combo_value(self.difficulty_combo, getattr(self, 'difficulty_custom', None)),
            "sentence_length_desc": self._get_combo_value(self.length_combo, getattr(self, 'length_custom', None)),
            "learning_language": self.learning_language_combo.currentText(),
            "highlight_target_word": self.highlight_target_word_combo.currentText() == "是",
            # 保存提示词模板设置
            "prompt_template": self.prompt_template_edit.toPlainText(),
            "prompt_format_normal": self.normal_format_edit.toPlainText(),
            "prompt_format_highlight": self.highlight_format_edit.toPlainText(),
        }
        save_config(new_config) # 调用 config_manager 中的保存函数
        QMessageBox.information(self, "成功", "配置已保存。") # 提示用户
        self.accept() # 关闭对话框

# --- 全局函数 ---
_dialog_instance = None

def show_config_dialog():
    """显示配置对话框 (单例模式)"""
    global _dialog_instance
    # 确保父窗口是活动的 Anki 主窗口
    parent = aqt.mw
    if _dialog_instance is None or _dialog_instance.parent() != parent:
        _dialog_instance = ConfigDialog(parent)

    # 重新加载当前配置以反映任何外部更改（如果需要）
    # current_config = get_config() # 可选：如果配置可能在对话框外部更改
    # _dialog_instance.load_config(current_config) # 需要添加 load_config 方法

    _dialog_instance.show()
    _dialog_instance.raise_()
    _dialog_instance.activateWindow()

def register_menu_item():
    """在工具菜单添加配置入口"""
    action = aqt.QAction("AI例句配置...", aqt.mw) # 加省略号表示打开对话框
    action.triggered.connect(show_config_dialog)
    aqt.mw.form.menuTools.addAction(action)
