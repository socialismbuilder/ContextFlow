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

# 使用相对导入来引入其他模块的功能
from .config_manager import get_config
from .cache_manager import load_cache, save_cache
from .api_client import generate_ai_sentence
from .Process_Card import Process_back_html,Process_front_html

# --- 后台任务队列 ---
task_queue = queue.PriorityQueue() # 使用优先级队列
cache_lock = threading.Lock() # 用于保护缓存访问和队列检查/添加
stop_event = threading.Event()
# worker_thread = None # 不再需要单个工作线程，将使用线程池
executor = None # 用于管理线程池
# --- 结束后台任务队列 ---

# showing_sentence 和 showing_translation 仍然需要，用于跨 question/answer 状态传递
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
    """后台工作线程管理器，从队列中获取任务并提交到线程池"""
    global executor
    if executor is None: # 确保线程池已初始化
        print("ERROR: Thread pool executor not initialized in _sentence_worker_manager.")
        return

    while not stop_event.is_set():
        try:
            # 等待任务，设置超时以便能响应 stop_event
            # PriorityQueue.get() 返回 (priority, item)
            keyword_with_priority = task_queue.get(timeout=1)
            # 将任务提交给线程池
            # executor.submit 返回一个 Future 对象，我们这里不需要它
            # 我们需要确保 task_done 在任务完成后被调用
            future = executor.submit(_process_keyword_task, keyword_with_priority)
            # 当任务完成时调用 task_done
            future.add_done_callback(lambda f: task_queue.task_done())

        except queue.Empty:
            continue # 队列为空，继续循环等待
        except Exception as e:
            print(f"ERROR: Error getting/submitting task from/to queue: {e}")
            # 如果从队列获取任务时出错，可能需要将任务放回或记录
            # 如果是 submit 出错，也需要处理
            # 简单起见，暂时仅打印错误并继续
            # 如果任务已取出但提交失败，需要 task_queue.task_done() 或重新入队
            try:
                # 尝试标记任务完成，即使处理失败，以避免队列阻塞
                task_queue.task_done()
            except ValueError: # 如果任务未被 get
                pass
            continue

    print("DEBUG: Sentence worker manager thread stopped.")


