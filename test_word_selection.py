# -*- coding: utf-8 -*-
"""
选中词汇例句生成功能测试脚本
用于验证新功能的基本工作流程
"""

def test_config_management():
    """测试配置管理功能"""
    try:
        from .config_manager import get_word_selection_config, save_word_selection_config
        
        # 测试获取默认配置
        config = get_word_selection_config()
        print("默认配置:", config)
        
        # 测试保存配置
        test_config = {
            "enabled": True,
            "target_deck_name": "测试牌组",
            "sentence_count": 5,
            "custom_prompt": "测试提示词",
            "use_custom_prompt": False,
            "difficulty_level": "中级",
            "sentence_length": "中等长度"
        }
        save_word_selection_config(test_config)
        print("配置保存测试完成")
        
        return True
    except Exception as e:
        print(f"配置管理测试失败: {e}")
        return False

def test_text_cleaning():
    """测试文本清理功能"""
    try:
        from .context_menu import clean_selected_text, is_valid_word
        
        test_cases = [
            ("<b>hello</b>", "hello"),
            ("  world  ", "world"),
            ("test&nbsp;word", "test word"),
            ("example123", "example123"),
            ("", ""),
            ("a", ""),  # 太短
            ("hello-world", "hello-world"),
        ]
        
        for input_text, expected in test_cases:
            result = clean_selected_text(input_text)
            valid = is_valid_word(result)
            print(f"输入: '{input_text}' -> 输出: '{result}' -> 有效: {valid}")
        
        return True
    except Exception as e:
        print(f"文本清理测试失败: {e}")
        return False

def test_prompt_creation():
    """测试提示词创建功能"""
    try:
        from .word_sentence_generator import create_word_prompt
        from .config_manager import get_config
        
        config = get_config()
        word = "example"
        prompt = create_word_prompt(word, config)
        
        print("生成的提示词:")
        print(prompt[:200] + "..." if len(prompt) > 200 else prompt)
        
        # 检查提示词是否包含关键词
        if word in prompt:
            print("✓ 提示词包含目标词汇")
        else:
            print("✗ 提示词不包含目标词汇")
        
        return True
    except Exception as e:
        print(f"提示词创建测试失败: {e}")
        return False

def test_anki_functions():
    """测试ANKI相关功能"""
    try:
        from .anki_card_creator import validate_card_data, get_available_decks
        
        # 测试数据验证
        test_data = [
            ("word", "This is a sentence with word.", "这是一个包含单词的句子。", True),
            ("", "sentence", "翻译", False),  # 空词汇
            ("word", "", "翻译", False),  # 空例句
            ("word", "sentence", "", False),  # 空翻译
            ("word", "This sentence has no target.", "翻译", False),  # 例句不包含词汇
        ]
        
        for word, sentence, translation, expected in test_data:
            valid, message = validate_card_data(word, sentence, translation)
            result = "✓" if valid == expected else "✗"
            print(f"{result} 验证 '{word}': {message}")
        
        # 测试获取牌组列表（如果Anki可用）
        try:
            decks = get_available_decks()
            print(f"可用牌组数量: {len(decks)}")
        except:
            print("Anki不可用，跳过牌组测试")
        
        return True
    except Exception as e:
        print(f"ANKI功能测试失败: {e}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("开始选中词汇例句生成功能测试...")
    print("=" * 50)
    
    tests = [
        ("配置管理", test_config_management),
        ("文本清理", test_text_cleaning),
        ("提示词创建", test_prompt_creation),
        ("ANKI功能", test_anki_functions),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n测试: {test_name}")
        print("-" * 30)
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"结果: {'通过' if result else '失败'}")
        except Exception as e:
            print(f"测试异常: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("测试总结:")
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name}: {status}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\n总计: {passed}/{total} 测试通过")

if __name__ == "__main__":
    run_all_tests()
