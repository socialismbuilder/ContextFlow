import time # 用于超时控制
import traceback # 用于打印更详细的错误信息

import aqt
from aqt.qt import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QGroupBox, QHBoxLayout, QWidget, QDialogButtonBox, QMessageBox, QApplication
)
from .config_manager import get_config, save_config # 使用相对导入
from .cache_manager import clear_cache
from . import api_client # 导入 api_client 以便调用测试函数

# 主流厂商 API URL 预设
PRESET_API_URLS = {
    "火山/豆包/字节（推荐）": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "OpenRouter": "https://openrouter.ai/api/v1/chat/completions", 
    "硅基流动": "https://api.siliconflow.cn/v1/chat/completions",
    "Moonshot AI (Kimi)": "https://api.moonshot.cn/v1/chat/completions",
    "阿里云百练": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "Ollama (localhost)": "http://localhost:11434/api/chat", # 假设Ollama在本地运行
    "自定义": "" # 自定义选项
}

# 预设词汇量等级
preset_vocab_levels = [
    # 按教育阶段（国内系统参考）
    "小学核心词汇 (约1500词)",
    "初中核心词汇 (约3000词)",
    "高中核心词汇 (约4500词)",
    # 按大学英语等级
    "大学英语四级 CET-4 (4000词)",
    "大学英语六级 CET-6 (6000词)",
    # 按欧洲共同语言参考标准 (CEFR)
    "CEFR A2 (基础，约1500词)",
    "CEFR B1 (初级进阶，约3000词)",
    "CEFR B2 (中级，约5000词)",
    "CEFR C1 (高级，约7500词)",
    "CEFR C2 (精通，约10000词)",
    # 按留学/专业考试
    "TOEFL iBT (8000词)",
    "IELTS Academic (9000词)",
    "GRE General Test (10000词)",
    # BEC (Business English Certificate) 暂时不加，如需可再添加
    # 按学术/专业领域
    "学术英语进阶 (12000词)", # 适合研究生、博士或高阶研究者
    "商务英语常用词 (约6000词)", # 贴近商务场景
    # 母语者及高阶词汇
    "母语者水平 / 高阶词库 (20000+词)",
    # 自定义选项保留
    "自定义"]

# 预设学习目标选项列表
preset_learning_goals = [
    # 基础及日常目标
    "进行基础的日常英语交流 (问候、购物、指路等)",
    "流利进行日常及社交英语对话",
    "提升日常浏览英文网页与资料的流畅度", # 保留原选项
    # 学术相关目标
    "学术论文阅读与理解", # 保留原选项，可以进一步细化
    "撰写学术论文摘要、报告或科研邮件",
    "理解英文讲座、学术会议或课堂内容",
    # 商务相关目标
    "商务英语沟通 (会议、谈判、电话等)", # 保留原选项，侧重口语听力
    "撰写专业的商务邮件、报告或提案", # 侧重写作
    "理解商务文件、合同或行业报告", # 侧重阅读理解
    # 考试准备目标
    "备考中考", # 注意这里可能少了个逗号，如果前面是列表项的话
    "备考高考",
    "备考雅思 (IELTS)",
    "备考托福 (TOEFL)",
    "备考GRE General Test",
    "备考大学英语四级 (CET-4)",
    "备考大学英语六级 (CET-6)",
    "备考BEC (商务英语证书)",
    "备考其他标准化英语考试 (如专四/专八)", # 增加一个泛指
    # 特定场景或能力目标
    "提高出国旅行时的英语沟通能力",
    "自信应对英文工作面试",
    "用英语介绍个人、项目或进行小型演讲 (Presentation)",
    "提高英文电影、电视剧、播客的理解能力 (无字幕或少字幕)", # 侧重听力理解与文化
    "用英语进行在线交流和写作 (社交媒体、论坛等)",
    # 全面或进阶目标
    "全面提升听说读写各项英语能力",
    "达到接近母语者的英语水平", #  ambitious goal
    "利用英语进行深入研究或专业探索", # High-level, professional/academic use
    # 自定义选项保留
    "自定义"
]

