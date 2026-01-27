# AI错误分析系统 - 详细使用说明

## 系统概述

AI错误分析系统是一个专门用于分析学生编程错误的智能化工具，通过AI技术对学生代码错误进行三级分类和深度分析。系统直接从MySQL数据库读取学生答题数据，经过数据聚合、AI分析等步骤，最终生成错误分类和详细的分析报告。

## 核心模块

### 1. dataProcess.py - 数据处理模块
从数据库读取学生答题记录，进行数据聚合和预处理。

**使用方法**：
```bash
python src/AIProcess/dataProcess.py <question_id> <term_id>
```

**功能**：
- 从 `code_clustering_user_answer_record` 表读取学生答题记录
- 按 `answer_hash` 聚合相同答案的用户记录
- 生成本地Excel文件供AI分析使用

### 2. AI_process.py - AI分析模块
对错误代码进行AI分析，实现三级错误分类。

**使用方法**：
```bash
python src/AIProcess/AI_process.py <term_id> <question_id>
```

**功能**：
- 调用AI API分析每个错误代码
- 实现三级分类：category → subcategory → thirdCategory
- 自动创建和维护错误分类数据库表
- 生成详细的分析报告

## 配置文件

### config.ini 完整配置
```ini
[Database]
host = 10.72.96.33
port = 3306
user = bitest
password = your_password
database = bitest

[API]
api_url = https://data.corp.hetao101.com/dc-route-api/route/v1/chat/completions
api_key = your-api-key
model = qwen-plus
temperature = 0
timeout = 30
max_retry = 3
max_workers = 8
request_delay = 0.2
analysis_timeout = 600  # AI分析总超时时间（秒）

[Prompt]
system_prompt_path = assets/system_prompt.txt
user_prompt = 题目配置：{question_info}\n\n参考答案：{standard_code}\n\n用户作答：{answer_code}\n\n错误信息：{error_info}

[DataTable]
records_table = code_clustering_user_answer_record
question_info_table = code_clustering_question_parse

[Template]
template_id = 6765
```

## 数据库表结构

### 输入表（已存在）
- **code_clustering_user_answer_record**：学生答题记录表
- **code_clustering_question_parse**：题目信息表

### 输出表（自动创建）
- **ai_{term_id}_{question_id}**：AI分析结果表
- **reusableCategory_{term_id}_{question_id}**：错误分类表

## 三级分类体系

### 分类层级
1. **category（主类别）**：语法错误、逻辑错误、其他错误
2. **subcategory（子类别）**：条件判断错误、循环结束条件错误、变量使用错误等
3. **thirdCategory（三级类别）**：更细分的错误类型

### AI分析输出格式
```json
{
  "category": "语法错误",
  "subcategory": "缺少操作符",
  "thirdCategory": "输出语句错误",
  "mark_code": "标记后的代码"
}
```

## 使用流程

### 一键运行（推荐）
```bash
python run.py 17787 77337
```

### 分步执行
```bash
# 步骤1：数据处理
python src/AIProcess/dataProcess.py 77337 17787
# 输出：数据处理完成 [term_id=17787, question_id=77337]: 168 条聚合记录, 168 个用户

# 步骤2：AI分析
python src/AIProcess/AI_process.py 17787 77337
# 输出：AI分析完成 [term_id=17787, question_id=77337]: 165/168 (98.2%)
```

## API服务

### 启动服务
```bash
python start_api.py
```

### 主要接口

#### 1. 概览数据接口
**地址**：`GET /domain/api/overview`

**返回字段**：
- `term_name`, `term_id`, `question_id`, `question_name`
- `user_count`, `record_count`
- `requirements`, `standard_code`, `unit_sequence`
- `unit_id`, `unit_template_id`, `unit_template_name`, `course_level`

#### 2. 聚类分析接口
**地址**：`POST /domain/api/clustering`

**请求参数**：
```json
{
  "term_id": "17787",
  "question_id": "77337"
}
```

**功能**：执行完整的AI错误分析流程

#### 3. 健康检查接口
**地址**：`GET /health`

## 输出文件

### Excel数据文件
**文件名**：`data/data_{term_id}_{question_id}.xlsx`
**内容**：聚合后的学生答题数据

### 分析报告
**文件名**：`data/report_{term_id}_{question_id}_{timestamp}.txt`
**内容**：详细的AI分析统计报告，包括处理统计、错误分类统计、分类库更新记录等

### 性能优化

### 多线程配置
```ini
[API]
max_workers = 8        # 建议值：CPU核心数
request_delay = 0.2    # 根据API限制调整
timeout = 30           # 单次API调用超时（秒）
analysis_timeout = 600 # AI分析总超时时间（秒）
```

### 超时时间配置
- `timeout`：单次API调用超时时间，建议30-60秒
- `analysis_timeout`：整个AI分析流程超时时间，根据数据量调整：
  - 小数据集（<500条）：300-600秒
  - 中等数据集（500-2000条）：600-1800秒  
  - 大数据集（>2000条）：1800-3600秒

### 批量处理策略
- **小数据集**（<500条）：直接处理
- **中等数据集**（500-2000条）：单次处理
- **大数据集**（>2000条）：分批处理

## 故障排除

### 常见错误及解决方案

#### 1. 数据库连接错误
```
错误: mysql.connector.errors.DatabaseError
解决: 检查config.ini中的数据库配置，确认数据库服务正在运行
```

#### 2. API调用错误
```
错误: requests.exceptions.RequestException
解决: 检查API密钥、URL和网络连接
```

#### 3. 数据表不存在
```
错误: Table 'bitest.code_clustering_user_answer_record' doesn't exist
解决: 确认数据库中存在相应的数据表
```

#### 4. 分析超时错误
```
错误: subprocess.TimeoutExpired
解决: 在config.ini中增加analysis_timeout值，或分批处理大数据集
```

#### 5. 文件权限错误
```
错误: PermissionError: Permission denied: 'data/'
解决: 确保对data目录有写权限
```

### 调试技巧

#### 分步调试
```bash
# 单独测试数据处理
python src/AIProcess/dataProcess.py 77337 17787

# 单独测试AI分析
python src/AIProcess/AI_process.py 17787 77337
```

#### 数据验证
```bash
# 检查数据库连接
python check_table_structure.py

# 验证配置文件
python -c "import configparser; c=configparser.ConfigParser(); c.read('config.ini'); print('配置文件正常')"
```

## 扩展和定制

### 自定义AI提示词
编辑 `assets/system_prompt.txt` 文件，调整AI分析的行为和输出格式。

### 添加新的数据处理步骤
在 `src/AIProcess/` 目录下添加新的处理模块。

### 扩展API接口
在 `api/app.py` 中添加新的API端点。

## 最佳实践

### 数据质量保证
- 定期检查数据库数据完整性
- 验证学生代码的有效性
- 监控AI分析结果的质量

### 性能监控
- 记录处理时间和成功率
- 监控API调用频率和响应时间
- 跟踪数据库查询性能

### 安全考虑
- 定期更新API密钥
- 限制数据库用户权限
- 保护敏感配置信息

### 维护建议
- 定期备份重要数据
- 更新依赖包版本
- 清理临时文件和日志