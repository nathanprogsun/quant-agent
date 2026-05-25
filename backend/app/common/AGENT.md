# Common 层规范

## 职责

Common 层包含整个项目共享的通用组件：
- **异常定义**：标准化的应用异常类
- **类型定义**：跨模块使用的类型系统
- **统计指标**：可观测性基础设施
- **公共工具**：可复用的辅助函数

## 目录结构

```
common/
├── __init__.py
├── error_code.py              # 错误码 StrEnum 定义
├── exception/                 # 异常定义
│   ├── __init__.py
│   └── exception.py          # 异常类
├── lifespan.py                # DI 依赖声明函数
├── stats/                    # 统计指标
│   ├── __init__.py
│   └── metric.py             # 指标定义
├── type/                     # 类型定义
│   ├── __init__.py
│   └── patch_request.py       # PATCH 请求类型
└── util.py                    # 环境判断工具函数
```

## 异常类层次结构

```
ApplicationError (ABC)
├── DatabaseError
├── ConcurrentModificationError
├── ResourceNotFoundError
├── InvalidArgumentError
├── ConflictResourceError
├── IllegalStateError
├── ServiceError
├── UnauthorizedError
├── ForbiddenError
├── ClientError
├── ExternalServiceError
├── RequestEntityTooLargeError
└── UnprocessableEntity
```

## 正确示例

### 定义新的应用异常

```python
# common/exception/exception.py
class ConcurrentModificationError(ApplicationError):
    error_code = "CONCURRENT_MODIFICATION"
    
    def http_code(self) -> int:
        return HTTPStatus.CONFLICT
```

### 使用异常

```python
# 在业务逻辑中抛出
from app.common.exception import ResourceNotFoundError

def get_user(user_id: UUID) -> User:
    user = user_repo.find(user_id)
    if not user:
        raise ResourceNotFoundError(f"User {user_id} not found")
    return user
```

### 自定义错误详情

```python
from app.common.exception import ApplicationError, ErrorDetails

raise ApplicationError(
    "Custom message",
    additional_error_details=ErrorDetails(
        code="CUSTOM_CODE",
        details="Additional context",
        reference_id="req-123"
    )
)
```

### 使用 PatchRequest 类型

```python
# common/type/patch_request.py
from app.common.type.patch_request import PatchRequest, is_unset

class UpdateUserRequest(PatchRequest[User]):
    email: EmailStr | Unset = UNSET
    name: str | Unset = UNSET

    def has_updates(self) -> bool:
        return is_unset(self.email) is False or is_unset(self.name) is False
```

## 错误示例

```python
# ❌ 直接抛出数据库异常
def get_user(user_id: UUID):
    try:
        return db.query(user_id)
    except SQLAlchemyError as e:
        raise e  # 错误！应该转换为 ApplicationError

# ❌ 在 common 层引入业务逻辑
class UserValidationError(ApplicationError):
    # 错误！common 层不应包含特定业务逻辑
    pass

# ❌ 使用过于宽泛的异常
raise Exception("Something went wrong")  # 应使用具体 ApplicationError 子类

# ❌ 在异常中包含敏感信息
raise ResourceNotFoundError(f"User password for {user_id} not found")
```

## 注意事项

1. **异常转换**：数据访问层（db/dao）必须将底层异常转换为 ApplicationError 子类
2. **错误码规范**：error_code 使用下划线分隔的全大写字母（如 `RESOURCE_NOT_FOUND`）
3. **HTTP 状态码**：确保异常子类正确映射到对应的 HTTP 状态码
4. **无业务耦合**：common 层不应包含特定业务领域的类型或异常
5. **类型可复用**：types 中的类型应该可以在多个领域间共享使用
