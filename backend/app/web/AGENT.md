# Web 层规范

## 职责

Web 层是 HTTP 接口层，负责：
- **API 路由**：定义 RESTful API 端点
- **Schema**：请求/响应数据校验
- **Middleware**：跨切面关注点（认证、指标、异常处理）
- **Application**：FastAPI 应用实例化和配置

## 目录结构

```
web/
├── __init__.py
├── __main__.py              # uvicorn 启动入口
├── application.py           # FastAPI 应用工厂
├── api_router_ext.py        # APIRouterExt 扩展
├── lifespan.py              # 应用生命周期
├── lifespan_service.py      # 服务依赖工厂
├── api/                     # API 路由定义
│   ├── __init__.py
│   ├── deps.py              # 依赖注入声明
│   ├── auth/                # 认证 API
│   │   ├── __init__.py
│   │   └── views.py
│   └── user/                # 用户域 API
│       ├── __init__.py
│       ├── schema.py
│       └── views.py
└── middleware/              # 中间件
    ├── __init__.py
    ├── auth_middleware.py    # 用户认证注入
    ├── exception/           # 异常处理中间件
    │   ├── __init__.py
    │   └── exception_handler.py
    └── metrics.py           # 指标中间件
```

## 正确示例

### 定义 API 端点

```python
from app.core.user.service.user_service import UserService
from app.core.user.types import UserDTO
from app.web.api_router_ext import APIRouterExt

router = APIRouterExt()


@router.get("/{user_id}", response_model=UserDTO)
async def get_user_by_id(
    user_id: UUID,
    user_service: Annotated[UserService, Depends()],
) -> UserDTO:
    user = await user_service.get_by_id(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### 定义请求/响应 Schema

```python
class UserResponse(BaseModel):
    id: UUID
    email: str
    first_name: str | None = None
    last_name: str | None = None
```

### 异常处理中间件

```python
async def application_error_handler(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    level = Level.ERROR if exc.http_code() >= 500 else Level.WARNING
    error_response = exc.to_json_response()
    logger.opt(exception=exc).log(level, "application error", ...)
    return error_response
```

## 错误示例

```python
# ❌ 在 API 层直接操作数据库
@router.get("/{user_id}")
async def get_user(user_id: UUID, engine=Depends(get_db)):
    result = await engine.one(text("SELECT * FROM users WHERE id=:id"), ...)

# ❌ 返回原始异常给前端
@router.get("/{user_id}")
async def get_user(user_id: UUID):
    try:
        user = await service.get_by_id(user_id)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

# ❌ Schema 中包含敏感字段
class UserResponse(BaseModel):
    password_hash: str  # 错误！

# ❌ 注入 Repository 而非 Service
@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    repo: UserRepository = Depends(),  # 错误！
):
    pass
```

## 注意事项

1. **严格分层**：web 层只调用 core 层的 Service，不直接访问 db/dao
2. **依赖注入**：使用 FastAPI Depends 管理服务依赖
3. **输入校验**：使用 Pydantic schema 校验所有输入
4. **错误处理**：所有异常通过中间件统一处理，不泄漏内部细节
5. **统一响应格式**：使用标准的 JSON 响应格式
6. **无业务逻辑**：web 层不包含业务逻辑，仅做 HTTP 协议适配
