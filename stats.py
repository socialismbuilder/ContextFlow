import aqt
from aqt import gui_hooks, mw
from aqt.stats import NewDeckStats
from aqt.qt import (
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTabWidget,
    QSizePolicy,
    QScrollArea,
    Qt,
    QPushButton,
    QLabel
)
from aqt.webview import AnkiWebView
from datetime import datetime, date, timedelta
# --- 新增函数：用于创建自定义统计选项卡的内容 ---
def create_custom_stats_tab_content(deck_name: str) -> QWidget:
    """
    创建并返回包含所有自定义统计内容的 QWidget。
    所有自定义统计界面的修改都应在此函数内部进行。
    """
    print("--- create_custom_stats_tab_content: 正在构建自定义统计内容... ---")
    print(f"当前牌组名称: {deck_name}")

    # 创建自定义统计内容的容器
    my_custom_stats_container = QWidget()
    # 使用 QVBoxLayout 作为主布局，垂直排列内容
    my_custom_stats_layout = QVBoxLayout(my_custom_stats_container)
    my_custom_stats_layout.setContentsMargins(15, 15, 15, 15) # 增加一些边距
    
    # 创建统计信息WebView
    stats_webview = AnkiWebView()
    stats_webview.setMinimumHeight(400)
    my_custom_stats_layout.addWidget(stats_webview)
    
    # 存储当前牌组名称和WebView引用以便刷新
    my_custom_stats_container.deck_name = deck_name
    my_custom_stats_container.stats_webview = stats_webview
    
    # 初始生成统计内容
    refresh_stats_content(my_custom_stats_container, deck_name)

    print("--- create_custom_stats_tab_content: 自定义统计内容构建完成。 ---")
    return my_custom_stats_container

# 辅助函数：获取指定牌组在日期范围内的学习数据
def get_deck_study_stats_for_date_range(deck_name: str, start_date: date, end_date: date) -> tuple[dict, dict]:
    """
    查询指定牌组在给定日期范围内的学习卡片数量和总学习时间，按日期分组。
    
    注意：此函数需要在一个Anki插件环境或任何可以访问 `mw.col` (Anki收藏对象) 的环境中运行。
          `mw.col` 通常通过 `from aqt import mw` 获得。

    :param deck_name: 要查询的牌组名称。
    :param start_date: 查询的开始日期（datetime.date 对象）。
    :param end_date: 查询的结束日期（datetime.date 对象）。
    :return: 两个字典 (按日期的卡片数量, 按日期的学习时间_秒)。
             如果牌组未找到，或 Anki 收藏不可用，或发生错误，返回 ({}, {})。
    """
    # 确保 Anki 收藏对象 mw.col 是可用的
    if mw is None or mw.col is None:
        print("错误：Anki 收藏未打开或不可用。")
        return {}, {}

    cards_by_date = {}
    time_by_date = {}

    try:
        # 1. 根据牌组名称获取牌组 ID
        deck = mw.col.decks.by_name(deck_name)
        if not deck:
            print(f"牌组 '{deck_name}' 未找到。")
            return {}, {}
        deck_id = deck['id']
        
        # 2. 构建时间范围的时间戳（毫秒）
        # 开始日期：当天的凌晨4点（04:00:00）
        start_dt = datetime(start_date.year, start_date.month, start_date.day, 4, 0, 0)
        # 结束日期：结束日期下一天的凌晨4点减去1微秒（即结束日期那一天的最后一刻是第二天的03:59:59.999999）
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 4, 0, 0) + timedelta(days=1) - timedelta(microseconds=1)
        
        start_timestamp = int(start_dt.timestamp() * 1000)
        end_timestamp = int(end_dt.timestamp() * 1000)
        
        # 3. 获取所有匹配牌组ID(包含子牌组)
        deck_ids = [d['id'] for d in mw.col.decks.all() if deck_name in d['name']]
        
        if not deck_ids:
            return {}, {}
            
        # 构建查询语句 - 按日期分组
        query = f"""
            SELECT 
                strftime('%m-%d', datetime((id/1000)-14400, 'unixepoch', 'localtime')) as day,
                COUNT(*) as cards,
                SUM(time)/1000.0 as study_time
            FROM revlog 
            WHERE cid IN (
                SELECT id FROM cards WHERE did IN ({','.join(str(id) for id in deck_ids)})
            ) AND id >= {start_timestamp}
            AND id <= {end_timestamp}
            AND time > 1  -- 过滤学习时间小于0.1秒的记录
            GROUP BY day
            ORDER BY day
        """
        
        # 执行查询
        for day, cards, study_time in mw.col.db.execute(query):
            cards_by_date[day] = cards
            time_by_date[day] = study_time
            
    except Exception as e:
        print(f"查询学习统计时出错: {e}")
        return {}, {}

    return cards_by_date, time_by_date

