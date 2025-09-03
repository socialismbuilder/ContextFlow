import time
import traceback
import os
import json

import aqt
from aqt.qt import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QGroupBox, QHBoxLayout, QWidget, QDialogButtonBox, QMessageBox, QApplication,
    QTabWidget, QTextEdit, QSplitter, Qt, QGridLayout, QCompleter, QScrollArea
)
from .config_manager import get_config, save_config
from . import api_client
from . import main_logic # 导入 main_logic 以便调用线程池

# Custom ComboBox to ignore wheel events
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

def setup_prompt_template_tab(parent_dialog, layout, config):
    prompt_group = QGroupBox("提示词编辑")
    prompt_layout = QVBoxLayout()

    help_label = QLabel("提示词编辑器用于编辑测试自定义提示词。可以使用以下占位符：")
    help_label.setWordWrap(True)
    prompt_layout.addWidget(help_label)

    grid_layout = QGridLayout()
    grid_layout.addWidget(QLabel("{world}:关键词"), 0, 0)
    grid_layout.addWidget(QLabel("{language}:学习语言"), 0, 1)
    grid_layout.addWidget(QLabel("{vocab_level}:词汇量等级"), 0, 2)

    grid_layout.addWidget(QLabel("{learning_goal}:学习目标"), 1, 0)
    grid_layout.addWidget(QLabel("{difficulty_level}:句子难度"), 1, 1)
    grid_layout.addWidget(QLabel("{sentence_length_desc}:句子长度"), 1, 2)

    grid_layout.addWidget(QLabel("{second_keywords}:第二关键词"), 2, 0)

    prompt_layout.addLayout(grid_layout)

    edit_prompt_layout = QHBoxLayout()
    edit_prompt = QLabel("提示词编辑:")
    edit_prompt_layout.addWidget(edit_prompt)

    parent_dialog.prompt_source_combo = NoWheelComboBox()
    current_config = get_config()
    custom_prompts = current_config.get("custom_prompts", {})
    parent_dialog.prompt_source_combo.addItems(
        ["默认-不标记目标词", "默认-标记目标词"] + list(custom_prompts.keys()) + ["空"])
    edit_prompt_layout.addWidget(parent_dialog.prompt_source_combo)

    parent_dialog.delete_prompt_btn = QPushButton("删除")
    parent_dialog.delete_prompt_btn.clicked.connect(lambda: delete_selected_prompt(parent_dialog))
    edit_prompt_layout.addWidget(parent_dialog.delete_prompt_btn)
    prompt_layout.addLayout(edit_prompt_layout)

    parent_dialog.prompt_template_edit = QTextEdit()
    parent_dialog.prompt_template_edit.setMinimumHeight(200)
    prompt_layout.addWidget(parent_dialog.prompt_template_edit)

    save_layout = QHBoxLayout()
    save_layout.addWidget(QLabel("存储名:"))
    parent_dialog.prompt_name_edit = QLineEdit()
    save_layout.addWidget(parent_dialog.prompt_name_edit)
    parent_dialog.save_prompt_btn = QPushButton("保存")
    parent_dialog.save_prompt_btn.clicked.connect(lambda: save_custom_prompt(parent_dialog))
    save_layout.addWidget(parent_dialog.save_prompt_btn)
    prompt_layout.addLayout(save_layout)

    parent_dialog.prompt_source_combo.currentTextChanged.connect(lambda source: load_selected_prompt(parent_dialog, source))
    load_selected_prompt(parent_dialog, parent_dialog.prompt_source_combo.currentText())

    test_group = QGroupBox("提示词测试")
    test_layout = QVBoxLayout()
    test_input_layout = QHBoxLayout()
    keyword_layout = QVBoxLayout()
    keyword_label = QLabel("测试关键词:")
    keyword_layout.addWidget(keyword_label)
    parent_dialog.test_keyword_edit = QLineEdit()
    parent_dialog.test_keyword_edit.setText("example")
    keyword_layout.addWidget(parent_dialog.test_keyword_edit)

    test_mode_layout = QHBoxLayout()

    test_mode_label = QLabel("测试模式:")
    test_mode_layout.addWidget(test_mode_label)
    parent_dialog.test_mode_combo = NoWheelComboBox()
    parent_dialog.test_mode_combo.addItems(["生成例句", "查看提示词"])
    test_mode_layout.addWidget(parent_dialog.test_mode_combo)
    test_mode_layout.addStretch()
    parent_dialog.test_prompt_button = QPushButton("测试")
    parent_dialog.test_prompt_button.clicked.connect(lambda: test_prompt_template(parent_dialog))
    test_mode_layout.addWidget(parent_dialog.test_prompt_button)
    test_mode_layout.setSpacing(10)
    keyword_layout.addLayout(test_mode_layout)

    test_input_layout.addLayout(keyword_layout)
    test_result_label = QLabel("测试结果:")
    test_layout.addWidget(test_result_label)
    parent_dialog.test_result_edit = QTextEdit()
    parent_dialog.test_result_edit.setReadOnly(True)
    parent_dialog.test_result_edit.setMinimumHeight(150)
    test_layout.addWidget(parent_dialog.test_result_edit)
    test_layout.addLayout(test_input_layout)
    test_group.setLayout(test_layout)
    prompt_group.setLayout(prompt_layout)
    layout.addWidget(prompt_group)
    layout.addWidget(test_group)

