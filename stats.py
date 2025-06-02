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
        # 开始日期：当天的凌晨4点（04:00:00）
        start_dt = datetime(start_date.year, start_date.month, start_date.day, 4, 0, 0)
        # 结束日期：结束日期下一天的凌晨4点减去1微秒（即结束日期那一天的最后一刻是第二天的03:59:59.999999）
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 4, 0, 0) + timedelta(days=1) - timedelta(microseconds=1)
        
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

# 刷新统计内容函数
def refresh_stats_content(container, deck_name):
    """刷新统计内容"""
    print(f"--- 刷新统计内容，牌组: {deck_name} ---")
    stats_webview = container.stats_webview
    end_date = date.today()
    start_date = end_date - timedelta(days=29)  # 获取30天数据
    
    # 准备图表数据
    dates = []
    cards_data = []
    time_data = []
    avg_time_data = []
    
    # 获取每日统计数据
    for i in range(30):
        day_date = end_date - timedelta(days=i)
        cards, study_time = get_deck_study_stats_for_date_range(deck_name, day_date, day_date)
        
        # 计算平均学习时间
        avg_time = study_time / cards if cards > 0 else 0
        study_time_hours = study_time / 3600  # 转换为小时
        
        dates.append(day_date.strftime('%m-%d'))
        cards_data.append(cards)
        time_data.append(study_time_hours)
        avg_time_data.append(avg_time)
    
    # 反转数据，使日期从早到晚
    dates.reverse()
    cards_data.reverse()
    time_data.reverse()
    avg_time_data.reverse()
    
    # 生成HTML内容
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            .chart-container {{
                margin: 20px 0;
                padding: 15px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h3 {{
                margin-top: 0;
                color: #333;
            }}
            .loading {{
                text-align: center;
                padding: 20px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <h3>{deck_name} - 最近30天学习统计</h3>
        
        <div class="chart-container">
            <div class="loading">图表加载中...</div>
            <canvas id="cardsChart"></canvas>
        </div>
        
        <div class="chart-container">
            <div class="loading">图表加载中...</div>
            <canvas id="timeChart"></canvas>
        </div>
        
        <div class="chart-container">
            <div class="loading">图表加载中...</div>
            <canvas id="avgTimeChart"></canvas>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
            function initCharts() {{
                // 确保Chart对象存在
                if (typeof Chart === 'undefined') {{
                    setTimeout(initCharts, 100);
                    return;
                }}
                
                // 隐藏加载提示
                document.querySelectorAll('.loading').forEach(el => el.style.display = 'none');
                
                // 学习卡片数图表
                new Chart(
                    document.getElementById('cardsChart'),
                    {{
                        type: 'line',
                        data: {{
                            labels: {dates},
                            datasets: [{{
                                label: '学习卡片数',
                                data: {cards_data},
                                borderColor: 'rgb(75, 192, 192)',
                                tension: 0.1,
                                fill: false
                            }}]
                        }},
                        options: {{
                            responsive: true,
                            plugins: {{
                                title: {{
                                    display: true,
                                    text: '每日学习卡片数'
                                }}
                            }}
                        }}
                    }}
                );
                
                // 总学习时间图表
                new Chart(
                    document.getElementById('timeChart'),
                    {{
                        type: 'bar',
                        data: {{
                            labels: {dates},
                            datasets: [{{
                                label: '学习时间(小时)',
                                data: {time_data},
                                backgroundColor: 'rgba(54, 162, 235, 0.5)',
                                borderColor: 'rgb(54, 162, 235)',
                                borderWidth: 1
                            }}]
                        }},
                        options: {{
                            responsive: true,
                            plugins: {{
                                title: {{
                                    display: true,
                                    text: '每日学习时间(小时)'
                                }}
                            }}
                        }}
                    }}
                );
                
                // 平均学习时间图表
                new Chart(
                    document.getElementById('avgTimeChart'),
                    {{
                        type: 'line',
                        data: {{
                            labels: {dates},
                            datasets: [{{
                                label: '平均学习时间(秒/卡片)',
                                data: {avg_time_data},
                                borderColor: 'rgb(255, 99, 132)',
                                backgroundColor: 'rgba(255, 99, 132, 0.5)',
                                tension: 0.1,
                                fill: true
                            }}]
                        }},
                        options: {{
                            responsive: true,
                            plugins: {{
                                title: {{
                                    display: true,
                                    text: '卡片平均学习时间(秒)'
                                }}
                            }}
                        }}
                    }}
                );
            }}
            
            // 页面加载完成后初始化图表
            document.addEventListener('DOMContentLoaded', initCharts);
        </script>
    </body>
    </html>
    """
    
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
    # 调试输出statsdialog完整结构
    print("\n=== statsdialog结构分析 ===")
    print(f"statsdialog类型: {type(statsdialog)}")
    print(f"statsdialog对象名: {statsdialog.objectName()}")
    
    # 输出所有子控件
    print("\n子控件列表:")
    children = statsdialog.findChildren(QWidget)
    for i, child in enumerate(children):
        print(f"{i}: {type(child).__name__} 对象名='{child.objectName()}'")
    
    # 定义刷新函数
    def on_deck_changed():
        current_deck = mw.col.decks.current()
        deck_name = current_deck['name'] if current_deck else '未知牌组'
        print(f"牌组已切换至: {deck_name}")
        refresh_stats_content(my_custom_stats_container, deck_name)
    
    # 方法1: 使用Anki的hook系统
    print("\n注册牌组变化hook")
    def on_deck_browser_did_render(deck_browser, _):
        try:
            on_deck_changed()
        except Exception as e:
            print(f"hook回调出错: {e}")
    
    gui_hooks.deck_browser_did_render.append(on_deck_browser_did_render)
    
    # 方法2: 定时检查牌组变化 (使用single_shot避免内存泄漏)
    print("\n设置安全的定时检查牌组变化")
    last_deck_name = current_deck_name
    def check_deck_changed():
        nonlocal last_deck_name
        try:
            current_deck = mw.col.decks.current()
            new_deck_name = current_deck['name'] if current_deck else '未知牌组'
            if new_deck_name != last_deck_name:
                last_deck_name = new_deck_name
                print(f"定时检查检测到牌组变化: {new_deck_name}")
                on_deck_changed()
        except Exception as e:
            print(f"定时检查出错: {e}")
        finally:
            # 使用single_shot并指定parent避免内存泄漏
            mw.progress.single_shot(1000, check_deck_changed, my_custom_stats_container)
    
    # 首次启动定时检查
    mw.progress.single_shot(1000, check_deck_changed, my_custom_stats_container)
    
    print("\n已设置安全的牌组变化检测机制 (hook + single_shot定时检查)")

    print("--- add_stats (Tabbed Interface): 选项卡界面创建完成。 ---")
