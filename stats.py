import aqt
from aqt import gui_hooks
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
    QPushButton, # 示例：添加一个按钮
    QLabel      # 示例：添加一个标签
)
from aqt.webview import AnkiWebView

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

    # 1. 添加你的主要测试框
    test_box = QTextEdit()
    test_box.setReadOnly(True)
    test_box.setPlaceholderText(
        "这是我的自定义统计内容！\n"
        "我可以完全控制这个选项卡中的所有 Qt 控件和布局。\n"
        "例如，我可以添加图表、表格、按钮等。"
    )
    test_box.setMinimumHeight(150)
    test_box.setStyleSheet(
        "QTextEdit {"
        "  border: 2px dashed #007bff;"
        "  padding: 15px;"
        "  background-color: #e0f7fa;"
        "  font-family: 'Segoe UI', sans-serif;"
        "  color: #212529;"
        "  border-radius: 5px;"
        "}"
    )
    test_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    my_custom_stats_layout.addWidget(test_box)

    # 2. 示例：添加一个水平布局的按钮和标签
    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 10, 0, 0) # 顶部留白

    my_button = QPushButton("点击我！")
    my_button.clicked.connect(lambda: print("自定义按钮被点击了！"))
    button_layout.addWidget(my_button)

    my_label = QLabel("这是一个自定义标签。")
    button_layout.addWidget(my_label)

    # 将这个水平布局添加到主垂直布局中
    my_custom_stats_layout.addLayout(button_layout)

    # 3. 示例：添加一个可滚动的区域，如果内容很多的话
    # scroll_area = QScrollArea()
    # scroll_area.setWidgetResizable(True)
    # # 创建一个内部 widget 来放置所有内容，然后将这个 widget 设置给 QScrollArea
    # scroll_area_content_widget = QWidget()
    # scroll_area_content_layout = QVBoxLayout(scroll_area_content_widget)
    # scroll_area_content_layout.addWidget(QLabel("这里是滚动区域内的内容..."))
    # scroll_area.setWidget(scroll_area_content_widget)
    # my_custom_stats_layout.addWidget(scroll_area)


    my_custom_stats_layout.addStretch(1) # 在底部添加一个伸缩器，将内容推到顶部

    print("--- create_custom_stats_tab_content: 自定义统计内容构建完成。 ---")
    return my_custom_stats_container

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

