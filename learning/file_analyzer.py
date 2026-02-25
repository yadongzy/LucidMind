#!/usr/bin/env python3
"""
基础编程练习2：文件分析器
目标：练习文件操作、异常处理、数据统计
"""

import os
import json
from datetime import datetime

def analyze_file(filepath):
    """分析文件基本信息"""
    try:
        if not os.path.exists(filepath):
            return {"error": f"文件不存在: {filepath}"}
        
        stats = os.stat(filepath)
        
        # 获取文件信息
        info = {
            "filename": os.path.basename(filepath),
            "path": os.path.abspath(filepath),
            "size_bytes": stats.st_size,
            "size_kb": round(stats.st_size / 1024, 2),
            "size_mb": round(stats.st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
            "modified": datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            "is_file": os.path.isfile(filepath),
            "is_dir": os.path.isdir(filepath)
        }
        
        # 如果是文本文件，尝试读取内容
        if info["is_file"] and info["size_bytes"] < 1024 * 1024:  # 小于1MB
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    info["line_count"] = len(content.splitlines())
                    info["word_count"] = len(content.split())
                    info["char_count"] = len(content)
                    
                    # 检测文件类型
                    if filepath.endswith('.json'):
                        try:
                            json.loads(content)
                            info["file_type"] = "valid_json"
                        except:
                            info["file_type"] = "invalid_json"
                    elif filepath.endswith('.py'):
                        info["file_type"] = "python"
                    elif filepath.endswith('.txt'):
                        info["file_type"] = "text"
                    else:
                        info["file_type"] = "unknown"
                        
            except UnicodeDecodeError:
                info["file_type"] = "binary"
            except Exception as e:
                info["read_error"] = str(e)
        
        return info
        
    except Exception as e:
        return {"error": f"分析文件时出错: {str(e)}"}

def analyze_directory(dirpath):
    """分析目录内容"""
    try:
        if not os.path.exists(dirpath):
            return {"error": f"目录不存在: {dirpath}"}
        
        if not os.path.isdir(dirpath):
            return {"error": f"不是目录: {dirpath}"}
        
        items = os.listdir(dirpath)
        
        analysis = {
            "directory": os.path.abspath(dirpath),
            "total_items": len(items),
            "files": [],
            "directories": [],
            "file_extensions": {},
            "total_size_bytes": 0
        }
        
        for item in items:
            item_path = os.path.join(dirpath, item)
            try:
                stats = os.stat(item_path)
                
                if os.path.isfile(item_path):
                    analysis["files"].append({
                        "name": item,
                        "size_bytes": stats.st_size,
                        "extension": os.path.splitext(item)[1]
                    })
                    analysis["total_size_bytes"] += stats.st_size
                    
                    # 统计文件扩展名
                    ext = os.path.splitext(item)[1]
                    if ext:
                        analysis["file_extensions"][ext] = analysis["file_extensions"].get(ext, 0) + 1
                        
                elif os.path.isdir(item_path):
                    analysis["directories"].append(item)
                    
            except Exception as e:
                print(f"警告：无法分析 {item}: {e}")
        
        analysis["total_size_kb"] = round(analysis["total_size_bytes"] / 1024, 2)
        analysis["total_size_mb"] = round(analysis["total_size_bytes"] / (1024 * 1024), 2)
        
        return analysis
        
    except Exception as e:
        return {"error": f"分析目录时出错: {str(e)}"}

def main():
    """主函数"""
    print("=== 文件分析器 ===")
    print("1. 分析单个文件")
    print("2. 分析目录")
    
    choice = input("请选择操作 (1/2): ")
    
    if choice == '1':
        filepath = input("请输入文件路径: ")
        result = analyze_file(filepath)
        print("\n文件分析结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif choice == '2':
        dirpath = input("请输入目录路径: ")
        result = analyze_directory(dirpath)
        print("\n目录分析结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    else:
        print("无效的选择")

if __name__ == "__main__":
    main()