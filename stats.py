import aqt
from aqt.qt import QTextEdit, QVBoxLayout
from aqt import mw
from aqt.stats import NewDeckStats

def add_stats(statsdialog: NewDeckStats) -> None:
    """
    给 Anki 的新版统计对话框添加一个测试用的空统计框。
    """
    print("正在尝试给统计界面添加测试框...")
    # 1. 创建一个 QTextEdit 控件作为我们的“统计框”
    test_box = QTextEdit()
    test_box.setReadOnly(True) # 设置为只读，用户不能编辑
    test_box.setPlaceholderText("这是一个用于测试的统计框。") # 显示占位符文本
    test_box.setMinimumHeight(150) # 设置最小高度，确保它足够大以便看到
    
    # 添加一些样式，让它在界面中更显眼，方便测试
    test_box.setStyleSheet(
        "border: 2px dashed #888;"  # 虚线边框
        "padding: 10px;"            # 内边距
        "background-color: #f9f9f9;" # 浅灰色背景
        "font-family: monospace;"   # 等宽字体
        "color: #555;"              # 字体颜色
    )
    # 2. 找到统计对话框中合适的布局来添加我们的控件
    # NewDeckStats 的 UI 通常有一个名为 'verticalLayout' 的 QBoxLayout
    # 它是通过 Qt Designer 生成的 UI 对象的属性 (statsdialog.form.verticalLayout)
    target_layout = None
    try:
        # 尝试获取 form 对象中的 verticalLayout
        target_layout = statsdialog.form.verticalLayout
    except AttributeError:
        # 如果没有找到，尝试获取对话框本身的顶层布局
        # (虽然 NewDeckStats 通常会有一个 form.verticalLayout)
        target_layout = statsdialog.layout()
    if target_layout:
        # 3. 将测试框添加到找到的布局中
        target_layout.addWidget(test_box)
        print("测试统计框已成功添加到统计界面。")
    else:
        print("错误：无法找到合适的布局来添加测试框。请检查 Anki 版本或 UI 结构。")