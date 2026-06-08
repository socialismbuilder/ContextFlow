import time
import traceback
import os
import json
import threading

import aqt
from aqt.qt import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QGroupBox, QHBoxLayout, QWidget, QDialogButtonBox, QMessageBox, QApplication,
    QTabWidget, QTextEdit, QSplitter, Qt, QGridLayout, QCompleter, QScrollArea,
    QCheckBox, QSpinBox
)
from ..config_manager import get_config, save_config
from ..cache.cache_manager import clear_cache
from .. import api_client
from ..card.card_template_manager import update_card_templates
from PyQt6.QtCore import QTimer

# Custom ComboBox to ignore wheel events
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

def add_api_setting(parent_dialog, basic_layout, current_config):
    api_group = QGroupBox("API 设置")
    api_layout = QFormLayout()

    PRESET_API_URLS = current_config.get("preset_api_urls")
    parent_dialog.api_provider_combo = NoWheelComboBox()
    parent_dialog.api_provider_combo.addItems(PRESET_API_URLS.keys())
    api_layout.addRow("API 提供商:", parent_dialog.api_provider_combo)

    parent_dialog.api_url = QLineEdit()
    api_layout.addRow("API 接口地址:", parent_dialog.api_url)

    saved_api_url = current_config.get("api_url", "")
    provider_match = False
    for provider, url in PRESET_API_URLS.items():
        if url == saved_api_url and provider != "自定义":
            parent_dialog.api_provider_combo.setCurrentText(provider)
            provider_match = True
            break
    if not provider_match and saved_api_url:
        parent_dialog.api_provider_combo.setCurrentText("自定义")
    elif not saved_api_url and "火山/豆包/字节（推荐）" in PRESET_API_URLS:
        parent_dialog.api_provider_combo.setCurrentText("火山/豆包/字节（推荐）")

    _on_api_provider_changed(parent_dialog)
    parent_dialog.api_url.setText(saved_api_url)
    parent_dialog.api_provider_combo.currentTextChanged.connect(lambda: _on_api_provider_changed(parent_dialog))

    parent_dialog.api_key = QLineEdit(current_config.get("api_key", ""))
    parent_dialog.api_key.setEchoMode(QLineEdit.EchoMode.Password)
    api_layout.addRow("API 密钥:", parent_dialog.api_key)

    parent_dialog.model_name = NoWheelComboBox()
    parent_dialog.model_name.setEditable(True)
    parent_dialog.model_name.setEditText(current_config.get("model_name", ""))

    parent_dialog.model_completer = QCompleter([])
    parent_dialog.model_completer.setFilterMode(Qt.MatchFlag.MatchContains)
    parent_dialog.model_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    parent_dialog.model_name.setCompleter(parent_dialog.model_completer)

    parent_dialog.refresh_models_btn = QPushButton("刷新")
    parent_dialog.refresh_models_btn.clicked.connect(lambda: _refresh_model_list(parent_dialog, force=True))

    model_widget = QWidget()
    model_layout = QHBoxLayout(model_widget)
    model_layout.setContentsMargins(0, 0, 0, 0)
    model_layout.addWidget(parent_dialog.model_name)
    model_layout.addWidget(parent_dialog.refresh_models_btn)
    api_layout.addRow("模型名称:", model_widget)

    parent_dialog.test_connection_button = QPushButton("测试 API 连接")
    parent_dialog.test_connection_button.clicked.connect(lambda: _test_api_connection(parent_dialog))
    parent_dialog.test_status_label = QLabel("点击按钮测试连接状态")
    parent_dialog.test_status_label.setWordWrap(True)

    test_layout = QHBoxLayout()
    test_layout.addWidget(parent_dialog.test_connection_button)
    test_layout.addWidget(parent_dialog.test_status_label)
    api_layout.addRow(test_layout)

    api_group.setLayout(api_layout)
    basic_layout.addWidget(api_group)
    _refresh_model_list(parent_dialog)

