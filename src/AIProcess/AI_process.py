import configparser
import json
import mysql.connector
import pandas as pd
import requests
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# 全局变量
category_updates = {
    'new_subcategories': [],
    'similar_rejections': [],  # 记录因相似而被拒绝的子类别
    'category_stats': {}       # 记录每个主类别的使用统计
}
file_lock = Lock()

class Counter:
    def __init__(self):
        self._value = 0
        self._lock = Lock()
    
    def increment(self):
        with self._lock:
            self._value += 1
    
    @property
    def value(self):
        return self._value

def get_config():
    """从config.ini读取配置"""
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    db_config = {
        'host': config.get('Database', 'host'),
        'port': int(config.get('Database', 'port')),
        'user': config.get('Database', 'user'),
        'password': config.get('Database', 'password'),
        'database': config.get('Database', 'database')
    }
    
    api_config = {
        'api_url': config.get('API', 'api_url'),
        'api_key': config.get('API', 'api_key'),
        'model': config.get('API', 'model'),
        'temperature': config.getfloat('API', 'temperature', fallback=0),
        'timeout': config.getint('API', 'timeout', fallback=30),
        'max_retry': config.getint('API', 'max_retry', fallback=3),
        'analysis_timeout': config.getint('API', 'analysis_timeout', fallback=600)
    }
    
    prompt_config = {
        'system_prompt_path': config.get('Prompt', 'system_prompt_path'),
        'user_prompt': config.get('Prompt', 'user_prompt')
    }
    
    thread_config = {
        'max_workers': config.getint('API', 'max_workers', fallback=8),
        'request_delay': config.getfloat('API', 'request_delay', fallback=0.2)
    }
    
    template_config = {
        'template_id': '1001'  # 默认值
    }
    
    try:
        if 'Template' in config:
            template_section = config['Template']
            template_config['template_id'] = template_section.get('template_id', '1001')
    except Exception:
        pass
    
    return db_config, api_config, prompt_config, thread_config, template_config

