# ANNA 结构路径寻址系统

> 对应原则：**P1 — 结构优先于文本（Structure over Text）**

---

## 为什么行号是错误的抽象？

传统 AI 代码修改流程：
```
1. 读取文件，找到目标函数（假设在第 47 行）
2. 生成修改后的代码
3. 替换第 47–72 行
```

问题：
- 在步骤 1 和步骤 3 之间，任何其他修改都可能导致行号偏移
- 并发的多个 AI patch 几乎必然产生冲突
- "第 47 行" 无法表达任何语义信息

ANNA 的方案：**用语义路径代替行号**。

---

## 结构路径语法

```
#<module_path>.<TypeOrFn>.<member>.<sub_member>
```

路径以 `#` 开头，各段用 `.` 分隔，每段均为有意义的代码元素名称：

```
#auth                              → auth 模块
#auth.User                         → auth 模块中的 User 类型
#auth.User.email                   → User.email 字段
#auth.login                        → auth 模块中的 login 函数
#auth.login.params                 → login 函数的参数列表
#auth.login.params.password        → login 函数的 password 参数
#auth.login.body                   → login 函数的函数体
#auth.login.body.validation        → 函数体内名为 "validation" 的命名块
#auth.AuthError                    → AuthError 类型
#auth.AuthError.InvalidToken       → AuthError 的 InvalidToken 枚举变体
#auth.MAX_SESSION_TTL              → MAX_SESSION_TTL 常量
```

---

## 路径寻址规则

### 模块段（可省略）

路径的前几段是模块路径。如果类型/函数名在当前模块上下文唯一，可以省略前缀：

```anna
// 完整路径
patch #ecommerce.cart.add_item { ... }

// 在 ecommerce.cart 模块文件内，可简写
patch #add_item { ... }
```

### 可寻址的代码元素

| 路径结尾 | 指向 | 可用 patch 操作 |
|---------|------|----------------|
| `#mod.Fn` | 函数声明 | rename, delete, 修改签名 |
| `#mod.Fn.body` | 函数体 | replace_with, insert_before, insert_after |
| `#mod.Fn.body.blockname` | 命名块 | replace_with |
| `#mod.Fn.params` | 参数列表 | add_param, remove_param, rename_param |
| `#mod.Fn.params.name` | 单个参数 | 修改类型、默认值 |
| `#mod.Type` | 类型声明 | rename, delete |
| `#mod.Type.fields` | 结构体字段集合 | add_field, remove_field, change_type |
| `#mod.Type.Field` | 单个字段 | rename, change_type |
| `#mod.Enum.Variant` | 枚举变体 | insert_case（在其前后） |
| `#mod.CONST` | 常量 | rename, 修改值 |

---

## 命名块（`@block`）

命名块让函数内部的逻辑分区成为可寻址的节点：

```anna
fn process_order(order: Order) -> Result<Receipt, OrderError>
    !IO !Database !Network
{
    intent "处理订单的完整生命周期"

    @block("validation")         // #order.process_order.body.validation
    let validated = {
        require order.amount > 0
        require order.items.len() > 0
        require order.user_id > 0
        order
    }

    @block("inventory_check")    // #order.process_order.body.inventory_check
    let reserved = reserve_inventory(validated.items)?

    @block("payment")            // #order.process_order.body.payment
    let receipt = charge_payment(order.payment_method, order.amount)?

    @block("confirmation")       // #order.process_order.body.confirmation
    let _ = send_confirmation_email(order.user_id, receipt)?

    return Ok(receipt)
}
```

AI 可以精确替换单个块：

```anna
// 只替换库存检查逻辑，不影响其他块
patch #order.process_order.body.inventory_check
    @reason("切换到新的库存服务 API")
    @confidence(0.93)
{
    replace_with {
        let resp = inventory_service_v2.reserve(validated.items, order.id)?
        resp.reserved_items
    }
}
```

---

## 路径引用 vs 路径寻址

路径有两种用途：

### 1. 作为 patch 目标（寻址）

```anna
patch #auth.User.email { ... }     // 对 email 字段进行操作
```

### 2. 作为表达式中的引用（引用）

```anna
query {
    find type
    where references(#auth.User)   // 引用 User 类型
}

patch #module.Shape
    @when(#module.Shape.variants contains "Triangle")  // 条件中引用
{
    insert_case after #module.Shape.Triangle { ... }    // 操作中引用
}
```

---

## 路径稳定性保证

以下操作**不会使路径失效**：
- 在函数体中添加/删除语句
- 重新排列函数参数的默认值
- 修改函数体内部的表达式

以下操作**会更新路径**（带 `@cascade` 的 rename patch 自动处理）：
- `rename_to`：路径末尾的名称改变，旧路径不再有效
- `delete`：路径对应节点消失
- 移动到不同模块：路径前缀改变

---

## 路径冲突检测

当两个 patch 的目标路径重叠时，工具链报告冲突：

```
[PatchConflict] 以下两个 patch 的目标路径存在重叠：

  Patch A: #auth.login.body (replace_with)
  Patch B: #auth.login.body.validation (replace_with)

  Patch B 的目标是 Patch A 目标的子节点。
  在 Patch A 应用后，Patch B 的目标节点路径可能已变化。

  建议：先应用 Patch B，再应用 Patch A；或合并为 patch_group @atomic。
```

---

## 隐式索引寻址（v1.1）

对于高阶函数内的**匿名闭包**和**未命名块**，无需手动打 `@id` 标签。  
ANNA v1.1 提供基于文本出现顺序的隐式索引路径：

```
#module.fn/closure@N    第 N 处闭包（从 1 开始）
#module.fn/match[N]     函数体中第 N 个 match 块（从 1 开始）
#module.fn/if[N]        函数体中第 N 个 if 块
```

**示例**：

```anna
// 原函数
fn process_orders(orders: List<Order>) -> List<Result<Order, Err>> {
    orders
        .filter(|o| o.status == Active)          // closure@1
        .map(|o| validate_order(o))              // closure@2
        .map(|o| match o {                       // match[1], closure@3
            | Ok(order) => fulfill(order)
            | Err(e)    => log_error(e)
        })
}

// 只修改第 2 处闭包
patch #fulfillment.process_orders/closure@2
    @reason("validate_order 改名为 check_eligibility")
    @confidence(0.97)
{
    replace_with { |o| check_eligibility(o) }
}
```

**注意**：隐式索引在函数结构变化后（如新增闭包）会偏移，建议：
- 若闭包逻辑稳定，升级为命名块 `//! @id("block_name")`
- 若闭包是临时目标（一次性 patch），隐式索引足够

---

## 相对路径锚定（v1.1）

在极度复杂的长函数体中，支持以字符串内容为定锚点：

```anna
patch #payment.process_payment
    @reason("在信用评分检查后插入欺诈检测")
{
    insert_after block("credit_check") {
        let fraud_score = fraud_service.score(payment)?
        if fraud_score > FRAUD_THRESHOLD {
            return Err(PaymentError::FraudDetected { score: fraud_score })
        }
    }
}
```

推荐优先使用命名块（`@id`），相对路径锚定作为备选。

