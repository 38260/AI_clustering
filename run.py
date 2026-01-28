#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI错误分析系统 - 运行入口
用法: python run.py <term_id> <question_id>
"""

import sys
import subprocess
import os

def run_command(cmd, step_name, term_id, question_id):
    """执行命令并处理错误"""
    print(f"\n{step_name} [term_id={term_id}, question_id={question_id}]: {cmd}")
    try:
        # 使用subprocess.run替代os.system，提供更好的编码处理
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'  # 用替换字符代替无法解码的字节
        )
        
        # 打印输出（如果有）
        if result.stdout:
            print(result.stdout)
        
        # 检查返回码
        if result.returncode != 0:
            print(f"❌ {step_name} 执行失败 [term_id={term_id}, question_id={question_id}]")
            print(f"错误代码: {result.returncode}")
            
            # 打印错误信息（如果有）
            if result.stderr:
                print(f"错误信息: {result.stderr}")
            
            # 根据不同步骤提供具体的故障排除建议
            if "步骤1" in step_name:
                print("\n可能的原因:")
                print("1. 数据库连接失败 - 检查config.ini中的数据库配置")
                print(f"2. 表 records_{sys.argv[1]}_{sys.argv[2]} 不存在 - 确认数据库中有对应的表")
                print("3. 数据处理失败 - 检查数据表结构和数据完整性")
                print("\n调试建议:")
                print(f"手动执行: {cmd}")
            elif "步骤2" in step_name:
                print("\n可能的原因:")
                print("1. 数据库连接失败")
                print("2. AI API连接失败 - 检查API配置和网络")
                print("3. 数据文件不存在或格式错误")
                print("4. 数据库写入失败")
                print("\n调试建议:")
                print(f"手动执行: {cmd}")
            
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ {step_name} 执行异常 [term_id={term_id}, question_id={question_id}]: {e}")
        return False

def main():
    if len(sys.argv) != 3:
        print("用法: python run.py <term_id> <question_id>")
        print("示例: python run.py 17787 77337")
        print("\n也可以分步执行:")
        print("  python src/AIProcess/dataProcess.py <term_id> <question_id>")
        print("  python src/AIProcess/AI_process.py <term_id> <question_id>")
        sys.exit(1)
    
    term_id, question_id = sys.argv[1], sys.argv[2]
    
    print(f"开始执行AI错误分析 [term_id={term_id}, question_id={question_id}]")
    
    commands = [
        (f"python src/AIProcess/dataProcess.py {term_id} {question_id}", "步骤1: 数据处理"),
        (f"python src/AIProcess/AI_process.py {term_id} {question_id}", "步骤2: AI分析")
    ]
    
    for cmd, step_name in commands:
        if not run_command(cmd, step_name, term_id, question_id):
            print(f"\n💡 建议:")
            print("1. 检查config.ini配置文件是否正确")
            print("2. 确认数据库服务正在运行")
            print("3. 验证网络连接是否正常")
            print(f"4. 确认数据表存在且有数据 [term_id={term_id}, question_id={question_id}]")
            print("5. 手动执行失败的命令查看详细错误")
            sys.exit(1)
    
    print(f"\n✅ 所有步骤执行完成 [term_id={term_id}, question_id={question_id}]")

if __name__ == "__main__":
    main()