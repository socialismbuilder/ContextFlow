import aqt
import json
import os
import re
import html
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
    # Anki 写入的 meta.json 是单行且中文全部被转义成 \uxxxx，重新格式化以提升可读性
    pretty_print_meta()


def pretty_print_meta():
    """把 Anki 写入的 meta.json 重新格式化：中文原样、4 空格缩进、分行。

    输出仍是合法 JSON，Anki 可正常读取；Anki 自行改写配置后格式会还原，
    下次 save_config 或 profile 加载时会再次格式化。
    """
    try:
        meta_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meta.json")
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
        with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"WARN: 格式化 meta.json 失败（不影响功能）: {e}")


def clean_html(raw_string):
    """
    清洗 HTML 内容：移除标签、方括号内容、解码实体、去首尾空格
    """
    no_html = re.sub(r'<.*?>', '', raw_string)
    no_sound = re.sub(r'\[.*?\]', '', no_html)
    decoded = html.unescape(no_sound)
    return decoded.strip()