# 刷新统计内容函数
def refresh_stats_content(container, deck_name):
    """刷新统计内容"""
    print(f"--- 刷新统计内容，牌组: {deck_name} ---")
    
    # 检查容器和WebView是否有效
    if not container or not hasattr(container, 'stats_webview') or not container.stats_webview:
        print("刷新终止: 统计组件已被销毁")
        return
        
    stats_webview = container.stats_webview
    # 设置加载中状态
    stats_webview.setHtml('<div style="padding:20px;text-align:center;">数据加载中...</div>')
    end_date = date.today()
    start_date = end_date - timedelta(days=364)  # 获取1年数据
    
    # 一次性获取所有数据
    cards_by_date, time_by_date = get_deck_study_stats_for_date_range(deck_name, start_date, end_date)
    
    # 准备图表数据
    dates = []
    cards_data = []
    time_data = []
    avg_time_data = []
    total_cards_data = []
    total_time_data = []
    
    # 填充日期序列并匹配数据（从最早日期开始）
    for i in reversed(range(365)):
        day_date = end_date - timedelta(days=i)
        date_str = day_date.strftime('%m-%d')
        cards = cards_by_date.get(date_str, 0)
        study_time = time_by_date.get(date_str, 0)
        
        # 计算平均学习时间
        avg_time = study_time / cards if cards > 0 else 0
        study_time_minutes = study_time / 60  # 转换为分钟
        
        dates.append(date_str)
        cards_data.append(cards)
        time_data.append(study_time_minutes)
        avg_time_data.append(avg_time)
    
    # 计算累计值（从最早日期开始累加）
    total_cards = 0
    total_time_minutes = 0
    for i in range(len(dates)):
        total_cards += cards_data[i]
        total_time_minutes += time_data[i]
        total_cards_data.append(total_cards)
        total_time_data.append(total_time_minutes / 60)  # 转换为小时
    
    # 过滤前端连续为0的数据
    first_non_zero = 0
    for i, cards in enumerate(cards_data):
        if cards > 0:
            first_non_zero = i
            break
            
    dates = dates[first_non_zero:]
    cards_data = cards_data[first_non_zero:]
    time_data = time_data[first_non_zero:]
    avg_time_data = avg_time_data[first_non_zero:]
    total_cards_data = total_cards_data[first_non_zero:]
    total_time_data = total_time_data[first_non_zero:]
    
    # 从模板文件读取HTML内容（使用插件根目录路径）
    import os
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'stats.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 读取chart.js文件内容
    chart_js_path = os.path.join(os.path.dirname(__file__), 'chart.js')
    with open(chart_js_path, 'r', encoding='utf-8') as f:
        chart_js_content = f.read()
    
    # 替换模板变量
    html_content = html_content.replace('{deck_name}', deck_name)
    html_content = html_content.replace('{dates}', str(dates))
    html_content = html_content.replace('{cards_data}', str(cards_data))
    html_content = html_content.replace('{time_data}', str(time_data))
    html_content = html_content.replace('{avg_time_data}', str(avg_time_data))
    html_content = html_content.replace('{total_cards_data}', str(total_cards_data))
    html_content = html_content.replace('{total_time_data}', str(total_time_data))
    html_content = html_content.replace('{chart_js_content}', chart_js_content)
    
    # 设置HTML内容
    stats_webview.setHtml(html_content)


