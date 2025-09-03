import aqt
from aqt import mw
from aqt import gui_hooks
import queue
import threading
import time
import traceback # Add traceback for worker error logging
import concurrent.futures # Add for thread pool
from anki.cards import Card
import re
from PyQt6.QtCore import QTimer  # 导入PyQt6的QTimer类
import html
from . import config_manager
# 使用相对导入来引入其他模块的功能
from .config_manager import get_config
from .cache_manager import load_cache, save_cache, clear_cache, pop_cache
from .api_client import generate_ai_sentence
from .Process_Card import Process_back_html,Process_front_html
from .stats import add_stats
# --- 后台任务队列 ---
task_queue = queue.PriorityQueue() # 使用优先级队列
cache_lock = threading.Lock() # 用于保护缓存访问和队列检查/添加
stop_event = threading.Event()
executor = None # 使用单个线程池
Occupy_bar = False
# --- 结束后台任务队列 ---

showing_sentence = ""
showing_translation = ""
# _processing_card_id 和 _processing_keyword 不再需要

def _process_keyword_task(keyword_with_priority):
    """处理单个关键词生成任务（由线程池中的线程调用）"""
    priority, keyword = keyword_with_priority  # 解包优先级和关键词
    config = get_config() # 在每次处理任务前获取最新的配置
    print(f"DEBUG:正在处理关键词: {keyword} (优先级: {priority})")

    try:
        # 调用同步的 API 函数
        sentence_pairs = generate_ai_sentence(config, keyword)

        if sentence_pairs: # 确保返回了有效的句子对
            with cache_lock: # 获取锁以安全地修改缓存
                save_cache(keyword, sentence_pairs) # 存储列表的列表
            print(f"DEBUG: {keyword}处理成功")
        else:
            print(f"WARNING: {keyword}处理失败")

    except Exception as e:
        # 记录生成过程中发生的任何错误
        print(f"ERROR: Worker failed to generate/cache sentences for '{keyword}': {type(e).__name__} - {str(e)}")
        traceback.print_exc() # 打印详细的回溯信息
    finally:
        pass # task_done 将在 _sentence_worker_manager 中处理


def _sentence_worker_manager():
    """后台工作线程管理器，从队列中获取任务并提交到线程池"""
    global executor
    if executor is None:
        print("ERROR: Thread pool executor not initialized in _sentence_worker_manager.")
        return

    while not stop_event.is_set():
        try:
            # 检查线程池是否有空闲线程
            if executor._work_queue.qsize() >= executor._max_workers:
                # 线程池已满，等待一段时间再检查
                time.sleep(0.1)
                continue

            priority, keyword = task_queue.get(timeout=1) # 解包
            keyword_with_priority = (priority, keyword) # 重新打包以传递

            # 提交任务到线程池
            future = executor.submit(_process_keyword_task, keyword_with_priority)
            
            # 当任务完成时调用 task_done
            future.add_done_callback(lambda f: task_queue.task_done())
            #print(f"DEBUG_QUEUE: 任务已提交: {keyword} (优先级: {priority})")

        except queue.Empty:
            continue # 队列为空，继续循环等待
        except Exception as e:
            print(f"ERROR: Error getting/submitting task from/to queue: {e}")
            try:
                task_queue.task_done() # 尝试标记任务完成以避免队列阻塞
            except ValueError:
                pass # 如果任务未被 get
            continue

    print("DEBUG: Sentence worker manager thread stopped.")



def clean_html(raw_string):
    """
    清洗 HTML 内容，包括：
    1. 移除所有 HTML 标签
    2. 移除方括号内容（如 [sound:...]）
    3. 解码 HTML 实体（如 &nbsp; -> 空格）
    4. 去除首尾空格
    """
    no_html = re.sub(r'<.*?>', '', raw_string)
    no_sound = re.sub(r'\[.*?\]', '', no_html)
    decoded = html.unescape(no_sound)
    cleaned = decoded.strip()
    return cleaned



