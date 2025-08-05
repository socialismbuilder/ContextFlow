# -*- coding: utf-8 -*-

import aqt
from aqt import mw
from aqt.qt import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                    QTextEdit, QScrollArea, QWidget, QFrame, QMessageBox,
                    QApplication, QProgressBar, QComboBox, QTimer)
from .config_manager import get_word_selection_config
from . import word_sentence_generator
from . import main_logic
import time
import re

class SentenceManagementDialog(QDialog):
    """例句管理对话框"""
    
    def __init__(self, word, parent=None):
        super().__init__(parent)
        self.word = word
        self.sentences = []
        self.setup_ui()
        self.generate_sentences()
    
    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle(f'为 "{self.word}" 生成的例句')
        self.setMinimumSize(600, 500)
        self.resize(700, 600)
        
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel(f'为词汇 "{self.word}" 生成的例句')
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)
        
        # 进度条（初始时显示）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 无限进度条
        self.progress_label = QLabel("正在生成例句，请稍候...")
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        
        # 例句显示区域（初始时隐藏）
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.hide()  # 初始隐藏
        layout.addWidget(self.scroll_area)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        
        self.regenerate_button = QPushButton("重新生成")
        self.regenerate_button.clicked.connect(self.regenerate_sentences)
        self.regenerate_button.hide()  # 初始隐藏
        
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.close)
        
        button_layout.addWidget(self.regenerate_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
    
    def generate_sentences(self):
        """生成例句"""
        # 使用现有的线程池进行异步生成
        if main_logic.high_prio_executor:
            future = main_logic.high_prio_executor.submit(
                word_sentence_generator.generate_sentences_for_word, 
                self.word
            )
            
            # 定期检查结果
            self.check_generation_result(future)
        else:
            self.show_error("线程池未初始化，无法生成例句")
    
    def check_generation_result(self, future):
        """检查生成结果"""
        if future.done():
            try:
                sentences = future.result()
                if sentences:
                    self.sentences = sentences
                    self.display_sentences()
                else:
                    self.show_error("生成例句失败，请检查网络连接和API配置")
            except Exception as e:
                self.show_error(f"生成例句时出错: {str(e)}")
        else:
            # 100ms后再次检查
            QTimer.singleShot(100, lambda: self.check_generation_result(future))
    
    def display_sentences(self):
        """显示生成的例句"""
        # 隐藏进度条
        self.progress_bar.hide()
        self.progress_label.hide()
        
        # 显示例句区域
        self.scroll_area.show()
        self.regenerate_button.show()
        
        # 清空之前的内容
        for i in reversed(range(self.scroll_layout.count())):
            self.scroll_layout.itemAt(i).widget().setParent(None)
        
        # 添加例句
        for i, (sentence, translation) in enumerate(self.sentences):
            sentence_widget = self.create_sentence_widget(sentence, translation, i)
            self.scroll_layout.addWidget(sentence_widget)
        
        # 添加弹性空间
        self.scroll_layout.addStretch()
    
    def create_sentence_widget(self, sentence, translation, index):
        """创建单个例句的显示组件"""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.Box)
        frame.setStyleSheet("QFrame { border: 1px solid #ccc; border-radius: 5px; margin: 5px; padding: 10px; }")
        
        layout = QVBoxLayout(frame)
        
        # 例句编号
        number_label = QLabel(f"例句 {index + 1}:")
        number_label.setStyleSheet("font-weight: bold; color: #666;")
        layout.addWidget(number_label)
        
        # 高亮显示目标词汇的例句
        highlighted_sentence = self.highlight_word_in_sentence(sentence, self.word)
        sentence_label = QLabel(highlighted_sentence)
        sentence_label.setWordWrap(True)
        sentence_label.setStyleSheet("font-size: 14px; margin: 5px 0;")
        layout.addWidget(sentence_label)
        
        # 翻译
        translation_label = QLabel(f"翻译: {translation}")
        translation_label.setWordWrap(True)
        translation_label.setStyleSheet("font-size: 12px; color: #666; margin: 5px 0;")
        layout.addWidget(translation_label)
        
        # 添加到ANKI按钮
        add_button = QPushButton("添加到 ANKI")
        add_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; border: none; padding: 5px 10px; border-radius: 3px; }")
        add_button.clicked.connect(lambda: self.add_to_anki(sentence, translation))
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(add_button)
        layout.addLayout(button_layout)
        
        return frame
    
    def highlight_word_in_sentence(self, sentence, word):
        """在例句中高亮显示目标词汇"""
        # 使用正则表达式进行不区分大小写的匹配
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        highlighted = pattern.sub(f'<span style="background-color: #ffeb3b; padding: 2px 4px; border-radius: 3px;"><b>{word}</b></span>', sentence)
        return highlighted
    
    def add_to_anki(self, sentence, translation):
        """添加例句到ANKI"""
        try:
            config = get_word_selection_config()
            target_deck = config.get("target_deck_name", "")
            
            if not target_deck:
                QMessageBox.warning(self, "错误", "请先在设置中配置目标牌组名称")
                return
            
            # 导入ANKI卡片创建模块
            from . import anki_card_creator
            
            success = anki_card_creator.create_word_sentence_card(
                word=self.word,
                sentence=sentence,
                translation=translation,
                deck_name=target_deck
            )
            
            if success:
                QMessageBox.information(self, "成功", f"例句已成功添加到牌组 '{target_deck}'")
            else:
                QMessageBox.warning(self, "失败", "添加例句到ANKI失败，请检查牌组名称是否正确")
                
        except Exception as e:
            print(f"ERROR: 添加到ANKI时出错: {e}")
            QMessageBox.warning(self, "错误", f"添加到ANKI时出错: {str(e)}")
    
    def regenerate_sentences(self):
        """重新生成例句"""
        # 隐藏例句区域，显示进度条
        self.scroll_area.hide()
        self.regenerate_button.hide()
        self.progress_bar.show()
        self.progress_label.show()
        self.progress_label.setText("正在重新生成例句，请稍候...")
        
        # 重新生成
        self.generate_sentences()
    
    def show_error(self, message):
        """显示错误信息"""
        self.progress_bar.hide()
        self.progress_label.setText(f"错误: {message}")
        self.regenerate_button.show()
