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
# 使用相对导入来引入其他模块的功能
from .config_manager import get_config
from .cache_manager import load_cache, save_cache
from .api_client import generate_ai_sentence
from .Process_Card import Process_back_html,Process_front_html
from .stats import add_stats
# --- 后台任务队列 ---
task_queue = queue.PriorityQueue() # 使用优先级队列
cache_lock = threading.Lock() # 用于保护缓存访问和队列检查/添加
stop_event = threading.Event()
high_prio_executor = None # 用于高优先级任务
low_prio_executor = None  # 用于低优先级任务
Occupy_bar = False
# executor = None # 不再需要单个执行器
# --- 结束后台任务队列 ---

# showing_sentence 和 showing_translation 仍然需要，用于跨 question/answer 状态传递
showing_sentence = ""
showing_translation = ""
upcoming_cards_cache = []  # 全局缓存，存储排序后的新卡片关键词列表
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
                cache = load_cache()
                cache[keyword] = sentence_pairs # 存储列表的列表
                save_cache(cache)
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
    """后台工作线程管理器，从队列中获取任务并提交到相应的线程池"""
    global high_prio_executor, low_prio_executor
    if high_prio_executor is None or low_prio_executor is None:
        print("ERROR: One or both thread pool executors not initialized in _sentence_worker_manager.")
        return

    while not stop_event.is_set():
        try:
            priority, keyword = task_queue.get(timeout=1) # 解包
            keyword_with_priority = (priority, keyword) # 重新打包以传递

            #rint(f"DEBUG_QUEUE: 从队列中获取任务: {keyword} (优先级: {priority})")

            if priority == 0: # 假设0是最高优先级
                #print(f"DEBUG_QUEUE: 提交高优先级任务到 high_prio_executor: {keyword}")
                future = high_prio_executor.submit(_process_keyword_task, keyword_with_priority)
            else:
                #print(f"DEBUG_QUEUE: 提交低优先级任务到 low_prio_executor: {keyword}")
                future = low_prio_executor.submit(_process_keyword_task, keyword_with_priority)
            
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



