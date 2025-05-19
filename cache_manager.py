# -*- coding: utf-8 -*-

import json
import os
import copy
import aqt
import concurrent.futures

# 缓存文件路径 (使用 __name__ 获取插件目录)
ADDON_FOLDER = os.path.dirname(__file__)
CACHE_FILE = os.path.join(ADDON_FOLDER, "sentence_cache.json")

# 内存缓存（减少文件IO次数）
_memory_cache = None

def load_cache():
    """加载例句缓存（优先使用内存缓存）"""
    global _memory_cache
    if _memory_cache is None:
        try:
            # 确保使用正确的路径加载缓存
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                _memory_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _memory_cache = {}
    return _memory_cache

def save_cache(cache):
    """保存例句缓存（同步写入确保持久化）"""
    global _memory_cache
    _memory_cache = cache  # 更新内存缓存
    # 直接保存完整缓存（移除严格过滤，确保所有合法数据保存）
    try:
        # 确保使用正确的路径保存缓存
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        # 保存成功后打印调试信息
        #print(f"DEBUG: 已成功保存缓存到 {CACHE_FILE}，当前缓存键：{list(cache.keys())}")
    except Exception as e:
        error_msg = f"保存缓存失败：{str(e)}，文件路径：{CACHE_FILE}"
        aqt.utils.showInfo(error_msg)
        print(f"ERROR: {error_msg}")

def clear_cache():
    """
    清除例句缓存（同时删除本地文件和内存缓存）
    返回操作是否成功 (True/False)
    """
    global _memory_cache
    
    # 1. 删除内存缓存
    _memory_cache = None
    
    # 2. 尝试删除本地缓存文件
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            aqt.utils.showInfo(f"已成功删除缓存文件 {os.path.basename(CACHE_FILE)}")
            return True
        else:
            aqt.utils.showInfo(f"缓存文件 {os.path.basename(CACHE_FILE)} 不存在，无需删除")
            return True
    except Exception as e:
        error_msg = f"删除缓存文件失败：{str(e)}"
        aqt.utils.showInfo(error_msg)
        return False



# 注意：_async_save 在原代码中未使用，暂时保留但注释掉，
# 如果需要异步保存，需要确保它被正确调用并处理并发问题。
# def _async_save(serializable_cache_to_save):
#     """异步保存缓存到文件（添加调试日志）"""
#     try:
#         with open(CACHE_FILE, 'w', encoding='utf-8') as f:
#             json.dump(serializable_cache_to_save, f, ensure_ascii=False, indent=2)
#         # 保存成功后打印调试信息
#         print(f"DEBUG: 已异步保存缓存到 {CACHE_FILE}，当前缓存键：{list(serializable_cache_to_save.keys())}")
#     except Exception as e:
#         error_msg = f"异步保存缓存失败：{str(e)}，文件路径：{CACHE_FILE}"
#         aqt.utils.showInfo(error_msg)
#         print(f"ERROR: {error_msg}")
