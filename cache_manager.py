# -*- coding: utf-8 -*-

import json
import os
import sqlite3
import aqt

# 缓存文件路径 (使用 __name__ 获取插件目录)
ADDON_FOLDER = os.path.dirname(__file__)
CACHE_FILE = os.path.join(ADDON_FOLDER, "sentence_cache.json")
DB_FILE = os.path.join(ADDON_FOLDER, "sentence_cache.db")

def _init_db():
    """初始化数据库表"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # 创建表：word为关键词，sentence_pairs为JSON格式的例句翻译对列表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                word TEXT PRIMARY KEY,
                sentence_pairs TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"ERROR: 初始化数据库失败：{str(e)}")

def _get_db_connection():
    """获取数据库连接"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
        return conn
    except Exception as e:
        print(f"ERROR: 连接数据库失败：{str(e)}")
        return None

def load_cache(word=None):
    """
    加载例句缓存
    如果提供word参数，则返回该单词的例句翻译对
    如果不提供word参数，则返回整个缓存（为了兼容旧接口）
    """
    _init_db()
    
    if word is not None:
        # 根据单词查询例句翻译对
        try:
            conn = _get_db_connection()
            if conn is None:
                return []
            cursor = conn.cursor()
            cursor.execute("SELECT sentence_pairs FROM cache WHERE word = ?", (word,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return json.loads(row['sentence_pairs'])
            else:
                return []
        except Exception as e:
            print(f"ERROR: 查询单词'{word}'缓存失败：{str(e)}")
            return []
    else:
        # 兼容旧接口：返回整个缓存
        try:
            conn = _get_db_connection()
            if conn is None:
                return {}
            cursor = conn.cursor()
            cursor.execute("SELECT word, sentence_pairs FROM cache")
            rows = cursor.fetchall()
            conn.close()
            
            cache = {}
            for row in rows:
                cache[row['word']] = json.loads(row['sentence_pairs'])
            return cache
        except Exception as e:
            print(f"ERROR: 加载完整缓存失败：{str(e)}")
            return {}

def save_cache(word, sentence_pairs=None):
    """
    保存例句缓存
    如果提供word和sentence_pairs，则保存该单词的例句翻译对
    如果只提供word，则删除该单词的缓存（为了兼容旧接口）
    """
    _init_db()
    
    if sentence_pairs is not None:
        # 保存单词和例句翻译对
        try:
            conn = _get_db_connection()
            if conn is None:
                return False
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO cache (word, sentence_pairs, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (word, json.dumps(sentence_pairs, ensure_ascii=False)))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            error_msg = f"保存单词'{word}'缓存失败：{str(e)}"
            aqt.utils.showInfo(error_msg)
            print(f"ERROR: {error_msg}")
            return False
    else:
        # 兼容旧接口：删除指定单词的缓存
        try:
            conn = _get_db_connection()
            if conn is None:
                return False
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cache WHERE word = ?", (word,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            error_msg = f"删除单词'{word}'缓存失败：{str(e)}"
            aqt.utils.showInfo(error_msg)
            print(f"ERROR: {error_msg}")
            return False

def clear_cache():
    """
    清除例句缓存（同时删除数据库文件和JSON缓存文件）
    返回操作是否成功 (True/False)
    """
    try:
        success = True
        
        # 删除数据库文件
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            print(f"DEBUG: 已删除数据库文件 {os.path.basename(DB_FILE)}")
        
        # 删除旧的JSON缓存文件
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(f"DEBUG: 已删除JSON缓存文件 {os.path.basename(CACHE_FILE)}")
        
        aqt.utils.showInfo("已成功清除所有缓存文件")
        return True
        
    except Exception as e:
        error_msg = f"清除缓存文件失败：{str(e)}"
        aqt.utils.showInfo(error_msg)
        return False

# 初始化数据库
_init_db()
