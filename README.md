# AI错误分析系统

基于AI的学生编程错误智能分析工具，实现错误代码的三级分类和教学数据统计。

## 核心功能

- **三级错误分类**：category → subcategory → thirdCategory
- **数据库集成**：从MySQL读取学生答题数据，按answer_hash聚合
- **AI分析**：调用大语言模型API进行错误分类
- **API服务**：提供数据概览和分析接口
- **动态分类库**：自动维护和更新错误分类体系

## 快速开始

### 1. 环境配置
```bash
pip install -r requirements.txt
python setup.py
cp config.ini.example config.ini
# 编辑config.ini填入数据库和API配置

# 测试配置文件
python test_config.py
```

### 2. 运行分析
```bash
# 完整分析流程
python run.py <term_id> <question_id>

# 示例
python run.py 17787 77337
```

### 3. API服务
```bash
python start_api.py
# 服务地址：http://localhost:5000
```

## 主要模块

### 数据处理 (dataProcess.py)
- 从`code_clustering_user_answer_record`表读取数据
- 按`answer_hash`聚合相同答案的用户记录
- 输出Excel文件供后续分析使用

### AI分析 (AI_process.py)
- 直接从数据库读取并聚合数据（不依赖Excel文件）
- 调用AI API分析错误代码
- 实现三级分类并存储到`ai_{term_id}`表（按question_id筛选）
- 维护`reusableCategory_{term_id}`分类库（按question_id筛选）
- 生成详细分析报告

### API服务 (api/app.py)
- `GET /domain/api/overview` - 数据概览统计
- `POST /domain/api/clustering` - 执行完整分析流程
- `GET /health` - 服务健康检查

## 配置文件

```ini
[Database]
host = your_host
user = your_user
password = your_password
database = your_database

[API]
api_url = https://your-api-endpoint.com/v1/chat/completions
api_key = your-api-key
model = qwen-plus
max_workers = 8
analysis_timeout = 600  # AI分析超时时间（秒）

[DataTable]
records_table = code_clustering_user_answer_record
question_info_table = code_clustering_question_parse
```

## 输出结果

### 数据库表
- `ai_{term_id}` - AI分析结果（包含question_id字段用于筛选）
- `reusableCategory_{term_id}` - 错误分类库（包含question_id字段用于筛选）

### 文件输出
- `data/data_{term_id}_{question_id}.xlsx` - 聚合数据
- `data/report_{term_id}_{question_id}_{timestamp}.txt` - 分析报告

## 使用示例

```bash
# 命令行分析
python run.py 17787 77337

# 输出示例：
开始执行AI错误分析 [term_id=17787, question_id=77337]

步骤1: 数据处理 [term_id=17787, question_id=77337]: python src/AIProcess/dataProcess.py 17787 77337
数据处理完成 [term_id=17787, question_id=77337]: 168 条聚合记录, 168 个用户
✅ 步骤1: 数据处理 执行成功 [term_id=17787, question_id=77337] (3.47秒)

步骤2: AI分析 [term_id=17787, question_id=77337]: python src/AIProcess/AI_process.py 17787 77337
AI分析开始 [term_id=17787, question_id=77337]
AI分析完成 [term_id=17787, question_id=77337]: 165/168 (98.2%)
耗时: 89.5秒
✅ 步骤2: AI分析 执行成功 [term_id=17787, question_id=77337] (89.5秒)

✅ 所有步骤执行完成 [term_id=17787, question_id=77337]

# API调用
curl http://localhost:5000/domain/api/overview
curl -X POST http://localhost:5000/domain/api/clustering \
  -H "Content-Type: application/json" \
  -d '{"term_id": "17787", "question_id": "77337"}'
```

## 故障排除

- **数据库连接失败**：检查config.ini数据库配置
- **API调用失败**：验证API密钥和网络连接  
- **表不存在**：确认数据库中存在相应数据表
- **分析超时**：调整config.ini中的`analysis_timeout`参数

### 超时配置建议
- 小数据集（<500条）：`analysis_timeout = 300`
- 中等数据集（500-2000条）：`analysis_timeout = 600`  
- 大数据集（>2000条）：`analysis_timeout = 1800`

详细说明请参考 [USAGE.md](USAGE.md) 和 [api/README.md](api/README.md)。