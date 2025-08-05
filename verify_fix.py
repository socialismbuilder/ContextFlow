# -*- coding: utf-8 -*-
"""
验证UI修复的脚本
"""

def verify_ui_fix():
    """验证UI修复是否成功"""
    print("验证UI修复...")
    
    try:
        # 检查ConfigDialog类是否存在setup_word_selection_tab方法
        import sys
        import os
        
        # 添加插件路径到sys.path（如果需要）
        plugin_path = os.path.dirname(os.path.abspath(__file__))
        if plugin_path not in sys.path:
            sys.path.insert(0, plugin_path)
        
        # 尝试导入ui_manager模块
        try:
            import ui_manager
            print("✓ ui_manager模块导入成功")
        except ImportError as e:
            print(f"✗ ui_manager模块导入失败: {e}")
            return False
        
        # 检查ConfigDialog类
        if hasattr(ui_manager, 'ConfigDialog'):
            print("✓ ConfigDialog类存在")
            
            # 检查setup_word_selection_tab方法
            if hasattr(ui_manager.ConfigDialog, 'setup_word_selection_tab'):
                print("✓ setup_word_selection_tab方法存在")
                
                # 检查方法是否可调用
                method = getattr(ui_manager.ConfigDialog, 'setup_word_selection_tab')
                if callable(method):
                    print("✓ setup_word_selection_tab方法可调用")
                    return True
                else:
                    print("✗ setup_word_selection_tab方法不可调用")
                    return False
            else:
                print("✗ setup_word_selection_tab方法不存在")
                return False
        else:
            print("✗ ConfigDialog类不存在")
            return False
            
    except Exception as e:
        print(f"✗ 验证过程中出现异常: {e}")
        return False

def check_file_structure():
    """检查文件结构"""
    print("\n检查文件结构...")
    
    try:
        with open('ui_manager.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查关键结构
        checks = [
            ("class ConfigDialog(QDialog):", "ConfigDialog类定义"),
            ("def setup_word_selection_tab(self, layout, config):", "setup_word_selection_tab方法定义"),
            ("# --- 全局函数 ---", "全局函数分隔符"),
            ("def show_config_dialog():", "show_config_dialog函数"),
            ("def register_menu_item():", "register_menu_item函数"),
        ]
        
        for pattern, description in checks:
            if pattern in content:
                print(f"✓ {description}存在")
            else:
                print(f"✗ {description}缺失")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ 文件结构检查失败: {e}")
        return False

if __name__ == "__main__":
    print("开始验证UI修复...")
    print("=" * 50)
    
    structure_ok = check_file_structure()
    
    if structure_ok:
        fix_ok = verify_ui_fix()
        
        print("=" * 50)
        if fix_ok:
            print("🎉 UI修复验证成功！ConfigDialog现在应该可以正常工作了。")
        else:
            print("❌ UI修复验证失败，可能还需要进一步调整。")
    else:
        print("❌ 文件结构检查失败，请检查ui_manager.py文件。")