def add_Preferences_setting(parent_dialog, basic_layout, current_config):
    prefs_group = QGroupBox("句子生成偏好")
    prefs_layout = QFormLayout()

    parent_dialog.vocab_level_combo = NoWheelComboBox()
    PRESET_VOCAB_LEVELS = current_config.get("preset_vocab_levels")
    parent_dialog.vocab_level_combo.addItems(PRESET_VOCAB_LEVELS)
    current_vocab = current_config.get("vocab_level", "大学英语四级 CET-4 (4000词)")
    parent_dialog.vocab_level_custom = None
    if current_vocab not in PRESET_VOCAB_LEVELS[:-1]:
        parent_dialog.vocab_level_combo.setCurrentText("自定义")
        parent_dialog.vocab_level_custom = QLineEdit(current_vocab)
    else:
        parent_dialog.vocab_level_combo.setCurrentText(current_vocab)
    prefs_layout.addRow("词汇量等级:", parent_dialog.vocab_level_combo)
    if parent_dialog.vocab_level_custom:
        prefs_layout.addRow("", parent_dialog.vocab_level_custom)
    parent_dialog.vocab_level_combo.currentIndexChanged.connect(lambda: _handle_custom_change(parent_dialog, parent_dialog.vocab_level_combo, 'vocab_level_custom', _get_form_layout(parent_dialog.vocab_level_combo)))
    _toggle_custom_widget(parent_dialog.vocab_level_combo, parent_dialog.vocab_level_custom, _get_form_layout(parent_dialog.vocab_level_combo))

    parent_dialog.learning_goal_combo = NoWheelComboBox()
    PRESET_LEARNING_GOALS = current_config.get("preset_learning_goals")
    parent_dialog.learning_goal_combo.addItems(PRESET_LEARNING_GOALS)
    current_goal = current_config.get("learning_goal", "提升日常浏览英文网页与资料的流畅度")
    parent_dialog.learning_goal_custom = None
    if current_goal not in PRESET_LEARNING_GOALS[:-1]:
        parent_dialog.learning_goal_combo.setCurrentText("自定义")
        parent_dialog.learning_goal_custom = QLineEdit(current_goal)
    else:
        parent_dialog.learning_goal_combo.setCurrentText(current_goal)
    prefs_layout.addRow("学习目标:", parent_dialog.learning_goal_combo)
    if parent_dialog.learning_goal_custom:
        prefs_layout.addRow("", parent_dialog.learning_goal_custom)
    parent_dialog.learning_goal_combo.currentIndexChanged.connect(lambda: _handle_custom_change(parent_dialog, parent_dialog.learning_goal_combo, 'learning_goal_custom', _get_form_layout(parent_dialog.learning_goal_combo)))
    _toggle_custom_widget(parent_dialog.learning_goal_combo, parent_dialog.learning_goal_custom, _get_form_layout(parent_dialog.learning_goal_combo))

    parent_dialog.difficulty_combo = NoWheelComboBox()
    PRESET_DIFFICULTIES = current_config.get("preset_difficulties")
    parent_dialog.difficulty_combo.addItems(PRESET_DIFFICULTIES)
    current_diff = current_config.get("difficulty_level","中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围")
    parent_dialog.difficulty_custom = None
    if current_diff not in PRESET_DIFFICULTIES[:-1]:
        parent_dialog.difficulty_combo.setCurrentText("自定义")
        parent_dialog.difficulty_custom = QLineEdit(current_diff)
    else:
        parent_dialog.difficulty_combo.setCurrentText(current_diff)
    prefs_layout.addRow("句子难度:", parent_dialog.difficulty_combo)
    if parent_dialog.difficulty_custom:
        prefs_layout.addRow("", parent_dialog.difficulty_custom)
    parent_dialog.difficulty_combo.currentIndexChanged.connect(lambda: _handle_custom_change(parent_dialog, parent_dialog.difficulty_combo, 'difficulty_custom', _get_form_layout(parent_dialog.difficulty_combo)))
    _toggle_custom_widget(parent_dialog.difficulty_combo, parent_dialog.difficulty_custom, _get_form_layout(parent_dialog.difficulty_combo))

    PRESET_LENGTHS = current_config.get("preset_lengths")
    parent_dialog.length_combo = NoWheelComboBox()
    parent_dialog.length_combo.addItems(PRESET_LENGTHS)
    current_length = current_config.get("sentence_length_desc","中等长度句 (约25-40词): 通用对话及文章常用长度")
    parent_dialog.length_custom = None
    if current_length not in PRESET_LENGTHS[:-1]:
        parent_dialog.length_combo.setCurrentText("自定义")
        parent_dialog.length_custom = QLineEdit(current_length)
    else:
        parent_dialog.length_combo.setCurrentText(current_length)
    prefs_layout.addRow("句子长度:", parent_dialog.length_combo)
    if parent_dialog.length_custom:
        prefs_layout.addRow("", parent_dialog.length_custom)
    parent_dialog.length_combo.currentIndexChanged.connect(lambda: _handle_custom_change(parent_dialog, parent_dialog.length_combo, 'length_custom', _get_form_layout(parent_dialog.length_combo)))
    _toggle_custom_widget(parent_dialog.length_combo, parent_dialog.length_custom, _get_form_layout(parent_dialog.length_combo))

    prefs_group.setLayout(prefs_layout)
    basic_layout.addWidget(prefs_group)

