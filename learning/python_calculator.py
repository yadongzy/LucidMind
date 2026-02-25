#!/usr/bin/env python3
"""
基础编程练习1：简单计算器
目标：练习Python基础语法、函数定义、用户输入处理
"""

def add(a, b):
    """加法"""
    return a + b

def subtract(a, b):
    """减法"""
    return a - b

def multiply(a, b):
    """乘法"""
    return a * b

def divide(a, b):
    """除法"""
    if b == 0:
        return "错误：除数不能为0"
    return a / b

def calculator():
    """主计算器函数"""
    print("=== 简单计算器 ===")
    print("支持的操作：+ - * /")
    
    try:
        num1 = float(input("请输入第一个数字: "))
        operator = input("请输入运算符 (+, -, *, /): ")
        num2 = float(input("请输入第二个数字: "))
        
        if operator == '+':
            result = add(num1, num2)
        elif operator == '-':
            result = subtract(num1, num2)
        elif operator == '*':
            result = multiply(num1, num2)
        elif operator == '/':
            result = divide(num1, num2)
        else:
            print("错误：不支持的运算符")
            return
        
        print(f"{num1} {operator} {num2} = {result}")
        
    except ValueError:
        print("错误：请输入有效的数字")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    calculator()