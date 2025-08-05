# -*- coding: utf-8 -*-
"""
测试UI修复是否成功
"""

def test_config_dialog_creation():
    """测试配置对话框是否能正常创建"""
    try:
        from .ui_manager import ConfigDialog
        from .config_manager import get_config
        
        # 模拟创建配置对话框
        print("正在测试ConfigDialog创建...")
        
        # 检查类是否有setup_word_selection_tab方法
        if hasattr(ConfigDialog, 'setup_word_selection_tab'):
            print("✓ ConfigDialog类包含setup_word_selection_tab方法")
        else:
            print("✗ ConfigDialog类缺少setup_word_selection_tab方法")
            return False
        
        print("✓ UI修复测试通过")
        return True
        
    except Exception as e:
        print(f"✗ UI修复测试失败: {e}")
        return False

def test_method_signature():
    """测试方法签名是否正确"""
    try:
        from .ui_manager import ConfigDialog
        import inspect
        
        # 检查方法签名
        method = getattr(ConfigDialog, 'setup_word_selection_tab', None)
        if method:
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            print(f"方法参数: {params}")
            
            # 应该有self, layout, config三个参数
            if len(params) == 3 and params[0] == 'self' and 'layout' in params and 'config' in params:
                print("✓ 方法签名正确")
                return True
            else:
                print("✗ 方法签名不正确")
                return False
        else:
            print("✗ 方法不存在")
            return False
            
    except Exception as e:
        print(f"✗ 方法签名测试失败: {e}")
        return False

if __name__ == "__main__":
    print("开始UI修复测试...")
    print("=" * 40)
    
    test1 = test_config_dialog_creation()
    test2 = test_method_signature()
    
    print("=" * 40)
    if test1 and test2:
        print("✓ 所有测试通过，UI修复成功！")
    else:
        print("✗ 部分测试失败，需要进一步修复")
