#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI错误分析系统 - 快速配置脚本
"""

import os
import shutil

def setup_project():
    """设置项目环境"""
    print("AI错误分析系统 - 环境配置")
    print("=" * 50)
    
    # 检查并创建必要目录
    directories = ['data', 'assets']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✅ 创建目录: {directory}")
        else:
            print(f"📁 目录已存在: {directory}")
    
    # 复制配置文件模板
    if not os.path.exists('config.ini'):
        if os.path.exists('config.ini.example'):
            shutil.copy('config.ini.example', 'config.ini')
            print("创建配置文件: config.ini")
            print("请编辑 config.ini 文件，填入你的数据库和API配置")
        else:
            print("配置文件模板不存在: config.ini.example")
    else:
        print("配置文件已存在: config.ini")
    
    # 检查必要文件
    required_files = [
        'assets/system_prompt.txt',
        'requirements.txt'
    ]
    
    print("\n检查必要文件:")
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path}")
        else:
            print(f"{file_path} - 文件缺失")
    
    print("\n下一步:")
    print("1. 编辑 config.ini 文件，填入你的配置")
    print("2. 安装依赖: pip install -r requirements.txt")
    print("3. 运行: python run.py <term_id> <question_id>")
    
    print("\n配置完成！")

if __name__ == "__main__":
    setup_project()