# DBEngine 层规范

## 职责

DBEngine 层是数据库访问的核心引擎，负责：
- **连接池管理**：异步数据库连接的获取和释放
- **事务管理**：显式事务的开启、提交和回滚
- **查询执行**：提供 `execute`、`all`、`one`、`at_most_one` 等查询方法

## 目录结构

```
db/dbengine/
├── __init__.py
├── core.py            # DatabaseEngine, Connection, Transaction 核心类
└── util.py            # 引擎创建工具函数
```

## 核心类型

### DatabaseEngine

异步数据库引擎封装类：
- 内部维护 `AsyncEngine` 和任务级别的连接映射
- 通过 `begin()` 上下文管理器管理事务
- 提供 `prewarm_db_connection()` 预热连接池

**核心方法**：
| 方法 | 用途 |
|------|------|
| `begin()` | 获取事务上下文 |
| `execute()` | 执行语句并返回 Result |
| `all()` | 执行并返回所有行 |
| `at_most_one()` | 执行并返回最多一行（无则 None） |
| `one()` | 执行并返回唯一一行 |
| `first_or_none()` | 返回第一行或 None |
| `close()` | 关闭引擎，释放连接池 |

### Connection

任务级别的数据库连接封装：
- 维护引用计数，支持连接复用
- 支持嵌套的事务和查询锁
- 每个 asyncio Task 独立管理连接

### Transaction

显式事务控制器：
- 通过 `begin()` 和 `__aexit__` 管理事务生命周期
- 自动处理 commit 和 rollback
- 每个 Connection 同一时间只能有一个活跃事务

## 正确示例

### 创建和使用 DatabaseEngine

```python
from {{cookiecutter.package_name}}.db.dbengine.core import DatabaseEngine

engine = DatabaseEngine(
    url=settings.database_url,
    pool_size=20,
    max_overflow=5,
    echo=False,
)

# 预热连接池
await engine.prewarm_db_connection()
```

### 执行查询

```python
from sqlalchemy import text

# 查询单行
stmt = text("SELECT * FROM user WHERE id = :id")
row = await engine.at_most_one(stmt, parameters={"id": user_id})

# 查询多行
stmt = text("SELECT * FROM user WHERE organization_id = :org_id")
rows = await engine.all(stmt, parameters={"org_id": org_id})

# 执行插入/更新
stmt = text("""
    INSERT INTO user (id, email, created_at)
    VALUES (:id, :email, :created_at)
""")
await engine.execute(stmt, parameters={"id": uid, "email": email, "created_at": now})
```

### 使用事务

```python
async with engine.begin():
    stmt1 = text("INSERT INTO account (...) VALUES (...)")
    stmt2 = text("INSERT INTO audit_log (...) VALUES (...)")
    await engine.execute(stmt1)
    await engine.execute(stmt2)
# 自动 commit，如果抛出异常则 rollback
```

## 错误示例

```python
# ❌ 在多个 Task 间共享 Connection
async def bad_example():
    conn = await engine._connect()  # 错误！Connection 是 Task 绑定的
    result = await conn._all(...)

# ❌ 手动管理连接生命周期
conn = await engine._connect()
await conn._all(...)
await conn.__aexit__(...)  # 错误！应该使用上下文管理器

# ❌ 在事务外期望自动 commit
async def bad_example():
    stmt = text("UPDATE user SET name = :name WHERE id = :id")
    await engine.execute(stmt, ...)
# 错误！不在事务内的 execute 不会自动 commit

# ❌ 创建嵌套事务
async with engine.begin():
    async with engine.begin():  # 错误！同一引擎不能嵌套 begin
        pass
```

## 注意事项

1. **Task 绑定**：Connection 与 asyncio.Task 绑定，不能跨 Task 共享
2. **事务边界**：所有写操作必须在 `begin()` 事务上下文中执行
3. **连接池预热**：生产环境应调用 `prewarm_db_connection()` 避免冷启动延迟
4. **参数化查询**：始终使用绑定参数（`:param` 语法），防止 SQL 注入
5. **关闭顺序**：应用关闭时应先关闭 AppContext（内部调用 `engine.close()`）
6. **使用 text() SQL**：所有 SQL 必须使用 `sqlalchemy.sql.text()` 包装
7. **读写分离**：当前架构不支持读写分离，所有查询使用同一引擎
