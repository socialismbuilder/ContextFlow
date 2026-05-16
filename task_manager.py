import aqt
from aqt import mw
import queue
import threading
import time
import traceback
import concurrent.futures
from anki.cards import Card

from .config_manager import get_config, clean_html
from .cache.cache_manager import load_cache, save_cache, pop_cache
from .api_client import generate_ai_sentence


class SentenceTaskManager:
    """管理后台例句生成的优先级任务队列和线程池"""

    def __init__(self):
        self.task_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.processing_keywords: set = set()
        self.cache_lock: threading.Lock = threading.Lock()
        self.stop_event: threading.Event = threading.Event()
        self.executor: concurrent.futures.ThreadPoolExecutor = None
        self.max_workers: int = 0
        self._manager_thread: threading.Thread = None
        self.showing_sentence: str = ""
        self.showing_translation: str = ""

    # --- Lifecycle ---

    def start(self, config: dict) -> None:
        """启动线程池和管理器线程"""
        if self.executor is not None:
            print("DEBUG: 工作线程已在运行或未正确清理。")
            return

        self.stop_event.clear()
        api_url = config.get("api_url", "")

        if "ollama" in api_url.lower() or "localhost" in api_url.lower() or "127.0.0.1" in api_url.lower():
            self.max_workers = 1
            print("DEBUG: 检测到ollama或localhost API，启用单线程模式")
        else:
            self.max_workers = 3
            print("DEBUG: 使用多线程模式（3个线程）")

        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix='SentenceWorker'
        )
        self._manager_thread = threading.Thread(target=self._worker_manager, daemon=True)
        self._manager_thread.start()
        print(f"DEBUG: 句子处理线程池及管理器已启动（{self.max_workers}个线程）。")

    def stop(self) -> None:
        """停止管理器线程和线程池"""
        # 取消注册右键菜单
        try:
            from .ui import context_menu
            context_menu.unregister_context_menu()
            print("DEBUG: 选中词汇例句生成功能已停用")
        except Exception as e:
            print(f"ERROR: 取消注册选中词汇例句生成功能失败: {e}")

        print("DEBUG: Stopping sentence worker manager and thread pool...")
        self.stop_event.set()

        # 清空队列和正在处理的关键词集合
        with self.cache_lock:
            while not self.task_queue.empty():
                try:
                    self.task_queue.get_nowait()
                    self.task_queue.task_done()
                except queue.Empty:
                    break
                except Exception as e:
                    print(f"Error clearing queue during stop: {e}")
                    break
            self.processing_keywords.clear()

        if self.executor:
            print("DEBUG: Initiating immediate thread pool shutdown...")
            self.stop_event.set()
            self.executor.shutdown(wait=False)
            print("DEBUG: Thread pool shutdown completed (immediate).")
            self.executor = None

        self._manager_thread = None
        print("DEBUG: All workers stopped immediately.")

    # --- Task submission (for external callers like prompt_editor_ui) ---

    def submit_task(self, fn, *args, **kwargs):
        """向线程池提交任务，供外部调用者使用"""
        if self.executor is None:
            raise RuntimeError("Thread pool not initialized. Call start() first.")
        return self.executor.submit(fn, *args, **kwargs)

    # --- Queue management ---

    def reorganize_queue(self, keywords, is_repopulate=False):
        """
        重组任务队列，根据提供的关键词调整优先级。
        is_repopulate: 如果为True，表示由于缓存用尽而重新生成，优先级最低。
        """
        with self.cache_lock:
            if isinstance(keywords, str):
                if is_repopulate:
                    keywords_to_process = [keywords] if keywords not in self.processing_keywords else []
                else:
                    keywords_to_process = [keywords] if not load_cache(keywords) and keywords not in self.processing_keywords else []
            else:
                keywords_to_process = [kw for kw in keywords if not load_cache(kw) and kw not in self.processing_keywords]

            if not keywords_to_process:
                return

            current_tasks = []
            while not self.task_queue.empty():
                current_tasks.append(self.task_queue.get())

            updated_tasks = []
            processed_keywords = set()

            if isinstance(keywords, str):
                keyword = keywords
                target_priority = 999 if is_repopulate else 0

                task_found = False
                for priority, kw in current_tasks:
                    if kw == keyword:
                        if is_repopulate:
                            updated_tasks.append((target_priority, kw))
                        else:
                            updated_tasks.append((0, kw))
                        task_found = True
                    else:
                        updated_tasks.append((priority, kw))
                if not task_found and keyword in keywords_to_process:
                    print(f"DEBUG: 新任务添加到队列: {keyword} (优先级: {target_priority})")
                    updated_tasks.append((target_priority, keyword))
            else:
                upcoming_keywords = keywords
                for priority, kw in current_tasks:
                    if priority == 0:
                        processed_keywords.add(kw)
                        updated_tasks.append((priority, kw))
                    elif kw in upcoming_keywords:
                        new_priority = upcoming_keywords.index(kw) + 1
                        updated_tasks.append((new_priority, kw))
                        processed_keywords.add(kw)
                    else:
                        updated_tasks.append((len(upcoming_keywords) + 1, kw))
                        processed_keywords.add(kw)

                for i, kw in enumerate(upcoming_keywords):
                    if kw not in processed_keywords and kw in keywords_to_process:
                        updated_tasks.append((i + 1, kw))

            for priority, kw in updated_tasks:
                self.task_queue.put((priority, kw))

    def get_upcoming_card_keywords(self, deck_name):
        """获取接下来的卡片关键词（调度器队列+学习中卡片），并过滤掉已有缓存的关键词"""
        is_single_threaded = self.executor is not None and self.max_workers == 1
        fetch_limit = 100 if is_single_threaded else 20

        output = mw.col.sched.get_queued_cards(fetch_limit=fetch_limit, intraday_learning_only=False)
        queued_cards = output.cards[1:] if output.cards else []  # 跳过第一张（当前卡片）

        # 补充学习中的卡片（调度器已吐出过的不在队列中）
        learn_card_ids = aqt.mw.col.find_cards(f"deck:{deck_name} is:learn")
        learn_cards = []
        for cid in learn_card_ids:
            try:
                learn_cards.append(mw.col.get_card(cid))
            except Exception:
                continue

        seen_keywords = set()
        keywords = []

        for kw in self._iter_card_keywords(queued_cards, deck_name, use_backend=True):
            if kw not in seen_keywords:
                seen_keywords.add(kw)
                keywords.append(kw)

        for kw in self._iter_card_keywords(learn_cards, deck_name, use_backend=False):
            if kw not in seen_keywords:
                seen_keywords.add(kw)
                keywords.append(kw)

        return keywords

    def _iter_card_keywords(self, cards, deck_name, use_backend=True):
        """从卡片列表中提取目标牌组的关键词（已过滤缓存）"""
        for card_or_queued in cards:
            try:
                if use_backend:
                    upcoming_card = Card(mw.col, backend_card=card_or_queued.card)
                else:
                    upcoming_card = card_or_queued

                card_deck_name = aqt.mw.col.decks.name(upcoming_card.did)
                if not (card_deck_name == deck_name or card_deck_name.startswith(deck_name + "::")):
                    continue

                note = upcoming_card.note()
                first_field = note.fields[0] if note.fields else ""
                cleaned_keyword = clean_html(first_field)

                if cleaned_keyword and not load_cache(cleaned_keyword):
                    yield cleaned_keyword
            except Exception:
                continue

    # --- Internal workers ---

    def _process_keyword_task(self, keyword_with_priority):
        """处理单个关键词生成任务（由线程池中的线程调用）"""
        priority, keyword = keyword_with_priority

        if self.stop_event.is_set():
            print(f"DEBUG: 停止事件已设置，跳过处理关键词: {keyword}")
            with self.cache_lock:
                if keyword in self.processing_keywords:
                    self.processing_keywords.remove(keyword)
            return

        config = get_config()
        print(f"DEBUG:正在处理关键词: {keyword} (优先级: {priority})")

        try:
            sentence_pairs = generate_ai_sentence(config, keyword)

            if sentence_pairs:
                with self.cache_lock:
                    save_cache(keyword, sentence_pairs)

        except Exception as e:
            print(f"ERROR: Worker failed to generate/cache sentences for '{keyword}': {type(e).__name__} - {str(e)}")
            traceback.print_exc()
        finally:
            with self.cache_lock:
                if keyword in self.processing_keywords:
                    self.processing_keywords.remove(keyword)

    def _worker_manager(self):
        """后台工作线程管理器，从队列中获取任务并提交到线程池"""
        if self.executor is None:
            print("ERROR: Thread pool executor not initialized in _worker_manager.")
            return

        while not self.stop_event.is_set():
            try:
                if self.executor._work_queue.qsize() >= self.max_workers:
                    time.sleep(0.1)
                    continue

                try:
                    priority, keyword = self.task_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                with self.cache_lock:
                    if keyword in self.processing_keywords:
                        self.task_queue.task_done()
                        continue
                    self.processing_keywords.add(keyword)

                keyword_with_priority = (priority, keyword)
                future = self.executor.submit(self._process_keyword_task, keyword_with_priority)

                def task_completed_callback(f):
                    self.task_queue.task_done()
                    with self.cache_lock:
                        remaining_tasks = self.task_queue.qsize() + len(self.processing_keywords)
                    message = f"后台缓存+1，生成队列剩余: {remaining_tasks} 个。"
                    aqt.mw.taskman.run_on_main(lambda: aqt.utils.tooltip(message, period=2000, parent=mw))

                future.add_done_callback(task_completed_callback)

            except queue.Empty:
                time.sleep(0.2)
                continue
            except Exception as e:
                print(f"ERROR: Error getting/submitting task from/to queue: {e}")
                with self.cache_lock:
                    if 'keyword' in locals() and keyword in self.processing_keywords:
                        self.processing_keywords.remove(keyword)
                try:
                    self.task_queue.task_done()
                except ValueError:
                    pass
                continue

        print("DEBUG: Sentence worker manager thread stopped.")
