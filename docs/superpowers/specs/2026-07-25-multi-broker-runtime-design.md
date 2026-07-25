# 多券商账户路由运行时设计

日期：2026-07-25
状态：已确认

## 1. 目标

把当前单一全局 vn.py Gateway 改造成账户驱动的多券商运行时，使中信证券和国泰海通证券能够：

1. 使用各自独立的配置、环境变量、Gateway 进程和健康状态；
2. 通过管道中已经保存的 `account_id` 选择正确券商；
3. 在 LIVE 审批时显式校验用户选择的券商；
4. 分别连接、分别熔断，单个账户故障不影响其他账户；
5. 通过同一注册表扩展后续券商，而不修改研究、风控和管道状态机。

本阶段不接入券商私有 SDK，不向真实账户发送订单。未安装授权 Gateway 的账户继续安全显示为 `API_UNAVAILABLE`。

## 2. 核心约束

- `BAGHOLDER_LIVE_ENABLED` 是平台实盘总开关，默认关闭。
- 每个账户拥有独立的账户实盘开关，默认关闭。
- 券商配置文件只保存非敏感元数据，不保存密钥、密码、令牌或服务器会话。
- Gateway 插件、插件摘要和交易节点密钥只从账户专属环境变量读取。
- LIVE 订单必须按 `account_id` 路由；禁止回退到默认 Gateway。
- 用户在 LIVE 审批时提供的券商必须与账户配置一致。
- 一个账户配置或健康检查失败时，其他有效账户仍可完成状态检查和路由。
- 测试 Gateway、摘要不匹配插件或身份不匹配插件绝不能进入 `READY`。
- LIVE 失败绝不降级为 PAPER。
- 主平台、TradingAgents 和 vn.py 继续使用三个独立 Python 3.12 环境。

## 3. 配置模型

### 3.1 券商账户配置

`config/brokers/*.json` 统一包含：

```json
{
  "account_id": "citic-main",
  "broker_code": "CITIC",
  "display_name": "中信证券",
  "currency": "CNY",
  "environment_prefix": "BAGHOLDER_CITIC_MAIN",
  "required_capabilities": [
    "live_orders",
    "cancel",
    "funds_query",
    "positions_query",
    "orders_query",
    "trades_query",
    "market_data"
  ]
}
```

国泰海通账户使用 `broker_code=GUOTAI_HAITONG` 和
`environment_prefix=BAGHOLDER_GUOTAI_HAITONG_MAIN`。

配置校验规则：

- `account_id` 必须匹配 `^[a-z0-9][a-z0-9-]{2,63}$`；
- `broker_code` 必须属于平台注册的 `BrokerCode`；
- `currency` 第一版只接受 `CNY`；
- `environment_prefix` 必须匹配 `^BAGHOLDER_[A-Z0-9_]+$`；
- 所有配置中的 `account_id` 和 `environment_prefix` 必须唯一；
- `required_capabilities` 只接受平台定义的能力名称且不能重复。

配置目录默认是 `config/brokers`，可通过
`BAGHOLDER_BROKER_CONFIG_DIR` 指向其他绝对或相对目录。

### 3.2 账户专属环境变量

平台在配置的 `environment_prefix` 后拼接固定字段。中信示例：

```text
BAGHOLDER_CITIC_MAIN_LIVE_ENABLED
BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN
BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256
BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX
BAGHOLDER_CITIC_MAIN_VNPY_PYTHON
```

国泰海通使用自己的前缀。插件和密钥变量不得出现在状态、日志、SQLite 或证据文件中。
`VNPY_PYTHON` 未设置时使用项目的 `.runtime/vnpy/Scripts/python.exe`；其他四项没有安全默认值。

旧的单账户变量：

```text
BAGHOLDER_ACCOUNT_LIVE_ENABLED
BAGHOLDER_VNPY_GATEWAY_PLUGIN
BAGHOLDER_VNPY_GATEWAY_SHA256
BAGHOLDER_TRADING_NODE_SECRET_HEX
```

不再参与运行时装配，`.env.example` 和 README 统一迁移到新变量。

## 4. 组件设计

### 4.1 BrokerConfigLoader

新建 `src/bagholder/adapters/broker/broker_config.py`，提供：

```python
@dataclass(frozen=True, slots=True)
class BrokerAccountConfig:
    account_id: str
    broker_code: BrokerCode
    display_name: str
    currency: str
    environment_prefix: str
    required_capabilities: frozenset[str]

@dataclass(frozen=True, slots=True)
class BrokerConfigurationError:
    source_file: str
    error_code: str

@dataclass(frozen=True, slots=True)
class BrokerConfigurationSet:
    accounts: tuple[BrokerAccountConfig, ...]
    errors: tuple[BrokerConfigurationError, ...]

class BrokerConfigLoader:
    def load(self, directory: Path) -> BrokerConfigurationSet: ...
```

