# Util 层规范

## 职责

Util 层提供通用工具函数和类型：
- **时间工具**：时区处理、时间格式化
- **枚举工具**：枚举定义模式
- **Pydantic 类型**：自定义 Pydantic 类型和校验器
- **验证**：参数校验工具

## 目录结构

```
util/
├── __init__.py
├── enum_util.py            # 枚举工具（NameValueStrEnum）
├── time.py                 # 时间工具（zoned_utc_now 等）
├── traceback_utils.py      # 异常格式化工具
├── validation.py           # 验证工具（not_none, one_row_only 等）
└── pydantic_types/         # 自定义 Pydantic 类型
    └── time.py             # ZoneRequiredDateTime, LocalTime 等
```

## 正确示例

### 时间工具使用

```python
from app.util.time import zoned_utc_now, zoned_utc_from_timestamp

now = zoned_utc_now()
dt = zoned_utc_from_timestamp(1700000000)
```

### 验证工具使用

```python
from app.util.validation import not_none, one_row_only

user_id = not_none(kwargs.get("user_id"), "user_id is required")
result = one_row_only(rows)
```

### 自定义 Pydantic 类型

```python
from app.util.pydantic_types.time import ZoneRequiredDateTime

class Event(BaseModel):
    name: str
    occurred_at: ZoneRequiredDateTime
```

## 错误示例

```python
# ❌ Util 函数依赖项目其他模块
from app.db.models.user import User  # 错误！

# ❌ Util 函数包含副作用
def generate_id():
    global counter  # 错误！
    counter += 1
    return counter

# ❌ 在 util 中处理业务逻辑
def is_valid_email_domain(email: str) -> bool:
    company_domains = ["company.com"]  # 错误！
    return email.split("@")[1] in company_domains

# ❌ 在 util 中访问配置
def get_db_timeout():
    from app.settings import settings  # 错误！
    return settings.db_timeout
```

## 注意事项

1. **纯函数原则**：util 函数应该是纯函数
2. **无副作用**：不要修改全局状态、写文件、网络请求
3. **无业务耦合**：util 层不应包含任何业务逻辑或领域概念
4. **类型安全**：充分利用类型注解，提供清晰的 API 签名
5. **简单优先**：工具函数应保持简单
