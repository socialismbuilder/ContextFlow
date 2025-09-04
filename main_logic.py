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
from aqt.utils import tooltip # 导入 tooltip
# --- 后台任务队列 ---
task_queue = queue.PriorityQueue() # 使用优先级队列
processing_keywords = set() # 存储正在处理的关键词
queued_keywords = set() # 存储已经在队列中的关键词（新增）
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
    
    with cache_lock:
        if keyword in processing_keywords:
            return # 如果已在处理中，则跳过
        processing_keywords.add(keyword)

    config = get_config() # 在每次处理任务前获取最新的配置
    #print(f"DEBUG:正在处理关键词: {keyword} (优先级: {priority})")

    try:
        # 调用同步的 API 函数
        sentence_pairs = generate_ai_sentence(config, keyword)

        if sentence_pairs: # 确保返回了有效的句子对
            with cache_lock: # 获取锁以安全地修改缓存
                save_cache(keyword, sentence_pairs) # 存储列表的列表
            #print(f"DEBUG: {keyword}处理成功")

    except Exception as e:
        # 记录生成过程中发生的任何错误
        #print(f"ERROR: Worker failed to generate/cache sentences for '{keyword}': {type(e).__name__} - {str(e)}")
        traceback.print_exc() # 打印详细的回溯信息
    finally:
        with cache_lock:
            processing_keywords.remove(keyword) # 无论成功或失败，都从集合中移除
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
            
            # 当任务完成时调用 task_done 并从 queued_keywords 中移除
            def task_completed_callback(f):
                task_queue.task_done()
                with cache_lock:
                    if keyword in queued_keywords:
                        queued_keywords.remove(keyword)
                        #print(f"DEBUG_QUEUE: 任务完成，从已入队集合中移除: {keyword}")
                    
                    # --- 添加 tooltip 逻辑 ---
                    remaining_tasks = len(queued_keywords) # 获取剩余任务数量
                    message = f"后台缓存+1，生成队列剩余: {remaining_tasks} 个。"
                    # 使用 taskman.run_on_main 确保在主线程中调用 tooltip
                    aqt.mw.taskman.run_on_main(lambda: tooltip(message, period=1000))
                    # --- 结束 tooltip 逻辑 ---

            future.add_done_callback(task_completed_callback)
            # 添加到已入队集合
            with cache_lock:
                queued_keywords.add(keyword)
                #print(f"DEBUG_QUEUE: 任务已提交，添加到已入队集合: {keyword} (优先级: {priority})")
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



