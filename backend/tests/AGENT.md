# Tests 层规范

## 职责

Tests 层负责：
- **单元测试**：测试单个函数/类的行为，mock 所有外部依赖
- **集成测试**：测试服务间协作、API 端点、完整业务流程

## 目录结构

```
tests/
├── __init__.py
├── conftest.py                      # 根配置（最小化）
├── unit/
│   ├── __init__.py
│   ├── conftest.py                  # unit fixtures（mock repo/service/settings）
│   ├── test_auth_service.py         # AuthService 单元测试
│   ├── test_user_service.py         # UserService 单元测试
│   └── test_auth_api_structure.py   # 路由注册、Pydantic 模型验证
└── integration/
    ├── __init__.py
    ├── conftest.py                  # integration fixtures
    ├── test_auth_flow.py            # 认证服务完整流程（注册→登录→token）
    └── test_health.py               # HTTP 端点测试（httpx.AsyncClient）
```

## 运行测试

```bash
# 运行全部测试
make test

# 仅运行单元测试
make test-unit

# 仅运行集成测试
make test-integration

# 手动运行
pytest -v --cov=app                    # 全部
pytest -v --cov=app tests/unit/        # 单元
pytest -v --cov=app tests/integration/ # 集成
```

## 测试分类标准

### 单元测试 (`tests/unit/`)

- mock 所有外部依赖（repository、service、settings）
- 测试单个类/函数的逻辑分支
- 快速，无 I/O，无网络
- 示例：`AuthService.verify_password()`、`UserService.get_by_id()`

### 集成测试 (`tests/integration/`)

- 测试多个组件协作的完整流程
- 可使用真实 HTTP 客户端（`httpx.AsyncClient` + `ASGITransport`）
- 测试端到端业务流程
- 示例：注册→哈希密码→存储→登录验证

## 测试约定

1. **文件名**：`test_{module}.py` 或 `test_{feature}_flow.py`
2. **函数名**：`test_{function}_{scenario}`
3. **异步测试**：`asyncio_mode = "auto"` 已配置，无需手动添加 `@pytest.mark.asyncio`
4. **fixtures**：按目录分层，根 conftest 保持最小化
5. **覆盖率目标**：最少 80%
6. **mock 策略**：unit 层 mock 到 repository 边界，integration 层 mock 到外部服务边界

## 注意事项

1. 单元测试之间完全独立，不共享可变状态
2. 集成测试使用 `ASGITransport` 创建真实 HTTP 客户端，不依赖网络
3. mock 外部服务，不依赖真实 API
4. 使用不可变模式：`model_copy(update={...})` 替代直接修改
5. fixture 按作用域分层：unit conftest 放 mock，integration conftest 放服务实例
