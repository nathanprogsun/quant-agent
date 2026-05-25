# Middleware 层规范

## 职责

Middleware 层负责跨切面关注点（Cross-Cutting Concerns），包含：
- **认证中间件**：从 Cookie/Header 提取用户身份
- **指标中间件**：请求/响应指标采集
- **异常处理中间件**：统一异常转换和响应格式化
- **访问控制**：基于租户的访问控制

## 目录结构

```
web/middleware/
├── __init__.py
├── auth_middleware.py       # 用户认证注入
├── metrics.py               # 指标采集
└── exception/               # 异常处理
    ├── __init__.py
    └── exception_handler.py # ApplicationError 处理器
```

## 中间件注册

在 `application.py` 中注册中间件：

```python
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from app.web.middleware.auth_middleware import AuthMiddleware
from app.web.middleware.metrics import MetricsMiddleware

app = FastAPI()
app.add_middleware(MetricsMiddleware)
app.add_middleware(BaseHTTPMiddleware.dispatch, dispatch=AuthMiddleware().dispatch)
```

## 核心中间件

### MetricsMiddleware

请求/响应指标采集：

```python
class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录请求开始时间
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        # 计算请求耗时
        duration = time.perf_counter() - start_time
        # 上报到指标系统（Prometheus/Datadog）
        
        return response
```

### AuthMiddleware

用户身份注入到请求状态：

```python
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 公开路径跳过认证
        if request.url.path in public_paths:
            return await call_next(request)
        
        # 从 Cookie 获取 token
        token = request.cookies.get("access_token")
        if token:
            payload = auth_service.decode_token(token)
            if payload:
                request.state.current_user_id = payload.get("sub")
                request.state.current_user_email = payload.get("email")
        
        return await call_next(request)
```

### ExceptionHandler

统一异常处理：

```python
async def application_error_handler(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    # 5xx 错误记录为 ERROR，4xx 记录为 WARNING
    level = Level.ERROR if exc.http_code() >= 500 else Level.WARNING
    error_response = exc.to_json_response()
    logger.opt(exception=exc).log(level, "application error", ...)
    return error_response
```

## 正确示例

### 在视图中使用 request.state

```python
# web/api/user/views.py
from fastapi import Depends, Request

@router.get("/{user_id}")
async def get_user(request: Request, user_service = Depends()):
    current_user_id = getattr(request.state, "current_user_id", None)
    # 使用 current_user_id 进行权限校验
```

### 添加新的公开路径

```python
class AuthMiddleware(BaseHTTPMiddleware):
    public_paths = {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/health",
        "/docs",
        "/openapi.json",
    }
```

### 记录结构化日志

```python
logger.opt(exc_info=exc).log(
    level,
    "application error",
    http_path=request.url.path,
    http_method=request.method,
    http_status=exc.http_code(),
    error_code=exc.error_code,
)
```

## 错误示例

```python
# ❌ 在中间件中执行数据库写操作
async def dispatch(self, request: Request, call_next):
    # 错误！中间件不应该有副作用
    await db.execute("INSERT INTO audit_log ...")

# ❌ 在中间件中处理业务逻辑
async def dispatch(self, request: Request, call_next):
    # 错误！应该在 Service 层处理
    if request.state.user_id not in allowed_users:
        raise ForbiddenError()

# ❌ 中间件中返回原始异常
async def dispatch(self, request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        return JSONResponse({"error": str(e)})  # 错误！

# ❌ 在中间件中导入业务模型
from app.core.user.types import UserDTO  # 错误！

# ❌ 遗漏异常处理
async def dispatch(self, request: Request, call_next: Callable) -> Response:
    # 错误！所有路径都应该返回 Response
    await call_next(request)
    # 没有处理异常情况
```

## 注意事项

1. **最小职责**：中间件只负责横切关注点，不处理业务逻辑
2. **避免副作用**：中间件不应该有数据库写操作等副作用
3. **性能影响**：中间件在每个请求路径上执行，避免复杂计算
4. **顺序敏感**：中间件注册顺序影响执行顺序，异常处理应最后注册
5. **公开路径**：在 AuthMiddleware 中明确列出所有不需要认证的路径
6. **日志规范**：使用结构化日志，包含请求路径、方法、状态码等字段
7. **异常处理**：通过 `exception_handler` 统一处理，不在中间件中 catch
8. **不要阻塞**：异步中间件必须使用 `await`，避免阻塞事件循环