def get_upcoming_cards(card, deck_name):
    """使用V3调度器API获取接下来的卡片的关键词"""
    # 检查是否为单线程模式（通过executor的线程数判断）
    global executor
    is_single_threaded = executor is not None and executor._max_workers == 1
    
    # 如果是单线程模式，获取100张卡片；否则获取10张
    fetch_limit = 100 if is_single_threaded else 10
    
    # 使用V3调度器API获取队列中的卡片
    output = mw.col.sched.get_queued_cards(fetch_limit=fetch_limit, intraday_learning_only=False)
    
    if not output.cards:
        return []
    
    # 获取接下来的卡片的关键词
    keywords = []
    for i in range(min(fetch_limit, len(output.cards))):
        try:
            # 直接使用output.cards中的卡片信息
            queued_card = output.cards[i]
            
            # 获取卡片对象
            backend_card = queued_card.card
            upcoming_card = Card(mw.col, backend_card=backend_card)
            
            # 检查卡片是否属于目标牌组
            card_deck_name = aqt.mw.col.decks.name(upcoming_card.did)
            if not (card_deck_name == deck_name or card_deck_name.startswith(deck_name + "::")):
                continue  # 跳过不属于目标牌组的卡片
            
            # 获取卡片的第一个字段并清理
            note = upcoming_card.note()
            first_field = note.fields[0] if note.fields else ""
            cleaned_keyword = clean_html(first_field)
            
            if cleaned_keyword:  # 过滤空关键词
                keywords.append(cleaned_keyword)
                
        except Exception:
            continue
    return keywords