def get_upcoming_cards(card):
    config = get_config()
    deck_name = config.get("deck_name")
    print(f"目标牌组: {deck_name}")

    # Initialize empty lists for keywords
    new_keywords = []
    learn_keywords = []
    review_keywords = []

    # Get 3 new cards
    new_query = f"deck:{deck_name} is:new"
    new_card_ids = mw.col.find_cards(new_query)[:3]  # Limit to 3

    for card_id in new_card_ids:
        card = mw.col.get_card(card_id)
        keyword = card.note().fields[0]
        # Clean the keyword
        keyword = re.sub('<.*?>', '', keyword)  # Remove HTML tags
        keyword = re.sub('\[.*?\]', '', keyword)  # Remove sound tags
        keyword = keyword.strip()
        new_keywords.append(keyword)

    # Get 3 learning cards
    learning_query = f"deck:{deck_name} is:learn"
    learning_card_ids = mw.col.find_cards(learning_query)  # Limit to 3

    for card_id in learning_card_ids:
        card = mw.col.get_card(card_id)
        keyword = card.note().fields[0]
        # Clean the keyword
        keyword = re.sub('<.*?>', '', keyword)  # Remove HTML tags
        keyword = re.sub('\[.*?\]', '', keyword)  # Remove sound tags
        keyword = keyword.strip()
        learn_keywords.append(keyword)

    # Get 3 review cards
    review_query = f"deck:{deck_name} is:due"
    review_card_ids = mw.col.find_cards(review_query)  # Limit to 3

    for card_id in review_card_ids:
        card = mw.col.get_card(card_id)
        keyword = card.note().fields[0]
        # Clean the keyword
        keyword = re.sub('<.*?>', '', keyword)  # Remove HTML tags
        keyword = re.sub('\[.*?\]', '', keyword)  # Remove sound tags
        keyword = keyword.strip()
        review_keywords.append(keyword)

    # Combine results
    #all_keywords = new_keywords + learn_keywords + review_keywords
    all_keywords = list(dict.fromkeys(new_keywords + learn_keywords + review_keywords))

    # Print results
    #print(f"新学卡片关键词 ({len(new_keywords)}张): {new_keywords}")
    #print(f"学习中卡片关键词 ({len(learn_keywords)}张): {learn_keywords}")
    #print(f"复习卡片关键词 ({len(review_keywords)}张): {review_keywords}")
    print(f"全部关键词:共 {len(all_keywords)}个")

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
        print("当前牌组名称："+current_deck)
    except Exception as e:
        print(f"ERROR: 获取牌组名称失败 for card {card.id}: {e}")
        return html # 获取失败则不处理

    # 仅目标牌组生效
    if current_deck == config.get("deck_name"): # 使用 .get 避免 KeyError
        # 获取当前复习器状态（'question' 或 'answer'）
        state = aqt.mw.reviewer.state if aqt.mw.reviewer else 'unknown'

        # --- 根据复习器状态区分处理 ---
        if state == 'question':
            # 如果是显示问题面
            try:
                note = card.note()
                # 假设关键词在第一个字段
                keyword = note.fields[0].strip() if note.fields and len(note.fields) > 0 else ""
                keyword = re.sub('<.*?>', '', keyword)
                keyword = re.sub('\[.*?\]', '', keyword).strip()
                

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
                        print(f"DEBUG: 显示 '{keyword}' 的缓存句子")
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
                    print(f"DEBUG: Added '{keyword}' to queue (cache miss, priority 0).")

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
                        showing_sentence = "超时：未找到例句"
                        showing_translation = ""
                        if mw.reviewer and mw.reviewer.card and mw.reviewer.card.id == card.id:
                            return

                    # 检查缓存（主线程安全）
                    with cache_lock:
                        cache = load_cache()
                        if keyword in cache and cache[keyword]:
                            timer.stop()  # 停止QTimer
                            mw.progress.finish()
                            # 取出第一个例句对并更新缓存
                            sentence_pairs = cache[keyword]
                            if sentence_pairs:
                                sentence_list = sentence_pairs.pop(0)
                                current_sentence, current_translation = sentence_list
                                cache[keyword] = sentence_pairs
                                save_cache(cache)
                                showing_sentence = current_sentence
                                showing_translation = current_translation
                            if mw.reviewer and mw.reviewer.card and mw.reviewer.card.id == card.id:
                                mw.reset()
                            return

                # 连接QTimer的timeout信号到更新函数
                timer.timeout.connect(update_ui)
                # 启动定时器（100ms间隔）
                timer.start(100)

                # 设置初始显示状态
                showing_sentence = "例句生成中..."
                showing_translation = ""
                html_to_return = Process_front_html(showing_sentence)

            # --- Preloading Logic (Runs AFTER determining initial HTML) ---
            print("DEBUG: 开始预加载逻辑...")
            try:
                upcoming_keywords = get_upcoming_cards(card) # Call the function to get upcoming keywords
                print(f"DEBUG: 预加载检查 - 待处理关键词: {upcoming_keywords}") # 添加日志
                if upcoming_keywords:
                    with cache_lock: # Lock for safe cache access and queue adding
                        cache = load_cache() # Load cache once inside the lock
                        # Get current queue items to avoid adding duplicates unnecessarily
                        # Note: This is a snapshot, race conditions still possible but less likely
                        current_queue_items = set(item for item in task_queue.queue)

                        for kw in upcoming_keywords:
                            #if kw and kw not in cache and kw not in current_queue_items:
                            if kw and (kw not in cache or (not cache.get(kw))) and kw not in current_queue_items:
                                task_queue.put((1, kw)) # 被动缓存，低优先级 (1)
                                print(f"DEBUG: Preloading - Added '{kw}' to queue (priority 1).")
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
    """启动后台例句生成工作线程（现在是线程池和管理器）"""
    global executor, manager_thread # manager_thread 将是运行 _sentence_worker_manager 的线程
    if executor is None: # 或者检查 manager_thread 是否存活
        stop_event.clear()
        # 创建一个固定大小为5的线程池
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        # 启动一个单独的线程来管理从队列到线程池的任务提交
        manager_thread = threading.Thread(target=_sentence_worker_manager, daemon=True)
        manager_thread.start()
        print("DEBUG: 句子处理线程池和管理器已启动。")

def stop_worker():
    """停止后台例句生成工作线程（线程池和管理器）"""
    global executor, manager_thread
    if executor:
        print("DEBUG: Stopping sentence worker manager and thread pool...")
        stop_event.set() # 通知 _sentence_worker_manager 停止

        # 清空队列，帮助 manager_thread 退出 get() 调用
        # 注意：这可能导致正在处理的任务丢失，但对于关闭是必要的
        while not task_queue.empty():
            try:
                # 从优先级队列中取出项，它是一个元组 (priority, item)
                _ = task_queue.get_nowait() # 取出但不处理
                task_queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                print(f"Error clearing queue during stop: {e}")
                break

        # 等待 manager_thread 结束
        if manager_thread and manager_thread.is_alive():
            manager_thread.join(timeout=5) # 等待管理器线程结束
            if manager_thread.is_alive():
                print("WARNING: Sentence worker manager thread did not stop gracefully.")

        # 关闭线程池
        # shutdown(wait=True) 会等待所有已提交的任务完成
        # shutdown(wait=False) 会尝试取消待处理的任务并立即返回
        # 我们希望尽快关闭，但也要给正在运行的任务一点时间
        executor.shutdown(wait=True, cancel_futures=False) # 等待当前任务完成，不取消
        print("DEBUG: Thread pool shutdown complete.")
        executor = None
        manager_thread = None # 清理 manager_thread 引用
    else:
        print("DEBUG: Worker (executor) not running or already stopped.")


def register_hooks():
    """注册所有需要的钩子，并启动工作线程"""
    gui_hooks.card_will_show.append(on_card_render)
    gui_hooks.profile_will_close.append(stop_worker) # 注册停止函数
    # Optionally, add hook for addon unload if needed, though profile_will_close often covers it
    # aqt.addHook("unloadAddon", stop_worker) # Example if using older hook system

    start_worker() # 启动工作线程
