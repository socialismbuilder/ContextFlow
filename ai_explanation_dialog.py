import aqt
from aqt.qt import (QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, 
                    QPushButton, QWidget, QScrollArea, Qt, QTextCursor, 
                    QTimer, QSizePolicy) # 导入 QSizePolicy
from aqt.utils import showInfo, tooltip
import requests
import json
import threading
import queue
import markdown

# 假设这个函数存在
from .config_manager import get_config

# --- 深色主题样式 ---
DARK_THEME_STYLESHEET = """
    AIExplanationDialog {
        background-color: #2e2e2e; /* 主窗口深灰色背景 */
    }
    QScrollArea {
        border: none;
        background-color: transparent;
    }
    #conversationWidget {
        background-color: transparent;
    }
    QLineEdit {
        background-color: #3c3c3c;
        color: #f0f0f0;
        border: 1px solid #555;
        border-radius: 15px;
        padding: 8px 12px;
        font-size: 14px;
    }
    QPushButton {
        background-color: #555;
        color: #f0f0f0;
        border: none;
        border-radius: 15px;
        padding: 8px 16px;
        font-size: 14px;
    }
    QPushButton:hover {
        background-color: #666;
    }
    QPushButton:pressed {
        background-color: #444;
    }
"""

USER_BUBBLE_STYLE = """
    QTextEdit {
        background-color: #3c3c3c; /* 用户气泡颜色 */
        color: #f0f0f0; /* 用户文字颜色 */
        border-radius: 15px;
        padding: 10px;
        border: none;
        font-size: 14px;
    }
"""

AI_BUBBLE_STYLE = """
    QTextEdit {
        background-color: #f0f0f0; /* AI气泡颜色，如截图所示 */
        color: #1e1e1e; /* AI文字颜色 */
        border-radius: 15px;
        padding: 10px;
        border: none;
        font-size: 14px;
    }
"""

class MessageBubble(QWidget):
    """一个用于显示单条消息的气泡控件。"""
    def __init__(self, text: str, sender: str, parent_dialog, parent=None):
        super().__init__(parent)
        self.sender = sender

        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.document().setDocumentMargin(0)
        self.text_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 【优化】设置最小高度和最大宽度
        self.text_display.setMinimumHeight(40) 
        self.text_display.setMaximumWidth(int(parent_dialog.width() * 0.75))
        
        if sender == "user":
            self.text_display.setPlainText(text)
        else:
            self.text_display.setHtml(text)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        if self.sender == 'user':
            self.text_display.setStyleSheet(USER_BUBBLE_STYLE)
            layout.addStretch()
            layout.addWidget(self.text_display)
        else:
            self.text_display.setStyleSheet(AI_BUBBLE_STYLE)
            layout.addWidget(self.text_display)
            layout.addStretch()

        self.setLayout(layout)
        
        # 动态调整高度以适应内容
        self.text_display.textChanged.connect(self.update_height)
        self.update_height()

    def set_html(self, html: str):
        self.text_display.setHtml(html)

    def update_height(self):
        """根据内容自动调整 QTextEdit 的高度"""
        # 使用 sizeHint 来获取理想的高度，更加可靠
        doc_height = self.text_display.document().size().height()
        # 增加一些内边距缓冲
        new_height = max(40, int(doc_height) + 10) 
        self.text_display.setFixedHeight(new_height)

class AIExplanationDialog(QDialog):
    def __init__(self, parent, word_to_explain: str):
        super().__init__(parent)
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
        
        # 【优化】应用深色主题样式
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
        self.conversation_widget.setObjectName("conversationWidget") # for styling
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
        # 【优化】将 self (dialog) 传入，以便气泡计算宽度
        bubble = MessageBubble(text, sender, parent_dialog=self)
        self.conversation_layout.insertWidget(self.conversation_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def start_explanation(self):
        system_prompt = (f"你是一个专业的词汇解释助手。请详细解释词汇 '{self.word_to_explain}'，包括其定义、用法、例句、同义词、反义词等。"
                         f"请以清晰、结构化的方式呈现。请务必使用Markdown格式输出，可以灵活使用表格（table）、代码块（code blocks）、列表等来增强可读性。")
        self.conversation_history = [{"role": "system", "content": system_prompt}]
        self.send_message_to_ai()

    def send_message(self):
        user_message = self.user_input.text().strip()
        if not user_message or self.is_streaming:
            if self.is_streaming:
                tooltip("AI正在生成中，请稍候...", period=1000)
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
        self.current_ai_bubble = self._add_message_bubble("...", 'ai') # 使用...作为占位符
        
        self.is_streaming = True
        self.stop_streaming.clear()
        threading.Thread(target=self._stream_api_response, daemon=True).start()
        self.timer = self.startTimer(50)

    def _stream_api_response(self):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        # 【修正】将 "thinking" 参数添加回来
        payload = {
            "model": self.model_name,
            "messages": self.conversation_history,
            "stream": True,
            "thinking": {"type": "disabled"}
        }
        try:
            # The rest of the streaming logic remains the same
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
            # is_streaming is set to False in timerEvent on end

    def timerEvent(self, event):
        # The timer event logic remains largely the same, but simplified
        chunks_to_process = ""
        is_end = False
        end_payload = ""

        while not self.stream_queue.empty():
            chunk = self.stream_queue.get_nowait()
            if "[STREAM_END]" in chunk:
                is_end = True
                end_payload = chunk.replace("[STREAM_END]", "").replace("[STREAM_END_ERROR]", "")
                chunks_to_process += end_payload
                break
            else:
                chunks_to_process += chunk

        if chunks_to_process and self.current_ai_bubble:
            self.current_ai_response_raw_text += chunks_to_process
            # 为 Markdown 表格添加一些基本样式，使其在深色模式下可读
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
            self.current_ai_bubble.set_html(styled_html)
        
        if is_end:
            self.killTimer(self.timer)
            self.current_ai_bubble = None
            self.current_ai_response_raw_text = ""
            self.is_streaming = False
        
        self._scroll_to_bottom()

    def closeEvent(self, event):
        self.stop_streaming.set()
        if hasattr(self, 'timer'):
            self.killTimer(self.timer)
        super().closeEvent(event)

