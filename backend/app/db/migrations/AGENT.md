# Migrations 层规范

## 职责

Migrations 层负责：
- **数据库版本管理**：通过 Alembic 管理数据库 schema 变更
- **离线/在线模式**：支持离线迁移和在线（async）迁移

## 目录结构

```
db/migrations/
├── __init__.py
├── env.py              # Alembic 环境配置和迁移入口
├── hook.py             # post_write_hook: 自动更新 latest_revision.txt
├── script.py.mako      # 迁移脚本模板
├── latest_revision.txt # 记录最近一次生成的迁移文件名（由 hook 自动维护）
└── versions/           # 具体迁移脚本
    └── {timestamp}_{revision}.py
```

## 迁移脚本命名规范

```
{YYYY-MM-DD-HH-MM-SS}_{short_hash}.py
```

示例：`2026-05-26-14-49-21_a0f9617d90dd.py`

## Migration Generation

```bash
# Create a new migration script locally
alembic revision -m "Create account table"

# For automatic change detection (需要本地 DB 运行)
alembic revision --autogenerate -m "add user table"

# For empty file generation
alembic revision
```

> ⚠️ 本项目使用 `TableModel`（Pydantic）+ raw SQL，不使用 SQLAlchemy ORM mapping，
> 因此 `--autogenerate` 无法检测模型变更，需要手写 SQL。

## 执行迁移

```bash
# 执行所有待执行的迁移
alembic upgrade "head"

# 执行到指定 revision
alembic upgrade "<revision_id>"
```

## 回滚迁移

```bash
# 回滚到指定 revision
alembic downgrade <revision_id>

# 回滚全部
alembic downgrade base
```

## 手动编写迁移示例

```python
"""Add user table

Revision ID: abc123
Revises:
Create Date: 2026-05-26 14:49:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "abc123"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")
```

## alembic.ini 配置

```ini
[alembic]
script_location = app/db/migrations
prepend_sys_path = .
file_template = %%(year)d-%%(month).2d-%%(day).2d-%%(hour).2d-%%(minute).2d-%%(second).2d_%%(rev)s
version_path_separator = os

[post_write_hooks]
hooks = black,touch_latest_alembic_revision
touch_latest_alembic_revision.type = console_scripts
touch_latest_alembic_revision.entrypoint = touch_latest_alembic_revision
touch_latest_alembic_revision.options = REVISION_SCRIPT_FILENAME
black.type = console_scripts
black.entrypoint = black
black.options = REVISION_SCRIPT_FILENAME
```

> `hooks` key 必须在 `[post_write_hooks]` section 内（不是 `[alembic]`），否则 hook 不会执行。

## 注意事项

1. **手写 SQL**：本项目使用 Pydantic TableModel + raw SQL，迁移中直接写 DDL
2. **单一职责**：每个迁移文件只包含一个逻辑变更
3. **down_revision**：除了初始迁移，每个迁移必须指定 `down_revision`
4. **链式管理**：迁移之间形成链式依赖，避免分叉（branch）
5. **索引命名**：使用 `ix_{table}_{column}` 命名规范
6. **版本顺序**：以 `down_revision` 链为准，文件名时间戳不代表执行顺序
7. **latest_revision.txt**：由 `touch_latest_alembic_revision` hook 自动维护，无需手动编辑