加载器按文件名排序，独立解析每个 JSON。单个文件格式错误会生成脱敏错误记录而不是终止整个目录加载。跨文件重复账户或前缀会使所有冲突配置失效，并生成 `DUPLICATE_ACCOUNT_CONFIG` 或 `DUPLICATE_ENVIRONMENT_PREFIX`。

### 4.2 BrokerRuntimeRegistry

新建 `src/bagholder/adapters/broker/broker_runtime_registry.py`：

```python
@dataclass(frozen=True, slots=True)
class BrokerRuntimeBinding:
    config: BrokerAccountConfig
    account_live_enabled: bool
    gateway: BrokerGateway | None
    api_state: BrokerApiState
    health: dict[str, object]
    reason: str | None

class BrokerRuntimeRegistry:
    def get(self, account_id: str) -> BrokerRuntimeBinding: ...
    def bindings(self) -> tuple[BrokerRuntimeBinding, ...]: ...
    def configuration_errors(self) -> tuple[BrokerConfigurationError, ...]: ...
```

注册表构建器逐账户读取专属环境变量并创建 `SubprocessVnpyTransport`。缺少插件、摘要、密钥或 Python 路径时，该账户为 `API_UNAVAILABLE`，其他账户继续构建。

健康响应必须至少包含：

```json
{
  "status": "READY",
  "broker_code": "CITIC",
  "account_ids": ["citic-main"],
  "live_orders": true,
  "capabilities": [
    "live_orders",
    "cancel",
    "funds_query",
    "positions_query",
    "orders_query",
    "trades_query",
    "market_data"
  ],
  "reconciled": true,
  "test_plugin": false
}
```

只有以下条件全部满足才进入 `READY`：

- `status` 为 `READY`；
- `test_plugin` 明确为 `false`；
- `broker_code` 与配置一致；
- `account_ids` 包含配置账户；
- `live_orders` 为 `true`；
- 配置要求的所有能力均由健康响应声明支持。

### 4.3 账户路由执行器

新建 `AccountRoutedLiveExecutionService`，实现现有 `OrderExecutor` 接口。它从
`ExecutionRequest.proposal.account_id` 解析 `BrokerRuntimeBinding`，确认绑定为 `READY` 后，再创建或复用该账户的 `LiveExecutionService`。

路由器禁止：

- 使用第一个可用 Gateway 作为默认值；
- 账户不存在时调用任意 Gateway；
- 一个账户不可用时尝试其他账户；
- LIVE 执行失败后调用 PAPER。

执行幂等记录继续由共享 `SqlitePlatformStore` 保存，幂等键不因路由方式改变。

### 4.4 PlatformRuntime

`PlatformRuntime` 用以下字段替代单 Gateway 字段：

```python
broker_registry: BrokerRuntimeRegistry
system_live_enabled: bool
```

以下方法变为账户级：

```python
def broker_binding(self, account_id: str) -> BrokerRuntimeBinding: ...
def live_gate_context(
    self,
    account_id: str,
    *,
    interactive_confirmation: bool,
) -> LiveGateContext: ...
def live_risk_context(
    self,
    account_id: str,
    security_key: str,
) -> LiveRiskContext: ...
```

资金、持仓、能力、对账和行情事实全部来自同一账户绑定，不能混用其他 Gateway 的健康信息。

### 4.5 CLI

`bagholder status --json` 构建真实运行时状态，输出：

```json
{
  "project": "bagholder-trading-platform",
  "version": "0.1.0",
  "live_trading_enabled": false,
  "configuration_errors": [],
  "accounts": [
    {
      "account_id": "citic-main",
      "broker": "CITIC",
      "account_live_enabled": false,
      "api_state": "API_UNAVAILABLE",
      "supports_live_orders": false,
      "reason": "GATEWAY_CONFIG_INCOMPLETE"
    }
  ]
}
```

输出不得包含环境变量值、插件摘要、节点密钥、插件内部异常或原始健康响应。

`pipeline approve` 增加：

```text
--broker CITIC
--broker GUOTAI_HAITONG
```

当 `--mode LIVE` 时，`--broker` 必填。审批流程校验券商与运行中的
`account_id` 配置一致。交互确认文本包含：

```text
<broker_code> <account_id> <security_key> <side> <quantity>
```

PAPER 审批不接受也不需要 `--broker`。
如果 PAPER 审批携带 `--broker`，CLI 返回 `BROKER_NOT_ALLOWED_FOR_PAPER`。

## 5. 状态与错误处理

账户运行状态和稳定错误码：