# --- 原始函数：保持函数签名不变 ---
def add_stats(statsdialog: NewDeckStats) -> None:
    """
    给 Anki 的新版统计对话框添加选项卡，一个显示原生统计，一个显示自定义统计。
    """
    print(f"--- add_stats (Tabbed Interface): 正在尝试创建选项卡界面 (Anki 版本: {aqt.appVersion})... ---")
    print(f"传入的 statsdialog 类型: {type(statsdialog)}")

    # 1. 创建 QTabWidget
    tab_widget = QTabWidget(statsdialog)
    tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # 2. 准备原生统计内容的容器
    original_stats_container = QWidget()
    original_stats_layout = QVBoxLayout(original_stats_container)
    original_stats_layout.setContentsMargins(0, 0, 0, 0)

    # 遍历 statsdialog 的主布局，将所有现有控件移动到 original_stats_container
    main_dialog_layout = statsdialog.layout()
    if not main_dialog_layout:
        print("错误：statsdialog.layout() 返回 None。无法创建选项卡界面。")
        return

    widgets_to_move = []
    for i in range(main_dialog_layout.count()):
        item = main_dialog_layout.itemAt(i)
        if item and item.widget():
            widgets_to_move.append(item.widget())

    for widget in widgets_to_move:
        main_dialog_layout.removeWidget(widget)
        original_stats_layout.addWidget(widget)
        print(f"  移动原生控件: {getattr(widget, 'objectName', 'N/A')()} (类型: {type(widget).__name__})")

    # 3. 调用新函数来获取自定义统计内容的容器，传入当前牌组名称
        # 获取当前牌组名称
        try:
            current_deck = mw.col.decks.current()
            current_deck_name = current_deck['name'] if current_deck else '未知牌组'
            print(f"当前牌组名称: {current_deck_name}")
        except Exception as e:
            print(f"获取牌组名称时出错: {e}")
            current_deck_name = '未知牌组'
        
    my_custom_stats_container = create_custom_stats_tab_content(current_deck_name)

    # 4. 将选项卡添加到 QTabWidget
    tab_widget.addTab(original_stats_container, "Anki 统计")
    tab_widget.addTab(my_custom_stats_container, "我的统计")

    # 5. 将 QTabWidget 添加到 statsdialog 的主布局
    main_dialog_layout.addWidget(tab_widget)
    main_dialog_layout.setStretch(main_dialog_layout.indexOf(tab_widget), 1)

    # 6. 连接牌组选择变化信号到刷新函数
    
    # 定义刷新函数
    def on_deck_changed():
        current_deck = mw.col.decks.current()
        deck_name = current_deck['name'] if current_deck else '未知牌组'
        print(f"牌组已切换至: {deck_name}")
        refresh_stats_content(my_custom_stats_container, deck_name)
    
    # 定时检查牌组变化 (使用single_shot避免内存泄漏)
    print("\n设置定时检查牌组变化机制")
    last_deck_name = current_deck_name
    def check_deck_changed():
        nonlocal last_deck_name
        try:
            # 严格检查所有相关对象是否有效
            if (not my_custom_stats_container or 
                not hasattr(my_custom_stats_container, 'stats_webview') or 
                not my_custom_stats_container.stats_webview):
                print("定时检查终止: 统计组件已被销毁")
                return
            
            # 获取当前牌组前再次检查对象有效性
            if not mw or not mw.col:
                print("定时检查终止: Anki主窗口不可用")
                return
                
            current_deck = mw.col.decks.current()
            new_deck_name = current_deck['name'] if current_deck else '未知牌组'
            
            if new_deck_name != last_deck_name:
                last_deck_name = new_deck_name
                print(f"定时检查检测到牌组变化: {new_deck_name}")
                
                # 执行刷新前最终确认对象有效性
                if (my_custom_stats_container and 
                    hasattr(my_custom_stats_container, 'stats_webview') and 
                    my_custom_stats_container.stats_webview):
                    on_deck_changed()
                
        except Exception as e:
            print(f"定时检查出错: {e}")
            # 任何异常都停止检查
            print("定时检查终止: 发生异常")
            return
            
        # 仅在所有检查通过后安排下次检查
        if (mw and mw.col and 
            my_custom_stats_container and 
            hasattr(my_custom_stats_container, 'stats_webview') and 
            my_custom_stats_container.stats_webview):
            mw.progress.single_shot(1000, check_deck_changed, my_custom_stats_container)
    
    # 首次启动定时检查
    mw.progress.single_shot(1000, check_deck_changed, my_custom_stats_container)
    
    print("\n已设置定时检查牌组变化机制")

    print("--- add_stats (Tabbed Interface): 选项卡界面创建完成。 ---")
