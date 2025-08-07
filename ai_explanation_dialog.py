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

from .config_manager import get_config
from .anki_card_creator import create_sentence_card

# --- 样式部分无变化 ---
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
        self.text_display.setFixedWidth(int(parent_dialog.width() * 0.75))
        
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

    # 【核心修复】重新实现 add_example_sentence_block，并正确处理高度
    def add_example_sentence_block(self, sentence: str, translation: str):
        if self.sender != 'ai':
            return

        example_block_widget = QWidget()
        example_block_layout = QVBoxLayout(example_block_widget)
        example_block_layout.setContentsMargins(10, 10, 10, 10)
        example_block_layout.setSpacing(8)
        example_block_widget.setStyleSheet("QWidget { background-color: #4a4a4a; border-radius: 8px; }")

        # 动态调整高度的辅助函数
        def adjust_text_edit_height(text_edit):
            doc_height = text_edit.document().size().height()
            text_edit.setFixedHeight(int(doc_height) + 5)

        # 例句
        sentence_label = QTextEdit()
        sentence_label.setReadOnly(True)
        sentence_label.setHtml(f"<div style='color: #f0f0f0;'><p style='font-weight: bold;'>例句:</p><p>{sentence}</p></div>")
        sentence_label.setStyleSheet("background-color: transparent; border: none;")
        sentence_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sentence_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 连接信号，使用 lambda 确保在内容变化时能正确调整自己的高度
        sentence_label.textChanged.connect(lambda: adjust_text_edit_height(sentence_label))
        
        # 翻译
        translation_label = QTextEdit()
        translation_label.setReadOnly(True)
        translation_label.setHtml(f"<div style='color: #f0f0f0;'><p style='font-weight: bold;'>翻译:</p><p>{translation}</p></div>")
        translation_label.setStyleSheet("background-color: transparent; border: none;")
        translation_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        translation_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        translation_label.textChanged.connect(lambda: adjust_text_edit_height(translation_label))

        # 按钮
        add_button = QPushButton("添加到Anki")
        add_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff; color: #ffffff; border: none;
                border-radius: 10px; padding: 6px 12px; font-size: 13px;
                max-width: 120px; margin-top: 5px;
            }
            QPushButton:hover { background-color: #0056b3; }
            QPushButton:pressed { background-color: #004085; }
        """)
        add_button.clicked.connect(partial(self.example_sentence_requested.emit, sentence, translation))
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(add_button)

        example_block_layout.addWidget(sentence_label)
        example_block_layout.addWidget(translation_label)
        example_block_layout.addLayout(button_layout)
        
        self.example_sentences_layout.addWidget(example_block_widget)

        # 【关键】内容设置后，手动调用一次以确保初始高度正确
        QTimer.singleShot(0, lambda: adjust_text_edit_height(sentence_label))
        QTimer.singleShot(0, lambda: adjust_text_edit_height(translation_label))


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
        system_prompt = (
            f"你是一个专业的词汇解释助手。用户对'{self.sentence}'例句中的，'{self.word_to_explain}'这部分感到困惑，请你给用户详细解释。\n"
            "在你的解释中，如果提供例句和翻译，请务必使用以下JSON格式输出，一个例句翻译对就是一个JSON对象，并且不要包含额外的Markdown代码块标记（例如```json```）：\n"
            "```json\n"
            "{\n"
            "  \"sentence\": \"例句原文\",\n"
            "  \"translation\": \"例句翻译\"\n"
            "}\n"
            "```\n"
            "请确保JSON是独立的，前后可以有其他解释文本，但JSON本身不要被Markdown代码块包裹。"
        )
        self.conversation_history = [{"role": "system", "content": system_prompt}]
        self.send_message_to_ai()

    def send_message(self):
        user_message = self.user_input.text().strip()
        if not user_message or self.is_streaming:
            if self.is_streaming: tooltip("AI正在生成中，请稍候...", period=1000)
            return
            
        self.user_input.clear()
        self._add_message_bubble(user_message, 'user')
        self.conversation_history.append({"role": "user", "content": user_message})
        self.send_message_to_ai()

    def send_message_to_ai(self):
        if self.is_streaming: return
        if not self.api_url or not self.api_key or not self.model_name:
            showInfo("请在配置中设置API URL、API Key和模型名称。")
            return

        self.current_ai_response_raw_text = ""
        self.current_ai_bubble = self._add_message_bubble("...", 'ai')
        
        self.is_streaming = True
        self.stop_streaming.clear()
        threading.Thread(target=self._stream_api_response, daemon=True).start()
        self.timer = self.startTimer(50)

    def _stream_api_response(self):
        # 此函数逻辑不变
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        from . import api_client
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
            
            md_html = markdown.markdown(self.current_ai_response_raw_text, extensions=self.markdown_extensions)
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
            
            json_pattern = re.compile(r'(\{[\s\S]*?"sentence":[\s\S]*?\})', re.DOTALL)
            final_text_parts = []
            last_end = 0

            for match in json_pattern.finditer(self.current_ai_response_raw_text):
                if match.start() > last_end:
                    final_text_parts.append(self.current_ai_response_raw_text[last_end:match.start()])
                
                json_str = match.group(1)
                try:
                    example_data = json.loads(json_str)
                    sentence = example_data.get("sentence", "")
                    translation = example_data.get("translation", "")
                    if sentence and translation and self.current_ai_bubble:
                        self.current_ai_bubble.add_example_sentence_block(sentence, translation)
                        self.current_ai_bubble.example_sentence_requested.connect(self._handle_example_sentence_request)
                except json.JSONDecodeError:
                    final_text_parts.append(json_str)
                
                last_end = match.end()
            
            if last_end < len(self.current_ai_response_raw_text):
                final_text_parts.append(self.current_ai_response_raw_text[last_end:])

            remaining_text = "".join(final_text_parts)
            md_html = markdown.markdown(remaining_text, extensions=self.markdown_extensions)
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

    def _handle_example_sentence_request(self, sentence: str, translation: str):
        print(f"接收到例句：{sentence}")
        print(f"接收到翻译：{translation}")

        config = get_config()
        save_deck = config.get("save_deck", "收藏例句")
        create_sentence_card(sentence, translation, save_deck)
        tooltip("例句已发送到后端处理！", period=1500)