def get_upcoming_cards(card,deck_name):

    config = get_config()

    # Initialize empty lists for keywords
    new_keywords = []
    learn_keywords = []
    review_keywords = []


    # 优化后的缓存逻辑
    global upcoming_cards_cache  # 声明使用全局缓存

    # 初始化new_keywords
    new_keywords = []

    # 检查缓存是否存在（非空）
    if upcoming_cards_cache:
        #print("成功获取缓存")
        # 获取当前卡片的keyword（用于查找缓存位置）
        current_raw_keyword = card.note().fields[0] if card.note().fields else ""
        current_keyword = clean_html(current_raw_keyword)

        # 查找当前keyword在缓存中的位置
        try:
            index = upcoming_cards_cache.index(current_keyword)
            # 取缓存中当前位置之后的三个关键词（最多三个）
            new_keywords = upcoming_cards_cache[index+1:index+4]
            #print("从缓存取出三个新词")
        except ValueError:
            # 缓存中找不到当前keyword，清空缓存并重置new_keywords
            new_keywords = []
            #print("缓存中未找到该词")
    else:
        #print("未获取缓存")
        # 缓存不存在，启动异步排序并显示进度条
        new_query = f"deck:{deck_name} is:new"
        all_new_card_ids = mw.col.find_cards(new_query)  # 获取所有新卡片ID
        all_new_cards = [mw.col.get_card(cid) for cid in all_new_card_ids]  # 提前获取卡片对象
        
        # 启动进度条
        mw.progress.start(
            immediate=True,
            label="正在排序新卡片...",
            min=0,
            max=100
        )
        
        # 定义异步排序任务
        def async_sort():
            return sorted(all_new_cards, key=lambda c: c.due)  # 按due升序排序

        # 提交到高优先级线程池
        future = high_prio_executor.submit(async_sort)
        
        # 使用QTimer轮询排序状态
        timer = QTimer()
        start_time = time.time()
        max_wait = 30  # 最大等待30秒

        def check_sort_complete():
            nonlocal timer
            if future.done():
                timer.stop()
                mw.progress.finish()
                try:
                    sorted_new_cards = future.result()
                    # 处理排序后的卡片，生成并缓存关键词
                    upcoming_cards_cache.clear()
                    for c in sorted_new_cards:
                        raw_keyword = c.note().fields[0] if c.note().fields else ""
                        keyword = clean_html(raw_keyword)
                        if keyword:  # 过滤空关键词
                            upcoming_cards_cache.append(keyword)
                    # 初始加载时取前三个关键词作为new_keywords
                    nonlocal new_keywords
                    new_keywords = upcoming_cards_cache[:3]
                except Exception as e:
                    print(f"排序过程中发生错误: {str(e)}")
                    new_keywords = []
                return

            # 进度条更新（简单线性进度）
            elapsed = time.time() - start_time
            progress = int((elapsed / max_wait) * 100)
            global Occupy_bar
            if not Occupy_bar:
                mw.progress.update(
                    label=f"正在排序新卡片... ({min(int(elapsed), max_wait)}秒/{max_wait}秒)",
                    value=min(progress, 100)
                )
            print(future.done())

            # 超时处理
            if elapsed >= max_wait:
                timer.stop()
                mw.progress.finish()
                print("警告：新卡片排序超时")
                new_keywords = []

        # 启动定时器检查排序状态（每100ms检查一次）
        timer.timeout.connect(check_sort_complete)
        timer.start(100)
    
    print(new_keywords)

    # Get 3 learning cards
    learning_query = f"deck:{deck_name} is:learn"
    learning_card_ids = mw.col.find_cards(learning_query) 

    for card_id in learning_card_ids:
        card = mw.col.get_card(card_id)
        keyword = card.note().fields[0]
        # Clean the keyword
        keyword = clean_html(keyword)
        learn_keywords.append(keyword)

    # Get 3 review cards
    review_query = f"deck:{deck_name} is:due"
    review_card_ids = mw.col.find_cards(review_query)  # Limit to 3

    for card_id in review_card_ids:
        card = mw.col.get_card(card_id)
        keyword = card.note().fields[0]
        # Clean the keyword
        keyword = clean_html(keyword)
        review_keywords.append(keyword)

    # Combine results
    #all_keywords = new_keywords + learn_keywords + review_keywords
    all_keywords = list(dict.fromkeys(new_keywords + learn_keywords + review_keywords))

    # Print results
    #print(f"新学卡片关键词 ({len(new_keywords)}张): {new_keywords}")
    #print(f"学习中卡片关键词 ({len(learn_keywords)}张): {learn_keywords}")
    #print(f"复习卡片关键词 ({len(review_keywords)}张): {review_keywords}")
    #print(f"全部关键词:共 {len(all_keywords)}个")

    return all_keywords


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

            cache = load_cache()

            if keyword in cache:
                # --- Cache Hit Logic ---
                try:
                    sentence_pairs = cache[keyword]
                    # 验证缓存数据格式 (从JSON加载后应为列表的列表)
                    if not isinstance(sentence_pairs, list) or not all(isinstance(p, list) and len(p) == 2 for p in sentence_pairs):
                        # 检查内部元素是否为列表
                        err_msg = f"缓存数据格式错误：关键词 '{keyword}' 对应的值不是 [例句, 翻译] 列表的列表，而是 {type(sentence_pairs)} 或内部元素格式不正确。"
                        print(err_msg)
                        # 打印具体内容帮助调试
                        print(f"调试：'{keyword}'的缓存数据无效：{sentence_pairs}")
                        aqt.utils.showInfo(err_msg + " 请检查调试控制台。")
                        del cache[keyword] # 删除错误数据
                        save_cache(cache)
                        # _clear_processing_state() # Removed
                        return "缓存数据格式错误"

                    if sentence_pairs:
                        # 缓存列表非空，取出第一个列表
                        # --- Cache Hit ---
                        sentence_list = sentence_pairs.pop(0)
                        current_sentence, current_translation = sentence_list
                        cache[keyword] = sentence_pairs # Update cache with remaining pairs
                        save_cache(cache)
                        # _clear_processing_state() # Removed
                        showing_sentence = current_sentence
                        showing_translation = current_translation
                        #print(f"DEBUG: 显示 '{keyword}' 的缓存句子")
                        html_to_return = Process_front_html(current_sentence) # Set HTML for return
                    else:
                        # --- Cache Hit but list is empty ---
                        del cache[keyword] # Remove empty entry
                        save_cache(cache)
                        # _clear_processing_state() # Removed
                        showing_sentence = "无可用缓存例句" # Display message
                        showing_translation = ""
                        print(f"DEBUG: 关键字 '{keyword}' 的缓存条目为空，正在请求生成。")
                        # Add to queue even if cache was empty, worker will handle generation
                        with cache_lock: # Use lock for queue access consistency
                            # Check if already in queue? Maybe not necessary, worker checks cache again.
                            task_queue.put((0, keyword)) # 主动缓存，高优先级 (0)
                            print(f"DEBUG: 将'{keyword}'加入队列（来自空缓存，优先级0）。")
                        # Need to start waiting process even if cache was hit but empty
                        # Treat as cache miss for waiting purposes
                        print(f"DEBUG: 缓存命中但内容为空，关键词为'{keyword}'。开始等待。")
                        # Fall through to cache miss logic below
                        pass # Let the 'else' block handle the waiting start

                except KeyError:
                    # This shouldn't happen due to 'if keyword in cache' check, but handle defensively
                    aqt.utils.showInfo(f"缓存读取异常：关键词 '{keyword}' 在尝试读取时不存在。")
                    # _clear_processing_state() # Removed
                    showing_sentence = "缓存读取异常"
                    showing_translation = ""
                    html_to_return = Process_front_html(showing_sentence) # Set error HTML
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = f"处理缓存时发生意外错误 ({error_type})：{str(e)}"
                    print(error_msg)
                    aqt.utils.showInfo(error_msg)
                    # _clear_processing_state() # Removed
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
                    # 检查是否已在队列中或正在处理？现在等待的优先级较低。
                    task_queue.put((0, keyword)) # 主动缓存，高优先级 (0)
                    print(f"DEBUG: 已添加'{keyword}'到队列（缓存未命中，优先级0）。")

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
                        cache = load_cache()
                        if keyword in cache and cache[keyword]:
                            timer.stop()  # 停止QTimer
                            mw.progress.finish()
                            # 取出第一个例句对并更新缓存
                            sentence_pairs = cache[keyword]
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
                        cache = load_cache() # Load cache once inside the lock
                        # Get current queue items to avoid adding duplicates unnecessarily
                        # Note: This is a snapshot, race conditions still possible but less likely
                        current_queue_items = set(item for item in task_queue.queue)

                        for kw in upcoming_keywords:
                            #if kw and kw not in cache and kw not in current_queue_items:
                            if kw and (kw not in cache or (not cache.get(kw))) and kw not in current_queue_items and kw != keyword:
                                task_queue.put((1, kw)) # 被动缓存，低优先级 (1)
                                #print(f"调试：预加载 - 已将'{kw}'加入队列（优先级1）。")
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
    """启动后台例句生成工作线程（现在是两个线程池和管理器）"""
    global high_prio_executor, low_prio_executor, manager_thread
    if high_prio_executor is None and low_prio_executor is None:
        stop_event.clear()
        # 创建两个线程池
        # 例如：高优先级用1个线程，低优先级用9个线程
        high_prio_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='HighPrioWorker')
        low_prio_executor = concurrent.futures.ThreadPoolExecutor(max_workers=9, thread_name_prefix='LowPrioWorker')
        
        manager_thread = threading.Thread(target=_sentence_worker_manager, daemon=True)
        manager_thread.start()
        print("DEBUG: 高优先级和低优先级句子处理线程池及管理器已启动。")
    else:
        print("DEBUG: 工作线程已在运行或未正确清理。")


