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
    
    # 合并配置，但确保预设配置项（以preset_开头）始终使用默认值
    merged_config = {**default_config, **user_config}
    
    # 将所有以preset_开头的配置项恢复为默认值
    for key in default_config:
        if key.startswith('preset_'):
            merged_config[key] = default_config[key]
    
    return merged_config
def save_config(new_config):
    """保存配置到Anki"""
    # 过滤掉所有以preset_开头的配置项，确保预设值不会被保存到用户配置中
    filtered_config = {key: value for key, value in new_config.items() 
                      if not key.startswith('preset_')}
    
    # 直接使用插件名保存配置
    aqt.mw.addonManager.writeConfig(ADDON_NAME, filtered_config)
