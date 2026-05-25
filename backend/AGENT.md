# {{cookiecutter.project_slug}} 项目架构规范

## 概述

{{cookiecutter.project_slug}} 是一个基于 FastAPI + SQLAlchemy 的分层架构后端项目，遵循领域驱动设计（DDD）原则。

## 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                           web/                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   api/      │  │ middleware/ │  │  application.py     │ │
│  │  (路由)     │  │ (认证/指标) │  │        (FastAPI)    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                       app_context/                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              AppContext / 依赖容器                    │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                           core/                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         {domain}/service/ 和 types.py               │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                           db/                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │    dao/     │  │   models/   │  │     dbengine/       │ │
│  │  (数据访问)  │  │ (数据库模型) │  │    (数据库引擎)      │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐                                            │
│  │  migrations/│                                            │
│  │ (数据库迁移)  │                                           │
│  └─────────────┘                                            │
├─────────────────────────────────────────────────────────────┤
│                          common/                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ exception/  │  │   stats/    │  │      type/          │ │
│  │  (异常定义)  │  │   (统计)    │  │   (类型定义)         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                           util/                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   time.py   │  │ enum_util   │  │  pydantic_types/    │ │
│  │  (时间工具)  │  │ (枚举工具)   │  │   (Pydantic类型)    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ validation/ │  │ asyncio_util│  │  traceback_utils    │ │
│  │  (验证工具)  │  │ (异步工具)   │  │   (堆栈追踪)        │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 层级职责

| 层级 | 目录 | 职责 | AGENT.md |
|------|------|------|----------|
| **web** | `web/` | API 层，处理 HTTP 请求/响应、中间件 | `{{cookiecutter.package_name}}/web/AGENT.md` |
| **app_context** | `app_context/` | 应用生命周期管理和依赖容器 | `{{cookiecutter.package_name}}/app_context/AGENT.md` |
| **core** | `core/{domain}/` | 业务领域层，核心业务逻辑和服务 | `{{cookiecutter.package_name}}/core/AGENT.md` |
| **db** | `db/` | 数据访问层，包含 DAO、Models、Migrations | `{{cookiecutter.package_name}}/db/AGENT.md` |
| **common** | `common/` | 通用组件，异常、错误码、统计、类型 | `{{cookiecutter.package_name}}/common/AGENT.md` |
| **util** | `util/` | 工具函数，时间、枚举、类型定义 | `{{cookiecutter.package_name}}/util/AGENT.md` |

## 核心域（core）

`core/` 包含以下业务域示例：
- `user` — 用户管理
- `auth` — 认证授权

## 数据流向

```
HTTP Request
    ↓
web/api/views.py (接收请求、Schema 验证)
    ↓
core/{domain}/service/*.py (业务逻辑)
    ↓
db/dao/*.py (数据访问)
    ↓
db/dbengine/core.py (数据库引擎)
    ↓
PostgreSQL Database
```

## 目录结构

```
{{cookiecutter.package_name}}/
├── app_context/                 # 应用上下文容器
│   └── app_context.py
├── common/                      # 通用层
│   ├── error_code.py            # 错误码定义
│   ├── exception/               # 异常类定义
│   ├── lifespan.py              # DI 依赖声明
│   ├── stats/                   # 统计指标
│   ├── type/                    # 通用类型
│   └── util.py                  # 环境工具函数
├── core/                        # 业务领域层
│   ├── auth/                    # 认证域
│   │   ├── types.py             # DTO 定义
│   │   └── service/             # 服务类
│   └── user/                    # 用户域
│       ├── types.py             # DTO 定义
│       └── service/             # 服务类
├── db/                          # 数据访问层
│   ├── dao/                     # 数据访问对象
│   ├── models/                  # 数据库模型
│   │   └── core/                # 模型基类
│   ├── dbengine/                # 数据库引擎
│   └── migrations/              # 数据库迁移
├── util/                        # 工具函数
│   ├── asyncio_util/            # 异步工具
│   ├── enum_util.py             # 枚举工具
│   ├── pydantic_types/          # Pydantic 类型
│   ├── time.py                  # 时间工具
│   ├── traceback_utils.py       # 堆栈追踪工具
│   └── validation.py            # 验证工具
└── web/                         # API 层
    ├── api/                     # API 路由
    ├── middleware/               # 中间件
    ├── application.py           # 应用入口
    ├── __main__.py              # 启动入口
    ├── api_router_ext.py        # 路由扩展
    ├── lifespan.py              # 生命周期管理
    └── lifespan_service.py      # 服务工厂
```

## 正确示例

### 层级调用顺序

```python
# web/api/user/views.py
from {{cookiecutter.package_name}}.core.user.service.user_service import UserService

@router.get("/{user_id}", response_model=UserDTO)
async def get_user(user_id: UUID, service: UserService = Depends()):
    return await service.get_user(user_id)

# core/user/service/user_service.py
from {{cookiecutter.package_name}}.db.dao.user_repository import UserRepository

class UserService:
    def __init__(self, user_repository: UserRepository = Depends()):
        self.user_repo = user_repository

    async def get_user(self, user_id: UUID) -> UserDTO | None:
        return await self.user_repo.find_by_primary_key(User, id=user_id)
```

## 错误示例

```python
# ❌ 在 web 层直接访问数据库
@router.get("/{user_id}")
async def get_user(user_id: UUID, engine = Depends(get_db)):
    result = await engine.one(text("SELECT * FROM users WHERE id = :id"), ...)
    return result

# ❌ 在 core 层直接处理 HTTP 请求
class UserService:
    def get_user(self, request: Request):  # 错误！
        return request.query_params.get("id")

# ❌ 在 core 层直接调用外部 API
class UserService:
    async def create_user(self, user_data):
        async with httpx.AsyncClient() as client:  # 错误！应通过 Service 层封装
            await client.post("https://api.example.com/users", json=user_data)
```

## 注意事项

1. **单向依赖原则**：web → core → db，只能上层依赖下层
2. **禁止跨层调用**：web 层不应直接访问 db/dao
3. **使用依赖注入**：通过 FastAPI Depends 管理服务依赖
4. **遵循领域划分**：每个 domain 是独立的业务边界
5. **异常处理**：使用 common/exception 中的异常类，不抛原始 DB 异常
6. **模型不可变**：所有模型实例不可变，更新操作返回新实例
7. **输入校验**：所有输入通过 Pydantic Schema 验证
8. **日志规范**：使用结构化日志，统一 app_logging 工具
