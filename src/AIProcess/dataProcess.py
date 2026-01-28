import mysql.connector
import pandas as pd
import configparser
import json
import sys

def get_database_config():
    """从config.ini读取数据库配置"""
    config = configparser.ConfigParser()
    
    # 尝试多种编码方式读取配置文件
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
    config_read = False
    
    for encoding in encodings:
        try:
            config.read('config.ini', encoding=encoding)
            config_read = True
            break
        except UnicodeDecodeError:
            continue
    
    if not config_read:
        raise Exception("无法读取config.ini文件,请检查文件编码")
    
    db_config = {
        'host': config.get('Database', 'host'),
        'port': int(config.get('Database', 'port')),
        'user': config.get('Database', 'user'),
        'password': config.get('Database', 'password'),
        'database': config.get('Database', 'database')
    }
    return db_config

def get_data_table_config():
    """从config.ini读取数据表配置"""
    config = configparser.ConfigParser()
    
    # 尝试多种编码方式读取配置文件
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
    config_read = False
    
    for encoding in encodings:
        try:
            config.read('config.ini', encoding=encoding)
            config_read = True
            break
        except UnicodeDecodeError:
            continue
    
    table_config = {
        'records_table': 'records_{term_id}_{question_id}',  # 默认值
        'question_info_table': 'question_info_{term_id}'     # 默认值
    }
    
    try:
        if config_read and 'DataTable' in config:
            table_section = config['DataTable']
            table_config['records_table'] = table_section.get('records_table', 'records_{term_id}_{question_id}')
            table_config['question_info_table'] = table_section.get('question_info_table', 'question_info_{term_id}')
    except Exception:
        pass
    
    return table_config

def process_data(term_id, question_id):
    """直接从数据库中的真实数据表读取记录"""
    db_config = get_database_config()
    table_config = get_data_table_config()
    
    # 添加字符集配置
    db_config['charset'] = 'utf8mb4'
    db_config['use_unicode'] = True
    
    conn = mysql.connector.connect(**db_config)
    
    try:
        # 使用配置中的真实表名
        records_table = table_config['records_table']  # code_clustering_user_answer_record
        
        # 检查表是否存在
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES LIKE %s", (records_table,))
        if not cursor.fetchone():
            print(f"错误: 数据表 {records_table} 不存在")
            return
        
        # 直接从真实表查询，按term_id和question_id筛选
        query = f"""
        SELECT term_id, question_id, user_id, event_time, 
               answer_url, error_info, answer_code, answer_hash
        FROM {records_table}
        WHERE term_id = %s AND question_id = %s AND answer_hash IS NOT NULL
        """
        
        print(f"从真实数据表读取: {records_table}")
        print(f"筛选条件: term_id={term_id}, question_id={question_id}")
        
        # 执行查询
        cursor.execute(query, (term_id, question_id))
        records = cursor.fetchall()
        
        # 获取列名
        column_names = [desc[0] for desc in cursor.description]
        cursor.close()
        
        if not records:
            print(f"表 {records_table} 中没有找到符合条件的有效数据")
            print(f"条件: term_id={term_id}, question_id={question_id}, answer_hash IS NOT NULL")
            return
        
        # 转换为DataFrame
        df = pd.DataFrame(records, columns=column_names)
        
        # 按answer_hash聚合数据
        processed_data = []
        total_users = len(df)
        
        for answer_hash, group in df.groupby('answer_hash'):
            user_list = group['user_id'].tolist()
            first_record = group.iloc[0]
            
            # 将user_list转换为不带单引号的字符串格式
            user_list_str = ', '.join(str(user_id) for user_id in user_list)
            
            processed_data.append({
                'answer_hash': answer_hash,
                'user_count': len(user_list),
                'user_list': user_list_str,  # 使用字符串格式而不是列表
                'error_info': first_record['error_info'],
                'answer_code': first_record['answer_code'],
                'term_id': first_record['term_id'],
                'question_id': first_record['question_id']
            })
        
        result_df = pd.DataFrame(processed_data)
        
        # 确保data目录存在
        import os
        os.makedirs('data', exist_ok=True)
        
        # 保存到Excel文件
        output_filename = f"data/data_{term_id}_{question_id}.xlsx"
        result_df.to_excel(output_filename, index=False)
        
        print(f"数据处理完成 [term_id={term_id}, question_id={question_id}]: {len(result_df)} 条聚合记录, {total_users} 个用户")
        print(f"数据已保存到: {output_filename}")
        
    except Exception as e:
        print(f"数据处理失败: {e}")
        raise
    finally:
        conn.close()

def main():
    """主函数"""
    if len(sys.argv) != 3:
        print("用法: python dataProcess.py <term_id> <question_id>")
        sys.exit(1)
    
    term_id = sys.argv[1]
    question_id = sys.argv[2]
    
    process_data(term_id, question_id)

if __name__ == "__main__":
    main()