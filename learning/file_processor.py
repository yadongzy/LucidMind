#!/usr/bin/env python3
"""
基础编程练习2：文件处理器
目标：练习文件读写、异常处理、字符串操作
"""

import os
import json

def read_text_file(filepath):
    """读取文本文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return f"错误：文件 {filepath} 不存在"
    except Exception as e:
        return f"读取文件时发生错误：{e}"

def write_text_file(filepath, content):
    """写入文本文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"成功写入文件：{filepath}"
    except Exception as e:
        return f"写入文件时发生错误：{e}"

def analyze_text(text):
    """分析文本"""
    if not text:
        return "文本为空"
    
    lines = text.split('\n')
    words = text.split()
    
    stats = {
        '字符数': len(text),
        '行数': len(lines),
        '单词数': len(words),
        '平均每行字符数': len(text) / max(1, len(lines)),
        '平均单词长度': sum(len(word) for word in words) / max(1, len(words))
    }
    
    return stats

def create_sample_data():
    """创建示例数据"""
    sample_data = {
        'name': 'Python学习数据',
        'exercises': [
            {'id': 1, 'name': '计算器', 'completed': True},
            {'id': 2, 'name': '文件处理器', 'completed': True},
            {'id': 3, 'name': '数据分析', 'completed': False}
        ],
        'stats': {
            'total_exercises': 3,
            'completed': 2,
            'completion_rate': 66.67
        }
    }
    return json.dumps(sample_data, ensure_ascii=False, indent=2)

def main():
    """主函数"""
    print("=== 文件处理器 ===")
    
    # 1. 创建示例数据
    sample_content = create_sample_data()
    print("1. 创建示例数据...")
    print(sample_content[:200] + "...")
    
    # 2. 写入文件
    output_file = "learning/sample_data.json"
    result = write_text_file(output_file, sample_content)
    print(f"2. {result}")
    
    # 3. 读取文件
    print("3. 读取文件...")
    content = read_text_file(output_file)
    if not content.startswith("错误"):
        print(f"读取成功，文件大小：{len(content)} 字符")
        
        # 4. 分析内容
        print("4. 分析内容...")
        if isinstance(content, str) and content.strip():
            stats = analyze_text(content)
            for key, value in stats.items():
                print(f"  {key}: {value}")
    else:
        print(content)
    
    # 5. 测试错误处理
    print("\n5. 测试错误处理...")
    error_result = read_text_file("learning/nonexistent_file.txt")
    print(f"读取不存在的文件：{error_result}")

if __name__ == "__main__":
    main()