def add_othersetting(parent_dialog, basic_layout, current_config):
    # ── 提前创建 learning_language_combo（TTS 信号需要引用） ──────
    parent_dialog.learning_language_combo = NoWheelComboBox()
    languages = ["英语", "法语", "日语", "西班牙语", "德语", "韩语", "俄语", "意大利语", "葡萄牙语", "阿拉伯语", "印地语"]
    parent_dialog.learning_language_combo.addItems(languages)
    saved_language = current_config.get("learning_language", "英语")
    if saved_language in languages:
        parent_dialog.learning_language_combo.setCurrentText(saved_language)
    else:
        parent_dialog.learning_language_combo.setCurrentText("英语")

    # ── TTS 设置（独立分组） ─────────────────────────────────────
    tts_group = QGroupBox("TTS 语音")
    tts_layout = QFormLayout()

    parent_dialog.tts_engine_combo = NoWheelComboBox()
    tts_engine_labels = {
        "edge_tts": "Edge TTS (高质量高延时)",
        "apple_tts": "Apple TTS (按语言跟随 macOS voice，无缓存)",
        "anki_native": "Anki 原生 TTS (低质量低延时)",
        "custom_url": "自定义 URL",
    }
    parent_dialog.tts_engine_combo.addItems(tts_engine_labels.values())
    saved_tts = current_config.get("tts_engine", "edge_tts")
    saved_tts_label = tts_engine_labels.get(saved_tts, "Edge TTS (高质量高延时)")
    parent_dialog.tts_engine_combo.setCurrentText(saved_tts_label)

    # Edge TTS voice picker
    parent_dialog.edge_voice_combo = NoWheelComboBox()
    saved_language_for_voice = current_config.get("learning_language", "英语")
    override_key = f"edge_tts_voice_{saved_language_for_voice}"
    saved_voice = current_config.get(override_key, "")
    _populate_voice_combo(parent_dialog, saved_language_for_voice, saved_voice)
    parent_dialog.edge_voice_combo.setVisible(saved_tts == "edge_tts")

    parent_dialog.tts_custom_url = QLineEdit(current_config.get("tts_custom_url", ""))
    parent_dialog.tts_custom_url.setPlaceholderText("POST {text, voice, language} → 返回音频文件")
    parent_dialog.tts_custom_url.setVisible(saved_tts == "custom_url")

    tts_layout.addRow("TTS 引擎:", parent_dialog.tts_engine_combo)
    tts_layout.addRow("Edge 人声:", parent_dialog.edge_voice_combo)
    tts_layout.addRow("", parent_dialog.tts_custom_url)

    def _on_tts_engine_changed(text):
        parent_dialog.tts_custom_url.setVisible("自定义" in text)
        parent_dialog.edge_voice_combo.setVisible("Edge" in text)

    parent_dialog.tts_engine_combo.currentTextChanged.connect(_on_tts_engine_changed)

    # Refresh voice list when learning language changes
    parent_dialog.learning_language_combo.currentTextChanged.connect(
        lambda lang: _on_learning_language_changed(parent_dialog, lang)
    )

    parent_dialog.tts_replace_audio = QCheckBox("替代卡片原有声音（自动朗读例句）")
    parent_dialog.tts_replace_audio.setChecked(current_config.get("tts_replace_audio", False))
    tts_layout.addRow("", parent_dialog.tts_replace_audio)

    tts_group.setLayout(tts_layout)
    basic_layout.addWidget(tts_group)

    # ── Web 后端设置（独立分组） ─────────────────────────────────
    web_group = QGroupBox("Web 后端（手机复习）")
    web_layout = QFormLayout()

    parent_dialog.web_enabled = QCheckBox("启用 Web 后端服务")
    parent_dialog.web_enabled.setChecked(current_config.get("web_enabled", True))

    parent_dialog.web_port = QSpinBox()
    parent_dialog.web_port.setRange(1024, 65535)
    parent_dialog.web_port.setValue(current_config.get("web_port", 8765))

    web_row = QWidget()
    web_row_layout = QHBoxLayout(web_row)
    web_row_layout.setContentsMargins(0, 0, 0, 0)
    web_row_layout.addWidget(parent_dialog.web_enabled, 1)
    web_row_layout.addWidget(QLabel("端口:"))
    web_row_layout.addWidget(parent_dialog.web_port, 1)
    web_layout.addRow(web_row)

    def _on_web_enabled_changed(checked):
        parent_dialog.web_port.setEnabled(checked)
    parent_dialog.web_enabled.toggled.connect(_on_web_enabled_changed)
    _on_web_enabled_changed(parent_dialog.web_enabled.isChecked())

    web_group.setLayout(web_layout)
    basic_layout.addWidget(web_group)

    # ── 其他 ──────────────────────────────────────────────────────
    other_group = QGroupBox("其他")
    other_layout = QFormLayout()

    parent_dialog.deck_name = QLineEdit(current_config.get("deck_name", ""))
    other_layout.addRow("目标牌组名称:", parent_dialog.deck_name)

    parent_dialog.save_deck = QLineEdit(current_config.get("save_deck", "这里填写收藏例句的牌组"))
    other_layout.addRow("收藏牌组名称:", parent_dialog.save_deck)

    parent_dialog.prompt_name_combo = NoWheelComboBox()
    custom_prompts = current_config.get("custom_prompts", {})
    prompt_choices = ["默认-不标记目标词", "默认-标记目标词"] + list(custom_prompts.keys())
    parent_dialog.prompt_name_combo.addItems(prompt_choices)

    saved_prompt_selection = current_config.get("prompt_name", "默认-不标记目标词")
    if saved_prompt_selection in prompt_choices:
        parent_dialog.prompt_name_combo.setCurrentText(saved_prompt_selection)
    else:
        parent_dialog.prompt_name_combo.setCurrentText("默认-不标记目标词")

    learning_options_layout = QHBoxLayout()
    learning_options_layout.addWidget(QLabel("学习语言:"))
    learning_options_layout.addWidget(parent_dialog.learning_language_combo)
    learning_options_layout.addSpacing(20)
    learning_options_layout.addWidget(QLabel("提示词选择:"))
    learning_options_layout.addWidget(parent_dialog.prompt_name_combo)
    learning_options_layout.addStretch()

    other_layout.addRow("学习选项:", learning_options_layout)

    # 添加字体选择
    parent_dialog.font_combo = NoWheelComboBox()
    PRESET_FONTS = current_config.get("preset_fonts", ["默认字体", "tms论文字体", "考试字体（衬线）"])
    parent_dialog.font_combo.addItems(PRESET_FONTS)
    saved_font = current_config.get("font_family", "默认字体")
    if saved_font in PRESET_FONTS:
        parent_dialog.font_combo.setCurrentText(saved_font)
    else:
        parent_dialog.font_combo.setCurrentText("默认字体")

    # 连接字体变化事件，以便更新卡片模板
    parent_dialog.font_combo.currentTextChanged.connect(lambda: _on_font_changed(parent_dialog))

    other_layout.addRow("字体选择:", parent_dialog.font_combo)

    other_group.setLayout(other_layout)
    basic_layout.addWidget(other_group)

    basic_layout.addStretch()

    # Kick off Edge TTS voice list fetch in background; refresh combo when done
    from ..tts.tts_manager import ensure_voice_list_loaded
    ensure_voice_list_loaded()

    def _refresh_voice_combo_after_load():
        """Wait for voice list to load, then refresh the combo on the main thread."""
        from ..tts.tts_manager import _voice_list_lock, _cached_voice_list
        for _ in range(50):  # poll every 100ms, up to 5 seconds
            with _voice_list_lock:
                if _cached_voice_list:
                    break
            time.sleep(0.1)
        QTimer.singleShot(0, lambda: _populate_voice_combo(
            parent_dialog,
            parent_dialog.learning_language_combo.currentText(),
            parent_dialog.edge_voice_combo.currentData() or "",
        ))

    threading.Thread(target=_refresh_voice_combo_after_load, daemon=True).start()

    del_cache_btn = QPushButton("删除缓存")
    del_cache_btn.clicked.connect(lambda: clear_cache_and_notify(parent_dialog))

    parent_dialog.button_box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    parent_dialog.button_box.accepted.connect(parent_dialog.save_and_close)
    parent_dialog.button_box.rejected.connect(parent_dialog.reject)

    button_layout = QHBoxLayout()
    button_layout.addWidget(del_cache_btn)
    button_layout.addStretch()
    button_layout.addWidget(parent_dialog.button_box)
    basic_layout.addLayout(button_layout)

