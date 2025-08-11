import aqt
# 插件的 __name__，用于访问 Anki 配置
ADDON_NAME = __name__.split('.')[0] # 获取顶级包名

showing_sentence = ""
showing_translation = ""

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