def reorganize_task_queue(keywords):
    """
    重组任务队列，根据提供的关键词（单个或列表）调整优先级。
    使用queued_keywords集合来避免重复添加任务。
    """
    with cache_lock:
        # 筛选出不在缓存中且不在处理中的关键词（即使已经在队列中也要更新优先级）
        if isinstance(keywords, str):
            # 单个关键词
            keyword = keywords
            should_process = (not load_cache(keyword) and 
                            keyword not in processing_keywords)
            keywords_to_process = [keyword] if should_process else []
        else:
            # 关键词列表
            keywords_to_process = []
            for kw in keywords:
                if (not load_cache(kw) and 
                    kw not in processing_keywords):
                    keywords_to_process.append(kw)

        # 获取当前队列中的所有任务
        current_tasks = []
        while not task_queue.empty():
            current_tasks.append(task_queue.get())

        # 更新任务优先级
        updated_tasks = []
        processed_keywords = set()

        if isinstance(keywords, str):
            # 单个关键词，优先级为0
            keyword = keywords
            # 检查队列中是否已存在该任务
            task_found = False
            for priority, kw in current_tasks:
                if kw == keyword:
                    updated_tasks.append((0, kw))
                    task_found = True
                    processed_keywords.add(kw)
                else:
                    updated_tasks.append((priority, kw))
            
            # 只有在关键词需要处理且不在队列中时才添加
            if not task_found and keyword in keywords_to_process:
                updated_tasks.append((0, keyword))
                processed_keywords.add(keyword)
                queued_keywords.add(keyword)  # 添加到已入队集合
        else:
            # 关键词列表
            upcoming_keywords = keywords
            # 首先处理传入的关键词列表，设置它们的优先级
            for i, kw in enumerate(upcoming_keywords):
                if kw not in keywords_to_process:
                    continue  # 跳过不需要处理的关键词
                    
                # 检查当前队列中是否已有该关键词
                found_in_current = False
                for j in range(len(current_tasks)):
                    priority, current_kw = current_tasks[j]
                    if current_kw == kw:
                        # 更新优先级为传入的优先级（不管原来是什么优先级）
                        updated_tasks.append((i + 1, kw))
                        #print(f"DEBUG_QUEUE: 优先级更新为 {i+1}：{kw}")
                        found_in_current = True
                        processed_keywords.add(kw)
                        # 从current_tasks中移除这个任务，避免后续重复处理
                        current_tasks.pop(j)
                        break
                
                # 如果不在当前队列中，则添加新任务
                if not found_in_current:
                    updated_tasks.append((i + 1, kw))
                    processed_keywords.add(kw)
                    queued_keywords.add(kw)  # 添加到已入队集合
            
            # 然后处理当前队列中不在传入列表中的任务
            for priority, kw in current_tasks:
                if kw not in processed_keywords:
                    # 不在传入列表中的任务，优先级降低
                    updated_tasks.append((len(upcoming_keywords) + 1, kw))

        # 将更新后的任务重新放入队列
        for priority, kw in updated_tasks:
            task_queue.put((priority, kw))
            
        #print(f"DEBUG_QUEUE: 队列重组完成，当前任务数: {len(updated_tasks)}, 已入队关键词数: {len(queued_keywords)}")

def get_upcoming_cards(card, deck_name):
    """使用V3调度器API获取接下来的卡片的关键词，并过滤掉已经有缓存的关键词"""
    # 检查是否为单线程模式（通过executor的线程数判断）
    global executor
    is_single_threaded = executor is not None and executor._max_workers == 1
    
    # 如果是单线程模式，获取100张卡片；否则获取10张
    fetch_limit = 100 if is_single_threaded else 10
    
    # 使用V3调度器API获取队列中的卡片
    output = mw.col.sched.get_queued_cards(fetch_limit=fetch_limit, intraday_learning_only=False)
    
    if not output.cards:
        return []
    
    # 获取接下来的卡片的关键词，并过滤掉已经有缓存的
    keywords = []
    for i in range(min(fetch_limit, len(output.cards))):
        try:
            if i == 0:
                # 跳过第一张卡片，第一张卡片是当前正在学习的卡片,其他部分已经处理
                continue
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
            
            if cleaned_keyword and not load_cache(cleaned_keyword):  # 过滤空关键词和已有缓存的关键词
                keywords.append(cleaned_keyword)
                
        except Exception:
            continue
    #print(f"DEBUG: 预加载关键词（已过滤缓存）: {keywords[:10]}")
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

                # 使用新的函数重组任务队列
                reorganize_task_queue(keyword)

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
            try:
                # 获取即将到来的关键词
                upcoming_keywords = get_upcoming_cards(card, base_deck_name)
                # 重组任务队列
                reorganize_task_queue(upcoming_keywords)
            except Exception as e:
                print(f"ERROR: Failed to preload and reorganize task queue: {e}")
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

    # 清空队列和已入队集合
    while not task_queue.empty():
        try:
            _ = task_queue.get_nowait()
            task_queue.task_done()
        except queue.Empty:
            break
        except Exception as e:
            print(f"Error clearing queue during stop: {e}")
            break
    
    # 清空已入队关键词集合
    queued_keywords.clear()
    print("DEBUG: 已清空已入队关键词集合")

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
