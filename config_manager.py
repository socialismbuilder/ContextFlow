import aqt
# 插件的 __name__，用于访问 Anki 配置
ADDON_NAME = __name__.split('.')[0] # 获取顶级包名
def get_config():
    """获取当前配置（基于config.json的默认值与用户保存值合并）"""
    # 直接通过插件名获取用户配置
    user_config = aqt.mw.addonManager.getConfig(ADDON_NAME) or {}
    # 从config.json读取默认配置（Anki会自动加载）
    default_config = aqt.mw.addonManager.addonConfigDefaults(ADDON_NAME) or {}
    # 合并默认配置与用户配置（用户配置优先级更高）
    return {**default_config, **user_config}
def save_config(new_config):
    """保存配置到Anki"""
    # 直接使用插件名保存配置
    aqt.mw.addonManager.writeConfig(ADDON_NAME, new_config)

def get_word_selection_config():
    """获取选中词汇功能的配置"""
    config = get_config()
    return config.get("word_selection", {
        "enabled": True,
        "target_deck_name": "",
        "sentence_count": 3,
        "custom_prompt": "",
        "use_custom_prompt": False,
        "difficulty_level": "中级 (B1): 并列/简单复合句，稍复杂话题，扩大词汇范围",
        "sentence_length": "中等长度句 (约25-40词): 通用对话及文章常用长度"
    })

def save_word_selection_config(word_selection_config):
    """保存选中词汇功能的配置"""
    config = get_config()
    config["word_selection"] = word_selection_config
    save_config(config)