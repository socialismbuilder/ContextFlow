import aqt
from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QWidget, QApplication, Qt, QTextCursor
from aqt.utils import showInfo, tooltip
import requests
import json
import threading
import queue
import time
import markdown # 导入 Markdown 转换库
from .config_manager import get_config

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
        
        # --- Markdown 渲染相关变量 ---
        self.current_ai_response_raw_text = ""
        self.ai_response_html_start_pos = -1
        # 【新增】定义要使用的 Markdown 扩展
        self.markdown_extensions = ['markdown.extensions.tables', 'markdown.extensions.fenced_code', 'markdown.extensions.nl2br']
        # -----------------------------------

        self.setWindowTitle(f"AI解释: {word_to_explain}")
        self.setMinimumSize(600, 400)

        self.init_ui()
        self.start_explanation()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.explanation_display = QTextEdit()
        self.explanation_display.setReadOnly(True)
        self.explanation_display.setPlaceholderText("AI正在生成解释...")
        main_layout.addWidget(self.explanation_display)
        input_layout = QHBoxLayout()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("输入你的问题...")
        self.user_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.user_input)
        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)
        self.setLayout(main_layout)

    def start_explanation(self):
        # 【优化】在提示词中更明确地要求使用表格和代码块
        system_prompt = (f"你是一个专业的词汇解释助手。请详细解释词汇 '{self.word_to_explain}'，包括其定义、用法、例句、同义词、反义词等。"
                         f"请以清晰、结构化的方式呈现。请务必使用Markdown格式输出，可以灵活使用表格（table）、代码块（code blocks）、列表等来增强可读性。")
        self.conversation_history = [{"role": "system", "content": system_prompt}]
        self.send_message_to_ai()

    def send_message(self):
        user_message = self.user_input.text().strip()
        if not user_message:
            return
        self.user_input.clear()
        escaped_message = user_message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.explanation_display.append(f"<b>你:</b> {escaped_message}<br>")
        self.conversation_history.append({"role": "user", "content": user_message})
        self.send_message_to_ai()

    def send_message_to_ai(self):
        if self.is_streaming:
            tooltip("AI正在生成中，请稍候...", period=1000)
            return
        if not self.api_url or not self.api_key or not self.model_name:
            showInfo("请在配置中设置API URL、API Key和模型名称。")
            return
        self.current_ai_response_raw_text = ""
        self.explanation_display.append("<b>AI:</b> ")
        self.ai_response_html_start_pos = self.explanation_display.textCursor().position()
        self.is_streaming = True
        self.stop_streaming.clear()
        threading.Thread(target=self._stream_api_response, daemon=True).start()
        self.timer = self.startTimer(50) # 可以适当调低间隔，让更新更平滑

    def _stream_api_response(self):
        # ... 此部分代码与之前相同，无需修改 ...
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": self.conversation_history,
            "stream": True,
            "thinking": {"type": "disabled"}
        }
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, stream=True, timeout=60)
            response.raise_for_status()
            full_response_content = ""
            for chunk in response.iter_content(chunk_size=None):
                if self.stop_streaming.is_set():
                    break
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
                            except json.JSONDecodeError:
                                continue
                        if "[DONE]" in line:
                            break
                    if "[DONE]" in chunk_str:
                        break
            if full_response_content:
                self.conversation_history.append({"role": "assistant", "content": full_response_content})
        except requests.exceptions.RequestException as e:
            self.stream_queue.put(f"<br><br><b>错误:</b> 网络请求失败: {e}<br>[STREAM_END_ERROR]")
        except Exception as e:
            self.stream_queue.put(f"<br><br><b>错误:</b> 发生意外错误: {e}<br>[STREAM_END_ERROR]")
        finally:
            # 确保流结束标记被发送
            q_list = list(self.stream_queue.queue)
            if not any(tag in q_list for tag in ["[STREAM_END]", "[STREAM_END_ERROR]"]):
                 self.stream_queue.put("[STREAM_END]")
            self.is_streaming = False


    def timerEvent(self, event):
        chunks_to_process = ""
        while not self.stream_queue.empty():
            chunk = self.stream_queue.get_nowait()
            
            if chunk in ["[STREAM_END]", "[STREAM_END_ERROR]"]:
                self.is_streaming = False # 确保流状态被重置
                if chunks_to_process: # 处理在结束标记前积累的最后内容
                    self.current_ai_response_raw_text += chunks_to_process
                    # 【核心修改】在最终渲染时也使用扩展
                    rendered_html = markdown.markdown(self.current_ai_response_raw_text, extensions=self.markdown_extensions)
                    self._update_explanation_display(rendered_html)
                
                self.killTimer(self.timer)
                if chunk == "[STREAM_END_ERROR]":
                    # 错误信息已经在队列中了，这里无需额外处理，只需确保显示
                    pass
                
                self.current_ai_response_raw_text = ""
                self.ai_response_html_start_pos = -1
                self.explanation_display.append("") # 添加空行
                break
            elif chunk.startswith("<br><br><b>错误:"): # 直接处理错误HTML
                self.explanation_display.insertHtml(chunk)
            else:
                chunks_to_process += chunk

        if chunks_to_process:
            self.current_ai_response_raw_text += chunks_to_process
            # 【核心修改】调用 markdown 时传入 extensions 参数
            rendered_html = markdown.markdown(self.current_ai_response_raw_text, extensions=self.markdown_extensions)
            self._update_explanation_display(rendered_html)

        # 始终确保滚动到底部
        cursor = self.explanation_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.explanation_display.setTextCursor(cursor)
        self.explanation_display.ensureCursorVisible()

    def _update_explanation_display(self, html_content: str):
        # ... 此部分代码与之前相同，无需修改 ...
        cursor = self.explanation_display.textCursor()
        cursor.setPosition(self.ai_response_html_start_pos)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(html_content)
        self.explanation_display.setTextCursor(cursor)
        self.explanation_display.ensureCursorVisible()

    def closeEvent(self, event):
        self.stop_streaming.set()
        if hasattr(self, 'timer'):
            self.killTimer(self.timer)
        super().closeEvent(event)