def clear_cache_and_notify(parent_dialog):
    try:
        clear_cache()
        # QMessageBox.information(parent_dialog, "成功", "缓存已成功清除。")
    except Exception as e:
        QMessageBox.warning(parent_dialog, "错误", f"清除缓存时出错: {e}")

def _on_api_provider_changed(parent_dialog):
    provider = parent_dialog.api_provider_combo.currentText()
    if provider == "自定义":
        parent_dialog.api_url.setReadOnly(False)
        parent_dialog.api_url.setPlaceholderText("请输入自定义 API URL")
    else:
        PRESET_API_URLS = get_config().get("preset_api_urls")
        parent_dialog.api_url.setText(PRESET_API_URLS.get(provider, ""))
        parent_dialog.api_url.setReadOnly(True)

def _refresh_model_list(parent_dialog, force=False):
    if hasattr(parent_dialog, 'cached_models') and parent_dialog.cached_models and not force:
        models = parent_dialog.cached_models
    else:
        api_url = parent_dialog.api_url.text()
        api_key = parent_dialog.api_key.text()

        # 检查是否为 ollama API（允许 API Key 为空）
        is_ollama = "ollama" in api_url.lower() or "localhost:11434" in api_url
        
        if not api_url:
            if force:
                QMessageBox.warning(parent_dialog, "错误", "请先填写 API URL")
            return
            
        if not api_key and not is_ollama:
            if force:
                QMessageBox.warning(parent_dialog, "错误", "请先填写 API Key")
            return

        models = api_client.fetch_available_models(api_url, api_key)
        if not models:
            if force:
                QMessageBox.warning(parent_dialog, "错误", "无法获取模型列表，可能是配置错误或供应商不支持查询列表")
            return

        parent_dialog.cached_models = models

    current = parent_dialog.model_name.currentText()
    parent_dialog.model_name.clear()
    parent_dialog.model_name.addItems(models)
    if current:
        index = parent_dialog.model_name.findText(current)
        if index >= 0:
            parent_dialog.model_name.setCurrentIndex(index)
        else:
            parent_dialog.model_name.setEditText(current)

    parent_dialog.model_completer = QCompleter(models)
    parent_dialog.model_completer.setFilterMode(Qt.MatchFlag.MatchContains)
    parent_dialog.model_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    parent_dialog.model_name.setCompleter(parent_dialog.model_completer)

