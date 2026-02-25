#!/usr/bin/env python3
"""
基础编程练习3：数据分析器
目标：练习数据处理、统计计算、图表生成
"""

import json
import statistics
import random
from datetime import datetime

def generate_sample_data(num_records=50):
    """生成示例数据"""
    data = []
    base_date = datetime(2024, 1, 1)
    
    for i in range(num_records):
        record = {
            'id': i + 1,
            'date': (base_date + timedelta(days=i)).strftime('%Y-%m-%d'),
            'value': random.randint(10, 100),
            'category': random.choice(['A', 'B', 'C', 'D']),
            'score': round(random.uniform(0, 100), 2)
        }
        data.append(record)
    
    return data

def analyze_data(data):
    """分析数据"""
    if not data:
        return {"error": "数据为空"}
    
    # 提取数值列
    values = [record['value'] for record in data]
    scores = [record['score'] for record in data]
    
    # 按类别分组
    categories = {}
    for record in data:
        cat = record['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(record['value'])
    
    # 计算统计信息
    analysis = {
        '记录数': len(data),
        '数值统计': {
            '总和': sum(values),
            '平均值': statistics.mean(values),
            '中位数': statistics.median(values),
            '标准差': statistics.stdev(values) if len(values) > 1 else 0,
            '最小值': min(values),
            '最大值': max(values)
        },
        '分数统计': {
            '平均分': statistics.mean(scores),
            '最高分': max(scores),
            '最低分': min(scores)
        },
        '类别统计': {}
    }
    
    # 计算每个类别的统计
    for cat, cat_values in categories.items():
        analysis['类别统计'][cat] = {
            '数量': len(cat_values),
            '平均值': statistics.mean(cat_values),
            '总和': sum(cat_values)
        }
    
    return analysis

def find_patterns(data):
    """寻找数据模式"""
    if len(data) < 2:
        return {"error": "数据不足"}
    
    patterns = []
    
    # 检查趋势
    values = [record['value'] for record in data]
    if all(values[i] <= values[i+1] for i in range(len(values)-1)):
        patterns.append("数值呈上升趋势")
    elif all(values[i] >= values[i+1] for i in range(len(values)-1)):
        patterns.append("数值呈下降趋势")
    
    # 检查异常值
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0
    
    if stdev > 0:
        outliers = []
        for i, value in enumerate(values):
            if abs(value - mean) > 2 * stdev:
                outliers.append({
                    '索引': i,
                    '值': value,
                    '偏离均值': round(value - mean, 2)
                })
        
        if outliers:
            patterns.append(f"发现 {len(outliers)} 个异常值")
    
    # 检查类别分布
    categories = {}
    for record in data:
        cat = record['category']
        categories[cat] = categories.get(cat, 0) + 1
    
    most_common = max(categories.items(), key=lambda x: x[1])
    patterns.append(f"最常见的类别是 {most_common[0]}，出现 {most_common[1]} 次")
    
    return patterns

def create_report(data, analysis, patterns):
    """创建报告"""
    report = []
    report.append("=== 数据分析报告 ===")
    report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"分析记录数: {analysis['记录数']}")
    report.append("")
    
    report.append("## 数值统计")
    for key, value in analysis['数值统计'].items():
        report.append(f"  {key}: {value}")
    
    report.append("")
    report.append("## 分数统计")
    for key, value in analysis['分数统计'].items():
        report.append(f"  {key}: {value}")
    
    report.append("")
    report.append("## 类别统计")
    for cat, stats in analysis['类别统计'].items():
        report.append(f"  类别 {cat}: {stats['数量']} 条记录，平均值 {stats['平均值']:.2f}")
    
    report.append("")
    report.append("## 数据模式")
    if patterns:
        for pattern in patterns:
            report.append(f"  • {pattern}")
    else:
        report.append("  未发现明显模式")
    
    return '\n'.join(report)

def main():
    """主函数"""
    print("=== 数据分析器 ===")
    
    # 生成示例数据
    print("1. 生成示例数据...")
    from datetime import timedelta
    data = generate_sample_data(30)
    print(f"生成 {len(data)} 条记录")
    
    # 分析数据
    print("2. 分析数据...")
    analysis = analyze_data(data)
    
    # 寻找模式
    print("3. 寻找数据模式...")
    patterns = find_patterns(data)
    
    # 创建报告
    print("4. 创建报告...")
    report = create_report(data, analysis, patterns)
    
    # 保存报告
    output_file = "learning/data_analysis_report.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"5. 报告已保存到: {output_file}")
    print("\n报告预览:")
    print(report[:500] + "...")

if __name__ == "__main__":
    main()