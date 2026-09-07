#!/usr/bin/env python3
"""
整理经验库脚本
1. 读取经验库
2. 分析重复和矛盾经验
3. 合并相似经验
4. 优化经验库结构
"""

import json
import re
from datetime import datetime
from collections import defaultdict

def load_lessons(filepath="data/lessons.json"):
    """加载经验库"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_lessons(lessons):
    """分析经验库"""
    print(f"总经验数: {len(lessons)}")
    
    # 按触发词分组
    trigger_groups = defaultdict(list)
    for lesson in lessons:
        trigger = lesson.get('trigger', '')
        # 简化触发词用于分组
        simple_trigger = re.sub(r'\{.*?\}', '', trigger)  # 移除参数
        simple_trigger = re.sub(r'\(.*?\)', '', simple_trigger)  # 移除括号内容
        simple_trigger = simple_trigger[:100]  # 截断
        trigger_groups[simple_trigger].append(lesson)
    
    # 统计重复触发
    duplicate_triggers = {k: v for k, v in trigger_groups.items() if len(v) > 1}
    print(f"重复触发数: {len(duplicate_triggers)}")
    
    # 按教训内容分组
    lesson_groups = defaultdict(list)
    for lesson in lessons:
        lesson_text = lesson.get('lesson', '')
        simple_lesson = re.sub(r'\[.*?\]', '', lesson_text)  # 移除括号
        simple_lesson = simple_lesson[:100]
        lesson_groups[simple_lesson].append(lesson)
    
    duplicate_lessons = {k: v for k, v in lesson_groups.items() if len(v) > 1}
    print(f"重复教训数: {len(duplicate_lessons)}")
    
    return trigger_groups, lesson_groups

def find_contradictions(lessons):
    """查找矛盾经验"""
    contradictions = []
    
    # 按触发词分组
    trigger_map = defaultdict(list)
    for lesson in lessons:
        trigger = lesson.get('trigger', '')
        if '[启动自检]' in trigger or '启动自检' in trigger:
            trigger_map['启动自检'].append(lesson)
        elif '工具失败' in trigger:
            trigger_map['工具失败'].append(lesson)
        elif '用户教学' in trigger:
            trigger_map['用户教学'].append(lesson)
    
    # 检查启动自检相关的矛盾
    if '启动自检' in trigger_map:
        boot_lessons = trigger_map['启动自检']
        print(f"启动自检相关经验: {len(boot_lessons)}条")
        
        # 检查矛盾
        for i, lesson1 in enumerate(boot_lessons):
            for j, lesson2 in enumerate(boot_lessons[i+1:], i+1):
                lesson1_text = lesson1.get('lesson', '')
                lesson2_text = lesson2.get('lesson', '')
                
                # 检查是否矛盾
                if '应直接根据用户指令' in lesson1_text and '应直接遵循用户指令' in lesson2_text:
                    if '提供具体行动建议' in lesson1_text and '先总结状态' in lesson2_text:
                        contradictions.append((lesson1, lesson2))
    
    return contradictions

def merge_similar_lessons(lessons):
    """合并相似经验"""
    merged = []
    seen_triggers = set()
    
    # 按触发词排序
    lessons_sorted = sorted(lessons, key=lambda x: x.get('trigger', ''))
    
    for lesson in lessons_sorted:
        trigger = lesson.get('trigger', '')
        lesson_text = lesson.get('lesson', '')
        
        # 简化触发词用于去重
        simple_trigger = re.sub(r'\{.*?\}', '', trigger)
        simple_trigger = re.sub(r'\(.*?\)', '', simple_trigger)
        simple_trigger = re.sub(r'\d+', '', simple_trigger)  # 移除数字
        simple_trigger = simple_trigger.strip()[:80]
        
        if simple_trigger in seen_triggers:
            # 找到已存在的相似经验
            for existing in merged:
                existing_trigger = existing.get('trigger', '')
                existing_simple = re.sub(r'\{.*?\}', '', existing_trigger)
                existing_simple = re.sub(r'\(.*?\)', '', existing_simple)
                existing_simple = re.sub(r'\d+', '', existing_simple)
                existing_simple = existing_simple.strip()[:80]
                
                if existing_simple == simple_trigger:
                    # 合并教训内容
                    existing_lesson = existing.get('lesson', '')
                    if lesson_text not in existing_lesson:
                        # 添加新的教训点
                        if '改进:' in existing_lesson and '改进:' in lesson_text:
                            # 合并改进点
                            existing_parts = existing_lesson.split('改进:')
                            lesson_parts = lesson_text.split('改进:')
                            if len(existing_parts) > 1 and len(lesson_parts) > 1:
                                combined = f"{existing_parts[0]}改进: {existing_parts[1].strip()}; {lesson_parts[1].strip()}"
                                existing['lesson'] = combined
                    break
        else:
            seen_triggers.add(simple_trigger)
            merged.append(lesson.copy())
    
    return merged

def optimize_lesson_structure(lessons):
    """优化经验结构"""
    optimized = []
    
    for lesson in lessons:
        optimized_lesson = lesson.copy()
        
        # 清理触发词
        trigger = lesson.get('trigger', '')
        if trigger.startswith('用户教学: '):
            optimized_lesson['trigger'] = trigger.replace('用户教学: ', '').strip()
        
        # 标准化教训格式
        lesson_text = lesson.get('lesson', '')
        if lesson_text.startswith('弱点: '):
            # 确保有改进部分
            if '改进:' not in lesson_text:
                optimized_lesson['lesson'] = f"{lesson_text} 改进: 根据具体情境选择合适策略。"
        
        # 添加分类标签
        trigger_lower = trigger.lower()
        if '工具失败' in trigger:
            optimized_lesson['category'] = 'tool_failure'
        elif '用户教学' in trigger or '老师指令' in lesson_text:
            optimized_lesson['category'] = 'user_teaching'
        elif '启动自检' in trigger:
            optimized_lesson['category'] = 'self_check'
        elif '反思' in trigger or '反思' in lesson_text:
            optimized_lesson['category'] = 'reflection'
        else:
            optimized_lesson['category'] = 'other'
        
        optimized.append(optimized_lesson)
    
    return optimized

def save_lessons(lessons, filepath="data/lessons_optimized.json"):
    """保存优化后的经验库"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(lessons, f, ensure_ascii=False, indent=2)
    print(f"已保存优化后的经验库到 {filepath}")

