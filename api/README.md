# API 文档

AI错误分析系统的Web接口服务。

## 启动服务

```bash
python start_api.py
# 服务地址：http://localhost:5000
```

## 接口列表

### 1. 数据概览
**地址**：`GET /domain/api/overview`

**功能**：获取系统数据统计概览

**返回示例**：
```json
{
  "success": true,
  "message": "200",
  "summary": {
    "total_terms": 5,
    "total_questions": 120,
    "total_records": 50000,
    "total_users": 8000
  },
  "data": [
    {
      "term_id": 17787,
      "question_id": "77337",
      "question_name": "第二阶段-线上-L7-1-练习5",
      "user_count": 168,
      "record_count": 168,
      "requirements": "题目要求...",
      "standard_code": "标准代码...",
      "unit_template_name": "【年课】- 趣C莫顿 - 第二阶段 - L7～L12"
    }
  ]
}
```

### 2. 聚类分析
**地址**：`POST /domain/api/clustering`

**功能**：执行完整的AI错误分析流程

**请求参数**：
```json
{
  "term_id": "17787",
  "question_id": "77337"
}
```

**返回示例**：
```json
{
  "success": true,
  "message": "聚类分析完成",
  "term_id": "17787",
  "question_id": "77337",
  "statistics": {
    "ai_records_count": 165,
    "input_users_count": 168,
    "categories_summary": {
      "语法错误": {
        "count": 85,
        "subcategories": {
          "缺少操作符": 45,
          "括号不匹配": 40
        }
      }
    }
  },
  "ai_table_data": [
    {
      "answer_hash": "abc123",
      "category": "语法错误",
      "subcategory": "缺少操作符",
      "specific_reason": "缺少<<",
      "user_ids": [1001, 1002],
      "user_count": 2
    }
  ]
}
```

### 3. 健康检查
**地址**：`GET /health`

**返回示例**：
```json
{
  "status": "healthy",
  "database": "connected",
  "message": "API服务运行正常"
}
```

## 使用示例

### Python
```python
import requests

# 获取概览数据
response = requests.get('http://localhost:5000/domain/api/overview')
data = response.json()

# 执行分析
payload = {"term_id": "17787", "question_id": "77337"}
response = requests.post(
    'http://localhost:5000/domain/api/clustering',
    json=payload,
    timeout=600
)
result = response.json()
```

### curl
```bash
# 概览数据
curl http://localhost:5000/domain/api/overview

# 聚类分析
curl -X POST http://localhost:5000/domain/api/clustering \
  -H "Content-Type: application/json" \
  -d '{"term_id": "17787", "question_id": "77337"}'
```

## 注意事项

- 聚类分析接口执行时间较长，可在config.ini中配置`analysis_timeout`参数调整超时时间
- 需要确保数据库中存在相关数据表
- 确保data目录有写入权限

## 配置说明

在`config.ini`中可配置AI分析超时时间：
```ini
[API]
analysis_timeout = 600  # 超时时间（秒），默认10分钟
```