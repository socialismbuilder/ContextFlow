import aqt
from aqt.qt import (QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, 
                    QPushButton, QWidget, QScrollArea, Qt, QTextCursor, 
                    QTimer, QSizePolicy, pyqtSignal)
from aqt.utils import showInfo, tooltip
import requests
import json
import threading
import queue
import markdown
import re
from functools import partial

from ..config_manager import get_config
from ..card.anki_card_creator import create_sentence_card

# --- 样式 ---
DARK_THEME_STYLESHEET = """
    AIExplanationDialog { background-color: #2e2e2e; }
    QScrollArea { border: none; background-color: transparent; }
    #conversationWidget { background-color: transparent; }
    QLineEdit {
        background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #555;
        border-radius: 15px; padding: 8px 12px; font-size: 14px;
    }
    QPushButton {
        background-color: #555; color: #f0f0f0; border: none;
        border-radius: 15px; padding: 8px 16px; font-size: 14px;
    }
    QPushButton:hover { background-color: #666; }
    QPushButton:pressed { background-color: #444; }
"""
USER_BUBBLE_STYLE = "QTextEdit { background-color: #3c3c3c; color: #f0f0f0; border-radius: 15px; padding: 10px; border: none; font-size: 14px; }"
AI_BUBBLE_STYLE = "QTextEdit { background-color: #f0f0f0; color: #1e1e1e; border-radius: 15px; padding: 10px; border: none; font-size: 14px; }"



prompt = """你是ContextFlow软件的语言学习助手，你将扮演一位资深的语言学家和友善的语言导师。你的任务是为语言学习者提供精准、简洁且高度相关的词汇/短语解释。

除例句外，输出篇幅控制在约200-300字。

你的核心原则是**灵活应变**。你需要首先判断用户输入的类型，然后选择最合适的解释策略，而不是死板地遵循一个固定模板。

# 用户输入：
- 原始例句: '{sentence}'
- 目标内容: '{word_to_explain}'

# 你的工作流程：

### 第一步：智能分析
在生成回答前，请先在内部完成以下思考：
1.  **判断输入类型**: 用户选中的 `{word_to_explain}` 是一个标准的【单词】、一个【固定短语/成语】、一个【语法结构】、一个【句子片段】，还是一个可能因不理解而产生的【错误组合】（例如，选中了“我是个老师”里的“个老”）？
2.  **确定解释重点**: 基于你的判断，决定解释的侧重点。目标是解决用户最根本的困惑，而不是机械地填充所有栏目。

### 第二步：生成解释卡片
请根据你的分析，**参考**使用以下最相关的模块，组合成一份清晰易懂的学习卡片。
对于不必要或不相关的模块，请**直接省略**。
对于你觉得非常有必要的，也可以***自行添加**。
请使用 Markdown 格式化你的回答。

---

#### 📌 核心解释
- **永远需要。** 针对选中的 `{word_to_explain}` 给出最核心的定义。
- 如果是**单词**，提供词性、拼音和基本含义。
- 如果是**短语或句子**，解释其整体意思。

#### 🌐 语境解析
- **大多数情况需要。** 解释 `{word_to_explain}` 在原句 `{sentence}` 中的具体作用和含义。

#### ✨ 用法辨析与扩展
- **（如果适用且有价值）** 提供近义词、反义词、形近词的辨析，或介绍相关的常见搭配、语法结构。**如果没有高质量的辨析内容，请果断跳过此项，保持简洁。**

#### 🔍 特别提醒 / 结构分析
- **（当判断为错误选择或复杂结构时使用）** 温和地指出这可能不是一个常规的词汇单位，并分解解释其组成部分。
- **例如**: 对于“个老”，应分别解释“个”（量词）和“老师”（名词），并说明正确的句子结构是“（一）个老师”。这能直接解决用户的根本困惑。

---

### 第三步：应用实例
最后，根据用户的学习要求生成 2-3 个高质量例句，来展示相关用法。
请确保例句和翻译使用以下JSON格式输出，一个例句翻译对就是一个JSON对象，这一部分必须放在段落最后且无额外内容或注释，以便系统识别：

- 词汇量大致为：{vocab_level}
- 学习目标是：{learning_goal}
- 句子最大难度：{difficulty_level}
- 句子最大长度:{sentence_length_desc}

**重要**: 例句和翻译必须以独立的 JSON 对象格式提供，并置于回答的末尾。不要在 JSON 代码块同一行内添加任何解释性文字或注释，以便系统识别：
系统会自动识别json语法，任何除json语法和代码块符号外的多余的注释，空行，逗号都会被残留，因此请避免任何多余的符合和格式。

```json
{{
  "sentence": "例句原文",
  "translation": "例句翻译"
}}```

你的回答应该像一位经验丰富的老师，既有深度，又懂得因材施教，直击要点。现在，请根据这个新的指导原则，为用户服务。

完成以上步骤后，等待用户的追问。对于追问，随后的追问，不必遵循上述流程，完全灵活的处理。例句生成工具依然可以调用，但建议只在用户主动提出时调用

"""


