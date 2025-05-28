from aqt import gui_hooks
from aqt.stats import NewDeckStats
from aqt.qt import (
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout, # 可能需要
    QWidget,
    QTabWidget,  # 导入 QTabWidget
    QSizePolicy,
    QScrollArea, # 如果原生内容或自定义内容可能溢出，需要滚动区域
    Qt # 用于 Qt.Orientation 等
)
from aqt.webview import AnkiWebView # StatsWebView 继承自 AnkiWebView

def add_stats(statsdialog: NewDeckStats) -> None:
    """
    给 Anki 的新版统计对话框添加选项卡，一个显示原生统计，一个显示自定义统计。
    """
    print(f"--- add_stats (Tabbed Interface): 正在尝试创建选项卡界面... ---")

    # 1. 创建 QTabWidget
    tab_widget = QTabWidget(statsdialog) # 将 statsdialog 作为父对象
    tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # 2. 准备原生统计内容的容器
    # 我们需要将 statsdialog 原有的所有内容（主要是 WebView）移动到一个新的 QWidget 中
    original_stats_container = QWidget()
    original_stats_layout = QVBoxLayout(original_stats_container)
    original_stats_layout.setContentsMargins(0, 0, 0, 0) # 移除内边距，让内容更紧凑

    # 遍历 statsdialog 的主布局，将所有现有控件移动到 original_stats_container
    main_dialog_layout = statsdialog.layout()
    if not main_dialog_layout:
        print("错误：statsdialog.layout() 返回 None。无法创建选项卡界面。")
        return

    # 临时存储要移动的控件
    widgets_to_move = []
    for i in range(main_dialog_layout.count()):
        item = main_dialog_layout.itemAt(i)
        if item and item.widget():
            widgets_to_move.append(item.widget())

    # 从主布局中移除所有控件
    # 注意：从布局中移除控件后，控件的父对象不会自动改变，但它不再由该布局管理
    for widget in widgets_to_move:
        main_dialog_layout.removeWidget(widget)
        # 确保控件没有父布局，以便可以添加到新的布局中
        # widget.setParent(None) # 通常不需要显式调用，addWidget 会处理

    # 将这些控件添加到新的原生统计容器中
    for widget in widgets_to_move:
        original_stats_layout.addWidget(widget)
        print(f"  移动原生控件: {getattr(widget, 'objectName', 'N/A')()} (类型: {type(widget).__name__})")

    # 3. 准备自定义统计内容的容器
    my_custom_stats_container = QWidget()
    my_custom_stats_layout = QVBoxLayout(my_custom_stats_container)
    my_custom_stats_layout.setContentsMargins(10, 10, 10, 10) # 给自定义内容一些边距

    # 创建你的自定义统计框
    test_box = QTextEdit()
    test_box.setReadOnly(True)
    test_box.setPlaceholderText(
        "这是我的自定义统计内容！\n"
        "我可以完全控制这个选项卡中的所有 Qt 控件和布局。\n"
        "例如，我可以添加图表、表格、按钮等。"
    )
    test_box.setMinimumHeight(200)
    test_box.setStyleSheet(
        "QTextEdit {"
        "  border: 2px dashed #007bff;"  # 蓝色虚线边框
        "  padding: 15px;"
        "  background-color: #e0f7fa;" # 浅蓝色背景
        "  font-family: 'Segoe UI', sans-serif;"
        "  color: #212529;"
        "  border-radius: 5px;"
        "}"
    )
    test_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # 将自定义统计框添加到自定义容器的布局中
    my_custom_stats_layout.addWidget(test_box)

    # 你可以在这里添加更多自定义控件
    # my_custom_stats_layout.addWidget(QPushButton("我的自定义按钮"))
    # my_custom_stats_layout.addWidget(QLabel("更多信息..."))

    # 4. 将选项卡添加到 QTabWidget
    tab_widget.addTab(original_stats_container, "Anki 统计")
    tab_widget.addTab(my_custom_stats_container, "我的统计")

    # 5. 清空 statsdialog 的主布局（如果之前没有清空）并添加 QTabWidget
    # 确保主布局是空的，然后添加 tab_widget
    # 之前已经移除了所有控件，现在直接添加 tab_widget
    main_dialog_layout.addWidget(tab_widget)
    print("QTabWidget 已添加到 statsdialog 的主布局。")

    # 确保 tab_widget 占据所有可用空间
    main_dialog_layout.setStretch(main_dialog_layout.indexOf(tab_widget), 1)

    print("--- add_stats (Tabbed Interface): 选项卡界面创建完成。 ---")


    # === Anki 自定义统计界面控件添加指南 ===
