# Core 层规范

## 职责

Core 层是业务领域核心，包含：
- **Types**：数据传输对象（DTO）和业务类型定义
- **Service**：核心业务逻辑和用例实现

Core 层是业务规则的中心，不依赖 web 层（HTTP 框架）和 db 层（数据访问），专注于业务本身。

## 目录结构

```
core/
└── {domain}/                   # 按领域组织（user, order, product 等）
    ├── __init__.py
    ├── types.py               # DTO 定义（UserDTO, OrderDTO 等）
    └── service/               # 服务类
        ├── __init__.py
        └── {domain}_service.py  # 具体服务（user_service.py）
```

## 核心概念

### Types (DTO)

数据传输对象，用于在层之间传递数据：
- 定义 API 请求/响应的数据结构
- 与数据库模型（db/models）分离
- 包含数据转换方法

### Service

业务服务类，实现核心业务逻辑：
- 通过 Repository 接口访问数据
- 编排多个业务操作
- 不直接处理 HTTP 请求/响应

## 正确示例

### 定义 DTO

```python
# core/user/types.py
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserDTO(BaseModel):
    """User data transfer object."""

    id: str
    email: str
    username: str | None = None
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
```

### 定义 Service

```python
# core/user/service/user_service.py
from typing import Annotated

from fastapi import Depends

from app.core.user.types import UserCreateDTO, UserDTO, UserUpdateDTO
from app.db.dao.user_repository import UserRepository
from app.db.models.user import User


class UserService:
    """Service for user operations."""

    def __init__(
        self,
        user_repository: Annotated[UserRepository, Depends()],
    ):
        self.user_repository = user_repository

    async def get_by_id(self, user_id: str) -> UserDTO | None:
        """Get user by ID."""
        result = await self.user_repository.find_by_primary_key(
            table_model=User,
            id=user_id,
        )
        return UserDTO.model_validate(result) if result else None

    async def create(self, data: UserCreateDTO) -> UserDTO:
        """Create a new user."""
        result = await self.user_repository.create(data)
        return UserDTO.model_validate(result)
```

## 错误示例

```python
# ❌ 在 Service 中直接处理 HTTP 请求
class UserService:
    async def create_user(self, request: Request):  # 错误！
        user_id = request.query_params.get("id")

# ❌ 在 Service 中直接访问数据库
class UserService:
    def __init__(self, engine: DatabaseEngine):  # 错误！
        self.engine = engine
    
    async def get_user(self, user_id: UUID):
        result = await self.engine.one(text("SELECT * FROM users..."))

# ❌ 在 Types 中包含数据库细节
class UserDTO(BaseModel):
    id: UUID
    email: str
    # 错误！不应包含 internal 字段或表结构细节
    _internal_column: str = None

# ❌ Service 包含 API 相关的依赖
class UserService:
    async def create_user(
        self,
        user_id: UUID = Header(...),  # 错误！不应处理 HTTP 头部
    ):
        pass

# ❌ 业务逻辑直接放在 DTO 中
class UserDTO(BaseModel):
    def authenticate(self, password: str):  # 错误！这是业务逻辑
        return self.password_hash == hash(password)
```

## 注意事项

1. **无外部依赖**：Core 层不应直接导入 web、dbengine 等外部依赖
2. **依赖注入**：Service 通过构造函数接收依赖（使用 Depends 或手动注入）
3. **数据转换**：使用 map_from_db_obj 方法在 Models 和 DTOs 之间转换
4. **事务边界**：事务管理应在调用 Service 的上层（web 层或专用事务层）
5. **领域隔离**：不同 domain 的 Service 相互隔离，避免跨领域直接调用
6. **纯业务逻辑**：Service 中只包含业务规则和流程，不处理基础设施问题
