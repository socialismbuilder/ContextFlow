# -*- coding: utf-8 -*-

import json
import os
import sqlite3
import aqt

# 缓存文件路径 (使用 __name__ 获取插件目录)
ADDON_FOLDER = os.path.dirname(__file__)
CACHE_FILE = os.path.join(ADDON_FOLDER, "sentence_cache.json")
DB_FILE = os.path.join(ADDON_FOLDER, "sentence_cache.db")

# 新增: 内存缓存层
# 这是一个简单的字典，用于在Anki运行时缓存已从数据库加载的例句。
# 结构: {'word': [ [sentence, translation], ... ], ...}
_memory_cache = {}


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
                sentence_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 检查并添加 sentence_count 字段（如果不存在）
        cursor.execute("PRAGMA table_info(cache)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'sentence_count' not in columns:
            cursor.execute("ALTER TABLE cache ADD COLUMN sentence_count INTEGER DEFAULT 0")
            print("DEBUG: 已添加 'sentence_count' 字段。")
            
            # 遍历现有数据，填充 sentence_count
            cursor.execute("SELECT word, sentence_pairs FROM cache")
            rows = cursor.fetchall()
            for row in rows:
                word = row[0]
                sentence_pairs_json = row[1]
                try:
                    sentence_pairs = json.loads(sentence_pairs_json)
                    sentence_count = len(sentence_pairs)
                    cursor.execute("UPDATE cache SET sentence_count = ? WHERE word = ?", (sentence_count, word))
                except json.JSONDecodeError:
                    print(f"WARNING: 无法解析单词 '{word}' 的 sentence_pairs。")
            print("DEBUG: 已遍历并更新现有记录的 'sentence_count' 字段。")
            
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
    # 修改: 加载例句缓存，优先从内存缓存读取。
    如果提供word参数，则返回该单词的例句翻译对
    """
    if not word:
        return None

    # 1. 检查内存缓存 (Cache Hit)
    if word in _memory_cache:
        # print(f"DEBUG: 内存缓存命中 '{word}'")
        return _memory_cache[word]

    # 2. 内存缓存未命中 (Cache Miss)，从数据库加载
    # print(f"DEBUG: 内存缓存未命中 '{word}'，从数据库加载。")
    _init_db()
    
    try:
        conn = _get_db_connection()
        if conn is None:
            return []
        cursor = conn.cursor()
        cursor.execute("SELECT sentence_pairs FROM cache WHERE word = ?", (word,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            sentence_pairs = json.loads(row['sentence_pairs'])
            # 3. 将从数据库加载的数据存入内存缓存
            _memory_cache[word] = sentence_pairs
            return sentence_pairs
        else:
            # 即使数据库中没有，也缓存这个“空”结果，避免对不存在的词反复查询数据库
            _memory_cache[word] = []
            return []
    except Exception as e:
        print(f"ERROR: 查询单词'{word}'缓存失败：{str(e)}")
        return []

def save_cache(word, sentence_pairs=None):
    """
    # 修改: 保存例句缓存，并在成功后更新内存缓存。
    如果提供word和sentence_pairs，则保存该单词的例句翻译对（合并现有数据）
    如果只提供word，则删除该单词的缓存（为了兼容旧接口）
    """
    _init_db()
    
    # 先加载现有缓存（会优先走内存缓存），合并现有例句和新例句
    existing_pairs = load_cache(word)
    final_pairs = existing_pairs
    if sentence_pairs:
        final_pairs = existing_pairs + sentence_pairs
    
    sentence_count = len(final_pairs)

    try:
        conn = _get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO cache (word, sentence_pairs, sentence_count, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (word, json.dumps(final_pairs, ensure_ascii=False), sentence_count))
        conn.commit()
        conn.close()
        
        # 新增: 数据库写入成功后，更新内存缓存以保持同步
        _memory_cache[word] = final_pairs
        # print(f"DEBUG: 内存缓存已更新 '{word}'")
        
        return True
    except Exception as e:
        error_msg = f"保存单词'{word}'缓存失败：{str(e)}"
        aqt.utils.showInfo(error_msg)
        print(f"ERROR: {error_msg}")
        return False

def pop_cache(word):
    """
    # 修改: 原子性地取出并删除第一个例句对，并在成功后更新内存缓存。
    返回取出的例句对 [sentence, translation]，如果没有例句对则返回 None
    """
    _init_db()
    
    conn = None # 确保 conn 在 try 外部可见
    try:
        conn = _get_db_connection()
        if conn is None:
            return None
        
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        
        cursor.execute("SELECT sentence_pairs FROM cache WHERE word = ?", (word,))
        row = cursor.fetchone()
        
        if not row:
            conn.commit() # 提交空事务
            # 新增: 如果数据库中没有，也确保内存缓存中没有
            if word in _memory_cache:
                del _memory_cache[word]
            return None
        
        sentence_pairs = json.loads(row['sentence_pairs'])
        if not sentence_pairs:
            cursor.execute("DELETE FROM cache WHERE word = ?", (word,))
            conn.commit()
            # 新增: 更新内存缓存
            if word in _memory_cache:
                del _memory_cache[word]
            return None
        
        popped_pair = sentence_pairs.pop(0)
        
        if sentence_pairs:
            new_sentence_pairs_json = json.dumps(sentence_pairs, ensure_ascii=False)
            new_count = len(sentence_pairs)
            cursor.execute('''
                UPDATE cache 
                SET sentence_pairs = ?, sentence_count = ?, updated_at = CURRENT_TIMESTAMP
                WHERE word = ?
            ''', (new_sentence_pairs_json, new_count, word))
        else:
            cursor.execute("DELETE FROM cache WHERE word = ?", (word,))
        
        conn.commit()
        
        # 新增: 数据库操作成功后，更新内存缓存
        _memory_cache[word] = sentence_pairs
        # print(f"DEBUG: 内存缓存已因 pop 操作更新 '{word}'")
        
        return popped_pair
        
    except Exception as e:
        error_msg = f"取出单词'{word}'缓存失败：{str(e)}"
        aqt.utils.showInfo(error_msg)
        print(f"ERROR: {error_msg}")
        if conn:
            try:
                conn.rollback()
            except Exception as rb_e:
                print(f"ERROR: 回滚事务失败: {rb_e}")
        return None
    finally:
        if conn:
            conn.close()


def clear_cache():
    """
    # 修改: 清除所有缓存，包括数据库文件和内存缓存。
    返回操作是否成功 (True/False)
    """
    try:
        # 删除数据库文件
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            print(f"DEBUG: 已删除数据库文件 {os.path.basename(DB_FILE)}")
        
        # 删除旧的JSON缓存文件
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(f"DEBUG: 已删除JSON缓存文件 {os.path.basename(CACHE_FILE)}")
        
        # 新增: 清空内存缓存
        global _memory_cache
        _memory_cache.clear()
        print("DEBUG: 内存缓存已清空。")
        
        aqt.utils.showInfo("已成功清除所有缓存文件和内存缓存")
        return True
        
    except Exception as e:
        error_msg = f"清除缓存文件失败：{str(e)}"
        aqt.utils.showInfo(error_msg)
        return False

# 初始化数据库
_init_db()
