import aqt
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget, QScrollArea, QSizePolicy
# 如果您使用 PyQt5，请取消注释下一行并注释掉上一行
# from PyQt5.QtWidgets import QTextEdit, QVBoxLayout, QWidget, QScrollArea, QSizePolicy
from aqt import mw
from aqt.stats import NewDeckStats
from aqt.webview import AnkiWebView # StatsWebView 继承自 AnkiWebView

# from aqt import gui_hooks # 您已声明这部分由您处理

# 函数签名保持不变
def add_stats(statsdialog: NewDeckStats) -> None:
    """
    给 Anki 的新版统计对话框添加一个测试用的空统计框。
    目标是让这个框与 WebView 统计图表共存。
    """
    print(f"--- add_stats (v4): 正在尝试给统计界面添加测试框 (Anki 版本: {aqt.appVersion})... ---")
    print(f"传入的 statsdialog 类型: {type(statsdialog)}")

    # 1. 创建 QTextEdit 控件
    test_box = QTextEdit()
    test_box.setReadOnly(True)
    test_box.setPlaceholderText(
        "这是一个用于测试的统计框 (Qt Widget)。\n"
        "目标是显示在 WebView 统计的下方。"
    )
    test_box.setMinimumHeight(80)
    test_box.setMaximumHeight(150)
    # test_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed) # 保持这个策略
    # 修正：对于QVBoxLayout中的项目，通常使用 Expanding, Preferred/Fixed/Minimum
    test_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)


    test_box.setStyleSheet(
        "QTextEdit {"
        "  border: 2px solid #17a2b8;"  # 青色边框
        "  padding: 8px;"
        "  background-color: #e8f7f9;" # 浅青色背景
        "  font-family: sans-serif;"
        "  color: #333;"
        "}"
    )

    # 2. 分析和修改 statsdialog 的布局
    main_dialog_layout = statsdialog.layout()

    if not main_dialog_layout:
        print("错误：statsdialog.layout() 返回 None。无法继续。")
        return

    print(f"statsdialog 的主布局类型: {type(main_dialog_layout).__name__}")
    print(f"主布局中的项目数量 (之前): {main_dialog_layout.count()}")
    
    stats_webview_widget = None
    # 查找 StatsWebView 实例及其在布局中的索引
    webview_layout_index = -1 # 用于 setStretchFactor(index, stretch)
    
    for i in range(main_dialog_layout.count()):
        item = main_dialog_layout.itemAt(i)
        if item and item.widget():
            widget_in_layout = item.widget()
            print(f"  主布局中的项目 {i}: {getattr(widget_in_layout, 'objectName', 'N/A')()} (类型: {type(widget_in_layout).__name__})")
            if isinstance(widget_in_layout, AnkiWebView) or widget_in_layout.objectName() == 'web':
                stats_webview_widget = widget_in_layout
                webview_layout_index = i # 保存索引
                print(f"    找到了 StatsWebView (或名为 'web' 的 AnkiWebView): '{stats_webview_widget.objectName()}' at index {webview_layout_index}")
                # 通常只有一个主要的 StatsWebView，但我们继续循环以打印所有项目
    
    # 如果通过布局迭代未找到，尝试直接访问（以防万一）
    if not stats_webview_widget:
        print("未在主布局中直接找到 StatsWebView。尝试通过 statsdialog.children() 或 statsdialog.web 查找...")
        if hasattr(statsdialog, 'web') and isinstance(statsdialog.web, AnkiWebView):
             stats_webview_widget = statsdialog.web
             print(f"通过 statsdialog.web 找到了 StatsWebView: '{stats_webview_widget.objectName()}'")
             # 如果这样找到，我们还需要在布局中找到它的索引
             for i in range(main_dialog_layout.count()):
                 item = main_dialog_layout.itemAt(i)
                 if item and item.widget() == stats_webview_widget:
                     webview_layout_index = i
                     print(f"    并确认其在布局中的索引为 {webview_layout_index}")
                     break
        # 进一步的遍历查找 (如果需要)
        # ...

    if stats_webview_widget:
        print("已定位 StatsWebView 实例。")
        if isinstance(main_dialog_layout, QVBoxLayout):
            print("主布局是 QVBoxLayout。将 test_box 添加到布局末尾。")
            
            main_dialog_layout.addWidget(test_box)
            test_box_layout_index = main_dialog_layout.indexOf(test_box) # 获取新添加的 test_box 的索引
            print(f"test_box 已添加到主 QVBoxLayout 的末尾，索引为 {test_box_layout_index}。")

            if webview_layout_index != -1 and test_box_layout_index != -1:
                # 正确的 setStretchFactor 调用方式是 (index, stretch_factor)
                main_dialog_layout.setStretch(webview_layout_index, 5) # 给 WebView 较大的拉伸因子
                main_dialog_layout.setStretch(test_box_layout_index, 1) # 给 test_box 较小的拉伸因子
                print(f"已为索引 {webview_layout_index} (WebView) 和索引 {test_box_layout_index} (test_box) 设置拉伸因子。")
                
                # 确保 WebView 的大小策略允许它扩展
                stats_webview_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            else:
                print("警告：未能确定 WebView 或 test_box 在布局中的索引以设置拉伸因子。")
        else:
            print(f"警告：主布局不是 QVBoxLayout (类型: {type(main_dialog_layout).__name__})。")
            print("将 test_box 添加到此布局可能产生意外结果。尝试直接添加...")
            main_dialog_layout.addWidget(test_box)
    else:
        print("错误：未能定位 StatsWebView 实例。无法智能地添加 test_box。")
        print("尝试将 test_box 添加到主布局的末尾作为备用方案...")
        if main_dialog_layout: # 再次检查以防万一
            main_dialog_layout.addWidget(test_box)

    print(f"主布局中的项目数量 (之后): {main_dialog_layout.count()}")
    print("--- add_stats (v4): 完成尝试。请检查界面。 ---")

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