def load_selected_prompt(parent_dialog, source):
    config = get_config()
    custom_prompts = config.get("custom_prompts", {})

    if source == "默认-不标记目标词":
        content = api_client.DEFAULT_PROMPT_TEMPLATE + api_client.DEFAULT_FORMAT_NORMAL
        parent_dialog.prompt_name_edit.setText("自定义提示词")
    elif source == "默认-标记目标词":
        content = api_client.DEFAULT_PROMPT_TEMPLATE + api_client.DEFAULT_FORMAT_HIGHLIGHT
        parent_dialog.prompt_name_edit.setText("自定义提示词")
    elif source == "空":
        content = ""
        parent_dialog.prompt_name_edit.setText("自定义提示词")
    else:
        content = custom_prompts.get(source, "")
        parent_dialog.prompt_name_edit.setText(source)

    parent_dialog.prompt_template_edit.setPlainText(content)

def delete_selected_prompt(parent_dialog):
    selected = parent_dialog.prompt_source_combo.currentText()

    if selected in ["默认-不标记目标词", "默认-标记目标词", "空"]:
        QMessageBox.warning(parent_dialog, "错误", f"不能删除 {selected} 提示词")
        return

    reply = QMessageBox.question(
        parent_dialog, "确认删除",
        f"确定要删除提示词 '{selected}' 吗？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    config = get_config()
    custom_prompts = config.get("custom_prompts", {})
    if selected in custom_prompts:
        del custom_prompts[selected]
        config["custom_prompts"] = custom_prompts
        save_config(config)

        parent_dialog.prompt_source_combo.removeItem(parent_dialog.prompt_source_combo.findText(selected))
        parent_dialog.prompt_source_combo.setCurrentText("默认-不标记目标词")
        load_selected_prompt(parent_dialog, "默认-不标记目标词")
        QMessageBox.information(parent_dialog, "成功", "提示词删除完成")
    else:
        QMessageBox.warning(parent_dialog, "错误", "未找到该存储提示词")
    
    current_items = ["默认-不标记目标词", "默认-标记目标词"] + list(custom_prompts.keys())
    parent_dialog.prompt_name_combo.clear()
    parent_dialog.prompt_name_combo.addItems(current_items)
    saved_prompt_selection = config.get("prompt_name", "默认-不标记目标词")
    if saved_prompt_selection in current_items:
        parent_dialog.prompt_name_combo.setCurrentText(saved_prompt_selection)
    else:
        parent_dialog.prompt_name_combo.setCurrentText("默认-不标记目标词")

def save_custom_prompt(parent_dialog):
    prompt_name = parent_dialog.prompt_name_edit.text().strip()
    prompt_content = parent_dialog.prompt_template_edit.toPlainText()

    if not prompt_name:
        QMessageBox.warning(parent_dialog, "错误", "存储名不能为空")
        return

    if prompt_name in ["默认-不标记目标词", "默认-标记目标词", "空"]:
        prompt_name = "自定义提示词"
        parent_dialog.prompt_name_edit.setText(prompt_name)

    config = get_config()
    custom_prompts = config.get("custom_prompts", {})
    custom_prompts[prompt_name] = prompt_content
    config["custom_prompts"] = custom_prompts
    save_config(config)

    current_items = ["默认-不标记目标词", "默认-标记目标词"] + list(custom_prompts.keys()) + ["空"]
    parent_dialog.prompt_source_combo.clear()
    parent_dialog.prompt_source_combo.addItems(current_items)
    parent_dialog.prompt_source_combo.setCurrentText(prompt_name)
    load_selected_prompt(parent_dialog, prompt_name)

    current_items = ["默认-不标记目标词", "默认-标记目标词"] + list(custom_prompts.keys())
    parent_dialog.prompt_name_combo.clear()
    parent_dialog.prompt_name_combo.addItems(current_items)
    saved_prompt_selection = config.get("prompt_name", "默认-不标记目标词")
    if saved_prompt_selection in current_items:
        parent_dialog.prompt_name_combo.setCurrentText(saved_prompt_selection)
    else:
        parent_dialog.prompt_name_combo.setCurrentText("默认-不标记目标词")

    QMessageBox.information(parent_dialog, "成功", "提示词保存完成")

def test_prompt_template(parent_dialog):
    keyword = parent_dialog.test_keyword_edit.text()
    if not keyword:
        parent_dialog.test_result_edit.setText("请输入测试关键词")
        return

    prompt = parent_dialog.prompt_template_edit.toPlainText()
    test_config = get_config()
    second_keywords_str = "strand,exasperated,grudgingly,guerrilla,parish,extent,casino,carousel,hypocritical,hunch"
    second_keywords_str = "- 在保证句子流畅的前提下，可以在每个例句中尝试融入若干以下词汇（" + second_keywords_str + "），不限制每句融入几个，也不强制融入，但必须以句子自然流畅为前提。"
    try:
        formatted_prompt = prompt.format(
            world=keyword,
            vocab_level=test_config["vocab_level"],
            learning_goal=test_config["learning_goal"],
            difficulty_level=test_config["difficulty_level"],
            sentence_length_desc=test_config["sentence_length_desc"],
            language=test_config["learning_language"],
            second_keywords=second_keywords_str
        )
    except Exception as e:
        parent_dialog.test_result_edit.setText(f"提示词格式化错误: {str(e)}")
        return

    test_mode = parent_dialog.test_mode_combo.currentText()

    if test_mode == "查看提示词":
        parent_dialog.test_result_edit.setText(formatted_prompt)
        return

    if not test_config["api_url"] or not test_config["api_key"] or not test_config["model_name"]:
        parent_dialog.test_result_edit.setText("错误: 请先在基本设置中配置API信息（URL、密钥和模型名称）")
        return

    parent_dialog.test_result_edit.setText("正在生成例句，请稍候...")
    parent_dialog.test_prompt_button.setEnabled(False)
    QApplication.processEvents()

    future = main_logic.executor.submit(
        api_client.get_api_response,
        test_config,
        formatted_prompt
    )

    def handle_result(future):
        aqt.mw.taskman.run_on_main(lambda: _handle_future(parent_dialog, future, keyword))

    future.add_done_callback(handle_result)

def _handle_future(parent_dialog, future, keyword):
    try:
        api_response = future.result()
        text_content = api_client.get_message_content(api_response, keyword)
        sentence_pairs = api_client.parse_message_content_to_sentence_pairs(text_content, keyword)

        if not sentence_pairs:
            parent_dialog.test_result_edit.setText("例句生成失败，原始输出内容为：\n" + text_content)
            return

        result_text = f"关键词 '{keyword}' 的例句测试结果：\n\n"
        for i, (sentence, translation) in enumerate(sentence_pairs, 1):
            result_text += f"\n例句 {i}:\n{sentence}\n翻译:\n{translation}\n"

        parent_dialog.test_result_edit.setText(result_text)
    except Exception as e:
        parent_dialog.test_result_edit.setText(f"测试错误: {str(e)}")
        traceback.print_exc()
    finally:
        parent_dialog.test_prompt_button.setEnabled(True)
        QApplication.processEvents()
