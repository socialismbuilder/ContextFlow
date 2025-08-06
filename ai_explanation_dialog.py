import aqt
from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QWidget, QApplication, Qt, QTextCursor
from aqt.utils import showInfo, tooltip
import requests
import json
import threading
import queue
import time
import markdown # <-- 新增导入：Markdown 转换库
from .config_manager import get_config
# from .api_client import fetch_available_models # 如果暂时不用可以注释掉

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

        # --- 新增变量用于 Markdown 渲染 ---
        self.current_ai_response_raw_text = "" # 存储当前 AI 响应的原始 Markdown 文本
        self.ai_response_html_start_pos = -1 # 存储当前 AI 响应在 QTextEdit 中 HTML 内容的起始位置
        # -----------------------------------

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
        system_prompt = f"你是一个专业的词汇解释助手。请详细解释词汇 '{self.word_to_explain}'，包括其定义、用法、例句、同义词、反义词等，并提供中文翻译。请以清晰、结构化的方式呈现，例如使用标题、列表等。请使用Markdown格式输出。" # <-- 提示词中增加Markdown输出要求
        self.conversation_history = [{"role": "system", "content": system_prompt}]
        self.send_message_to_ai()

    def send_message(self):
        user_message = self.user_input.text().strip()
        if not user_message:
            return

        self.user_input.clear()
        # 用户输入以HTML方式追加，避免其内容影响后续Markdown渲染
        escaped_message = user_message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.explanation_display.append(f"<b>你:</b> {escaped_message}<br>") # <br> 用于换行，QTextEdit自动处理
        self.conversation_history.append({"role": "user", "content": user_message})
        self.send_message_to_ai()

    def send_message_to_ai(self):
        if self.is_streaming:
            tooltip("AI正在生成中，请稍候...", period=1000)
            return

        if not self.api_url or not self.api_key or not self.model_name:
            showInfo("请在配置中设置API URL、API Key和模型名称。")
            return

        # --- 新增逻辑：为新的 AI 响应做准备 ---
        self.current_ai_response_raw_text = "" # 清空上一次 AI 响应的原始文本
        self.explanation_display.append("<b>AI:</b> ") # 先添加“AI: ”标签
        # 记录当前光标位置，这是 AI 响应 HTML 内容的起始位置
        self.ai_response_html_start_pos = self.explanation_display.textCursor().position()
        # -----------------------------------

        self.is_streaming = True
        self.stop_streaming.clear() # 重置停止事件

        threading.Thread(target=self._stream_api_response, daemon=True).start()
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
            for chunk in response.iter_content(chunk_size=None):
                if self.stop_streaming.is_set():
                    break
                if chunk:
                    # 使用 decode('utf-8', errors='ignore') 处理可能的不完整 UTF-8 字符
                    chunk_str = chunk.decode('utf-8', errors='ignore')
                    for line in chunk_str.splitlines():
                        if line.startswith("data: "):
                            json_data = line[len("data: "):].strip()
                            if json_data == "[DONE]":
                                # 确保 [DONE] 标记也被放到队列，以便 timerEvent 知道流结束
                                self.stream_queue.put("[STREAM_END]")
                                break # 退出内层循环
                            
                            try:
                                data = json.loads(json_data)
                                delta_content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta_content:
                                    self.stream_queue.put(delta_content) # 将 delta_content 放入队列
                                    full_response_content += delta_content
                            except json.JSONDecodeError:
                                # 可能是部分JSON数据或无效JSON，忽略
                                continue
                        # 如果在某个行中检测到 [DONE]，确保外层循环也退出
                        if "[DONE]" in line:
                            break
                    if "[DONE]" in chunk_str: # 再次检查整个 chunk_str，以防 [DONE] 不在行首
                        break
            
            if full_response_content:
                self.conversation_history.append({"role": "assistant", "content": full_response_content})

        except requests.exceptions.RequestException as e:
            # 错误信息直接放入队列，并标记为 HTML，让 timerEvent 处理
            self.stream_queue.put(f"<br><br><b>错误:</b> 网络请求失败: {e}<br>[STREAM_END_ERROR]")
        except Exception as e:
            self.stream_queue.put(f"<br><br><b>错误:</b> 发生意外错误: {e}<br>[STREAM_END_ERROR]")
        finally:
            # 确保无论如何都发送结束标记，除非已经因为 [DONE] 发送过
            if not self.stream_queue.empty() and self.stream_queue.queue[-1] not in ["[STREAM_END]", "[STREAM_END_ERROR]"]:
                self.stream_queue.put("[STREAM_END]")
            self.is_streaming = False

    def timerEvent(self, event):
        # 从队列中取出数据并更新UI
        while not self.stream_queue.empty():
            chunk = self.stream_queue.get()

            # --- 错误处理和流结束处理 ---
            if chunk == "[STREAM_END]" or chunk == "[STREAM_END_ERROR]":
                self.killTimer(self.timer)
                # 最终更新一次，确保所有内容都被渲染
                if self.current_ai_response_raw_text:
                    self._update_explanation_display(markdown.markdown(self.current_ai_response_raw_text))
                # 如果是错误，就直接显示错误信息
                if chunk == "[STREAM_END_ERROR]":
                    # 队列中已经包含了错误信息的HTML，直接追加
                    pass # 错误信息在 _stream_api_response 已经放入队列，不需要额外处理
                
                # 清理缓冲
                self.current_ai_response_raw_text = ""
                self.ai_response_html_start_pos = -1
                self.explanation_display.append("") # 添加一个空行，视觉上更清晰
                break # 跳出 while 循环，停止处理队列

            # --- 累积原始文本并实时渲染 Markdown ---
            else:
                self.current_ai_response_raw_text += chunk
                # 将累积的 Markdown 文本转换为 HTML
                rendered_html = markdown.markdown(self.current_ai_response_raw_text)
                self._update_explanation_display(rendered_html)

        # 确保滚动到底部，即使没有新内容
        cursor = self.explanation_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.explanation_display.setTextCursor(cursor)
        self.explanation_display.ensureCursorVisible() # 确保光标可见，即滚动到底部

    def _update_explanation_display(self, html_content: str):
        # 获取当前的 QTextEdit 文本光标
        cursor = self.explanation_display.textCursor()
        
        # 保存当前光标的结束位置（方便之后回到这里）
        original_end_pos = cursor.position()

        # 将光标移动到 AI 响应 HTML 内容的起始位置
        # 这是为了选择并替换 AI 正在生成的这部分内容
        cursor.setPosition(self.ai_response_html_start_pos)
        
        # 将光标从起始位置移动到当前文本的末尾，并“保持选中”
        # 这样就选中了从 AI 响应开始到当前所有内容
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        
        # 删除选中的文本（即旧的、不完整的 AI 响应）
        cursor.removeSelectedText()
        
        # 在删除的位置插入新的、渲染好的 HTML 内容
        cursor.insertHtml(html_content)
        
        # 将 QTextEdit 的光标设置回更新后的位置，并确保滚动到新内容的底部
        self.explanation_display.setTextCursor(cursor)


    def closeEvent(self, event):
        self.stop_streaming.set() # 设置停止事件，通知线程停止
        if hasattr(self, 'timer'):
            self.killTimer(self.timer)
        super().closeEvent(event)