def _test_api_connection(parent_dialog):
    api_url = parent_dialog.api_url.text()
    api_key = parent_dialog.api_key.text()
    model_name = parent_dialog.model_name.currentText()

    # 检查是否为 ollama API（允许 API Key 为空）
    is_ollama = "ollama" in api_url.lower() or "localhost:11434" in api_url
    
    if not api_url:
        parent_dialog.test_status_label.setText("<font color='red'>错误: API URL 不能为空。</font>")
        return
        
    if not api_key and not is_ollama:
        parent_dialog.test_status_label.setText("<font color='red'>错误: API Key 不能为空。</font>")
        return

    parent_dialog.test_status_label.setText("测试中，请稍候...")
    parent_dialog.test_connection_button.setEnabled(False)
    QApplication.processEvents()

    start_time = time.time()
    try:
        result_text, error_message = api_client.test_api_sync(
            api_url, api_key, model_name, timeout_seconds=30
        )
        print("输出结果：", result_text)

        elapsed_time = time.time() - start_time

        if error_message:
            parent_dialog.test_status_label.setText(
                f"<font color='red'>测试失败 ({elapsed_time:.2f}s): {error_message}</font>")
        elif result_text:
            parent_dialog.test_status_label.setText(
                f"<font color='green'>测试成功 ({elapsed_time:.2f}s)! 收到: '{result_text[:50]}...'</font>")
        else:
            parent_dialog.test_status_label.setText(
                f"<font color='orange'>测试完成但未收到明确内容 ({elapsed_time:.2f}s).</font>")

    except Exception as e:
        elapsed_time = time.time() - start_time
        error_detail = str(e)
        if "<think>" in error_detail.lower():
            error_detail += " (提示: 部分模型可能不支持以 <think> 开头的指令)"
        parent_dialog.test_status_label.setText(f"<font color='red'>测试失败 ({elapsed_time:.2f}s): {error_detail}</font>")
    finally:
        parent_dialog.test_connection_button.setEnabled(True)
        QApplication.processEvents()

