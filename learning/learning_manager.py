#!/usr/bin/env python3
"""
综合练习：学习管理系统
目标：整合文件操作、数据处理、用户交互
"""

import json
import os
from datetime import datetime

class LearningManager:
    """学习管理器"""
    
    def __init__(self, data_file="learning/learning_data.json"):
        self.data_file = data_file
        self.data = self.load_data()
    
    def load_data(self):
        """加载数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"exercises": [], "stats": {}}
        return {"exercises": [], "stats": {}}
    
    def save_data(self):
        """保存数据"""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        return True
    
    def add_exercise(self, name, category, difficulty=1):
        """添加练习"""
        exercise = {
            "id": len(self.data["exercises"]) + 1,
            "name": name,
            "category": category,
            "difficulty": difficulty,
            "completed": False,
            "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "completed_at": None,
            "attempts": 0,
            "successful_attempts": 0
        }
        self.data["exercises"].append(exercise)
        self.save_data()
        return exercise
    
    def complete_exercise(self, exercise_id):
        """完成练习"""
        for exercise in self.data["exercises"]:
            if exercise["id"] == exercise_id:
                exercise["completed"] = True
                exercise["completed_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                exercise["attempts"] += 1
                exercise["successful_attempts"] += 1
                self.save_data()
                return True
        return False
    
    def record_attempt(self, exercise_id, success=True):
        """记录尝试"""
        for exercise in self.data["exercises"]:
            if exercise["id"] == exercise_id:
                exercise["attempts"] += 1
                if success:
                    exercise["successful_attempts"] += 1
                self.save_data()
                return True
        return False
    
    def get_stats(self):
        """获取统计信息"""
        exercises = self.data["exercises"]
        if not exercises:
            return {"total": 0, "completed": 0, "completion_rate": 0}
        
        total = len(exercises)
        completed = sum(1 for e in exercises if e["completed"])
        total_attempts = sum(e["attempts"] for e in exercises)
        successful_attempts = sum(e["successful_attempts"] for e in exercises)
        
        stats = {
            "total_exercises": total,
            "completed_exercises": completed,
            "completion_rate": round(completed / total * 100, 2) if total > 0 else 0,
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "success_rate": round(successful_attempts / total_attempts * 100, 2) if total_attempts > 0 else 0,
            "by_category": {},
            "by_difficulty": {}
        }
        
        # 按类别统计
        categories = {}
        for exercise in exercises:
            cat = exercise["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "completed": 0}
            categories[cat]["total"] += 1
            if exercise["completed"]:
                categories[cat]["completed"] += 1
        
        for cat, data in categories.items():
            stats["by_category"][cat] = {
                "total": data["total"],
                "completed": data["completed"],
                "rate": round(data["completed"] / data["total"] * 100, 2) if data["total"] > 0 else 0
            }
        
        # 按难度统计
        difficulties = {}
        for exercise in exercises:
            diff = exercise["difficulty"]
            if diff not in difficulties:
                difficulties[diff] = {"total": 0, "completed": 0}
            difficulties[diff]["total"] += 1
            if exercise["completed"]:
                difficulties[diff]["completed"] += 1
        
        for diff, data in difficulties.items():
            stats["by_difficulty"][diff] = {
                "total": data["total"],
                "completed": data["completed"],
                "rate": round(data["completed"] / data["total"] * 100, 2) if data["total"] > 0 else 0
            }
        
        return stats
    
    def find_recommendations(self):
        """推荐练习"""
        exercises = self.data["exercises"]
        if not exercises:
            return []
        
        # 找出未完成且尝试次数少的练习
        recommendations = []
        for exercise in exercises:
            if not exercise["completed"] and exercise["attempts"] < 3:
                recommendations.append({
                    "id": exercise["id"],
                    "name": exercise["name"],
                    "category": exercise["category"],
                    "difficulty": exercise["difficulty"],
                    "priority": exercise["difficulty"] * (3 - exercise["attempts"])
                })
        
        # 按优先级排序
        recommendations.sort(key=lambda x: x["priority"], reverse=True)
        return recommendations[:5]
    
    def generate_report(self):
        """生成报告"""
        stats = self.get_stats()
        recommendations = self.find_recommendations()
        
        report = []
        report.append("=== 学习进度报告 ===")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        report.append("## 总体统计")
        report.append(f"总练习数: {stats['total_exercises']}")
        report.append(f"已完成: {stats['completed_exercises']}")
        report.append(f"完成率: {stats['completion_rate']}%")
        report.append(f"尝试次数: {stats['total_attempts']}")
        report.append(f"成功率: {stats['success_rate']}%")
        report.append("")
        
        if stats["by_category"]:
            report.append("## 按类别统计")
            for cat, data in stats["by_category"].items():
                report.append(f"  {cat}: {data['completed']}/{data['total']} ({data['rate']}%)")
            report.append("")
        
        if stats["by_difficulty"]:
            report.append("## 按难度统计")
            for diff, data in stats["by_difficulty"].items():
                report.append(f"  难度{diff}: {data['completed']}/{data['total']} ({data['rate']}%)")
            report.append("")
        
        if recommendations:
            report.append("## 推荐练习")
            for rec in recommendations:
                report.append(f"  {rec['id']}. {rec['name']} ({rec['category']}, 难度{rec['difficulty']})")
        else:
            report.append("## 推荐练习")
            report.append("  暂无推荐，所有练习都已完成或尝试多次")
        
        return '\n'.join(report)

def main():
    """主函数"""
    manager = LearningManager()
    
    print("=== 学习管理系统 ===")
    print("1. 查看进度")
    print("2. 添加练习")
    print("3. 完成练习")
    print("4. 生成报告")
    print("5. 查看推荐")
    
    try:
        choice = input("请选择操作 (1-5): ")
        
        if choice == '1':
            stats = manager.get_stats()
            print("\n学习进度:")
            print(f"总练习数: {stats['total_exercises']}")
            print(f"已完成: {stats['completed_exercises']}")
            print(f"完成率: {stats['completion_rate']}%")
            
        elif choice == '2':
            name = input("练习名称: ")
            category = input("类别: ")
            difficulty = int(input("难度 (1-5): "))
            exercise = manager.add_exercise(name, category, difficulty)
            print(f"添加成功: {exercise['name']} (ID: {exercise['id']})")
            
        elif choice == '3':
            try:
                exercise_id = int(input("练习ID: "))
                if manager.complete_exercise(exercise_id):
                    print("练习标记为完成")
                else:
                    print("未找到该练习")
            except ValueError:
                print("请输入有效的ID")
                
        elif choice == '4':
            report = manager.generate_report()
            print("\n" + report)
            
            # 保存报告
            report_file = "learning/learning_report.txt"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n报告已保存到: {report_file}")
            
        elif choice == '5':
            recommendations = manager.find_recommendations()
            if recommendations:
                print("\n推荐练习:")
                for rec in recommendations:
                    print(f"  {rec['id']}. {rec['name']} ({rec['category']}, 难度{rec['difficulty']})")
            else:
                print("\n暂无推荐练习")
                
        else:
            print("无效的选择")
            
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()