# DB 层规范

## 职责

DB 层负责数据访问，包含：
- **Models**：数据库表模型定义（SQLAlchemy 映射）
- **DAO**：数据访问对象，封装 CRUD 操作
- **DBEngine**：数据库引擎和连接管理
- **Migrations**：数据库迁移管理

## 目录结构

```
db/
├── __init__.py
├── dao/                    # 数据访问对象
│   ├── __init__.py
│   ├── generic_repository.py  # 通用 CRUD 仓库
│   └── user_repository.py    # 用户仓库示例
├── models/                 # 数据库模型
│   ├── __init__.py
│   ├── core/              # 模型基类
│   │   ├── __init__.py
│   │   └── base.py       # DBModel, TableModel 等基类
│   └── user.py            # 用户模型示例
├── dbengine/              # 数据库引擎
│   ├── __init__.py
│   ├── core.py            # DatabaseEngine 核心
│   └── util.py            # 引擎工具函数
└── migrations/            # 数据库迁移
    ├── __init__.py
    ├── env.py
    ├── script.py.mako
    └── versions/

## 核心类型

- **DBModel**：数据库模型基类，提供 `from_row` 方法
- **TableModel**：带表元数据的模型基类，提供 `table_name`, `fq_table_name` 等
- **SysTableModel**：继承 TableModel，额外提供 `id` 和 `sys_updated_at` 字段（框架自动管理时间戳）
- **GenericRepository**：通用 CRUD 仓库基类
- **DatabaseEngine**：数据库引擎，封装连接和事务管理

## 正确示例

### 定义数据库模型

选择正确的基类：
- 需要框架自动管理 `id` 和 `sys_updated_at` 的表 → 继承 `SysTableModel`
- 普通业务表 → 直接继承 `TableModel`

```python
# 普通业务表（继承 TableModel）
from app.db.models.core.base import Column, TableModel


class User(TableModel):
    """User table model.

    Note: Inherits TableModel (not SysTableModel) because the user table
    does not have sys_updated_at. Also, "user" is a PostgreSQL reserved
    keyword — always quote it in raw SQL: FROM "user".
    """

    table_name = "user"
    ordered_primary_keys = ("id",)

    id: Column[str]
    email: Column[str]
    created_at: Column[datetime]

    first_name: Column[str | None] = None
    last_name: Column[str | None] = None
    phone_number: Column[str | None] = None
    organization_id: Column[UUID | None] = None
```

### 定义 Repository

```python
from app.common.exception import ConflictResourceError
from app.db.dao.generic_repository import GenericRepository
from app.db.models.user import User


class UserRepository(GenericRepository):
    async def find_by_email(self, email: str) -> User | None:
        stmt = text('SELECT * FROM "user" WHERE email = :email').bindparams(email=email)
        row = await self.engine.at_most_one(stmt)
        return User.from_row(row) if row else None

    async def create(self, user: User) -> User:
        existing = await self.find_by_email(user.email)
        if existing:
            raise ConflictResourceError(f"Email already registered: {user.email}")
        return await self.insert(user)
```

### 使用 GenericRepository 通用方法

```python
user = await repo.find_by_primary_key(User, id=user_id)

updated = await repo.update_by_primary_key(
    User,
    primary_key_to_value={"id": user_id},
    column_to_update={"first_name": "NewName"},
)

user = await repo.find_by_tenanted_primary_key(
    User, organization_id=org_id, id=user_id,
)
```

## 错误示例

```python
# ❌ 在 Model 中包含业务逻辑
class User(SysTableModel):
    def validate_password(self, password: str) -> bool: ...

# ❌ 直接使用 SQLAlchemy 原始异常
async def create(self, user):
    try:
        return await self.insert(user)
    except IntegrityError:  # 错误！
        raise

# ❌ Repository 中使用 ORM session
class UserRepository:
    async def find(self, id):
        async with Session() as session: ...

# ❌ 在 DAO 中做业务验证
async def create(self, user):
    if not user.email.endswith("@company.com"):  # 错误！
        raise ValueError("Invalid email domain")
    return await self.insert(user)
```

## 注意事项

1. **使用 text() SQL**：所有查询使用原生 SQL text 语句，不使用 ORM 查询构建器
2. **JSONB 列处理**：JSONB 列需要使用 bindparam 和 JSONB type 绑定
3. **软删除**：支持 deleted_at/archived_at 的软删除模式
4. **异常转换**：DAO 层必须将数据库异常转换为 ApplicationError 子类
5. **租户隔离**：通过 organization_id 字段实现租户数据隔离
6. **不可变性**：所有模型实例不可变，更新操作返回新实例