def create_reusable_category_table(conn, term_id, question_id):
    """创建可复用分类表"""
    table_name = f"reusableCategory_{term_id}_{question_id}"
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
    table_exists = cursor.fetchone() is not None
    
    if not table_exists:
        create_table_sql = f"""
        CREATE TABLE {table_name} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(100) NOT NULL,
            subcategory VARCHAR(150) NOT NULL,
            thirdCategory VARCHAR(200) NOT NULL,
            UNIQUE KEY unique_category (category(50), subcategory(80), thirdCategory(100)),
            INDEX idx_category (category),
            INDEX idx_subcategory (subcategory),
            INDEX idx_thirdCategory (thirdCategory)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        cursor.execute(create_table_sql)
        conn.commit()
        
        # 初始化基础分类数据
        initial_categories = [
        ]
        
        insert_sql = f"""
        INSERT IGNORE INTO {table_name} (category, subcategory, thirdCategory)
        VALUES (%s, %s, %s)
        """
        cursor.executemany(insert_sql, initial_categories)
        conn.commit()
    
    cursor.close()
    return table_name

def load_categories_from_db(conn, table_name):
    """从数据库加载分类数据"""
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT DISTINCT category, subcategory, thirdCategory FROM {table_name}")
        rows = cursor.fetchall()
        cursor.close()
        
        # 转换为原来的JSON格式以便兼容现有逻辑
        categories = {}
        for row in rows:
            category = row['category']
            subcategory = row['subcategory']
            thirdCategory = row['thirdCategory']
            
            if category not in categories:
                categories[category] = {}
            
            if subcategory not in categories[category]:
                categories[category][subcategory] = []
            
            if thirdCategory not in categories[category][subcategory]:
                categories[category][subcategory].append(thirdCategory)
        
        # 转换为列表格式
        result = []
        for category, subcategories in categories.items():
            subcategory_list = []
            for subcategory, thirdCategories in subcategories.items():
                subcategory_list.append({
                    'subcategory': subcategory,
                    'thirdCategory': thirdCategories
                })
            result.append({
                'category': category,
                'subcategory': subcategory_list
            })
        
        return result
    except Exception as e:
        print(f"从数据库加载分类失败: {e}")
        return []

def load_system_prompt(system_prompt_path, conn, category_table_name):
    """加载系统提示词"""
    try:
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()
        
        # 从数据库加载分类数据
        categories = load_categories_from_db(conn, category_table_name)
        categories_text = json.dumps(categories, ensure_ascii=False, indent=2)
        
        # 在系统提示词中插入分类信息
        if "已有的错误分类体系将从数据库中动态加载。" in system_prompt:
            system_prompt = system_prompt.replace(
                "已有的错误分类体系将从数据库中动态加载。",
                f"已有的错误分类体系如下：\n\n{categories_text}\n"
            )
        
        return system_prompt
    except Exception as e:
        print(f"系统提示词加载失败: {e}")
        return ""

def connect_to_database(db_config):
    """连接到MySQL数据库"""
    return mysql.connector.connect(**db_config)

def create_ai_table(conn, table_name):
    """创建AI分析结果表"""
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
    table_exists = cursor.fetchone() is not None
    
    if not table_exists:
        create_table_sql = f"""
        CREATE TABLE {table_name} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            answer_hash VARCHAR(255) NOT NULL,
            question_id BIGINT NOT NULL,
            category VARCHAR(255),
            subcategory VARCHAR(255),
            thirdCategory VARCHAR(255),
            specific_reason VARCHAR(300),
            mark_code LONGTEXT,
            standard_code LONGTEXT,
            answer_code LONGTEXT,
            error_info TEXT,
            response JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_answer_hash (answer_hash),
            INDEX idx_question_id (question_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        cursor.execute(create_table_sql)
        conn.commit()
    else:
        # 检查并添加缺失的字段
        cursor.execute(f"DESCRIBE {table_name}")
        columns = [row[0] for row in cursor.fetchall()]
        
        if 'question_id' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN question_id BIGINT NOT NULL")
        if 'category' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN category VARCHAR(255)")
        if 'subcategory' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN subcategory VARCHAR(255)")
        if 'thirdCategory' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN thirdCategory VARCHAR(255)")
        if 'specific_reason' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN specific_reason VARCHAR(300)")
        if 'mark_code' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN mark_code LONGTEXT")
        if 'standard_code' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN standard_code LONGTEXT")
        if 'answer_code' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN answer_code LONGTEXT")
        if 'error_info' not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN error_info TEXT")
        if 'response' not in columns:
            if 'analysis_result' in columns:
                # 重命名现有的analysis_result列为response
                cursor.execute(f"ALTER TABLE {table_name} CHANGE COLUMN analysis_result response JSON")
            else:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN response JSON")
        
        conn.commit()
    
    cursor.close()

def get_question_info(conn, term_id, question_id):
    """从question_info表中获取题目信息"""
    try:
        # 从配置中获取表名
        config = configparser.ConfigParser()
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
        config_read = False
        
        for encoding in encodings:
            try:
                config.read('config.ini', encoding=encoding)
                config_read = True
                break
            except UnicodeDecodeError:
                continue
        
        # 获取question_info表名
        question_info_table = "code_clustering_question_parse"  # 默认值
        if config_read and 'DataTable' in config:
            table_section = config['DataTable']
            question_info_table = table_section.get('question_info_table', 'code_clustering_question_parse')
        
        query = f"""
        SELECT question_id, name as question_name, requirements, standard_code
        FROM {question_info_table}
        WHERE question_id = %s
        """
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, (question_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            # 处理requirements字段（JSON格式）
            requirements = result.get('requirements')
            if requirements and isinstance(requirements, (str, dict)):
                if isinstance(requirements, str):
                    import json
                    try:
                        requirements = json.loads(requirements)
                    except:
                        pass
                # 将JSON转换为字符串格式以便后续处理
                result['requirements'] = json.dumps(requirements, ensure_ascii=False) if isinstance(requirements, dict) else str(requirements)
        
        return result
    except Exception as e:
        print(f"获取题目信息失败: {e}")
        return None

def check_answer_exists(conn, table_name, answer_hash):
    """检查answer_hash是否已存在"""
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT id FROM {table_name} WHERE answer_hash = %s", (answer_hash,))
        result = cursor.fetchone()
        cursor.close()
        return result is not None
    except Exception:
        return False

def call_ai_api(api_config, system_prompt, user_prompt):
    """调用AI API进行分析"""
    headers = {
        'Authorization': f'Bearer {api_config["api_key"]}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'model': api_config['model'],
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': api_config['temperature']
    }
    
    last_error = None
    for attempt in range(api_config['max_retry']):
        try:
            response = requests.post(
                api_config['api_url'],
                headers=headers,
                json=data,
                timeout=api_config['timeout']
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"AI响应JSON解析失败 (尝试 {attempt + 1}/{api_config['max_retry']}): {e}")
                    print(f"原始响应内容: {content[:500]}...")
                    last_error = f"JSON解析失败: {e}"
            else:
                print(f"AI API调用失败 (尝试 {attempt + 1}/{api_config['max_retry']}): HTTP {response.status_code}")
                print(f"响应内容: {response.text[:500]}...")
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            
        except requests.exceptions.Timeout as e:
            print(f"AI API调用超时 (尝试 {attempt + 1}/{api_config['max_retry']}): {e}")
            last_error = f"请求超时: {e}"
        except requests.exceptions.RequestException as e:
            print(f"AI API请求异常 (尝试 {attempt + 1}/{api_config['max_retry']}): {e}")
            last_error = f"请求异常: {e}"
        except Exception as e:
            print(f"AI API调用未知异常 (尝试 {attempt + 1}/{api_config['max_retry']}): {e}")
            last_error = f"未知异常: {e}"
        
        if attempt < api_config['max_retry'] - 1:
            time.sleep(1)
    
    print(f"AI API调用最终失败，已重试 {api_config['max_retry']} 次，最后错误: {last_error}")
    return None

def is_similar_subcategory(new_subcategory, existing_subcategories):
    """检查新子类别是否与已有子类别相似"""
    new_sub_lower = new_subcategory.lower()
    
    for existing in existing_subcategories:
        existing_lower = existing.lower()
        
        # 检查是否包含相同的关键词
        new_keywords = set(new_sub_lower.replace('错误', '').replace('缺少', '').replace('不匹配', '').split())
        existing_keywords = set(existing_lower.replace('错误', '').replace('缺少', '').replace('不匹配', '').split())
        
        # 如果关键词重叠度超过70%，认为是相似的
        if len(new_keywords & existing_keywords) / max(len(new_keywords), len(existing_keywords)) > 0.7:
            return existing
    
    return None

def update_reusable_category_db(conn, category_table_name, ai_response):
    """更新可复用类别数据库表（带相似性检查和强制刷新）"""
    global category_updates
    
    with file_lock:
        try:
            category = ai_response.get('category', '')
            subcategory = ai_response.get('subcategory', '')
            thirdCategory = ai_response.get('thirdCategory', '')
            
            if not category or not subcategory or not thirdCategory:
                return
            
            # 统计主类别使用次数
            if category not in category_updates['category_stats']:
                category_updates['category_stats'][category] = 0
            category_updates['category_stats'][category] += 1
            
            cursor = conn.cursor()
            
            # 检查是否已存在完全相同的记录
            cursor.execute(f"""
                SELECT id FROM {category_table_name} 
                WHERE category = %s AND subcategory = %s AND thirdCategory = %s
            """, (category, subcategory, thirdCategory))
            
            if cursor.fetchone():
                cursor.close()
                return  # 已存在相同记录
            
            # 检查是否存在相同的category和subcategory组合
            cursor.execute(f"""
                SELECT subcategory FROM {category_table_name} 
                WHERE category = %s
            """, (category,))
            
            existing_subcategories = [row[0] for row in cursor.fetchall()]
            
            # 检查是否存在相似的子类别
            similar_subcategory = is_similar_subcategory(subcategory, existing_subcategories)
            if similar_subcategory and similar_subcategory != subcategory:
                # 如果存在相似的子类别，不添加新的，记录拒绝信息
                category_updates['similar_rejections'].append({
                    'category': category,
                    'rejected_subcategory': subcategory,
                    'similar_existing': similar_subcategory,
                    'reason': '与已有子类别相似'
                })
                print(f"发现相似子类别，使用已有的: '{similar_subcategory}' 而不是 '{subcategory}'")
                cursor.close()
                return
            
            # 插入新的分类记录
            insert_sql = f"""
            INSERT IGNORE INTO {category_table_name} (category, subcategory, thirdCategory)
            VALUES (%s, %s, %s)
            """
            cursor.execute(insert_sql, (category, subcategory, thirdCategory))
            
            if cursor.rowcount > 0:
                category_updates['new_subcategories'].append({
                    'category': category,
                    'subcategory': subcategory,
                    'thirdCategory': thirdCategory
                })
                # 强制提交事务，确保其他线程能立即看到更新
                conn.commit()
                print(f"新增分类: {category} -> {subcategory} -> {thirdCategory}")
            
            cursor.close()
                
        except Exception as e:
            print(f"更新分类数据库失败: {e}")
            # 发生错误时回滚事务
            try:
                conn.rollback()
            except:
                pass

def insert_ai_result(conn, table_name, data):
    """插入AI分析结果到数据库"""
    try:
        cursor = conn.cursor()
        insert_sql = f"""
        INSERT INTO {table_name} (
            answer_hash, question_id, category, subcategory, thirdCategory, specific_reason, mark_code,
            standard_code, answer_code, error_info, response
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_sql, (
            data['answer_hash'],
            data['question_id'],
            data['category'],
            data['subcategory'],
            data['thirdCategory'],
            data['specific_reason'],
            data['mark_code'],
            data['standard_code'],
            data['answer_code'],
            data['error_info'],
            json.dumps(data['response'], ensure_ascii=False)
        ))
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        print(f"数据库插入失败: {e}")
        print(f"数据: {data['answer_hash']}")
        # 确保返回False表示插入失败
        return False
        return False

def process_single_record(args):
    """处理单条记录"""
    (index, row, db_config, api_config, prompt_config, thread_config, template_config,
     question_info, system_prompt_path, ai_table_name, category_table_name) = args
    
    conn = None
    try:
        conn = connect_to_database(db_config)
        
        # 检查是否已存在
        if check_answer_exists(conn, ai_table_name, row['answer_hash']):
            return "skip", 'skip'
        
        # 每次都重新加载系统提示词，确保获取最新的分类数据
        system_prompt = load_system_prompt(system_prompt_path, conn, category_table_name)
        if not system_prompt:
            return "error", 'system_prompt_load_failed'
        
        # 构建用户提示词
        user_prompt = prompt_config['user_prompt'].format(
            question_info=question_info.get('requirements', ''),
            standard_code=question_info.get('standard_code', ''),
            answer_code=row.get('answer_code', '') if pd.notna(row.get('answer_code')) else '',
            error_info=row.get('error_info', '') if pd.notna(row.get('error_info')) else ''
        )
        
        # 调用AI API
        ai_response = call_ai_api(api_config, system_prompt, user_prompt)
        
        if ai_response:
            # 验证AI响应的完整性
            required_fields = ['category', 'subcategory', 'thirdCategory', 'specific_reason', 'mark_code']
            missing_fields = [field for field in required_fields if not ai_response.get(field)]
            
            if missing_fields:
                print(f"AI响应缺少必要字段 {missing_fields}: {row['answer_hash']}")
                return "error", f'ai_response_incomplete: missing {missing_fields}'
            
            # 更新类别库
            update_reusable_category_db(conn, category_table_name, ai_response)
            
            # 插入结果到数据库
            data = {
                'answer_hash': row['answer_hash'],
                'question_id': question_info.get('question_id', ''),
                'category': ai_response.get('category', ''),
                'subcategory': ai_response.get('subcategory', ''),
                'thirdCategory': ai_response.get('thirdCategory', ''),
                'specific_reason': ai_response.get('specific_reason', ''),
                'mark_code': ai_response.get('mark_code', ''),
                'standard_code': question_info.get('standard_code', ''),
                'answer_code': row.get('answer_code', '') if pd.notna(row.get('answer_code')) else '',
                'error_info': row.get('error_info', '') if pd.notna(row.get('error_info')) else '',
                'response': ai_response
            }
            
            if insert_ai_result(conn, ai_table_name, data):
                time.sleep(thread_config['request_delay'])
                return "success", 'success'
            else:
                print(f"数据库插入失败: {row['answer_hash']}")
                return "error", 'database_insert_failed'
        else:
            print(f"AI API调用失败: {row['answer_hash']}")
            return "error", 'api_call_failed'
            
    except Exception as e:
        print(f"处理记录异常 {row['answer_hash']}: {e}")
        return "error", f'exception: {str(e)}'
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

def process_ai_analysis(term_id, question_id):
    """主处理函数"""
    global category_updates
    category_updates = {
        'new_subcategories': [],
        'similar_rejections': [],
        'category_stats': {}
    }
    
    # 加载配置
    db_config, api_config, prompt_config, thread_config, template_config = get_config()
    
    print(f"AI分析开始 [term_id={term_id}, question_id={question_id}]")
    print("直接从数据库真实数据表读取数据")
    
    # 进一步降低并发数以减少数据库竞争
    thread_config['max_workers'] = 1  # 改为单线程处理，避免数据库竞争
    thread_config['request_delay'] = 0.5  # 适当减少延迟
    
    conn = connect_to_database(db_config)
    
    try:
        # 创建可复用分类表
        category_table_name = create_reusable_category_table(conn, term_id, question_id)
        
        # 加载系统提示词
        system_prompt = load_system_prompt(prompt_config['system_prompt_path'], conn, category_table_name)
        if not system_prompt:
            print("系统提示词加载失败")
            return
        
        # 获取题目信息
        question_info = get_question_info(conn, term_id, question_id)
        if not question_info:
            print(f"未找到题目信息 [term_id={term_id}, question_id={question_id}]")
            return
        
        # 创建AI分析表
        ai_table_name = f"ai_{term_id}_{question_id}"
        create_ai_table(conn, ai_table_name)
        
        # 直接从数据库读取数据，而不是从Excel文件
        print("直接从数据库读取聚合数据...")
        
        # 从配置中获取表名
        config = configparser.ConfigParser()
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
        config_read = False
        
        for encoding in encodings:
            try:
                config.read('config.ini', encoding=encoding)
                config_read = True
                break
            except UnicodeDecodeError:
                continue
        
        # 获取records表名
        records_table = "code_clustering_user_answer_record"  # 默认值
        if config_read and 'DataTable' in config:
            table_section = config['DataTable']
            records_table = table_section.get('records_table', 'code_clustering_user_answer_record')
        
        # 直接从数据库查询并聚合数据
        cursor = conn.cursor(dictionary=True)
        query = f"""
        SELECT term_id, question_id, user_id, answer_url, error_info, answer_code, answer_hash
        FROM {records_table}
        WHERE term_id = %s AND question_id = %s AND answer_hash IS NOT NULL
        """
        cursor.execute(query, (term_id, question_id))
        records = cursor.fetchall()
        cursor.close()
        
        if not records:
            print(f"数据库中没有找到符合条件的数据 [term_id={term_id}, question_id={question_id}]")
            return
        
        # 转换为DataFrame并按answer_hash聚合
        import pandas as pd
        df_raw = pd.DataFrame(records)
        
        # 按answer_hash聚合数据
        processed_data = []
        for answer_hash, group in df_raw.groupby('answer_hash'):
            user_list = group['user_id'].tolist()
            first_record = group.iloc[0]
            
            user_list_str = ', '.join(str(user_id) for user_id in user_list)
            
            processed_data.append({
                'answer_hash': answer_hash,
                'user_count': len(user_list),
                'user_list': user_list_str,
                'error_info': first_record['error_info'],
                'answer_code': first_record['answer_code'],
                'term_id': first_record['term_id'],
                'question_id': first_record['question_id']
            })
        
        df = pd.DataFrame(processed_data)
        print(f"从数据库读取并聚合到 {len(df)} 条数据 [term_id={term_id}, question_id={question_id}]")
        
        # 准备多线程处理
        counters = {
            'processed': Counter(),
            'skipped': Counter(),
            'error': Counter()
        }
        
        # 记录失败的详细信息
        failed_records = []
        
        tasks = []
        for index, row in df.iterrows():
            task_args = (index, row, db_config, api_config, prompt_config, thread_config, template_config,
                        question_info, prompt_config['system_prompt_path'], ai_table_name, category_table_name)
            tasks.append(task_args)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=thread_config['max_workers']) as executor:
            future_to_index = {executor.submit(process_single_record, task): i for i, task in enumerate(tasks)}
            
            completed = 0
            for future in as_completed(future_to_index):
                completed += 1
                task_index = future_to_index[future]
                try:
                    result, status = future.result()
                    
                    if status == 'success':
                        counters['processed'].increment()
                    elif status == 'skip':
                        counters['skipped'].increment()
                    else:
                        counters['error'].increment()
                        # 记录失败的详细信息
                        failed_record = {
                            'index': task_index,
                            'answer_hash': tasks[task_index][1]['answer_hash'],
                            'status': status,
                            'error': status
                        }
                        failed_records.append(failed_record)
                        print(f"记录 {completed} (hash: {failed_record['answer_hash']}) 处理失败: {status}")
                    
                    # 每处理5个任务显示一次进度
                    if completed % 5 == 0 or completed == len(tasks):
                        print(f"进度: {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%)")
                    
                except Exception as e:
                    counters['error'].increment()
                    failed_record = {
                        'index': task_index,
                        'answer_hash': tasks[task_index][1]['answer_hash'],
                        'status': 'exception',
                        'error': str(e)
                    }
                    failed_records.append(failed_record)
                    print(f"记录 {completed} (hash: {failed_record['answer_hash']}) 处理异常: {e}")
        
        elapsed_time = time.time() - start_time
        
        # 简化的结果输出
        success_rate = counters['processed'].value/len(df)*100 if len(df) > 0 else 0
        print(f"\nAI分析完成 [term_id={term_id}, question_id={question_id}]: {counters['processed'].value}/{len(df)} ({success_rate:.1f}%)")
        print(f"耗时: {elapsed_time:.1f}秒")
        
        # 显示分类库更新信息
        if category_updates['new_subcategories']:
            print(f"新增子类别: {len(category_updates['new_subcategories'])}个")
        if category_updates['similar_rejections']:
            print(f"拒绝相似子类别: {len(category_updates['similar_rejections'])}个")
        
        # 保存详细报告到文件
        os.makedirs('data', exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        report_filename = f"data/report_{term_id}_{question_id}_{timestamp}.txt"
        
        report_lines = [
            f"AI分析报告 - {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"题目ID: {question_id}, 学期ID: {term_id}",
            f"数据来源: 数据库真实数据表",
            f"分类表: {category_table_name}",
            "",
            "=== 处理统计 ===",
            f"总记录数: {len(df)}",
            f"成功分析: {counters['processed'].value}",
            f"跳过记录: {counters['skipped'].value}",
            f"失败记录: {counters['error'].value}",
            f"成功率: {success_rate:.1f}%",
            f"处理耗时: {elapsed_time:.2f}秒",
            ""
        ]
        
        # 添加失败记录的详细信息
        if failed_records:
            report_lines.extend([
                f"=== 失败记录详情 ({len(failed_records)}个) ===",
                ""
            ])
            for record in failed_records:
                report_lines.append(f"❌ {record['answer_hash']}")
                report_lines.append(f"   索引: {record['index']}")
                report_lines.append(f"   状态: {record['status']}")
                report_lines.append(f"   错误: {record['error']}")
                report_lines.append("")
        else:
            report_lines.extend([
                "=== 失败记录详情 ===",
                "无失败记录",
                ""
            ])
        
        # 添加分类库更新记录
        report_lines.extend([
            f"=== {category_table_name} 更新记录 ===",
            ""
        ])
        
        # 主类别使用统计
        if category_updates['category_stats']:
            report_lines.append("主类别使用统计:")
            for category, count in sorted(category_updates['category_stats'].items()):
                report_lines.append(f"  {category}: {count}次")
            report_lines.append("")
        
        # 新增子类别记录
        if category_updates['new_subcategories']:
            report_lines.append(f"新增分类记录 ({len(category_updates['new_subcategories'])}个):")
            for item in category_updates['new_subcategories']:
                report_lines.append(f"  ✓ {item['category']} -> {item['subcategory']} -> {item['thirdCategory']}")
            report_lines.append("")
        else:
            report_lines.append("新增分类记录: 无")
            report_lines.append("")
        
        # 相似性拒绝记录
        if category_updates['similar_rejections']:
            report_lines.append(f"拒绝的相似子类别 ({len(category_updates['similar_rejections'])}个):")
            for item in category_updates['similar_rejections']:
                report_lines.append(f"  ✗ {item['category']} -> {item['rejected_subcategory']}")
                report_lines.append(f"    原因: {item['reason']}")
                report_lines.append(f"    已有相似: {item['similar_existing']}")
            report_lines.append("")
        else:
            report_lines.append("拒绝的相似子类别: 无")
            report_lines.append("")
        
        # 分类库优化建议
        total_new = len(category_updates['new_subcategories'])
        total_rejected = len(category_updates['similar_rejections'])
        if total_rejected > 0:
            optimization_rate = (total_rejected / (total_new + total_rejected)) * 100
            report_lines.extend([
                "=== 分类库优化效果 ===",
                f"避免重复率: {optimization_rate:.1f}%",
                f"说明: 通过相似性检查，避免了{total_rejected}个重复或相似的子类别",
                ""
            ])
        
        try:
            with open(report_filename, 'w', encoding='utf-8') as f:
                f.write("\n".join(report_lines))
            print(f"详细报告已保存: {report_filename}")
        except Exception:
            pass
        
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
    finally:
        conn.close()

def main():
    """主函数"""
    if len(sys.argv) != 3:
        print("用法: python AI_process.py <term_id> <question_id>")
        sys.exit(1)
    
    term_id = sys.argv[1]
    question_id = sys.argv[2]
    
    process_ai_analysis(term_id, question_id)

if __name__ == "__main__":
    main()