def on_card_render(html: str, card: Card, context: str) -> str:
    # test(card) # Temporarily disable test call here, will add preloading later

    """卡片渲染钩子，处理问题面和答案面的显示逻辑"""
    # global _processing_card_id, _processing_keyword # No longer needed
    global showing_sentence, showing_translation # Keep these
    config = get_config()
    try:
        # 尝试获取卡片所在的牌组名称
        current_deck = aqt.mw.col.decks.name(card.did)
        # print("当前牌组名称："+current_deck)
    except Exception as e:
        print(f"ERROR: 获取牌组名称失败 for card {card.id}: {e}")
        return html # 获取失败则不处理

    # 解析配置中的牌组名称获取基础名称和字段索引
    config_deck_name = config.get("deck_name")
    # 使用正则匹配牌组名末尾的[数字]格式
    field_index_match = re.search(r'\[(\d+)\]$', config_deck_name)
    base_deck_name = re.sub(r'\[\d+\]$', '', config_deck_name) if field_index_match else config_deck_name
    
    # 仅目标牌组生效
    if (current_deck == base_deck_name or current_deck.startswith(base_deck_name + "::")) and card.ord == 0:
    # 当前牌组匹配配置的牌组（相同或子目录）

        # 获取当前复习器状态（'question' 或 'answer'）
        state = aqt.mw.reviewer.state if aqt.mw.reviewer else 'unknown'

        # --- 根据复习器状态区分处理 ---
        if state == 'question':
            # 如果是显示问题面
            try:
                note = card.note()
                # 使用配置中解析出的字段索引
                field_index = int(field_index_match.group(1)) - 1 if field_index_match else 0
                # 确保字段索引在有效范围内
                if field_index < 0 or (note.fields and field_index >= len(note.fields)):
                    field_index = 0
                # 获取关键词字段
                keyword = note.fields[field_index].strip() if note.fields and len(note.fields) > field_index else ""
                # 清理关键词
                keyword = clean_html(keyword)
                

                if not keyword:
                    return html # 没有关键词则不处理
            except Exception as e:
                aqt.utils.showInfo(f"获取卡片字段失败：{str(e)}")
                return html

            # --- 问题面逻辑 ---
            html_to_return = None # Variable to store the HTML result

            popped_pair = pop_cache(keyword)

            if popped_pair:
                # --- Cache Hit Logic ---
                try:
                    current_sentence, current_translation = popped_pair
                    showing_sentence = current_sentence
                    showing_translation = current_translation
                    #print(f"DEBUG: 显示 '{keyword}' 的缓存句子")
                    config_manager.showing_sentence = showing_sentence
                    config_manager.showing_translation = showing_translation
                    html_to_return = Process_front_html(current_sentence) # Set HTML for return
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = f"处理缓存时发生意外错误 ({error_type})：{str(e)}"
                    print(error_msg)
                    aqt.utils.showInfo(error_msg)
                    showing_sentence = "缓存处理错误"
                    showing_translation = ""
                    html_to_return = Process_front_html(showing_sentence) # Set error HTML

            # 如果设置了 html_to_return（缓存命中或错误），则跳过缓存未命中逻辑
            if html_to_return is None:
                # --- 缓存未命中逻辑（或缓存命中但为空） ---
                # 关键词不在缓存中或缓存列表为空。加入队列并等待。
                print(f"DEBUG: 缓存未命中 '{keyword}'。加入队列并开始等待。")

                # 添加到队列（工作进程将处理此项）
                with cache_lock:
                    # 检查队列中是否已有相同关键词的任务
                    existing_in_queue = False
                    higher_prio_exists = False
                    for item in task_queue.queue:
                        if item[1] == keyword:
                            existing_in_queue = True
                            if item[0] <= 0:  # 已有相同或更高优先级的任务
                                higher_prio_exists = True
                            break
                    
                    if not existing_in_queue or not higher_prio_exists:
                        task_queue.put((0, keyword)) # 主动缓存，高优先级 (0)
                        print(f"DEBUG: 已添加'{keyword}'到队列（缓存未命中，优先级0）。")
                    else:
                        print(f"DEBUG: 关键词'{keyword}'已在队列中且有相同或更高优先级，跳过添加")

                # 最终主线程安全的定时器实现（使用PyQt6的QTimer）
                start_time = time.time()
                max_wait = 30  # 最大等待30秒
                timer = QTimer()  # 创建QTimer实例

                # 启动进度条（设置明确最大值）
                mw.progress.start(
                    immediate=True,
                    label=f"正在为 '{keyword}' 生成例句...",
                    min=0,
                    max=max_wait  # 设置最大进度值为15秒
                )

                def update_ui():
                    """严格在主线程执行的UI更新函数"""
                    current_time = time.time()
                    elapsed = int(current_time - start_time)
                    global Occupy_bar
                    
                    # 更新进度条值（0-15）
                    mw.progress.update(
                        label=f"正在为 '{keyword}' 生成例句... (已等待{elapsed}秒/{max_wait}秒)",
                        value=elapsed,
                        max=max_wait
                    )

                    # 检查超时
                    if elapsed >= max_wait:
                        timer.stop()  # 停止QTimer
                        mw.progress.finish()
                        if mw.reviewer and mw.reviewer.card and mw.reviewer.card.id == card.id:
                            Occupy_bar = False
                            return

                    # 检查缓存（主线程安全）
                    with cache_lock:
                        sentence_pairs = load_cache(keyword)
                        if sentence_pairs:
                            timer.stop()  # 停止QTimer
                            mw.progress.finish()
                            # 取出第一个例句对并更新缓存
                            if mw.reviewer and mw.reviewer.card and mw.reviewer.card.id == card.id:
                                Occupy_bar = False
                                mw.reset()
                            return
                
                global Occupy_bar
                Occupy_bar = True
                timer.timeout.connect(update_ui)
                timer.start(100)


                # 设置初始显示状态
                showing_sentence = "例句生成中..."
                showing_translation = ""
                html_to_return = Process_front_html(showing_sentence)

            # --- Preloading Logic (Runs AFTER determining initial HTML) ---
            # print("DEBUG: 开始预加载逻辑...")
            try:
                upcoming_keywords = get_upcoming_cards(card,base_deck_name) # Call the function to get upcoming keywords
                # print(f"DEBUG: 预加载检查 - 待处理关键词: {upcoming_keywords}") # 添加日志
                if upcoming_keywords:
                    with cache_lock: # Lock for safe cache access and queue adding
                        # Get current queue items to avoid adding duplicates unnecessarily
                        # Note: This is a snapshot, race conditions still possible but less likely
                        current_queue_items = set(item for item in task_queue.queue)

                        for kw in upcoming_keywords:
                            if kw and kw != keyword:
                                # 检查该单词是否在缓存中且有数据
                                sentence_pairs = load_cache(kw)
                                if not sentence_pairs and kw not in current_queue_items:
                                    # 检查队列中是否已有相同关键词的高优先级任务
                                    has_high_prio = False
                                    for item in task_queue.queue:
                                        if item[1] == kw and item[0] <= 1:  # 已有优先级<=1的任务
                                            has_high_prio = True
                                            break
                                    
                                    if not has_high_prio:
                                        task_queue.put((1, kw)) # 被动缓存，低优先级 (1)
            except Exception as e:
                print(f"ERROR: Failed to preload keywords: {e}")
            except Exception as e:
                print(f"ERROR: Failed to preload keywords: {e}")
            # --- End Preloading Logic ---

            # Finally, return the determined HTML (cached sentence or "Generating...")
            return html_to_return


        elif state == 'answer':
            # 如果是显示答案面，显示之前问题面生成的例句 + 对应的翻译
            # showing_sentence 和 showing_translation 包含了需要显示的内容
            return Process_back_html(showing_sentence, showing_translation, html) # 使用全局变量

        # --- 结束状态判断 ---

    # 如果不是目标牌组，或者状态不是 question/answer，清除处理标记
    # （注意：这里可能需要更精细的逻辑，例如仅在卡片切换时清除）
    # if context not in ['question', 'answer']: # 原逻辑保留，但可能需要调整
    #     _clear_processing_state()

    return html # 返回原始 HTML

# --- Obsolete functions removed ---
# def _handle_new_sentences(...)
# def _clear_processing_state(...)
# --- End Obsolete functions ---

def start_worker():
    """启动后台例句生成工作线程（使用单个线程池）"""
    global executor, manager_thread
    if executor is None:
        stop_event.clear()
        
        # 获取配置以确定线程数量
        config = get_config()
        api_url = config.get("api_url", "")
        
        # 检查是否为ollama API或localhost，如果是则使用单线程模式
        if "ollama" in api_url.lower() or "localhost" in api_url.lower() or "127.0.0.1" in api_url.lower():
            max_workers = 1
            print("DEBUG: 检测到ollama或localhost API，启用单线程模式")
        else:
            max_workers = 3
            print("DEBUG: 使用多线程模式（3个线程）")
        
        # 创建单个线程池
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='SentenceWorker')
        
        manager_thread = threading.Thread(target=_sentence_worker_manager, daemon=True)
        manager_thread.start()
        print(f"DEBUG: 句子处理线程池及管理器已启动（{max_workers}个线程）。")
    else:
        print("DEBUG: 工作线程已在运行或未正确清理。")


def stop_worker():
    """停止后台例句生成工作线程（单个线程池和管理器）"""
    global executor, manager_thread

    # 取消注册选中词汇例句生成功能的右键菜单
    try:
        from . import context_menu
        context_menu.unregister_context_menu()
        print("DEBUG: 选中词汇例句生成功能已停用")
    except Exception as e:
        print(f"ERROR: 取消注册选中词汇例句生成功能失败: {e}")

    print("DEBUG: Stopping sentence worker manager and thread pool...")
    stop_event.set() # 通知 _sentence_worker_manager 停止

    # 清空队列
    while not task_queue.empty():
        try:
            _ = task_queue.get_nowait()
            task_queue.task_done()
        except queue.Empty:
            break
        except Exception as e:
            print(f"Error clearing queue during stop: {e}")
            break

    # 等待 manager_thread 结束
    if manager_thread and manager_thread.is_alive():
        manager_thread.join(timeout=5)
        if manager_thread.is_alive():
            print("WARNING: Sentence worker manager thread did not stop gracefully.")
    
    # 关闭线程池
    if executor:
        executor.shutdown(wait=True, cancel_futures=False)
        print("DEBUG: Thread pool shutdown complete.")
        executor = None
        
    manager_thread = None # 清理 manager_thread 引用
    
    if executor is None:
        print("DEBUG: All workers stopped and cleaned up.")
    else:
        print("DEBUG: Worker (executor) not running or already stopped, or cleanup issue.")

def register_hooks():
    """注册所有需要的钩子，并启动工作线程"""
    gui_hooks.card_will_show.append(on_card_render)
    gui_hooks.profile_will_close.append(stop_worker) # 注册停止函数
    gui_hooks.profile_did_open.append(start_worker)
    gui_hooks.stats_dialog_will_show.append(add_stats) # 添加统计钩子

    # 注册选中词汇例句生成功能的右键菜单
    try:
        from . import context_menu
        context_menu.register_context_menu()
        print("DEBUG: 选中词汇例句生成功能已启用")
    except Exception as e:
        print(f"ERROR: 注册选中词汇例句生成功能失败: {e}")

    start_worker() # 启动工作线程