# 预设句子难度选项列表
preset_difficulties = [
    # 按欧洲共同语言参考标准 (CEFR) 分级细化
    "入门级 (A1): 极简单句，高频词汇，用于基本沟通",
    "初级 (A2): 简单复合句，日常话题，基础语法结构",
    "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围",
    "中高级 (B2): 复杂句，抽象主题，多样化句式结构",
    "高级 (C1): 多主从复合句，深入探讨主题，使用高级词汇和表达",
    "精通级 (C2): 高度复杂及抽象句式，细微含义，流畅自如",
    # 按句子结构/语法特点划分
    "简单句结构: 仅包含主谓宾等基本成分，无从句或复杂短语",
    "基础复合句: 包含简单的并列句 (and, but, or) 和基础状语从句",
    "复杂句结构: 包含各类主语/宾语/定语/状语从句，非谓语动词，插入语等",
    "高级句式: 包含倒装、虚拟语气、强调结构、平行结构等复杂或正式句型",
    # 按语体风格/内容特点划分
    "日常口语化: 模拟真实生活对话，包含缩略语、习语等非正式元素",
    "标准通用: 规范的书面及正式口语，适用于新闻报道、通用文章等",
    "学术语体: 用于学术论文、教材等，结构严谨，词汇精确，逻辑清晰",
    "专业/技术领域: 包含特定行业或学科的术语及表达方式，句子结构可能较复杂",
    # 参照母语者水平
    "母语者复杂句: 涵盖母语者在复杂语境下可能使用的所有高级句式和表达", # 通常对应 C2 或更高复杂度
    # 自定义选项保留
    "自定义"
]

# 句子长度选择

preset_lengths = [
    # 按单词数量细分，并关联典型语境
    "极短句 (约5-10词): 适合标题、指令或极简表达",
    "短句 (约10-20词): 基础表达及日常简单交流", # 包含原选项15词左右
    "中等长度句 (约25-40词): 通用对话及文章常用长度", # 包含原选项30词左右
    "长句 (约45-60词): 包含较多修饰或从句", # 包含原选项50词左右，并暗示复杂度
    "超长句 (60+词): 高信息密度，常见于正式及学术文本", # 进一步提高难度
    # 按用途或理解目标划分 (长度与难度通常相关)
    "简洁明了: 目标是快速理解核心信息，通常句子较短 (约15-30词)",
    "标准篇幅: 适合学习通用语言，包含适当细节，长度适中 (约30-50词)",
    "信息密集: 包含丰富的细节、修饰和逻辑关系，通常句子较长 (50+词)",
    # 自定义选项保留
    "自定义"
]