| 条件 | API 状态 | 原因 |
|---|---|---|
| 配置有效但账户变量不完整 | `API_UNAVAILABLE` | `GATEWAY_CONFIG_INCOMPLETE` |
| Python 或节点脚本不存在 | `API_UNAVAILABLE` | `GATEWAY_RUNTIME_MISSING` |
| 插件摘要不匹配 | `API_UNAVAILABLE` | `GATEWAY_PLUGIN_HASH_MISMATCH` |
| 测试插件 | `API_UNAVAILABLE` | `TEST_GATEWAY_REJECTED` |
| 券商或账户身份不匹配 | `API_UNAVAILABLE` | `GATEWAY_IDENTITY_MISMATCH` |
| 必需能力缺失 | `API_UNAVAILABLE` | `GATEWAY_CAPABILITY_MISSING` |
| 健康请求失败 | `DISCONNECTED` | `GATEWAY_HEALTH_FAILED` |
| 所有检查通过 | `READY` | `null` |

配置目录级错误通过 `configuration_errors` 输出，错误记录只包含文件名和稳定错误码。

LIVE 审批额外错误：

- 未提供券商：`BROKER_CONFIRMATION_REQUIRED`
- 券商与账户不匹配：`BROKER_ACCOUNT_MISMATCH`
- 账户不存在：`BROKER_ACCOUNT_NOT_FOUND`
- PAPER 审批携带券商：`BROKER_NOT_ALLOWED_FOR_PAPER`

原有 `LIVE_DISABLED`、`ACCOUNT_LIVE_DISABLED`、`BROKER_API_UNAVAILABLE`、
`BROKER_CAPABILITY_MISSING`、`RECONCILIATION_REQUIRED` 和
`LIVE_CONFIRMATION_REQUIRED` 继续使用。

## 6. 数据流

```text
config/brokers/*.json
        ↓ BrokerConfigLoader
BrokerConfigurationSet
        ↓ 账户环境变量 + Gateway 健康检查
BrokerRuntimeRegistry
        ├── status：输出脱敏账户状态
        ├── pipeline run LIVE：生成账户级风控事实
        └── pipeline approve LIVE
                ↓ 校验 --broker 与 account_id
        AccountRoutedLiveExecutionService
                ↓ 只选择该账户 Gateway
        LiveExecutionService
                ↓ HMAC + 摘要 + nonce
        vn.py 私有 Gateway
```

## 7. 安全边界

- 配置加载失败关闭对应账户，不猜测默认值。
- `status` 健康检查不会提交、撤销或修改订单。
- Gateway 身份由健康响应与静态账户配置双向绑定。
- 插件名称白名单、插件文件 SHA-256、HMAC、时间窗和跨进程 nonce 保护继续保留。
- Gateway 原始异常映射为稳定错误码，不向 CLI 返回内部堆栈。
- 测试插件即使声明 `READY` 和 `live_orders=true` 仍被拒绝。
- LIVE 模式下不得调用模拟执行器。

## 8. 测试设计

### 8.1 配置测试

- 有效中信和国泰海通配置按文件名稳定加载；
- 非法 JSON、非法账户 ID、未知券商、非法前缀和未知能力被拒绝；
- 重复账户和重复环境前缀使冲突配置失效；
- 单个无效文件不阻止其他有效账户加载。

### 8.2 注册表测试

- 两个账户分别读取自己的环境变量；
- 中信 `READY` 与国泰海通 `API_UNAVAILABLE` 可以同时存在；
- 一个 Gateway 健康失败不影响另一个；
- 测试插件、身份不匹配、摘要不匹配和能力缺失不能进入 `READY`；
- 状态对象不含任何密钥或摘要值。

### 8.3 路由与 CLI 测试

- LIVE 订单只调用提案账户的 Gateway；
- 不存在或不可用账户不调用任何 Gateway；
- `--broker` 缺失或与账户不匹配时拒绝；
- 全局或账户开关关闭时不调用 Gateway；
- PAPER 审批保持原有行为；
- `status` 反映真实全局和账户开关；
- `status` 中一个账户断线不影响另一个账户显示。

### 8.4 回归验收

- 全量 pytest 通过；
- Ruff 通过；
- mypy strict 通过；
- wheel 构建通过；
- 真实公共 A 股日 K 冒烟通过；
- 中信和国泰海通未配置私有 Gateway 时均保持 `API_UNAVAILABLE`；
- 受控测试 Gateway 不产生真实订单。

## 9. 本阶段非目标

- 不接入中信或国泰海通私有 SDK；
- 不实现委托状态轮询、部分成交、撤单工作流或成交回报持久化；
- 不实现启动与重连自动对账；
- 不修改 TradingAgents 研究证据绑定；
- 不实现 pipeline 重试和恢复；
- 不建设 Web、桌面界面或常驻交易服务。

这些内容分别进入后续“实盘订单生命周期与对账”和“研究证据与运行审计”子项目。
