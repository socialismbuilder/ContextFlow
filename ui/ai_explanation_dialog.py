import aqt
from aqt.qt import (QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
                    QPushButton, QWidget, QScrollArea, Qt, QTextCursor,
                    QTimer, QSizePolicy, pyqtSignal)
from aqt.utils import showInfo, tooltip
import json
import threading
import queue
import markdown
import re
from functools import partial

from ..config_manager import get_config
from ..card.anki_card_creator import create_sentence_card
from .. import llm_client
from .. import prompts

# --- 样式 ---
DARK_THEME_STYLESHEET = """
    AIExplanationDialog { background-color: #2e2e2e; }
    QScrollArea { border: none; background-color: transparent; }
    #conversationWidget { background-color: transparent; }
    #userInputField {
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



# 提示词（EXPLANATION_PROMPT / build_explanation_prompt / build_explanation_messages）
# 统一由 ..prompts 模块管理。


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
        self.user_input = QTextEdit()
        self.user_input.setObjectName("userInputField")
        self.user_input.setPlaceholderText("继续提问... (Shift+Enter换行, Enter发送)")
        self.user_input.setFixedHeight(50)
        self.user_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.user_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.user_input.setAcceptRichText(False)
        # 内容变化时动态调整高度
        self.user_input.textChanged.connect(self._adjust_input_height)
        # 使用事件过滤器实现 Enter 发送, Shift+Enter 换行
        self.user_input.installEventFilter(self)
        input_layout.addWidget(self.user_input)

        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

    def _add_message_bubble(self, text: str, sender: str) -> MessageBubble:
        bubble = MessageBubble(text, sender, parent_dialog=self)
        if sender == 'ai':
            # 只在气泡创建时连接一次，避免每个例句块都重复连接导致保存多次
            bubble.example_sentence_requested.connect(self._handle_example_sentence_request)
        self.conversation_layout.insertWidget(self.conversation_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def start_explanation(self):
        # 【修改】系统提示回归到要求AI返回JSON（提示词组装统一在 prompts 模块）
        config = get_config()
        self.conversation_history = prompts.build_explanation_messages(
            config,
            sentence=self.sentence,
            word=self.word_to_explain,
            history=None,
            include_examples=True,
        )
        self.send_message_to_ai()

    def send_message(self):
        user_message = self.user_input.toPlainText().strip()
        if not user_message or self.is_streaming:
            if self.is_streaming: tooltip("AI正在生成中，请稍候...", period=1000)
            return
            
        self.user_input.clear()
        self.user_input.setFixedHeight(50)
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
        # 流式请求、thinking 降级、ollama 鉴权、qwen3 /no_think
        # 统一由 llm_client.chat_stream 处理，这里只负责消费事件流并投递到 UI 队列。
        config = get_config()
        full_response_content = ""
        try:
            for event in llm_client.chat_stream(config, self.conversation_history,
                                                stop_event=self.stop_streaming):
                if self.stop_streaming.is_set():
                    break
                if event["type"] == "delta":
                    self.stream_queue.put(event["content"])
                    full_response_content += event["content"]
                elif event["type"] == "error":
                    self.stream_queue.put(
                        f"<p style='color: #ff6b6b;'><b>错误:</b> {event['message']}</p>[STREAM_END_ERROR]")
                    return
            if full_response_content:
                self.conversation_history.append({"role": "assistant", "content": full_response_content})
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
                    code {{ background-color: #e8e8e8; color: #1e1e1e; padding: 2px 4px; border-radius: 4px; font-size: 13px; }}
                    pre {{ background-color: #f5f5f5; color: #1e1e1e; padding: 10px; border-radius: 6px; overflow-x: auto; }}
                    pre code {{ background-color: transparent; padding: 0; font-size: 13px; }}
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
                    table {{ width: 100%; border-collapse: collapse; }}
                    th, td {{ border: 1px solid #555; padding: 6px; text-align: left; }}
                    th {{ background-color: #4a4a4a; }}
                    code {{ background-color: #e8e8e8; color: #1e1e1e; padding: 2px 4px; border-radius: 4px; font-size: 13px; }}
                    pre {{ background-color: #f5f5f5; color: #1e1e1e; padding: 10px; border-radius: 6px; overflow-x: auto; }}
                    pre code {{ background-color: transparent; padding: 0; font-size: 13px; }}
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

    def _adjust_input_height(self):
        """根据内容动态调整输入框高度: 初始50px, 最大150px"""
        doc_height = self.user_input.document().size().height()
        new_height = min(max(int(doc_height) + 20, 50), 150)
        self.user_input.setFixedHeight(new_height)
        # 超出最大高度时启用滚动条
        if new_height >= 150:
            self.user_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.user_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def eventFilter(self, obj, event):
        """拦截输入框按键事件: Enter发送, Shift+Enter换行"""
        if obj is self.user_input and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # Shift+Enter: 插入换行，让 QTextEdit 默认处理
                    return False
                else:
                    # Enter: 发送消息
                    self.send_message()
                    return True
        return super().eventFilter(obj, event)

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