# 【修改】重新引入创建独立UI组件的逻辑
class MessageBubble(QWidget):
    example_sentence_requested = pyqtSignal(str, str)

    def __init__(self, text: str, sender: str, parent_dialog, parent=None):
        super().__init__(parent)
        self.sender = sender
        self.parent_dialog = parent_dialog

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(5)

        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.document().setDocumentMargin(0)
        self.text_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_display.setMinimumHeight(40)
        # 初始宽度设置，但后续会通过 resizeEvent 动态调整
        self.text_display.setFixedWidth(int(parent_dialog.width() * 0.75)) 
        self.text_display.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred) # 允许宽度调整
        
        self.text_display.textChanged.connect(self._adjust_main_text_height)

        if sender == "user":
            self.text_display.setPlainText(text)
            self.text_display.setStyleSheet(USER_BUBBLE_STYLE)
        else:
            self.text_display.setStyleSheet(AI_BUBBLE_STYLE)
            self.text_display.setHtml(text)

        self.content_layout.addWidget(self.text_display)
        
        # 用于存放例句块的布局
        self.example_sentences_layout = QVBoxLayout()
        self.example_sentences_layout.setContentsMargins(0, 8, 0, 0)
        self.example_sentences_layout.setSpacing(8)
        self.content_layout.addLayout(self.example_sentences_layout)

        if self.sender == 'user':
            self.main_layout.addStretch()
            self.main_layout.addWidget(self.content_widget)
        else:
            self.main_layout.addWidget(self.content_widget)
            self.main_layout.addStretch()

        self.setLayout(self.main_layout)

    def _adjust_main_text_height(self):
        doc_height = self.text_display.document().size().height()
        self.text_display.setFixedHeight(int(doc_height) + 30)
        
    def set_main_html(self, html: str):
        self.text_display.setHtml(html)

    # 添加例句块，并正确处理高度
    def add_example_sentence_block(self, sentence: str, translation: str):
        if self.sender != 'ai':
            return

        example_block_widget = QWidget()
        example_block_layout = QVBoxLayout(example_block_widget)
        example_block_layout.setContentsMargins(8, 8, 8, 8) # 调整边距
        example_block_layout.setSpacing(5) # 调整间距
        example_block_widget.setStyleSheet("QWidget { background-color: #4a4a4a; border-radius: 8px; }")

        # 动态调整高度的辅助函数
        def adjust_text_edit_height(text_edit):
            doc_height = text_edit.document().size().height()
            text_edit.setFixedHeight(int(doc_height) + 2) # 调整固定高度，使其更紧凑

        # 例句标签和添加到Anki按钮的水平布局
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        # 例句标签
        sentence_title_label = QTextEdit()
        sentence_title_label.setReadOnly(True)
        sentence_title_label.setHtml("<span style='color: #f0f0f0; font-size: 12px; font-weight: bold;'>例句:</span>") # 调整字体大小
        sentence_title_label.setStyleSheet("background-color: transparent; border: none;")
        sentence_title_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sentence_title_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sentence_title_label.setFixedHeight(20) # 固定高度以适应小字体
        sentence_title_label.setFixedWidth(40) # 固定宽度

        # 添加到Anki按钮
        add_button = QPushButton("添加到Anki")
        add_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff; color: #ffffff; border: none;
                border-radius: 10px; padding: 4px 10px; font-size: 13px;
                max-width: 120px;
            }
            QPushButton:hover { background-color: #0056b3; }
            QPushButton:pressed { background-color: #004085; }
        """)
        add_button.clicked.connect(partial(self.example_sentence_requested.emit, sentence, translation))
        
        header_layout.addWidget(sentence_title_label)
        header_layout.addStretch() # 将按钮推到右边
        header_layout.addWidget(add_button)

        # 例句内容
        sentence_content_label = QTextEdit()
        sentence_content_label.setReadOnly(True)
        sentence_content_label.setHtml(f"<div style='color: #f0f0f0; font-size: 15px; margin-top: 0;'>{sentence}</div>") # 保持文字大小
        sentence_content_label.setStyleSheet("background-color: transparent; border: none;")
        sentence_content_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sentence_content_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sentence_content_label.textChanged.connect(lambda: adjust_text_edit_height(sentence_content_label))
        
        # 翻译标签
        translation_title_label = QTextEdit()
        translation_title_label.setReadOnly(True)
        translation_title_label.setHtml("<span style='color: #f0f0f0; font-size: 12px; font-weight: bold;'>翻译:</span>") # 调整字体大小
        translation_title_label.setStyleSheet("background-color: transparent; border: none;")
        translation_title_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        translation_title_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        translation_title_label.setFixedHeight(20) # 固定高度以适应小字体
        translation_title_label.setFixedWidth(40) # 固定宽度

        # 翻译内容
        translation_content_label = QTextEdit()
        translation_content_label.setReadOnly(True)
        translation_content_label.setHtml(f"<div style='color: #f0f0f0; font-size: 15px; margin-top: 0;'>{translation}</div>") # 保持文字大小
        translation_content_label.setStyleSheet("background-color: transparent; border: none;")
        translation_content_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        translation_content_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        translation_content_label.textChanged.connect(lambda: adjust_text_edit_height(translation_content_label))

        example_block_layout.addLayout(header_layout)
        example_block_layout.addWidget(sentence_content_label)
        example_block_layout.addWidget(translation_title_label)
        example_block_layout.addWidget(translation_content_label)
        
        self.example_sentences_layout.addWidget(example_block_widget)

        # 【关键】内容设置后，手动调用一次以确保初始高度正确
        QTimer.singleShot(0, lambda: adjust_text_edit_height(sentence_content_label))
        QTimer.singleShot(0, lambda: adjust_text_edit_height(translation_content_label))


class AIExplanationDialog(QDialog):
    def __init__(self, parent, sentence: str, word_to_explain: str):
        super().__init__(parent)
        self.sentence = sentence
        self.word_to_explain = word_to_explain
        self.config = get_config()
        self.api_url = self.config.get("api_url")
        self.api_key = self.config.get("api_key")
        self.model_name = self.config.get("model_name")
        self.conversation_history = []
        self.stream_queue = queue.Queue()
        self.stop_streaming = threading.Event()
        self.is_streaming = False
        
        self.current_ai_response_raw_text = ""
        self.current_ai_bubble = None
        self.markdown_extensions = ['markdown.extensions.tables', 'markdown.extensions.fenced_code', 'markdown.extensions.nl2br']

        self.setWindowTitle(f"AI解释: {word_to_explain}")
        self.setGeometry(0, 0, 700, 800)
        
        self.setStyleSheet(DARK_THEME_STYLESHEET)

        if aqt.mw:
            self.move(aqt.mw.geometry().center() - self.rect().center())

        self.init_ui()
        self.start_explanation()

    def resizeEvent(self, event):
        # 当对话框大小改变时，更新所有气泡的宽度
        super().resizeEvent(event)
        new_bubble_width = int(self.width() * 0.75)
        for i in range(self.conversation_layout.count()):
            item = self.conversation_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageBubble):
                bubble = item.widget()
                bubble.text_display.setFixedWidth(new_bubble_width)
                # 确保主文本气泡的高度也随之调整
                bubble._adjust_main_text_height()

                # 确保例句块的宽度和高度也随之调整
                for j in range(bubble.example_sentences_layout.count()):
                    example_item = bubble.example_sentences_layout.itemAt(j)
                    if example_item and example_item.widget():
                        example_block_widget = example_item.widget()
                        example_block_widget.setFixedWidth(new_bubble_width - 16) # 减去内边距

                        # 遍历例句块内的所有QTextEdit，调整其高度
                        for child_item_idx in range(example_block_widget.layout().count()):
                            child_item = example_block_widget.layout().itemAt(child_item_idx)
                            if child_item and child_item.widget() and isinstance(child_item.widget(), QTextEdit):
                                text_edit = child_item.widget()
                                # 动态调整高度的辅助函数，与MessageBubble中定义的保持一致
                                doc_height = text_edit.document().size().height()
                                text_edit.setFixedHeight(int(doc_height) + 2)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.conversation_widget = QWidget()
        self.conversation_widget.setObjectName("conversationWidget")
        self.conversation_layout = QVBoxLayout(self.conversation_widget)
        self.conversation_layout.addStretch()
        self.conversation_layout.setSpacing(10)

        self.scroll_area.setWidget(self.conversation_widget)
        main_layout.addWidget(self.scroll_area)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("继续提问...")
        self.user_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.user_input)

        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

    def _add_message_bubble(self, text: str, sender: str) -> MessageBubble:
        bubble = MessageBubble(text, sender, parent_dialog=self)
        self.conversation_layout.insertWidget(self.conversation_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def start_explanation(self):
        # 【修改】系统提示回归到要求AI返回JSON
        config = get_config()
        DEFAULT_CONFIG = {
            "vocab_level": "大学英语四级 CET-4 (4000词)",
            "learning_goal": "提升日常浏览英文网页与资料的流畅度",
            "difficulty_level": "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围",
            "sentence_length_desc": "中等长度句 (约25-40词): 通用对话及文章常用长度",
            "learning_language": "英语",
            "prompt_name": "默认-不标记目标词"
        }
        vocab_level = config.get("vocab_level", DEFAULT_CONFIG["vocab_level"])
        learning_goal = config.get("learning_goal", DEFAULT_CONFIG["learning_goal"])
        difficulty_level = config.get("difficulty_level", DEFAULT_CONFIG["difficulty_level"])
        sentence_length_desc = config.get("sentence_length_desc", DEFAULT_CONFIG["sentence_length_desc"])

        system_prompt = prompt.format(
            sentence=self.sentence,
            word_to_explain=self.word_to_explain,
            vocab_level=vocab_level,
            learning_goal=learning_goal,
            difficulty_level=difficulty_level,
            sentence_length_desc=sentence_length_desc
        )
        
        # 检查模型名称是否包含qwen3，如果是则在提示词末尾添加/no_think标签
        if "qwen3" in self.model_name.lower():
            system_prompt += "\n/no_think"
            
        self.conversation_history = [
            {"role": "system", "content": ""},
            {"role": "user", "content": system_prompt}
        ]
        self.send_message_to_ai()

    def send_message(self):
        user_message = self.user_input.text().strip()
        if not user_message or self.is_streaming:
            if self.is_streaming: tooltip("AI正在生成中，请稍候...", period=1000)
            return
            
        self.user_input.clear()
        user_bubble = self._add_message_bubble(user_message, 'user')
        # 确保用户气泡高度在内容设置后正确调整
        QTimer.singleShot(0, user_bubble._adjust_main_text_height)
        self.conversation_history.append({"role": "user", "content": user_message})
        self.send_message_to_ai()

    def send_message_to_ai(self):
        if self.is_streaming: return
        if not self.api_url or not self.model_name:
            showInfo("请在配置中设置API URL和模型名称。")
            return
            
        # 检查是否为ollama模型（localhost、127.0.0.1或模型名包含ollama）
        is_ollama = ("localhost" in self.api_url or "127.0.0.1" in self.api_url or 
                    "ollama" in self.model_name.lower())
        
        # 对于非ollama模型，需要API key
        if not is_ollama and not self.api_key:
            showInfo("请在配置中设置API Key。")
            return

        self.current_ai_response_raw_text = ""
        self.current_ai_bubble = self._add_message_bubble("...", 'ai')
        
        self.is_streaming = True
        self.stop_streaming.clear()
        threading.Thread(target=self._stream_api_response, daemon=True).start()
        self.timer = self.startTimer(50)

    def _stream_api_response(self):
        # 检查是否为ollama模型（localhost、127.0.0.1或模型名包含ollama）
        is_ollama = ("localhost" in self.api_url or "127.0.0.1" in self.api_url or 
                    "ollama" in self.model_name.lower())
        
        # 对于ollama模型，不设置Authorization header
        if is_ollama:
            headers = {"Content-Type": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            
        from .. import api_client
        if api_client.support_thinking:
            payload = {"model": self.model_name, "messages": self.conversation_history, "stream": True,"thinking": {"type": "disabled"}}
        else:
            payload = {"model": self.model_name, "messages": self.conversation_history, "stream": True}
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, stream=True, timeout=60)
            response.raise_for_status()
            full_response_content = ""
            for chunk in response.iter_content(chunk_size=None):
                if self.stop_streaming.is_set(): break
                if chunk:
                    chunk_str = chunk.decode('utf-8', errors='ignore')
                    for line in chunk_str.splitlines():
                        if line.startswith("data: "):
                            json_data = line[len("data: "):].strip()
                            if json_data == "[DONE]":
                                self.stream_queue.put("[STREAM_END]")
                                break
                            try:
                                data = json.loads(json_data)
                                delta_content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta_content:
                                    self.stream_queue.put(delta_content)
                                    full_response_content += delta_content
                            except json.JSONDecodeError: continue
                        if "[DONE]" in line: break
                    if "[DONE]" in chunk_str: break
            if full_response_content:
                self.conversation_history.append({"role": "assistant", "content": full_response_content})
        except requests.exceptions.RequestException as e:
            self.stream_queue.put(f"<p style='color: #ff6b6b;'><b>网络错误:</b> {e}</p>[STREAM_END_ERROR]")
        except Exception as e:
            self.stream_queue.put(f"<p style='color: #ff6b6b;'><b>意外错误:</b> {e}</p>[STREAM_END_ERROR]")
        finally:
            q_list = list(self.stream_queue.queue)
            if not any(tag in q_list for tag in ["[STREAM_END]", "[STREAM_END_ERROR]"]):
                 self.stream_queue.put("[STREAM_END]")

    def timerEvent(self, event):
        chunks_to_process = ""
        is_end = False

        while not self.stream_queue.empty():
            chunk = self.stream_queue.get_nowait()
            if "[STREAM_END]" in chunk:
                is_end = True
                chunks_to_process += chunk.replace("[STREAM_END]", "").replace("[STREAM_END_ERROR]", "")
                break
            else:
                chunks_to_process += chunk

        if chunks_to_process and self.current_ai_bubble:
            self.current_ai_response_raw_text += chunks_to_process
            
            md_html = markdown.markdown(self.current_ai_response_raw_text.strip(), extensions=self.markdown_extensions)
            styled_html = f"""
                <style>
                    table {{ width: 100%; border-collapse: collapse; }}
                    th, td {{ border: 1px solid #555; padding: 6px; text-align: left; }}
                    th {{ background-color: #4a4a4a; }}
                    code {{ background-color: #4a4a4a; padding: 2px 4px; border-radius: 4px; }}
                </style>
                {md_html}
            """
            self.current_ai_bubble.set_main_html(styled_html)
        
        # 【修改】流结束后，解析JSON并创建UI组件
        if is_end:
            self.killTimer(self.timer)
            
            # 匹配JSON对象，包括可能被代码块包裹的情况
            json_pattern = re.compile(r'(```json\s*)?(\{[\s\S]*?"sentence":[\s\S]*?\})(\s*```)?', re.DOTALL)
            final_text_parts = []
            last_end = 0

            for match in json_pattern.finditer(self.current_ai_response_raw_text):
                if match.start() > last_end:
                    final_text_parts.append(self.current_ai_response_raw_text[last_end:match.start()])
                
                # 获取JSON字符串（第二个捕获组，索引为2）
                json_str = match.group(2)
                try:
                    example_data = json.loads(json_str)
                    sentence = example_data.get("sentence", "")
                    translation = example_data.get("translation", "")
                    if sentence and translation and self.current_ai_bubble:
                        self.current_ai_bubble.add_example_sentence_block(sentence, translation)
                        self.current_ai_bubble.example_sentence_requested.connect(self._handle_example_sentence_request)
                except json.JSONDecodeError:
                    # 如果JSON解析失败，保留原始匹配内容
                    full_match = match.group(0)
                    final_text_parts.append(full_match)
                
                last_end = match.end()
            
            if last_end < len(self.current_ai_response_raw_text):
                final_text_parts.append(self.current_ai_response_raw_text[last_end:])

            remaining_text = "".join(final_text_parts)
            # 清理多余的回车换行
            cleaned_text = self._clean_remaining_text(remaining_text)
            md_html = markdown.markdown(cleaned_text, extensions=self.markdown_extensions)
            styled_html = f"""
                <style>
                    /* Style for main bubble text */
                </style>
                {md_html}
            """
            if self.current_ai_bubble:
                self.current_ai_bubble.set_main_html(styled_html)

            self.current_ai_bubble = None
            self.current_ai_response_raw_text = ""
            self.is_streaming = False
        
        self._scroll_to_bottom()

    def closeEvent(self, event):
        self.stop_streaming.set()
        if hasattr(self, 'timer'):
            self.killTimer(self.timer)
        super().closeEvent(event)

    def _clean_remaining_text(self, text: str) -> str:
        """清理剩余文本中的多余回车换行"""
        if not text:
            return text
        
        # 清理连续多个空行，保留最多一个空行
        cleaned_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        # 清理开头和结尾的多余空行
        cleaned_text = cleaned_text.strip()
        return cleaned_text

    def _handle_example_sentence_request(self, sentence: str, translation: str):

        config = get_config()
        save_deck = config.get("save_deck", "收藏例句")
        create_sentence_card(sentence, translation, save_deck)
        tooltip("例句已发送到后端处理！", period=1500)