# 调试用，可以直接运行这个文件来测试弹窗
if __name__ == "__main__":
    # 为了能在Anki环境外独立运行，需要模拟aqt和config
    try:
        # 尝试导入PyQt6的真实模块
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QTextCursor
    except ImportError:
        # 如果失败，则说明可能在其他环境，这里只是一个示例
        print("请确保已安装 PyQt6 以便独立运行测试: pip install PyQt6")
        exit()

    # 假设的配置获取函数
    def mock_get_config():
        return {
            "api_url": "http://localhost:1234/v1/chat/completions", # 替换为你的本地模型服务地址
            "api_key": "not-needed", # 本地模型通常不需要key
            "model_name": "local-model" # 替换为你的模型名称
        }
    
    # 临时替换get_config，以便在独立运行时测试
    import sys
    # 创建一个假的模块对象并添加到sys.modules中
    mock_config_manager = type('module', (object,), {'get_config': mock_get_config})
    sys.modules['.config_manager'] = mock_config_manager()
    
    # 为了让 import aqt 不报错，也创建一个假的 aqt 模块
    mock_aqt = type('module', (object,), {})
    sys.modules['aqt'] = mock_aqt
    sys.modules['aqt.utils'] = type('module', (object,), {'showInfo': print, 'tooltip': print})
    
    # 将Qt类也挂载到假aqt上，这样类定义中的导入才能成功
    import PyQt6.QtWidgets
    import PyQt6.QtCore
    import PyQt6.QtGui
    mock_qt = type('module', (object,), {
        'QDialog': PyQt6.QtWidgets.QDialog,
        'QVBoxLayout': PyQt6.QtWidgets.QVBoxLayout,
        'QHBoxLayout': PyQt6.QtWidgets.QHBoxLayout,
        'QTextEdit': PyQt6.QtWidgets.QTextEdit,
        'QLineEdit': PyQt6.QtWidgets.QLineEdit,
        'QPushButton': PyQt6.QtWidgets.QPushButton,
        'QLabel': PyQt6.QtWidgets.QLabel,
        'QScrollArea': PyQt6.QtWidgets.QScrollArea,
        'QWidget': PyQt6.QtWidgets.QWidget,
        'QApplication': PyQt6.QtWidgets.QApplication,
        'Qt': PyQt6.QtCore.Qt,
        'QTextCursor': PyQt6.QtGui.QTextCursor, # 确保QTextCursor可用
    })
    sys.modules['aqt.qt'] = mock_qt
    
    app = QApplication(sys.argv)
    
    dialog = AIExplanationDialog(None, "anki")
    dialog.show()
    sys.exit(app.exec())

