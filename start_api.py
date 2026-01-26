#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动API服务脚本
"""

import os
import sys

def main():
    """启动API服务"""
    print("正在启动AI错误分析系统API服务...")
    
    # 切换到api目录并启动服务
    api_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api')
    os.chdir(api_path)
    
    # 启动Flask应用
    os.system('python app.py')

if __name__ == "__main__":
    main()