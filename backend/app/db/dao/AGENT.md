# DAO 层规范

## 职责

DAO（Data Access Object）层负责：
- **数据访问**：通过 GenericRepository 提供标准 CRUD 操作
- **查询方法**：实现特定领域的复杂查询方法
- **异常转换**：将底层数据库异常转换为 ApplicationError

DAO 层使用 `dbengine` 执行 SQL 查询，向上为 `core` 层提供服务接口。

## 目录结构

```
db/dao/
├── __init__.py
├── generic_repository.py       # 通用 CRUD 仓储基类
└── {domain}_repository.py      # 领域特定仓储
    └── user_repository.py
```

## GenericRepository 核心方法

| 方法 | 用途 |
|------|------|
| `insert()` | 插入新记录 |
| `upsert_pk()` | 基于主键的 upsert |
| `find_by_primary_key()` | 按主键查找 |
| `find_by_primary_key_or_fail()` | 按主键查找，不存在则抛异常 |
| `find_by_tenanted_primary_key()` | 按主键+租户查找 |
| `_find_by_column_values()` | 按列值查找（私有） |
| `_find_unique_by_column_values()` | 按列值查找唯一记录（私有） |
| `update_by_primary_key()` | 按主键更新 |
| `update_by_tenanted_primary_key()` | 按主键+租户更新 |
| `update_instance()` | 更新实例本身 |

## 正确示例

### 扩展 GenericRepository

```python
# db/dao/user_repository.py
from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.db.dao.generic_repository import GenericRepository
from app.db.dbengine.core import DatabaseEngine
from app.db.models.user import User


class UserRepository(GenericRepository):
    """Repository for user data access."""

    def __init__(self, *, engine: Annotated[DatabaseEngine, Depends()]):
        super().__init__(engine=engine)

    async def find_by_email(self, email: str) -> User | None:
        """Find user by email address."""
        return await self._find_unique_by_column_values(
            table_model=User,
            email=email,
        )

    async def find_active_users_by_org(
        self, organization_id: UUID
    ) -> list[User]:
        """Find all active users in an organization."""
        return await self._find_by_column_values(
            table_model=User,
            organization_id=organization_id,
            exclude_deleted_or_archived=True,
        )
```

### 使用 TableBoundedModel 进行更新

```python
from app.db.models.core.base import TableBoundedModel
from app.common.type.patch_request import UNSET

class UpdateUserRequest(TableBoundedModel[User]):
    """Model for updating user."""
    
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = UNSET

# 在 service 中使用
async def update_user(user_id: UUID, updates: UpdateUserRequest) -> User:
    return await self.repo.update_by_primary_key(
        table_model=User,
        primary_key_to_value={"id": user_id},
        column_to_update=updates,
    )
```

### 异常处理

```python
# 在 DAO 层必须转换异常
from sqlalchemy.exc import SQLAlchemyError
from app.common.exception import DatabaseError

async def get_user(self, user_id: UUID) -> User | None:
    try:
        return await self.find_by_primary_key(User, id=user_id)
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to query user: {e}") from e
```

## 错误示例

```python
# ❌ 直接返回原始 SQLAlchemy 模型到 web 层
class UserRepository(GenericRepository):
    async def find_all(self) -> list[User]:
        # 错误！应该转换为 DTO 或使用 TableModel
        return await self._find_all(User)

# ❌ 在 DAO 中包含业务逻辑
class UserRepository(GenericRepository):
    async def create_user_with_default_role(self, user: User):
        # 错误！这是业务逻辑，应该在 Service 层
        user.role = "default"
        await self.insert(user)

# ❌ 使用字符串拼接 SQL
class UserRepository(GenericRepository):
    async def search(self, query: str) -> list[User]:
        # 错误！使用参数化查询
        stmt = text(f"SELECT * FROM user WHERE name LIKE '%{query}%'")
        # SQL 注入风险！

# ❌ 不转换底层异常
class UserRepository(GenericRepository):
    async def find_by_email(self, email: str) -> User | None:
        try:
            return await self._find_unique_by_column_values(...)
        except SQLAlchemyError:
            raise  # 错误！应该转换为 ApplicationError

# ❌ 在 DAO 层处理 HTTP 响应
class UserRepository(GenericRepository):
    async def find_or_fail(self, user_id: UUID) -> User:
        result = await self.find_by_primary_key(...)
        if not result:
            raise HTTPException(status_code=404)  # 错误！

# ❌ 直接返回 Row 对象
class UserRepository(GenericRepository):
    async def find_raw(self, user_id: UUID) -> Row:
        return await self.engine.one(text("SELECT * FROM ..."))
```

## 注意事项

1. **异常转换**：所有底层异常必须在 DAO 层转换为 ApplicationError 子类
2. **参数化查询**：始终使用绑定参数，防止 SQL 注入
3. **Repository 模式**：每个领域对应一个 Repository 类
4. **私有方法**：通用查询方法使用 `_` 前缀标记为私有
5. **租户隔离**：多租户场景使用 `find_by_tenanted_primary_key` 系列方法
6. **不返回原始类型**：DAO 应返回 TableModel 实例，由上层转换为 DTO
