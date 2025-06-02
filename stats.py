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
def create_custom_stats_tab_content() -> QWidget:
    """
    创建并返回包含所有自定义统计内容的 QWidget。
    所有自定义统计界面的修改都应在此函数内部进行。
    """
    print("--- create_custom_stats_tab_content: 正在构建自定义统计内容... ---")

    # 创建自定义统计内容的容器
    my_custom_stats_container = QWidget()
    # 使用 QVBoxLayout 作为主布局，垂直排列内容
    my_custom_stats_layout = QVBoxLayout(my_custom_stats_container)
    my_custom_stats_layout.setContentsMargins(15, 15, 15, 15) # 增加一些边距

    # 只保留统计数据
    deck_name = "所有卡片::英语::美国当代英语语料库"
    end_date = date.today()
    start_date = end_date - timedelta(days=9)
    
    # 创建统计信息文本框
    stats_text_edit = QTextEdit()
    stats_text_edit.setReadOnly(True)
    stats_text_edit.setStyleSheet(
        "QTextEdit {"
        "  padding: 10px;"
        "  background-color: #f8f9fa;"
        "  border: 1px solid #dee2e6;"
        "  border-radius: 5px;"
        "  color: #212529;"
        "}"
    )
    stats_text_edit.setMinimumHeight(400)
    my_custom_stats_layout.addWidget(stats_text_edit)
    
    # 获取并显示每日统计数据
    html_content = "<h3>最近10天学习统计</h3>"
    html_content += "<table border='1' style='border-collapse: collapse; width: 100%;'>"
    html_content += "<tr><th>日期</th><th>学习卡片数</th><th>总学习时间(小时)</th><th>平均学习时间(秒/卡片)</th></tr>"
    
    # 获取每日统计数据
    for i in range(10):
        day_date = end_date - timedelta(days=i)
        cards, study_time = get_deck_study_stats_for_date_range(deck_name, day_date, day_date)
        
        # 计算平均学习时间
        avg_time = study_time / cards if cards > 0 else 0
        study_time = study_time/ 60  # 转换为分钟
        
        html_content += f"<tr><td>{day_date.strftime('%Y-%m-%d')}</td>"
        html_content += f"<td style='text-align: center;'>{cards}</td>"
        html_content += f"<td style='text-align: center;'>{study_time:.2f}</td>"
        html_content += f"<td style='text-align: center;'>{avg_time:.2f}</td></tr>"
    
    html_content += "</table>"
    
    # 设置HTML内容
    stats_text_edit.setHtml(html_content)

    print("--- create_custom_stats_tab_content: 自定义统计内容构建完成。 ---")
    return my_custom_stats_container

# 辅助函数：获取指定牌组在日期范围内的学习数据
def get_deck_study_stats_for_date_range(deck_name: str, start_date: date, end_date: date) -> tuple[int, float]:
    """
    查询指定牌组在给定日期范围内的学习卡片数量和总学习时间。
    
    注意：此函数需要在一个Anki插件环境或任何可以访问 `mw.col` (Anki收藏对象) 的环境中运行。
          `mw.col` 通常通过 `from aqt import mw` 获得。

    :param deck_name: 要查询的牌组名称。
    :param start_date: 查询的开始日期（datetime.date 对象）。
    :param end_date: 查询的结束日期（datetime.date 对象）。
    :return: 一个元组 (学习卡片数量, 总学习时间_秒)。
             如果牌组未找到，或 Anki 收藏不可用，或发生错误，返回 (0, 0.0)。
    """
    # 确保 Anki 收藏对象 mw.col 是可用的
    if mw is None or mw.col is None:
        print("错误：Anki 收藏未打开或不可用。")
        return 0, 0.0

    total_cards_reviewed = 0
    total_study_time_seconds = 0.0

    try:
        # 1. 根据牌组名称获取牌组 ID
        deck = mw.col.decks.by_name(deck_name)
        if not deck:
            print(f"牌组 '{deck_name}' 未找到。")
            return 0, 0.0
        deck_id = deck['id']
        
        # 2. 构建时间范围的时间戳（毫秒）
        # 开始日期：当天的开始（00:00:00）
        start_dt = datetime(start_date.year, start_date.month, start_date.day)
        # 结束日期：当天的结束（23:59:59.999）
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, 999999)
        
        start_timestamp = int(start_dt.timestamp() * 1000)
        end_timestamp = int(end_dt.timestamp() * 1000)
        
        # 3. 构建查询语句
        query = f"""
            SELECT COUNT(*), SUM(time)/1000.0 
            FROM revlog 
            WHERE cid IN (
                SELECT id FROM cards WHERE did = {deck_id}
            ) AND id >= {start_timestamp}
            AND id <= {end_timestamp}
        """
        
        # 3. 执行查询
        result = mw.col.db.first(query)
        if result:
            total_cards_reviewed = result[0] or 0
            total_study_time_seconds = result[1] or 0.0
            
    except Exception as e:
        print(f"查询学习统计时出错: {e}")
        return 0, 0.0

    return total_cards_reviewed, total_study_time_seconds


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

    # 3. 调用新函数来获取自定义统计内容的容器
    my_custom_stats_container = create_custom_stats_tab_content()

    # 4. 将选项卡添加到 QTabWidget
    tab_widget.addTab(original_stats_container, "Anki 统计")
    tab_widget.addTab(my_custom_stats_container, "我的统计")

    # 5. 将 QTabWidget 添加到 statsdialog 的主布局
    main_dialog_layout.addWidget(tab_widget)
    main_dialog_layout.setStretch(main_dialog_layout.indexOf(tab_widget), 1)

    print("--- add_stats (Tabbed Interface): 选项卡界面创建完成。 ---")