#
# 目标: 将一个自定义的 Qt QWidget (例如 QTextEdit) 添加到 Anki 的新版统计对话框
# (aqt.stats.NewDeckStats) 中，使其与现有的基于 WebView 的统计图表共存。
#
# 探索过程总结:
# 1. 初始尝试: 试图寻找如 `scrollAreaWidgetContents` 或 `form.verticalLayout` 这样的
#    传统 Qt 布局来添加控件。这在新版统计界面中不适用，因为它主要由一个
#    `StatsWebView` (继承自 aqt.webview.AnkiWebView) 驱动，用于渲染 HTML/JS 图表。
#    直接将控件添加到错误的布局会导致覆盖整个界面或控件不可见。
#
# 2. 关键发现:
#    - `NewDeckStats` 对话框 (`statsdialog`) 的主要内容区域是一个名为 'web' 的
#      `StatsWebView` 实例。这个 WebView 是 `statsdialog` 的直接子控件。
#    - `statsdialog` 自身是一个 `QDialog`，它有一个主布局 (通常是 `QVBoxLayout`)，
#      `StatsWebView` 是这个主布局中的一个主要项目。
#
# 3. 成功策略 (当前实现 - 控件在 WebView 下方):
#    - 获取 `statsdialog` 的主布局: `main_layout = statsdialog.layout()`。
#    - 确认主布局是 `QVBoxLayout`。
#    - 创建自定义控件 (如 `QTextEdit` 实例 `custom_widget`)。
#    - 将 `custom_widget` 添加到 `main_layout` 中: `main_layout.addWidget(custom_widget)`。
#    - 为了让 `StatsWebView` 占据主要空间，而 `custom_widget` 占据较小固定空间，
#      使用了 `main_layout.setStretch(index_of_webview, stretch_factor_webview)` 和
#      `main_layout.setStretch(index_of_custom_widget, stretch_factor_custom_widget)`。
#      通常给 WebView 较大的 stretch_factor (如 5)，给自定义控件较小的 (如 1)。
#    - 设置自定义控件的 `sizePolicy`，例如垂直方向为 `QSizePolicy.Policy.Preferred` 或
#      `QSizePolicy.Policy.Fixed`，并配合 `minimumHeight`/`maximumHeight`。
#
# 实现代码参考 (add_stats 函数 - v4 版本逻辑):
# (这里可以粘贴之前成功的 v4 版本 add_stats 函数的核心逻辑)
# def add_stats(statsdialog: NewDeckStats) -> None:
#     # ... (创建 QTextEdit test_box) ...
#     main_dialog_layout = statsdialog.layout()
#     if isinstance(main_dialog_layout, QVBoxLayout):
#         # ... (查找 stats_webview_widget 及其在布局中的索引 webview_layout_index) ...
#         if stats_webview_widget:
#             main_dialog_layout.addWidget(test_box)
#             test_box_layout_index = main_dialog_layout.indexOf(test_box)
#
#             main_dialog_layout.setStretch(webview_layout_index, 5)
#             main_dialog_layout.setStretch(test_box_layout_index, 1)
#             
#             stats_webview_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
#             test_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred) # 或者 Fixed
#             # ... (设置 test_box 的 min/max height) ...
#     # ... (错误处理和日志) ...
#
#
# 注意事项:
# 1.  Anki UI 结构: Anki 的内部 UI 结构可能会随版本更新而改变。代码应尽可能健壮，
#     例如，通过 `objectName` ('web') 或类型 (`AnkiWebView`) 来查找关键控件，
#     而不是依赖硬编码的控件层级或索引（虽然获取索引用于 setStretch 是必要的）。
# 2.  布局类型: 假定主布局是 `QVBoxLayout` 是基于当前观察。如果 Anki 未来更改了
#     `NewDeckStats` 的主布局类型，代码可能需要调整。
# 3.  `StatsWebView` 的行为: `StatsWebView` 是核心。任何改动都需确保不破坏其功能。
#     它通常被设计为占据尽可能多的可用空间。
# 4.  控件的 `sizePolicy` 和 `stretchFactor`: 这两者对于在布局中正确分配空间至关重要。
#     需要仔细调整以达到期望的视觉效果。
# 5.  错误处理和日志: 在尝试修改 UI 时，详细的日志对于调试非常重要，可以帮助快速定位
#     因 Anki 版本更新或代码逻辑错误导致的问题。
# 6.  PyQt/PySide 版本: Anki 可能会在 PyQt5 和 PyQt6 (PySide6) 之间切换或允许两者。
#     确保导入正确的 Qt 模块 (`PyQt6.QtWidgets` 或 `PyQt5.QtWidgets`)。
#     Anki 2.1.50+ 开始逐步迁移到 Qt6。
# 7.  钩子 (`gui_hooks`): 将此 `add_stats` 函数连接到 Anki 的正确钩子
#     (如 `gui_hooks.stats_dialog_will_render.append(add_stats)`) 是使此功能生效的前提。
#     (用户已声明此部分自行处理)
#
# === 如何实现“并列显示” (例如，自定义控件在 WebView 左侧/右侧) ===
#
# 当前实现是将自定义控件放在 WebView 的下方 (因为主布局是 QVBoxLayout)。
# 要实现并列显示 (水平排列)，通常需要一个 QHBoxLayout。
#
# 思路:
# 1.  **替换/包裹现有 WebView**:
#     a.  从 `statsdialog` 的主 `QVBoxLayout` 中移除 `StatsWebView`。
#         (注意：直接移除可能导致 WebView 失去父对象被销毁，需要小心处理，
#         或者在添加到新布局前调用 `setParent(None)`，然后添加到新布局后 Qt 会重新设置父对象)。
#         更安全的方式是，如果 `StatsWebView` 是主布局中唯一的 `QWidget`，那么我们可以
#         创建一个新的 `QWidget` 作为容器，设置 `QHBoxLayout` 给这个容器，然后把这个容器
#         `addWidget` 到主 `QVBoxLayout` 中，替换掉原来的 `StatsWebView`。
#
#     b.  创建一个新的 `QHBoxLayout` (我们称之为 `horizontal_layout`)。
#
#     c.  将你的自定义控件 (`custom_widget`) 和 `StatsWebView` (`stats_webview_widget`)
#         都添加到这个 `horizontal_layout` 中。
#         `horizontal_layout.addWidget(custom_widget)`
#         `horizontal_layout.addWidget(stats_webview_widget)`
#
#     d.  创建一个中间的 `QWidget` (我们称之为 `container_widget`)。
#         `container_widget = QWidget()`
#         `container_widget.setLayout(horizontal_layout)`
#
#     e.  将这个 `container_widget` 添加回 `statsdialog` 的主 `QVBoxLayout` 中，
#         通常是添加到之前 `StatsWebView` 所在的位置或替换它。
#         `main_dialog_layout.insertWidget(original_webview_index, container_widget)`
#         或者如果替换，则先 `main_dialog_layout.takeAt(original_webview_index)` (处理返回的 QLayoutItem)，
#         然后 `main_dialog_layout.insertWidget(original_webview_index, container_widget)`。
#
# 2.  **使用 QSplitter (更灵活)**:
#     `QSplitter` 允许用户动态调整并列控件之间的大小。
#     a.  从主 `QVBoxLayout` 中移除 `StatsWebView` (同样注意父对象问题)。
#     b.  创建一个 `QSplitter`: `splitter = QSplitter(Qt.Orientation.Horizontal)`。
#     c.  将你的 `custom_widget` 和 `stats_webview_widget` 添加到 `splitter` 中:
#         `splitter.addWidget(custom_widget)`
#         `splitter.addWidget(stats_webview_widget)`
#     d.  设置 `splitter` 的初始尺寸比例 (可选): `splitter.setSizes([width1, width2])`。
#     e.  设置 `splitter` 的 `stretchFactor` (如果 `splitter` 本身在另一个布局中) 或
#         其 `sizePolicy` (通常是 Expanding, Expanding)。
#     f.  将 `splitter` 添加回 `statsdialog` 的主 `QVBoxLayout` 中，替换原来的 `StatsWebView`。
#
# 详细步骤 (以思路 1 为例，假设主布局 `main_dialog_layout` 是 `QVBoxLayout`):
#
# ```python
# # (在 add_stats 函数内部，已定位 main_dialog_layout 和 stats_webview_widget)
# # (并且已创建了自定义控件 test_box)
#
# if stats_webview_widget and isinstance(main_dialog_layout, QVBoxLayout):
#     # 1a. 从主布局中找到 StatsWebView 并获取其索引
#     webview_item = None
#     original_webview_index = -1
#     for i in range(main_dialog_layout.count()):
#         item = main_dialog_layout.itemAt(i)
#         if item and item.widget() == stats_webview_widget:
#             webview_item = item # QLayoutItem
#             original_webview_index = i
#             break
#
#     if webview_item and original_webview_index != -1:
#         # 从布局中“取出”WebView，但它仍然存在
#         # main_dialog_layout.takeAt(original_webview_index) # 这会返回 QLayoutItem
#         # 更直接的方式可能是移除 widget 本身，如果布局允许
#         main_dialog_layout.removeWidget(stats_webview_widget)
#         # stats_webview_widget.setParent(None) # 确保它暂时没有父布局，避免重复添加问题
#                                            # 但在添加到新布局时，父对象会自动设置
#
#         # 1b. 创建新的 QHBoxLayout
#         horizontal_layout = QHBoxLayout()
#
#         # 1c. 添加自定义控件和 WebView 到水平布局
#         #     可以调整添加顺序来决定哪个在左，哪个在右
#         horizontal_layout.addWidget(test_box)      # test_box 在左
#         horizontal_layout.addWidget(stats_webview_widget) # WebView 在右
#
#         # 设置拉伸因子，让 WebView 占据更多水平空间
#         horizontal_layout.setStretchFactor(test_box, 1) # test_box 占 1 份
#         horizontal_layout.setStretchFactor(stats_webview_widget, 3) # WebView 占 3 份 (可调整)
#
#         # 确保它们的 SizePolicy 适合水平布局
#         test_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding) # 水平Preferred, 垂直Expanding
#         stats_webview_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
#
#         # 1d. 创建容器 QWidget
#         container_widget = QWidget()
#         container_widget.setLayout(horizontal_layout)
#
#         # 1e. 将容器 QWidget 插回主 QVBoxLayout
#         main_dialog_layout.insertWidget(original_webview_index, container_widget)
#         # 如果主QVBoxLayout只有一个元素（原来的WebView），现在用container_widget替换它
#         # 并且也可能需要为container_widget在主QVBoxLayout中设置stretch factor
#         main_dialog_layout.setStretchFactor(container_widget, 1) # 或者更大的值如果它是主要内容
#
#         print("已尝试将 test_box 和 WebView 并列显示。")
#     else:
#         print("错误: 未能在主布局中定位 WebView 以进行并列布局替换。")
# else:
#     print("错误: 未找到 WebView 或主布局不是 QVBoxLayout，无法进行并列布局。")
#
# ```
#
# **注意事项 (针对并列显示)**:
# *   **父对象管理**: 当从一个布局中移除控件并添加到另一个布局时，Qt 通常能正确处理父对象。
#     但有时显式调用 `widget.setParent(None)` 在移除后，再添加到新布局中可以避免一些问题。
#     当 `addWidget` 到一个新布局时，新布局会成为其父布局，控件也会成为新布局所在 widget 的子控件。
# *   **QLayoutItem**: `layout.takeAt(index)` 返回一个 `QLayoutItem`，它可能包含一个 widget 或一个嵌套布局。
#     你需要从 `QLayoutItem` 中获取 `widget()` (如果它是一个 widget item)。
#     `layout.removeWidget(widget)` 通常更直接。
# *   **Stretch Factors**: 在 `QHBoxLayout` 中，`stretchFactor` 控制水平空间的分配。
# *   **SizePolicy**: 控件的 `sizePolicy` 对于它们在 `QHBoxLayout` 中的行为也很重要。
#     例如，一个用于显示少量固定信息的侧边栏可能具有 `Fixed` 或 `Preferred` 的水平策略，
#     而主要内容区域（如 WebView）则应该是 `Expanding`。
# *   **复杂性**: 修改现有复杂对话框的布局比简单追加控件更具侵入性，需要更仔细的测试，
#     特别是当 Anki 版本更新时，原始布局可能会改变。
# *   **Alternative - Inserting into WebView**: 如果希望内容“看起来”像是现有统计图表的一部分，
#     那么需要通过 JavaScript 将 HTML 注入到 `StatsWebView` 内部。这完全是另一套逻辑，
#     需要与 WebView 的前端代码交互 (`page().runJavaScript(...)`)。
#
# 这个文档应该能为后续工作提供一个良好的起点。