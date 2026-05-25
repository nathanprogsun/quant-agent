# Models 层规范

## 职责

Models 层负责：
- **数据库模型定义**：使用 Pydantic + SQLAlchemy 风格的列定义
- **表结构元数据**：表名、主键、列类型等
- **数据转换**：提供与数据库行（Row）之间的转换方法

Models 层是数据访问的边界，与 SQLAlchemy Row 互转是核心能力。

## 目录结构

```
db/models/
├── __init__.py
├── {domain}.py              # 领域模型（user.py, order.py）
└── core/                     # 模型基类
    ├── __init__.py
    └── base.py               # TableModel, SysTableModel, Column 定义
```

## 模型类型层次

```
DBModel (BaseModel)
└── TableModel                  # 所有数据库表模型的基类
    ├── SysTableModel           # 框架管理的系统表（含 id UUID + sys_updated_at）
    │   └── {ManagedModel}      # 由框架管理 id/sys_updated_at 的业务模型
    ├── {DomainModel}            # 普通业务表模型（直接继承 TableModel）
    └── TableBoundedModel       # PATCH 等操作模型
```

## 列类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `Column[T]` | 普通列 | `id: Column[UUID]` |
| `JsonColumn[T]` | JSONB 列 | `metadata: JsonColumn[dict]` |
| `ArrayColumn[T]` | 数组列 | `tags: ArrayColumn[str]` |

## 正确示例

### 定义普通业务模型（继承 TableModel）

```python
# db/models/organization.py
from uuid import UUID

from app.db.models.core.base import Column, TableModel


class Organization(TableModel):
    """Organization table model.

    Inherits from TableModel directly — does NOT need sys_updated_at.
    """

    table_name = "organization"
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    name: Column[str]
```

### 定义框架管理系统模型（继承 SysTableModel）

SysTableModel 提供 `id: Column[UUID]` 和 `sys_updated_at` 字段，由框架自动管理。

```python
# db/models/audit_log.py
from uuid import UUID

from app.db.models.core.base import Column, SysTableModel


class AuditLog(SysTableModel):
    """Audit log — system-managed table with id and sys_updated_at."""

    table_name = "audit_log"
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    action: Column[str]
    entity_type: Column[str]
    entity_id: Column[str]
```

### 定义带 JSONB 的模型

```python
# db/models/config.py
from typing import Any
from uuid import UUID

from app.db.models.core.base import Column, JsonColumn, SysTableModel


class Config(SysTableModel):
    """Configuration table with JSONB metadata."""

    table_name = "config"
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    name: Column[str]
    metadata: JsonColumn[dict[str, Any]]  # PostgreSQL JSONB
```

### 处理 PostgreSQL 关键字表名（如 user）

`user` 是 PostgreSQL 保留关键字，使用时需：

```python
# db/models/user.py
from app.db.models.core.base import Column, TableModel


class User(TableModel):
    """User table model.

    Note: Inherits from TableModel (not SysTableModel) because the user
    table does not have sys_updated_at, and uses a string id instead of UUID.
    """

    table_name = "user"
    ordered_primary_keys = ("id",)

    id: Column[str]
    email: Column[str]
    username: Column[str | None] = None
    hashed_password: Column[str]
    is_active: Column[bool] = True
    created_at: Column[datetime]
```

在 DAO 层引用时，`user` 表名需要双引号：

```python
stmt = text('SELECT * FROM "user" WHERE email = :email')
```

### 使用 TableBoundedModel

```python
from app.db.models.core.base import TableBoundedModel
from app.db.models.user import User
from app.common.type.patch_request import UNSET, Unset


class UpdateUserRequest(TableBoundedModel[User]):
    """Model for updating user via PATCH."""

    first_name: str | Unset = UNSET
    last_name: str | Unset = UNSET
    phone_number: str | Unset = UNSET
```

## 错误示例

```python
# ❌ 普通业务表不该继承 SysTableModel（除非确实需要 sys_updated_at）
class Organization(SysTableModel):
    table_name = "organization"
    ordered_primary_keys = ("id",)
    id: Column[UUID]
    name: Column[str]
    # sys_updated_at 被自动添加但数据库表里没有此列，需要额外的 override

# ❌ 主键定义错误
class User(SysTableModel):
    table_name = "user"
    ordered_primary_keys = ("id", "email")  # 错误！id 已由 SysTableModel 提供
    email: Column[str]

# ❌ 使用错误的列类型
class User(SysTableModel):
    table_name = "user"
    ordered_primary_keys = ("id",)
    id: Column[UUID]
    data: dict  # 错误！应用 JsonColumn[dict]
    items: list[str]  # 错误！应用 ArrayColumn[list[str]]

# ❌ 在模型中包含业务方法
class User(SysTableModel):
    table_name = "user"
    ordered_primary_keys = ("id",)
    id: Column[UUID]
    def authenticate(self, password: str):  # 错误！这是业务逻辑
        return hash(self.password_hash) == hash(password)

# ❌ 缺少 table_name
class User(SysTableModel):
    table_name = "users"  # 应该是 "user"
    ordered_primary_keys = ("id",)
    id: Column[UUID]

# ❌ PostgreSQL 关键字表名未引号包裹
stmt = text("SELECT * FROM user WHERE id = :id")  # 错误！user 是关键字
stmt = text('SELECT * FROM "user" WHERE id = :id')  # 正确
```

## 注意事项

1. **选择正确的基类**：不需要 `sys_updated_at` 的业务表继承 `TableModel`，需要框架自动管理 `id` 和 `sys_updated_at` 的表继承 `SysTableModel`
2. **主键定义**：`ordered_primary_keys` 必须定义，且字段必须在模型中声明
3. **列类型注解**：使用 `Column[T]`、`JsonColumn[T]`、`ArrayColumn[T]` 标记列
4. **模型不可实例化**：通过设置 `is_base_table = True` 在 TableModel 层防止直接实例化
5. **数据转换**：使用 `from_row()` 方法从数据库行创建模型实例
6. **只读属性**：在模型中只定义计算属性，不包含业务逻辑
7. **冻结模型**：使用 `frozen=True` 确保模型实例不可变
8. **PostgreSQL 关键字**：`user`、`order` 等保留关键字作表名时，SQL 查询中用双引号包裹
