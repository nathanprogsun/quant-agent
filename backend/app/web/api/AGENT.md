# API 层规范

## 职责

API 层负责：
- **路由定义**：使用 FastAPI 路由装饰器定义 API 端点
- **请求验证**：使用 Pydantic schemas 验证请求数据
- **响应序列化**：将 DTO 转换为 HTTP 响应
- **依赖注入**：通过 Depends 注入 Service 层

API 层是 HTTP 世界的入口点，接收请求、调用 Service、处理响应。

## 目录结构

```
web/api/
├── __init__.py
├── deps.py                    # 依赖注入声明
├── {domain}/                  # 按领域组织
│   ├── __init__.py
│   ├── schema.py              # 请求/响应 Schema 定义
│   └── views.py               # 路由处理函数
├── auth/                      # 认证 API
│   ├── __init__.py
│   └── views.py
└── user/                      # 用户 API
    ├── __init__.py
    ├── schema.py
    └── views.py
```

## 正确示例

### 定义 Schema

```python
# web/api/user/schema.py
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.core.user.types import UserDTO


class UserResponse(BaseModel):
    """User API response schema."""
    
    model_config = {"from_attributes": True}
    
    id: UUID
    email: EmailStr
    first_name: str | None
    last_name: str | None


class PatchUserRequest(BaseModel):
    """Request schema for updating user."""
    
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
```

### 定义 Views

```python
# web/api/user/views.py
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status

from app.core.user.service.user_service import UserService
from app.core.user.types import UserCreateDTO, UserDTO, UserUpdateDTO
from app.web.api.deps import get_current_user
from app.web.api_router_ext import APIRouterExt

router = APIRouterExt()


@router.get("/me", response_model=UserDTO)
async def get_current_user_endpoint(
    current_user: UserDTO = Depends(get_current_user),
) -> UserDTO:
    """Get the current authenticated user."""
    return current_user


@router.get("/{user_id}", response_model=UserDTO)
async def get_user_by_id(
    user_id: str,
    user_service: Annotated[UserService, Depends()],
) -> UserDTO:
    """Get user by ID."""
    user = await user_service.get_by_id(user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.patch("/{user_id}", response_model=UserDTO)
async def update_user(
    user_id: str,
    data: UserUpdateDTO,
    user_service: Annotated[UserService, Depends()],
) -> UserDTO:
    """Update user information."""
    user = await user_service.update(user_id, data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
```

### 使用 APIRouterExt

```python
# web/api_router_ext.py
from fastapi import APIRouter

class APIRouterExt(APIRouter):
    """Extended APIRouter with common configurations."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            prefix="/api/v1",
            tags=["Common"],
            *args,
            **kwargs,
        )
```

## 错误示例

```python
# ❌ 在 views 中直接访问数据库
@router.get("/{user_id}")
async def get_user(user_id: UUID, engine = Depends(get_db)):
    result = await engine.one(text("SELECT * FROM users WHERE id = :id"))
    return result

# ❌ 在 views 中包含业务逻辑
@router.post("/users")
async def create_user(email: str, user_service = Depends()):
    # 错误！应该在 Service 层验证邮箱唯一性
    existing = await db.query("SELECT * FROM users WHERE email = :email")
    if existing:
        raise HTTPException(400, "Email exists")
    return await user_service.create(email)

# ❌ 缺少响应模型验证
@router.get("/{user_id}")
async def get_user(user_id: UUID):
    user = await service.get(user_id)
    return {"data": user}  # 错误！应该定义 response_model

# ❌ 直接返回数据库模型
@router.get("/{user_id}", response_model=User)  # 错误！应该返回 UserDTO
async def get_user(user_id: UUID):
    return await user_service.get_by_id(user_id)

# ❌ 处理异常不当
@router.get("/{user_id}")
async def get_user(user_id: UUID):
    try:
        return await service.get(user_id)
    except ResourceNotFoundError as e:
        raise HTTPException(400, str(e))  # 错误！应该保持 404

# ❌ 返回原始 HTTPException
@router.get("/{user_id}")
async def get_user(user_id: UUID):
    if not has_permission:
        raise HTTPException(403, "Forbidden")  # 可以，但最好使用中间件
```

## 注意事项

1. **使用 DTO**：API 层只与 DTO 交互，不直接处理 TableModel
2. **响应模型**：始终定义 `response_model`，使用 DTO 类型
3. **依赖注入**：通过 `Depends()` 注入 Service，不直接实例化
4. **异常处理**：使用 HTTPException 或在中间件中统一处理 ApplicationError
5. **路径参数验证**：使用类型注解（UUID、int 等）自动验证
6. **路由组织**：按领域组织 views.py，避免单个文件过大
7. **RESTful 规范**：遵循 HTTP 方法语义（GET/POST/PUT/PATCH/DELETE）
8. **分离 Schema**：将请求/响应 Schema 放在 schema.py 中