def stop_worker():
    """停止后台例句生成工作线程（两个线程池和管理器）"""
    global high_prio_executor, low_prio_executor, manager_thread
    
    print("DEBUG: Stopping sentence worker manager and thread pools...")
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
    
    # 关闭高优先级线程池
    if high_prio_executor:
        high_prio_executor.shutdown(wait=True, cancel_futures=False)
        print("DEBUG: High-priority thread pool shutdown complete.")
        high_prio_executor = None
        
    # 关闭低优先级线程池
    if low_prio_executor:
        low_prio_executor.shutdown(wait=True, cancel_futures=False)
        print("DEBUG: Low-priority thread pool shutdown complete.")
        low_prio_executor = None
        
    manager_thread = None # 清理 manager_thread 引用
    
    if high_prio_executor is None and low_prio_executor is None:
        print("DEBUG: All workers stopped and cleaned up.")
    else:
        print("DEBUG: Worker (executors) not running or already stopped, or cleanup issue.")

def register_hooks():
    """注册所有需要的钩子，并启动工作线程"""
    gui_hooks.card_will_show.append(on_card_render)
    gui_hooks.profile_will_close.append(stop_worker) # 注册停止函数
    gui_hooks.profile_did_open.append(start_worker)
    gui_hooks.stats_dialog_will_show.append(add_stats) # 添加统计钩子
    start_worker() # 启动工作线程
