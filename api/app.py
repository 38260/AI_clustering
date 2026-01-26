#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI错误分析系统 - API服务
"""

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import configparser
import mysql.connector
from mysql.connector import Error
import os
import sys
import json
import subprocess
import time
import glob
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 配置JSON返回中文不转义
app.config['JSON_AS_ASCII'] = False

class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime类型"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return super().default(obj)

def safe_json_serialize(data):
    """安全的JSON序列化，处理datetime等特殊类型"""
    return json.dumps(data, cls=DateTimeEncoder, ensure_ascii=False, indent=2)
    """自定义JSON编码器，保持原始转义字符"""
    def encode(self, obj):
        # 使用默认编码，但不转换转义字符
        result = super().encode(obj)
        return result
    
    def iterencode(self, obj, _one_shot=False):
        """重写iterencode方法以保持原始字符串格式"""
        if isinstance(obj, str):
            # 对于字符串，我们需要特殊处理以保持原始转义字符
            yield json.dumps(obj, ensure_ascii=False)
        elif isinstance(obj, dict):
            yield '{'
            first = True
            for key, value in obj.items():
                if not first:
                    yield ', '
                first = False
                yield json.dumps(key, ensure_ascii=False)
                yield ': '
                yield from self.iterencode(value, _one_shot)
            yield '}'
        elif isinstance(obj, list):
            yield '['
            first = True
            for item in obj:
                if not first:
                    yield ', '
                first = False
                yield from self.iterencode(item, _one_shot)
            yield ']'
        else:
            yield json.dumps(obj, ensure_ascii=False)

class DatabaseManager:
    """数据库管理类"""
    
    def __init__(self):
        self.config = self._load_config()
        self.connection = None
    
    def _load_config(self):
        """加载配置文件"""
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.ini')
        config.read(config_path, encoding='utf-8')
        return config
    
    def connect(self):
        """连接数据库"""
        try:
            self.connection = mysql.connector.connect(
                host=self.config.get('Database', 'host'),
                port=self.config.getint('Database', 'port'),
                user=self.config.get('Database', 'user'),
                password=self.config.get('Database', 'password'),
                database=self.config.get('Database', 'database'),
                charset='utf8mb4',
                autocommit=True,  # 启用自动提交
                use_unicode=True
            )
            
            # 设置事务隔离级别
            cursor = self.connection.cursor()
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.close()
            
            return True
        except Error as e:
            print(f"数据库连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开数据库连接"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
    
    def execute_query(self, query, params=None, max_retries=3):
        """执行查询，带重试机制"""
        for attempt in range(max_retries):
            try:
                if not self.connection or not self.connection.is_connected():
                    if not self.connect():
                        print("数据库连接失败")
                        return None
                
                cursor = self.connection.cursor(dictionary=True)
                cursor.execute(query, params or ())
                result = cursor.fetchall()
                cursor.close()
                return result
                
            except Error as e:
                error_code = e.errno if hasattr(e, 'errno') else None
                
                # 如果是表定义变更错误(1412)，重试
                if error_code == 1412 and attempt < max_retries - 1:
                    print(f"表定义已变更，正在重试 (尝试 {attempt + 1}/{max_retries})")
                    # 断开并重新连接
                    self.disconnect()
                    time.sleep(0.1)  # 短暂等待
                    continue
                
                print(f"查询执行失败: {e}")
                print(f"查询语句: {query}")
                return None
                
            except Exception as e:
                print(f"执行查询时发生未知错误: {e}")
                print(f"查询语句: {query}")
                return None
        
        print(f"查询重试 {max_retries} 次后仍然失败")
        return None

# 全局数据库管理器
db_manager = DatabaseManager()

@app.route('/domain/api/overview', methods=['GET'])
def get_overview():
    """
    获取数据概览统计
    从两个数据库表中统计数据，包含字段：
    term_name, term_id, question_id, question_name, user_count, record_count, requirements, standard_code, unit_sequence
    """
    try:
        # 从配置文件读取表名
        records_table = db_manager.config.get('DataTable', 'records_table')
        question_info_table = db_manager.config.get('DataTable', 'question_info_table')
        
        print(f"正在查询表: {records_table} 和 {question_info_table}")
        
        # 联合查询两个表，获取完整的统计数据
        # 注意：records表中没有term_name，我们用term_id作为term_name的替代
        data_query = f"""
        SELECT 
            CONCAT('Term_', r.term_id) as term_name,
            r.term_id,
            r.question_id,
            q.name as question_name,
            COUNT(DISTINCT r.user_id) as user_count,
            COUNT(*) as record_count,
            q.requirements,
            q.standard_code,
            r.unit_sequence,
            r.unit_id,
            r.unit_template_id,
            r.unit_template_name,
            r.course_level
        FROM {records_table} r
        LEFT JOIN {question_info_table} q ON r.question_id = q.question_id
        WHERE r.answer_hash IS NOT NULL
        GROUP BY r.term_id, r.question_id, q.name, q.requirements, q.standard_code, r.unit_sequence, r.unit_id, r.unit_template_id, r.unit_template_name, r.course_level
        ORDER BY r.term_id, r.question_id
        """
        
        results = db_manager.execute_query(data_query)
        
        if results is None:
            # 检查表是否存在
            check_records_table = f"SHOW TABLES LIKE '{records_table}'"
            check_question_table = f"SHOW TABLES LIKE '{question_info_table}'"
            
            records_exists = db_manager.execute_query(check_records_table)
            question_exists = db_manager.execute_query(check_question_table)
            
            missing_tables = []
            if not records_exists:
                missing_tables.append(records_table)
            if not question_exists:
                missing_tables.append(question_info_table)
            
            if missing_tables:
                return Response(
                    safe_json_serialize({
                        'success': False,
                        'message': f'数据表不存在: {", ".join(missing_tables)}',
                        'data': []
                    }),
                    mimetype='application/json; charset=utf-8',
                    status=404
                )
            else:
                return Response(
                    safe_json_serialize({
                        'success': False,
                        'message': '数据库查询失败',
                        'data': []
                    }),
                    mimetype='application/json; charset=utf-8',
                    status=500
                )
        
        # 构建数据框格式的返回数据
        data_frame = []
        for row in results:
            # 直接使用数据库原始数据，不做任何处理
            data_frame.append({
                'term_id': row['term_id'],
                'question_id': row['question_id'],
                'question_name': row['question_name'],
                'user_count': row['user_count'],
                'record_count': row['record_count'],
                'requirements': row['requirements'],
                'standard_code': row['standard_code'],
                'unit_sequence': row['unit_sequence'],
                'unit_id': row['unit_id'],
                'unit_template_id': row['unit_template_id'],
                'unit_template_name': row['unit_template_name'],
                'course_level': row['course_level']
            })
        
        # 统计汇总信息
        summary = {
            'total_terms': len(set(row['term_id'] for row in data_frame)),
            'total_questions': len(set(row['question_id'] for row in data_frame)),
            'total_records': sum(row['record_count'] for row in data_frame),
            'total_users': sum(row['user_count'] for row in data_frame),
            'data_sources': {
                'records_table': records_table,
                'question_info_table': question_info_table
            }
        }
        
        response_data = {
            'success': True,
            'message': '200',
            'summary': summary,
            'data': data_frame
        }
        
        # 使用安全序列化保持原始转义字符
        json_str = safe_json_serialize(response_data)
        
        return Response(
            json_str,
            mimetype='application/json; charset=utf-8'
        )
        
    except Exception as e:
        response_data = {
            'success': False,
            'message': f'服务器错误: {str(e)}',
            'data': []
        }
        return Response(
            json.dumps(response_data, ensure_ascii=False, indent=2),
            mimetype='application/json; charset=utf-8',
            status=500
        )

@app.route('/domain/api/clustering', methods=['POST'])
def clustering_analysis():
    """
    聚类分析接口
    完整流程：先执行AI分析生成结果表，再统计返回聚类数据
    """
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            response_data = {
                'success': False,
                'message': '请求参数不能为空',
                'data': None
            }
            return Response(
                safe_json_serialize(response_data),
                mimetype='application/json; charset=utf-8',
                status=400
            )
        
        term_id = data.get('term_id')
        question_id = data.get('question_id')
        
        if not term_id or not question_id:
            response_data = {
                'success': False,
                'message': '缺少必要参数: term_id 和 question_id',
                'data': None
            }
            return Response(
                safe_json_serialize(response_data),
                mimetype='application/json; charset=utf-8',
                status=400
            )
        
        # 验证参数格式
        try:
            term_id = str(term_id)
            question_id = str(question_id)
        except:
            response_data = {
                'success': False,
                'message': 'term_id 和 question_id 必须是有效的数字',
                'data': None
            }
            return Response(
                safe_json_serialize(response_data),
                mimetype='application/json; charset=utf-8',
                status=400
            )
        
        print(f"开始聚类分析流程 [term_id={term_id}, question_id={question_id}]")
        
        # 首先检查是否已有结果
        analysis_results = get_clustering_results(term_id, question_id)
        if analysis_results and isinstance(analysis_results, dict) and 'detailed_data' in analysis_results:
            print(f"找到现有分析结果，直接返回 [term_id={term_id}, question_id={question_id}]")
            
            detailed_data = analysis_results['detailed_data']
            
            response_data = {
                'success': True,
                'message': '聚类分析完成（使用现有结果）',
                'term_id': term_id,
                'question_id': question_id,
                'statistics': detailed_data['statistics'],  # 统计信息放在前面
                'ai_table_data': detailed_data['ai_table_data']  # AI表中的所有数据（已包含聚合的用户信息）
            }
            
            return Response(
                safe_json_serialize(response_data),
                mimetype='application/json; charset=utf-8'
            )
        
        # 步骤1: 执行AI分析流程
        start_time = time.time()
        
        # 从配置文件读取超时时间
        config = configparser.ConfigParser()
        config.read(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.ini'), encoding='utf-8')
        analysis_timeout = config.getint('API', 'analysis_timeout', fallback=600)
        
        commands = [
            (f"python src/AIProcess/dataProcess.py {question_id} {term_id}", "步骤1: 数据处理"),
            (f"python src/AIProcess/AI_process.py {term_id} {question_id}", "步骤2: AI分析")
        ]
        
        for cmd, step_name in commands:
            step_start = time.time()
            print(f"执行 {step_name} [term_id={term_id}, question_id={question_id}]: {cmd}")
            
            try:
                result = subprocess.run(
                    cmd, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    timeout=analysis_timeout,  # 使用配置的超时时间
                    encoding='utf-8',
                    errors='replace',  # 添加错误处理，用替换字符代替无法解码的字节
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 设置工作目录为项目根目录
                )
                
                step_duration = time.time() - step_start
                
                if result.returncode == 0:
                    print(f"✅ {step_name} 执行成功 [term_id={term_id}, question_id={question_id}] ({step_duration:.2f}秒)")
                else:
                    response_data = {
                        'success': False,
                        'message': f'{step_name} 执行失败',
                        'term_id': term_id,
                        'question_id': question_id,
                        'result_list': [],
                        'error_details': result.stderr
                    }
                    return Response(
                        safe_json_serialize(response_data),
                        mimetype='application/json; charset=utf-8',
                        status=500
                    )
                    
            except subprocess.TimeoutExpired:
                response_data = {
                    'success': False,
                    'message': f'{step_name} 执行超时',
                    'term_id': term_id,
                    'question_id': question_id,
                    'result_list': []
                }
                return Response(
                    safe_json_serialize(response_data),
                    mimetype='application/json; charset=utf-8',
                    status=500
                )
                
            except Exception as e:
                response_data = {
                    'success': False,
                    'message': f'{step_name} 执行异常: {str(e)}',
                    'term_id': term_id,
                    'question_id': question_id,
                    'result_list': []
                }
                return Response(
                    safe_json_serialize(response_data),
                    mimetype='application/json; charset=utf-8',
                    status=500
                )
        
        total_duration = time.time() - start_time
        print(f"AI分析完成 [term_id={term_id}, question_id={question_id}]，总耗时: {total_duration:.2f}秒")
        
        # 步骤2: 读取分析结果并统计
        analysis_results = get_clustering_results(term_id, question_id)
        
        # 检查返回的数据格式
        if isinstance(analysis_results, dict) and 'detailed_data' in analysis_results:
            # 新格式：包含详细数据
            detailed_data = analysis_results['detailed_data']
            
            response_data = {
                'success': True,
                'message': '聚类分析完成',
                'term_id': term_id,
                'question_id': question_id,
                'statistics': detailed_data['statistics'],  # 统计信息放在前面
                'ai_table_data': detailed_data['ai_table_data']  # AI表中的所有数据（已包含聚合的用户信息）
            }
        else:
            # 旧格式或空数据
            response_data = {
                'success': True,
                'message': '聚类分析完成',
                'term_id': term_id,
                'question_id': question_id,
                'statistics': {},
                'ai_table_data': []
            }
        
        return Response(
            safe_json_serialize(response_data),
            mimetype='application/json; charset=utf-8'
        )
        
    except Exception as e:
        response_data = {
            'success': False,
            'message': f'聚类分析服务异常: {str(e)}',
            'term_id': term_id if 'term_id' in locals() else '',
            'question_id': question_id if 'question_id' in locals() else '',
            'result_list': []
        }
        return Response(
            safe_json_serialize(response_data),
            mimetype='application/json; charset=utf-8',
            status=500
        )

def get_clustering_results(term_id, question_id):
    """
    获取聚类分析结果
    返回ai_{}数据库中的所有分析结果以及输入文件中的所有用户列表
    """
    try:
        # 查询AI分析结果表
        ai_table_name = f"ai_{term_id}_{question_id}"
        records_table = db_manager.config.get('DataTable', 'records_table')
        
        # 先检查AI结果表是否存在
        check_ai_table = f"SHOW TABLES LIKE '{ai_table_name}'"
        ai_table_exists = db_manager.execute_query(check_ai_table)
        
        if not ai_table_exists:
            print(f"AI结果表 {ai_table_name} 不存在")
            return []
        
        # 查看AI表的结构
        describe_ai_query = f"DESCRIBE {ai_table_name}"
        ai_table_structure = db_manager.execute_query(describe_ai_query)
        
        if ai_table_structure:
            print(f"AI表结构: {[row['Field'] for row in ai_table_structure]}")
        
        # 获取AI表中的所有数据
        ai_all_data_query = f"""
        SELECT *
        FROM {ai_table_name}
        ORDER BY category, subcategory, specific_reason
        """
        
        ai_all_data = db_manager.execute_query(ai_all_data_query)
        
        # 获取输入文件中的所有用户数据
        all_users_query = f"""
        SELECT *
        FROM {records_table}
        WHERE term_id = %s AND question_id = %s
        ORDER BY user_id
        """
        
        all_users_data = db_manager.execute_query(all_users_query, (term_id, question_id))
        
        # 构建返回数据结构
        result_data = {
            'ai_table_data': [],      # AI表中的所有数据（包含聚合的用户信息）
            'statistics': {
                'ai_records_count': 0,
                'input_users_count': 0,
                'categories_summary': {}
            }
        }
        
        # 先处理输入用户数据，建立hash到用户的映射
        hash_to_users = {}
        if all_users_data:
            for row in all_users_data:
                # 处理特殊类型
                user_record = {}
                for key, value in row.items():
                    if isinstance(value, datetime):
                        user_record[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        user_record[key] = value
                
                answer_hash = user_record.get('answer_hash')
                if answer_hash:
                    if answer_hash not in hash_to_users:
                        hash_to_users[answer_hash] = []
                    hash_to_users[answer_hash].append(user_record)
        
        # 处理AI表数据，并合并用户信息
        if ai_all_data:
            for row in ai_all_data:
                # 将所有字段都包含进来，并处理特殊类型
                ai_record = {}
                for key, value in row.items():
                    if isinstance(value, datetime):
                        ai_record[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        ai_record[key] = value
                
                # 根据answer_hash聚合对应的用户信息
                answer_hash = ai_record.get('answer_hash')
                if answer_hash and answer_hash in hash_to_users:
                    # 添加聚合的用户信息（只保留user_ids和user_count）
                    users_for_hash = hash_to_users[answer_hash]
                    ai_record['user_ids'] = [user.get('user_id') for user in users_for_hash]
                    ai_record['user_count'] = len(users_for_hash)
                else:
                    ai_record['user_ids'] = []
                    ai_record['user_count'] = 0
                
                result_data['ai_table_data'].append(ai_record)
                
                # 统计分类信息
                category = ai_record.get('category', '未知')
                if category not in result_data['statistics']['categories_summary']:
                    result_data['statistics']['categories_summary'][category] = {
                        'count': 0,
                        'subcategories': {}
                    }
                result_data['statistics']['categories_summary'][category]['count'] += 1
                
                subcategory = ai_record.get('subcategory', '未知')
                if subcategory not in result_data['statistics']['categories_summary'][category]['subcategories']:
                    result_data['statistics']['categories_summary'][category]['subcategories'][subcategory] = 0
                result_data['statistics']['categories_summary'][category]['subcategories'][subcategory] += 1
        
        # 更新统计信息
        result_data['statistics']['ai_records_count'] = len(result_data['ai_table_data'])
        result_data['statistics']['input_users_count'] = len(hash_to_users) if hash_to_users else 0
        
        # 返回完整的数据结构（删除result_list）
        return {
            'detailed_data': result_data  # 只返回详细数据
        }
        
    except Exception as e:
        print(f"获取聚类结果失败: {e}")
        import traceback
        traceback.print_exc()
        # 返回空的数据结构而不是空列表
        return {
            'detailed_data': {
                'ai_table_data': [],
                'statistics': {
                    'ai_records_count': 0,
                    'input_users_count': 0,
                    'categories_summary': {}
                }
            }
        }

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    try:
        # 测试数据库连接
        if db_manager.connect():
            db_status = 'connected'
        else:
            db_status = 'disconnected'
        
        response_data = {
            'status': 'healthy',
            'database': db_status,
            'message': 'API服务运行正常'
        }
        return Response(
            safe_json_serialize(response_data),
            mimetype='application/json; charset=utf-8'
        )
    except Exception as e:
        response_data = {
            'status': 'unhealthy',
            'message': f'服务异常: {str(e)}'
        }
        return Response(
            json.dumps(response_data, ensure_ascii=False, indent=2),
            mimetype='application/json; charset=utf-8',
            status=500
        )

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    response_data = {
        'success': False,
        'message': '接口不存在',
        'data': None
    }
    return Response(
        safe_json_serialize(response_data),
        mimetype='application/json; charset=utf-8',
        status=404
    )

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    response_data = {
        'success': False,
        'message': '服务器内部错误',
        'data': None
    }
    return Response(
        safe_json_serialize(response_data),
        mimetype='application/json; charset=utf-8',
        status=500
    )

if __name__ == '__main__':
    print("启动AI错误分析系统API服务...")
    print("数据概览接口: http://localhost:5000/domain/api/overview")
    print("聚类分析接口: http://localhost:5000/domain/api/clustering")
    print("健康检查: http://localhost:5000/health")
    print()
    
    # 启动Flask应用
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )