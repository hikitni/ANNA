# ANNA Patch 系统

> 对应原则：**P4 — 原子补丁原语（Atomic Patch Primitives）** · **P6 — 幂等操作（Idempotence）**

---

## Patch 是什么？

Patch 是 ANNA 中 AI 修改代码的**唯一推荐方式**。

传统方式（文本 diff）：
```diff
- fn activate(product: Product) -> Result<Product, ProductError> {
+ fn publish(product: Product) -> Result<Product, ProductError> {
```
问题：AI 需要知道函数的完整文本、精确位置，任何格式差异都会导致 diff 失败。

ANNA Patch 方式：
```anna
patch #ecommerce.product.activate
    @reason("产品语言统一：activate → publish")
    @author(@ai)
    @confidence(0.99)
{
    rename_to publish @cascade
}
```
AI 只需知道结构路径和操作语义，不需要知道行号或周围代码。

---

## Patch 基本结构

```anna
patch <结构路径>
    <元数据注解...>
{
    <patch 操作>
}
```

**必填元数据**：`@reason`（变更原因）  
**推荐元数据**：`@author`、`@confidence`、`@ticket`

---

## 八种 Patch 操作原语

### 1. `replace_with` — 替换节点内容

替换函数体、命名块或其他代码节点的完整内容：

```anna
patch #math.geometry.area.body
    @reason("重写实现以支持更多形状")
    @confidence(0.92)
{
    replace_with {
        intent "计算任意形状的面积"
        match shape {
            | Circle    { radius }        => Float64::PI * radius * radius
            | Rectangle { width, height } => width * height
            | Triangle  { base, height }  => 0.5 * base * height
            | Ellipse   { a, b }          => Float64::PI * a * b
        }
    }
}
```

### 2. `insert_before` / `insert_after` — 插入代码

在目标节点前后插入代码，不影响目标节点本身：

```anna
// 在函数体前插入缓存检查
patch #user.get_profile.body
    @reason("添加 Redis 缓存层，减少数据库压力")
    @confidence(0.88)
{
    insert_before {
        let cache_key = "profile:" + UInt64::to_str(user_id)
        if let Some(cached) = cache.get(cache_key) {
            return Ok(cached)
        }
    }
}

// 在函数体后插入审计日志
patch #user.update_email.body
    @reason("添加安全审计")
{
    insert_after {
        audit_log.record(AuditEvent {
            action:  "user.update_email",
            user_id: user.id,
            at:      current_timestamp(),
        })
    }
}
```

### 3. `insert_case` — 向枚举添加变体

在枚举的指定变体前后插入新变体：

```anna
patch #ecommerce.OrderStatus
    @reason("增加 Refunding 状态，支持退款流程")
    @confidence(0.96)
    @ticket("FEAT-88")
{
    insert_case after #ecommerce.OrderStatus.Shipped {
        | Refunding { requested_at: UInt64, reason: Str }
        | Refunded  { completed_at: UInt64, amount: Int64 }
    }
}
```

`insert_case` 是**幂等的**：如果变体名已存在，操作被拒绝并报告冲突，而不是重复插入。

### 4. `delete` — 删除节点

删除函数、类型、字段或常量：

```anna
patch #legacy.deprecated_helper
    @reason("函数已合并到 auth.login，不再需要独立存在")
    @ticket("REFACTOR-21")
{
    delete
}
```

`delete` 是**幂等的**：目标不存在时静默成功。

### 5. `rename_to` — 重命名

重命名函数、类型或字段，`@cascade` 控制是否同步更新所有引用：

```anna
patch #user.get_user_by_name
    @reason("统一命名：get_ 改为 find_，表示可能返回 None")
    @confidence(0.99)
{
    rename_to find_user_by_name @cascade(true)
}
```

`rename_to` 是**幂等的**：目标已经是新名称时，操作成功但无变化。

### 6. `extract_range` — 提取函数

将命名块提取为独立函数：

```anna
patch #payment.process.body
    @reason("验证逻辑复杂，提取为独立函数便于测试")
    @confidence(0.85)
{
    extract_range(block_id: "validation") into validate_payment_input
}
```

提取后，原命名块位置替换为对新函数的调用。

### 7. `inline` — 内联函数

将一个函数调用替换为其函数体（extract 的逆操作）：

```anna
patch #utils.compute_hash
    @reason("函数短小，内联消除调用开销")
{
    inline #crypto.sha256_hex
}
```

### 8. 修改参数列表

```anna
patch #api.create_order.params
    @reason("添加幂等键参数，支持安全重试")
    @confidence(0.94)
{
    add_param idempotency_key: Option<Str> = None  @position(last)
    remove_param legacy_session_id: Str
}
```

支持的参数操作：
- `add_param <name>: <type> = <default>? @position(first|last|after:<name>)`
- `remove_param <name>: <type>`
- `rename_param <old> to <new>`
- `change_param_type <name>: <old_type> => <new_type>`

### 修改字段

```anna
patch #ecommerce.Cart.fields
    @reason("Cart v2：扩展字段结构")
    @ticket("PERF-101")
{
    add_field   expires_at: Option<UInt64>
                @reason("支持购物车过期清理")
    change_type version:    UInt32 => UInt64
                @reason("高并发场景下 UInt32 存在溢出风险")
    remove_field legacy_coupon_code: Str
}
```

---

## 事务性 Patch 组（`patch_group`）

多个相关 patch 必须**同时成功或同时回滚**时，使用 `patch_group @atomic`：

```anna
patch_group
    @id("migrate-user-id-type")
    @atomic
    @reason("将用户 ID 从 Int32 升级为 Int64")
    @ticket("SCALE-42")
{
    patch #auth.User.fields {
        change_type id: Int32 => Int64
    }

    patch #auth.Session.fields {
        change_type user_id: Int32 => Int64
    }

    patch #auth.login.params {
        change_param_type user_id: Int32 => Int64
    }
}
```

若任一子 patch 失败，整组回滚，数据库和代码库保持一致性。

**不带 `@atomic` 的 `patch_group`**：各 patch 独立执行，失败的记录错误但继续后续 patch。  
适用于"尽力应用"场景，如大规模重构时的批量格式化。

---

## 条件 Patch 守卫（`@when`）

只在满足特定条件时才应用 patch：

```anna
patch #auth.login.body
    @when(project.version < "2.0.0")
    @when(#auth.login.body contains_annotation "@legacy_compat")
    @reason("v2.0 前的兼容性补丁")
{
    insert_before {
        let _ = legacy_session.migrate(user_id)
    }
}
```

支持的条件谓词：

| 谓词 | 说明 |
|------|------|
| `project.version < "x.y.z"` | 项目版本比较 |
| `#path contains "text"` | 目标节点文本包含指定内容 |
| `#path contains_annotation @annot` | 目标节点包含指定注解 |
| `#path exists` | 路径指向的节点存在 |
| `has_effect(!Effect)` | 目标函数有指定副作用 |

---

## 幂等性保证（P6）

所有 patch 操作均满足幂等性——相同 patch 施加多次与施加一次效果相同：

| 操作 | 幂等行为 |
|------|---------|
| `delete` | 目标不存在时：成功，无变化 |
| `rename_to X` | 已经是 X 时：成功，无变化 |
| `insert_case` | 变体名已存在时：报告冲突，拒绝（不重复插入）|
| `add_field` | 字段名已存在时：报告冲突，拒绝 |
| `replace_with` | 内容相同时：成功，无变化 |
| `insert_before/after` | **非幂等** — 需用命名块确保精确位置 |

对于 `insert_before/after`，建议配合条件守卫实现幂等：

```anna
patch #auth.login.body
    @when(!#auth.login.body contains_annotation "@rate_limit_added")
{
    insert_before {
        #! @rate_limit_added
        check_rate_limit(user_id)?
    }
}
```

---

## 并发控制：`@requires_state`（v1.1）

多个 AI Agent 并行工作时，patch 可能在不一致的 AST 状态上应用。  
`@requires_state` 允许在 patch 执行**前**断言目标节点的当前状态：

```anna
patch #auth.User.fields
    @requires_state("#auth.User.id == Int32")
    @reason("UserId 类型从 Int32 升级为 Int64")
    @ticket("SCALE-42")
{
    change_type id: Int32 => Int64
}
```

若目标节点当前 `id` 字段已经是 `Int64`（说明另一个 Agent 已先应用了此 patch），  
工具链拒绝重复执行并记录为"状态不符，跳过"。

常用断言格式：

| 格式 | 含义 |
|------|------|
| `"#path.field == TypeName"` | 字段类型等于指定类型 |
| `"#path exists"` | 路径指向的节点存在 |
| `"#path.variant_count == N"` | 枚举变体数量等于 N |

---

## 语义冲突与 `resolve_patch`（v1.1）

当两个 patch 产生无法自动合并的语义冲突时，系统生成 `ConflictDef` 节点：

```
[ConflictDetected] ID: conflict-20260310-001
  Target: #auth.User.fields
  Left Patch:  #patch-a  →  rename_field email => contact_email
  Right Patch: #patch-b  →  delete #auth.User.email
  描述: 左侧 patch 要重命名字段，右侧 patch 要删除同一字段，语义矛盾。
```

专门的"冲突解决 Agent"收到此节点后，执行 `resolve_patch`：

```anna
patch #conflict-20260310-001
    @reason("决策：采用删除方案，email 改由 Profile 子系统管理")
    @author(@human)
{
    resolve_patch(
        conflict_id: "conflict-20260310-001",
        resolution:  "apply_right"    // 采用 patch-b 的删除操作
    )
}
```

---

## 高级重构原语（v1.1）

### `move_to` — 跨模块迁移

将节点从当前模块剪切到目标模块：

```anna
patch #legacy.deprecated_helper
    @reason("合并到 auth 模块统一维护")
    @ticket("REFACTOR-88")
{
    move_to #auth.utils @cascade(true)
}
```

### `copy_to` — 复制到目标模块

保留原节点，在目标模块创建副本（常用于 API 版本兼容）：

```anna
patch #api.v1.create_order
    @reason("v2 API 新增 idempotency_key，v1 接口保持不变")
{
    copy_to #api.v2 new_name: create_order_v2
}
```

### `wrap_with` — 包裹函数体

用模板代码包裹函数体，`__BODY__` 占位符代表原始函数体：

```anna
patch #payment.charge
    @reason("全面添加 OpenTelemetry 追踪，不改变业务逻辑")
    @ticket("OBS-12")
{
    wrap_with {
        let _span = tracer.start("payment.charge")
        let result = { __BODY__ }
        _span.end(result.is_ok())
        result
    }
}
```

### `extract_interface` — 自动提取接口契约

基于结构体生成 trait/interface 定义，便于 Mock 和测试：

```anna
patch #payment.PaymentGateway
    @reason("提取接口，支持 Stripe/PayPal 多实现切换")
{
    extract_interface PaymentGatewayTrait
        methods: [charge, refund, get_status]
}
```

生成结果：

```anna
type PaymentGatewayTrait = {
    @interface("从 PaymentGateway 提取")

    charge:     fn(amount: Price, token: Str) -> Result<PaymentId, PaymentError>
    refund:     fn(id: PaymentId, amount: Price) -> Result<(), PaymentError>
    get_status: fn(id: PaymentId) -> Result<PaymentStatus, PaymentError>
}
```

---

## 人类审查与 LSP Diff 渲染

### 问题：结构化 Patch 序列难以直观审阅

人类工程师擅长阅读红绿平行 Diff，但 ANNA 的结构化 patch 序列对人类认知不友好：

```anna
// Reviewer 看到的：                       // Reviewer 希望看到的：
patch #auth.login.body {             │  - fn login(id: UserId, pwd: Str) -> Session {
    insert_before {                  │  -     validate(id, pwd)?  
        check_rate_limit(id)?       │  + fn login(id: UserId, pwd: Str) -> Session {
    }                                │  +     check_rate_limit(id)?  // 新增
}                                    │  +     validate(id, pwd)?
patch #auth.login {                  │  - }  
    rename_to authenticate @cascade  │  + fn authenticate(...) { ... }
}                                    │
```

### 解决方案：LSP 实时反向编译（v0.5）

**LSP 责任界面**：将 AI 提交的结构化 patch 序列，实时反向编译为人类熟悉的差异视图。

**三种视图模式**：

| 模式 | 内容 |
|------|------|
| **Patch 操作视图** | 原始 ANNA patch 序列，AI 提交与审计时参考 |
| **Human Diff 视图** | LSP 将 patch 億运算应用到 AST，展示双栏红绿 Diff |
| **影响范围地图** | 高亮所有 `@cascade` 引用变动位置 |

**交互功能**：
- AI 元数据（`@confidence`、`@reason`、`@ticket`）默认折叠到 tooltip，不占用 Diff 主界面
- Reviewer 可对单个 patch 进行‘接受 / 拒绝 / 转人审查' 操作，无需退出到 CLI
- `patch_group @atomic` 以整组为单元展示，不可傍批个接受

**实时反向编译算法**：

```
输入：PatchDef 序列 + 当前 AST 快照
  ↓
[1] 将每个 patch 应用到内存 AST，不写磁盘
  ↓
[2] 对比应用天然语言 AST 与原始 AST，提取差异节点
  ↓
[3] 将差异节点反向编译为代码文本
  ↓
输出：标准 Unified Diff 格式，可直接嵌入 PR 界面
```

这使得 ANNA 的结构化 patch 与人类审查流程**完全兼容**：  
Reviewer 审阅的是天然语言 Diff，审阅完成同时整个 ANNA Patch 厄运等内容全部记录在历史中。

