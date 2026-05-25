# App Context 层规范

## 职责

App Context 层是应用级别的上下文容器，负责：
- **生命周期管理**：管理应用级别资源的创建和销毁
- **服务容器**：通过 `LifeSpanService` 提供应用级单例服务
- **核心依赖**：存储数据库引擎、HTTP 客户端等核心依赖

## 目录结构

```
app_context/
├── __init__.py
└── app_context.py           # AppContext 和 LifeSpanService 定义
```

## 核心类型

### AppContext

应用上下文容器，持有：
- `main_db: DatabaseEngine` — 主数据库引擎
- `http_aclient: AsyncClient` — 异步 HTTP 客户端
- `lifespan_service: LifeSpanService` — 应用级服务容器

**特点**：
- 使用 `frozen=True` 的 dataclass，确保不可变性
- 存储在 `app.state.app_context` 中供依赖注入使用
- 提供 `close()` 方法统一释放所有资源

### LifeSpanService

应用级服务容器，用于存放单例服务实例：
- 通过 `Depends` 在路由处理函数中注入
- 添加新服务时作为 frozen 字段添加

## 正确示例

### 在应用启动时创建 AppContext

```python
# web/lifespan.py
from contextlib import asynccontextmanager

from httpx import AsyncClient

from {{cookiecutter.package_name}}.app_context.app_context import AppContext
from {{cookiecutter.package_name}}.db.dbengine.core import DatabaseEngine

async def lifespan_setup() -> AppContext:
    engine = DatabaseEngine(url=settings.database_url)
    http_aclient = AsyncClient()
    return AppContext(
        main_db=engine,
        http_aclient=http_aclient,
        lifespan_service=LifeSpanService(),
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    app_context = await lifespan_setup()
    app.state.app_context = app_context
    yield
    await app_context.close()
```

### 依赖注入获取数据库引擎

```python
# web/api/deps.py
from {{cookiecutter.package_name}}.app_context.app_context import AppContext

def get_db_engine(app_context: AppContext = Depends(get_app_context)) -> DatabaseEngine:
    return app_context.main_db
```

### 在 LifeSpanService 中添加新服务

```python
@dataclasses.dataclass(frozen=True)
class LifeSpanService:
    """Application service container."""
    
    cache_service: CacheService | None = None  # 添加新服务
```

## 错误示例

```python
# ❌ 在 AppContext 中存储可变状态
@dataclasses.dataclass
class AppContext:
    request_count: int = 0  # 错误！应该使用不可变数据结构

# ❌ 在启动后修改 AppContext
app_context.main_db = new_engine  # 错误！

# ❌ 直接实例化服务而不通过依赖注入
class MyService:
    def __init__(self):
        self.engine = DatabaseEngine(url=settings.db_url)  # 错误！
```

## 注意事项

1. **不可变性**：AppContext 和 LifeSpanService 必须使用 `frozen=True`
2. **资源清理**：确保 `close()` 方法释放所有持有的资源
3. **依赖注入**：通过 FastAPI 的 `Depends` 获取 AppContext 中的依赖
4. **无业务逻辑**：App Context 层只负责资源管理，不包含任何业务逻辑
5. **单例模式**：LifeSpanService 中的服务应该是应用级单例
