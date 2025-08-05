import aqt
# 1. 在这里添加 QTextCursor 的导入
from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QWidget, QApplication, Qt, QTextCursor
from aqt.utils import showInfo, tooltip
import requests
import json
import threading
import queue
import time
from .config_manager import get_config # 假设config_manager在同一包中
# from .api_client import fetch_available_models # 导入获取模型列表的函数 - 如果暂时不用可以注释掉

class AIExplanationDialog(QDialog):
    def __init__(self, parent, word_to_explain: str):
        super().__init__(parent)
        self.word_to_explain = word_to_explain
        self.config = get_config()
        self.api_url = self.config.get("api_url")
        self.api_key = self.config.get("api_key")
        self.model_name = self.config.get("model_name")
        self.conversation_history = [] # 存储对话历史
        self.stream_queue = queue.Queue()
        self.stop_streaming = threading.Event()
        self.is_streaming = False

        self.setWindowTitle(f"AI解释: {word_to_explain}")
        self.setMinimumSize(600, 400)

        self.init_ui()
        self.start_explanation()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # AI解释显示区域
        self.explanation_display = QTextEdit()
        self.explanation_display.setReadOnly(True)
        self.explanation_display.setPlaceholderText("AI正在生成解释...")
        main_layout.addWidget(self.explanation_display)

        # 对话输入区域
        input_layout = QHBoxLayout()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("输入你的问题...")
        self.user_input.returnPressed.connect(self.send_message) # 回车发送
        input_layout.addWidget(self.user_input)

        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

        self.setLayout(main_layout)

    def start_explanation(self):
        # 初始解释的系统提示词
        system_prompt = f"你是一个专业的词汇解释助手。请详细解释词汇 '{self.word_to_explain}'，包括其定义、用法、例句、同义词、反义词等，并提供中文翻译。请以清晰、结构化的方式呈现，例如使用标题、列表等。"
        self.conversation_history = [{"role": "system", "content": system_prompt}]
        self.send_message_to_ai()

    def send_message(self):
        user_message = self.user_input.text().strip()
        if not user_message:
            return

        self.user_input.clear()
        # 使用HTML实体转义，防止用户输入HTML标签
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

        self.explanation_display.append("<b>AI:</b> ")
        self.is_streaming = True
        self.stop_streaming.clear() # 重置停止事件

        # 在新线程中执行API请求
        threading.Thread(target=self._stream_api_response, daemon=True).start()
        # 启动一个定时器来处理队列中的数据并更新UI
        self.timer = self.startTimer(100) # 每100ms检查一次队列

    def _stream_api_response(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": self.conversation_history,
            "stream": True,
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, stream=True, timeout=60)
            response.raise_for_status()

            full_response_content = ""
            for chunk in response.iter_content(chunk_size=None): # 使用 None 让 requests 决定块大小
                if self.stop_streaming.is_set():
                    break
                if chunk:
                    chunk_str = chunk.decode('utf-8', errors='ignore')
                    for line in chunk_str.splitlines():
                        if line.startswith("data: "):
                            json_data = line[len("data: "):].strip()
                            if json_data == "[DONE]":
                                break
                            
                            try:
                                data = json.loads(json_data)
                                delta_content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta_content:
                                    self.stream_queue.put(delta_content)
                                    full_response_content += delta_content
                            except json.JSONDecodeError:
                                # 可能是部分JSON数据，忽略并等待下一个块
                                continue
                        # 如果处理了[DONE]，则跳出外层循环
                        if "data: [DONE]" in line:
                            break
            
            if full_response_content:
                self.conversation_history.append({"role": "assistant", "content": full_response_content})

        except requests.exceptions.RequestException as e:
            self.stream_queue.put(f"<br><br><b>错误:</b> 网络请求失败: {e}<br>")
        except Exception as e:
            self.stream_queue.put(f"<br><br><b>错误:</b> 发生意外错误: {e}<br>")
        finally:
            self.stream_queue.put("[STREAM_END]") # 标记流结束
            self.is_streaming = False

    def timerEvent(self, event):
        # 从队列中取出数据并更新UI
        while not self.stream_queue.empty():
            chunk = self.stream_queue.get()
            if chunk == "[STREAM_END]":
                self.killTimer(self.timer)
                self.explanation_display.append("") # 添加一个空行，视觉上更清晰
                # 再次确保滚动到底部
                cursor = self.explanation_display.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End) # <--- 【核心修改】
                self.explanation_display.setTextCursor(cursor)
                break
            else:
                # 如果块是错误信息，使用 insertHtml
                if chunk.startswith("<br><br><b>错误:"):
                    self.explanation_display.insertHtml(chunk)
                else:
                    self.explanation_display.insertPlainText(chunk)
                
                # 自动滚动到底部
                cursor = self.explanation_display.textCursor()
                # 2. 【核心修改】使用正确的 PyQt6 枚举常量
                # 旧代码: cursor.movePosition(cursor.End)
                # 新代码:
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.explanation_display.setTextCursor(cursor)

    def closeEvent(self, event):
        self.stop_streaming.set() # 设置停止事件，通知线程停止
        if hasattr(self, 'timer'):
            self.killTimer(self.timer)
        super().closeEvent(event)
