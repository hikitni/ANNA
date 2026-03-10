# ANNA 模块系统与元数据

> 对应原则：**P5 — 可溯源性（Full Traceability）**

---

## 模块声明

模块是 ANNA 的代码组织单元，也是结构路径的根节点。

```anna
module auth.session
    @version("2.1.0")
    @stability(stable)
    @owner("team-platform")
    @doc("用户会话管理：创建、续期、撤销")
    @ai_context(`
        会话使用 JWT（RS256 签名），无状态存储于客户端。
        服务端维护撤销列表（Redis），TTL 与 JWT exp 对齐。
        refresh_token 有效期 30 天，access_token 有效期 15 分钟。
        所有密码使用 Argon2id 哈希，cost 参数见 anna.manifest。
    `)
{
    // 模块内容
}
```

### 模块路径规则

```
module auth                  // 顶级模块
module auth.session          // 二级模块
module ecommerce.cart.v2     // 三级模块（版本化）
```

模块路径即结构路径的前缀，`#auth.session.create` 中 `auth.session` 是模块，`create` 是函数名。

---

## 稳定性标注

```anna
@stability(stable)       // 稳定 API，遵循语义化版本
@stability(experimental) // 实验性，可能在小版本变更
@stability(deprecated)   // 已弃用，附带迁移说明
```

`deprecated` 必须配合 `@deprecated_since` 和 `@use_instead`：

```anna
module auth.legacy
    @stability(deprecated)
    @deprecated_since("1.8.0")
    @use_instead("#auth.session")
{
    // ...
}
```

工具链会在 AI 引用已弃用模块时自动给出替代路径。

---

## Import 系统

```anna
// 导入具体名称
use auth.session.{ create, refresh, revoke }

// 导入并重命名
use ecommerce.cart.{ add_item as cart_add }

// 导入全部（谨慎使用，增加 AI 推理负担）
use std.math.*

// 导入类型
use auth.{ User, Session, AuthError }
```

---

## 元数据注解系统

所有声明（模块、函数、类型、字段）均可附加注解。注解是元数据，不影响运行时行为，但参与工具链分析和 AI 决策。

### 通用注解

| 注解 | 目标 | 说明 |
|------|------|------|
| `@version("x.y.z")` | 模块 | 语义化版本 |
| `@stability(level)` | 模块、函数、类型 | stable / experimental / deprecated |
| `@owner("team")` | 模块 | 负责团队 |
| `@doc("...")` | 任何声明 | 人类可读文档 |
| `@public` | 函数、类型 | 导出为公开 API |
| `@internal` | 函数、类型 | 仅限模块内使用 |

### AI 专用注解

| 注解 | 说明 |
|------|------|
| `@ai_context(...)` | AI 理解此模块所需的架构背景 |
| `@ai_hint("...")` | 对 AI 的单条提示（不对人类显示）|
| `@no_ai_modify` | 禁止 AI 自动修改此声明（需人类审批）|

### `@ai_context` 详解

`@ai_context` 是 ANNA 中最重要的 AI 专用注解。  
它解决了一个核心问题：**架构决策通常存在于工程师的大脑和文档中，而非代码中**。

```anna
module ecommerce.payment
    @ai_context(`
        支付流程：下单 → 预授权 → 履约确认 → 结算。
        退款走独立流程，不反转原交易，避免对账混乱。
        amount 单位为分（Int64），绝不用浮点。
        第三方渠道：支付宝（优先）、微信支付、银行卡直连。
        PCI-DSS 合规：卡号不得落库，仅存 token。
        幂等键由调用方生成，格式：{user_id}-{order_id}-{timestamp}。
    `)
{
    // ...
}
```

当 AI 修改 `ecommerce.payment` 中的代码时，它会先读取 `@ai_context`，  
从而知道"为什么 amount 是 Int64"、"为什么不能存卡号"，而不是盲目地"优化"。

---

## 验证与置信度系统

### 置信度注解

AI 生成的所有代码和 patch 应附带 `@confidence` 分数：

```anna
fn compute_discount(price: Int64, rate: Probability) -> Int64 {
    intent "计算折扣后价格"
    @confidence(0.95)            // AI 对此实现有 95% 信心
    @generated_from("TASK-217")  // 生成此函数的任务 ID

    require price >= 0
    require 0.0 <= rate && rate <= 1.0
    return price - Float64::to_int(Float64::from_int(price) * rate)
}
```

### 自动审查触发

```anna
fn risky_migration(data: Vec<User>) -> Result<(), DbError>  !IO !Database {
    intent "迁移用户数据结构"
    @confidence(0.71)
    @review_required(confidence < 0.8)   // 低于 0.8 自动标记为需审查
    @review_required(has_effect(!Database))  // 涉及数据库操作强制审查

    // ...
}
```

### AI 变更标记

```anna
// patch 元数据中的完整可溯源链
patch #auth.login.body
    @author(@ai)                    // 作者：AI
    @confidence(0.88)
    @reason("修复 JWT 过期时间计算错误")
    @ticket("BUG-1024")
    @applied_at("2026-03-10T09:30:00Z")
    @verified(false)                // 尚未经人类验证
    @review_required(true)
{
    replace_with { ... }
}
```

工具链可通过查询找到所有"AI 修改但未验证"的代码：

```anna
query {
    find patch
    where has_annotation(@author) == @ai
    where has_annotation(@verified) == false
    return [target, reason, confidence, applied_at]
}
```

---

## 变更历史

`history/*.log.anna` 由工具链自动维护，记录所有 patch 的应用历史：

```anna
// history/2026-03-10.log.anna（自动生成，勿手动编辑）

log_entry @id("anna-20260310-0042") {
    patch_ref  = #auth.login.body
    operation  = "replace_with"
    author     = @ai
    confidence = 0.88
    reason     = "修复 JWT 过期时间计算错误"
    ticket     = "BUG-1024"
    applied_at = "2026-03-10T09:30:00Z"
    status     = pending_review
    diff_hash  = "sha256:a3f9c2..."
}
```