class ConfigDialog(QDialog):
    """配置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI句子生成配置")
        self.setMinimumWidth(450) # 调整最小宽度以容纳新控件

        main_layout = QVBoxLayout(self)
        current_config = get_config()

        api_group = QGroupBox("API 设置")
        api_layout = QFormLayout()

        # API Provider ComboBox
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
        elif not saved_api_url and "OpenAI" in PRESET_API_URLS: # 默认选择OpenAI如果配置为空
             self.api_provider_combo.setCurrentText("OpenAI")

        self._on_api_provider_changed() # 根据 combo 初始化 URL 状态
        self.api_url.setText(saved_api_url) # 确保加载已保存的URL，即使是自定义的

        self.api_provider_combo.currentTextChanged.connect(self._on_api_provider_changed)

        self.api_key = QLineEdit(current_config.get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("API 密钥:", self.api_key)

        self.model_name = QLineEdit(current_config.get("model_name", ""))
        api_layout.addRow("模型名称:", self.model_name)

        # Test API Button and Status Label
        self.test_connection_button = QPushButton("测试 API 连接")
        self.test_connection_button.clicked.connect(self._test_api_connection)
        self.test_status_label = QLabel("点击按钮测试连接状态")
        self.test_status_label.setWordWrap(True)

        test_layout = QHBoxLayout()
        test_layout.addWidget(self.test_connection_button)
        test_layout.addWidget(self.test_status_label)
        api_layout.addRow(test_layout) # 将按钮和标签添加到表单布局的一行

        api_group.setLayout(api_layout)
        main_layout.addWidget(api_group)

        # --- 句子生成偏好设置组 ---
        prefs_group = QGroupBox("句子生成偏好")
        prefs_layout = QFormLayout()

        # 词汇量等级选择
        self.vocab_level_combo = QComboBox()


        self.vocab_level_combo.addItems(preset_vocab_levels)
        current_vocab = current_config.get("vocab_level", "大学英语四级 CET-4 (4000词)")
        self.vocab_level_custom = None # 初始化为 None
        if current_vocab not in preset_vocab_levels[:-1]:
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


        self.learning_goal_combo.addItems(preset_learning_goals)
        current_goal = current_config.get("learning_goal", "提升日常浏览英文网页与资料的流畅度")
        self.learning_goal_custom = None
        if current_goal not in preset_learning_goals[:-1]:
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
        #preset_difficulties = ["初级 (A1-A2)", "中级 (B1)", "中高级 (B2-C1)", "自定义"]



        self.difficulty_combo.addItems(preset_difficulties)
        current_diff = current_config.get("difficulty_level", "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围") # 修正默认值以匹配列表
        self.difficulty_custom = None
        if current_diff not in preset_difficulties[:-1]:
            self.difficulty_combo.setCurrentText("自定义")
            self.difficulty_custom = QLineEdit(current_diff)
        else:
            self.difficulty_combo.setCurrentText(current_diff)
        prefs_layout.addRow("句子难度:", self.difficulty_combo)
        if self.difficulty_custom:
            prefs_layout.addRow("", self.difficulty_custom)
        self.difficulty_combo.currentIndexChanged.connect(self.on_difficulty_changed)
        self._toggle_custom_widget(self.difficulty_combo, self.difficulty_custom, prefs_layout)



        self.length_combo = QComboBox()
        self.length_combo.addItems(preset_lengths)
        current_length = current_config.get("sentence_length_desc", "中等长度句 (约25-40词): 通用对话及文章常用长度") # 修正默认值
        self.length_custom = None
        if current_length not in preset_lengths[:-1]:
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
        main_layout.addWidget(prefs_group)

        # --- 其他设置 ---
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
        main_layout.addWidget(other_group)

        # --- 按钮 ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.save_and_close)
        button_box.rejected.connect(self.reject)

        # 删除缓存按钮 (单独添加)
        del_cache_btn = QPushButton("删除缓存")
        del_cache_btn.clicked.connect(self.clear_cache_and_notify)
        button_layout = QHBoxLayout() # 水平布局放按钮
        button_layout.addWidget(del_cache_btn)
        button_layout.addStretch() # 推到右边
        button_layout.addWidget(button_box) # 标准按钮盒

        main_layout.addLayout(button_layout) # 添加按钮布局

    def _on_api_provider_changed(self):
        """当API提供商选择变化时调用"""
        provider = self.api_provider_combo.currentText()
        if provider == "自定义":
            self.api_url.setReadOnly(False)
            # self.api_url.clear() # 用户可能想保留或修改已有的自定义URL
            self.api_url.setPlaceholderText("请输入自定义 API URL")
        else:
            self.api_url.setText(PRESET_API_URLS.get(provider, ""))
            self.api_url.setReadOnly(True)

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
    action = aqt.QAction("AI句子生成配置...", aqt.mw) # 加省略号表示打开对话框
    action.triggered.connect(show_config_dialog)
    aqt.mw.form.menuTools.addAction(action)