def _get_form_layout(widget):
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent.layout(), QFormLayout):
            return parent.layout()
        parent = parent.parentWidget()
    return None

def _toggle_custom_widget(combo_box, custom_widget, form_layout_ref):
    is_custom = (combo_box.currentText() == "自定义")
    form_layout = form_layout_ref

    if not form_layout:
        if custom_widget: custom_widget.setVisible(is_custom)
        return

    combo_row = -1
    for i in range(form_layout.rowCount()):
        item = form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
        if item and item.widget() == combo_box:
            combo_row = i
            break

    custom_widget_current_row = -1
    if custom_widget:
        for i in range(form_layout.rowCount()):
            field_item = form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if field_item and field_item.widget() == custom_widget:
                custom_widget_current_row = i
                break

    if is_custom:
        if custom_widget:
            custom_widget.setVisible(True)
            if custom_widget_current_row == -1 and combo_row != -1:
                form_layout.insertRow(combo_row + 1, QLabel(""), custom_widget)
            elif custom_widget_current_row != -1:
                label_item = form_layout.itemAt(custom_widget_current_row, QFormLayout.ItemRole.LabelRole)
                if label_item and label_item.widget():
                    label_item.widget().setVisible(True)
    else:
        if custom_widget and custom_widget_current_row != -1:
            custom_widget.setVisible(False)
            label_item = form_layout.itemAt(custom_widget_current_row, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(False)

def _handle_custom_change(parent_dialog, combo_box, custom_attr_name, form_layout_ref):
    is_custom_selected = (combo_box.currentText() == "自定义")
    custom_widget = getattr(parent_dialog, custom_attr_name, None)

    if is_custom_selected:
        if custom_widget is None:
            custom_widget = QLineEdit()
            setattr(parent_dialog, custom_attr_name, custom_widget)
    
    _toggle_custom_widget(combo_box, custom_widget, form_layout_ref)

def _get_combo_value(combo_box, custom_widget):
    value = combo_box.currentText()
    if value == "自定义" and custom_widget is not None:
        if custom_widget.isVisible():
            return custom_widget.text()
        else:
            return custom_widget.text() if custom_widget.text() else ""
    return value


def _populate_voice_combo(parent_dialog, language, saved_voice_shortname):
    """Populate the Edge TTS voice combo for the given language.
    Uses cached API voice list if available, otherwise falls back to TTS_VOICE_MAP defaults."""
    from ..tts.tts_manager import get_voices_for_language, TTS_VOICE_MAP

    voices = get_voices_for_language(language)
    parent_dialog.edge_voice_combo.clear()

    # First item: "(默认)" meaning use the TTS_VOICE_MAP default
    default_voice = TTS_VOICE_MAP.get(language, "en-US-EmmaMultilingualNeural")
    parent_dialog.edge_voice_combo.addItem(f"(默认) {default_voice}", "")

    # Add each voice; skip the default since it's already the first item
    for v in voices:
        shortname = v.get("ShortName", "")
        friendly = v.get("FriendlyName", shortname)
        display = f"{friendly} ({shortname})" if friendly != shortname else shortname
        if shortname == default_voice:
            continue
        parent_dialog.edge_voice_combo.addItem(display, shortname)

    # Restore saved selection
    if saved_voice_shortname:
        idx = parent_dialog.edge_voice_combo.findData(saved_voice_shortname)
        if idx >= 0:
            parent_dialog.edge_voice_combo.setCurrentIndex(idx)
        else:
            # Saved voice no longer in list -- add it as a preserved entry
            parent_dialog.edge_voice_combo.addItem(f"{saved_voice_shortname} (已保存)", saved_voice_shortname)
            parent_dialog.edge_voice_combo.setCurrentIndex(parent_dialog.edge_voice_combo.count() - 1)
    else:
        parent_dialog.edge_voice_combo.setCurrentIndex(0)


def _on_learning_language_changed(parent_dialog, language):
    """Refresh the voice picker when the learning language changes."""
    if not parent_dialog.edge_voice_combo.isVisible():
        return
    saved_voice = ""
    try:
        override_key = f"edge_tts_voice_{language}"
        saved_voice = get_config().get(override_key, "")
    except Exception:
        pass
    _populate_voice_combo(parent_dialog, language, saved_voice)

def save_basic_settings(parent_dialog):
    # Reverse map TTS engine label to value
    tts_engine_reverse = {
        "Edge TTS (高质量高延时)": "edge_tts",
        "Apple TTS (按语言跟随 macOS voice，无缓存)": "apple_tts",
        "Anki 原生 TTS (低质量低延时)": "anki_native",
        "自定义 URL": "custom_url",
    }
    tts_engine_label = parent_dialog.tts_engine_combo.currentText()
    tts_engine_value = tts_engine_reverse.get(tts_engine_label, "edge_tts")

    new_config = {
        "api_url": parent_dialog.api_url.text(),
        "api_key": parent_dialog.api_key.text(),
        "model_name": parent_dialog.model_name.currentText(),
        "deck_name": parent_dialog.deck_name.text(),
        "save_deck": parent_dialog.save_deck.text(),
        "vocab_level": _get_combo_value(parent_dialog.vocab_level_combo, getattr(parent_dialog, 'vocab_level_custom', None)),
        "learning_goal": _get_combo_value(parent_dialog.learning_goal_combo, getattr(parent_dialog, 'learning_goal_custom', None)),
        "difficulty_level": _get_combo_value(parent_dialog.difficulty_combo, getattr(parent_dialog, 'difficulty_custom', None)),
        "sentence_length_desc": _get_combo_value(parent_dialog.length_combo, getattr(parent_dialog, 'length_custom', None)),
        "learning_language": parent_dialog.learning_language_combo.currentText(),
        "prompt_name": parent_dialog.prompt_name_combo.currentText(),
        "font_family": parent_dialog.font_combo.currentText(),
        "tts_engine": tts_engine_value,
        "tts_custom_url": parent_dialog.tts_custom_url.text(),
        "tts_replace_audio": parent_dialog.tts_replace_audio.isChecked(),
        "web_enabled": parent_dialog.web_enabled.isChecked(),
        "web_port": parent_dialog.web_port.value(),
    }

    current_full_config = get_config()
    for key in ["custom_prompts", "preset_api_urls", "preset_vocab_levels", "preset_learning_goals", "preset_difficulties", "preset_lengths"]:
        if key in current_full_config:
            new_config[key] = current_full_config[key]

    # Preserve all existing edge_tts_voice_* overrides, update current language's
    for key in current_full_config:
        if key.startswith("edge_tts_voice_"):
            new_config[key] = current_full_config[key]
    current_lang = parent_dialog.learning_language_combo.currentText()
    voice_shortname = parent_dialog.edge_voice_combo.currentData() or ""
    new_config[f"edge_tts_voice_{current_lang}"] = voice_shortname

    save_config(new_config)
    
    # 保存配置后更新卡片模板
    _update_card_templates_with_notification(parent_dialog)

def _on_font_changed(parent_dialog):
    """
    字体设置变化时的处理函数
    """
    # 实时更新卡片模板，不需要等待保存
    _update_card_templates_with_notification(parent_dialog)

def _update_card_templates_with_notification(parent_dialog):
    """
    更新卡片模板并显示通知
    """
    try:
        success = update_card_templates()
        if success:
            # 可以选择显示一个通知，但为了避免频繁打扰，这里只在控制台输出
            print("SUCCESS: 卡片模板已根据字体设置更新")
        else:
            print("WARNING: 更新卡片模板失败")
    except Exception as e:
        print(f"ERROR: 更新卡片模板时出错: {e}")
