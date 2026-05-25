# Migrations 层规范

## 职责

Migrations 层负责：
- **数据库版本管理**：通过 Alembic 管理数据库 schema 变更
- **自动生成迁移**：支持 `alembic revision --autogenerate` 自动生成
- **离线/在线模式**：支持离线迁移和在线（async）迁移

## 目录结构

```
db/migrations/
├── __init__.py
├── env.py              # Alembic 环境配置和迁移入口
├── script.py.mako      # 迁移脚本模板
└── versions/           # 具体迁移脚本
    └── {timestamp}_{revision}_{description}.py
```

## 迁移脚本命名规范

```
{YYYY-MM-DD-HH-MM}_{short_hash}_{description}.py
```

示例：`2024-01-15-10-30_abc123_add_user_table.py`

## 正确示例

### 手动编写迁移

```python
"""Add user table

Revision ID: abc123
Revises:
Create Date: 2024-01-15 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = 'abc123'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_email', 'user', ['email'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_user_email', table_name='user')
    op.drop_table('user')
```

### 使用 auto generation

```bash
alembic revision --autogenerate -m "add user table"
```

> ⚠️ auto generation 有局限性，复杂变更（如 JSONB 列、重命名、约束）需要手动调整。

### 执行迁移

```bash
# 在线迁移（推荐）
alembic upgrade head

# 离线迁移（生成 SQL 脚本）
alembic upgrade head --sql > migration.sql

# 回滚
alembic downgrade -1
```

## Alembic 配置

### env.py 关键配置

```python
from {{cookiecutter.package_name}}.db.models import Base  # 导入 Base.metadata
from {{cookiecutter.package_name}}.settings import get_settings

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata
```

### alembic.ini

```ini
[alembic]
script_location = {{cookiecutter.package_name}}.db.migrations
prepend_sys_path = .
version_path_separator = os

[post_write_hooks]
```

## 错误示例

```python
# ❌ 在迁移中使用 ORM 模型
from {{cookiecutter.package_name}}.db.models.user import User

def upgrade():
    # 错误！迁移应该只使用 SQL 语句，不依赖应用代码
    engine.execute(User.__table__.create())

# ❌ 缺少 down_revision
revision: str = 'abc123'
down_revision: Union[str, None] = None  # ✓ 正确
# down_revision: Union[str, None] = 'xxx'  # 必须指明父版本

# ❌ 修改现有数据而不考虑回滚
def upgrade():
    op.execute("UPDATE user SET role = 'admin' WHERE email = 'admin@example.com'")
    # 错误！应该提供 down_revision 中对应的 UPDATE 回滚逻辑

# ❌ 使用 CASCADE 删除而不明确说明
def downgrade():
    op.drop_table('user', cascade=True)  # 应该先删除依赖表

# ❌ 在同一个迁移中混合多个不相关的变更
# 应该拆分为多个迁移，保持单一职责
```

## 注意事项

1. **单一职责**：每个迁移文件只包含一个逻辑变更（如只添加一个表或一个索引）
2. **幂等性**：`upgrade()` 和 `downgrade()` 都应该是幂等的
3. **down_revision`：除了初始迁移，每个迁移必须指定 `down_revision`
4. **链式管理**：迁移之间形成链式依赖，避免分叉（branch）
5. **避免 ORM**：迁移中不使用 ORM 模型，只使用原始 SQL 操作
6. **JSONB/ARRAY**：PostgreSQL 特有类型使用 `sa.JSON().with_variant(...)` 模式
7. **索引命名**：使用 `ix_{table}_{column}` 命名规范
8. **版本顺序**：文件名的时间戳不一定代表执行顺序，以 `down_revision` 链为准
9. **测试迁移**：在 CI 中验证 `upgrade` 和 `downgrade` 都能正常执行