def main():
    print("开始整理经验库...")
    
    # 加载经验库
    lessons = load_lessons()
    
    # 分析经验库
    trigger_groups, lesson_groups = analyze_lessons(lessons)
    
    # 查找矛盾
    contradictions = find_contradictions(lessons)
    print(f"找到矛盾经验对: {len(contradictions)}")
    
    # 合并相似经验
    merged_lessons = merge_similar_lessons(lessons)
    print(f"合并后经验数: {len(merged_lessons)} (减少了 {len(lessons) - len(merged_lessons)} 条)")
    
    # 优化结构
    optimized_lessons = optimize_lesson_structure(merged_lessons)
    
    # 保存备份
    import shutil
    shutil.copy2("data/lessons.json", "data/lessons_backup.json")
    print("已创建备份: data/lessons_backup.json")
    
    # 保存优化版本
    save_lessons(optimized_lessons, "data/lessons_optimized.json")
    
    # 也更新原文件
    save_lessons(optimized_lessons, "data/lessons.json")
    
    print("经验库整理完成！")
    
    # 生成报告
    report = {
        "original_count": len(lessons),
        "optimized_count": len(optimized_lessons),
        "reduction": len(lessons) - len(optimized_lessons),
        "contradictions_found": len(contradictions),
        "categories": defaultdict(int)
    }
    
    for lesson in optimized_lessons:
        category = lesson.get('category', 'other')
        report['categories'][category] += 1
    
    print("\n=== 整理报告 ===")
    print(f"原始经验数: {report['original_count']}")
    print(f"优化后经验数: {report['optimized_count']}")
    print(f"减少经验数: {report['reduction']}")
    print(f"发现矛盾: {report['contradictions_found']}")
    print("分类统计:")
    for category, count in report['categories'].items():
        print(f"  {category}: {count}")

if __name__ == "__main__":
    main()