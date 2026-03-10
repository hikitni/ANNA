# ANNA 契约系统

> 对应原则：**P2 — 意图与实现并列（Intent ≡ Implementation）**

---

## 契约是一等公民

在传统语言中，函数的"意图"存在于：
- 注释（可选，不被验证，会过时）
- 文档（与代码分离，AI 难以关联）
- 测试（测试覆盖范围有限，无法表达完整语义）

在 ANNA 中，契约与实现**同等地位**：

```anna
fn transfer(from: Account, to: Account, amount: Int64) -> Result<(Account, Account), TransferError>
    !IO !Database
{
    intent "在两个账户间转账，保证金额守恒"           // 语义意图（AI 优先读取）

    require amount > 0              @msg("转账金额必须为正")
    require from.balance >= amount  @msg("账户余额不足")
    require from.id != to.id        @msg("不能向自身转账")

    let new_from = Account { balance: from.balance - amount, ..from }
    let new_to   = Account { balance: to.balance   + amount, ..to   }

    ensure new_from.balance >= 0
    ensure new_from.balance + new_to.balance == from.balance + to.balance  // 金额守恒
    ensure new_from.id == from.id
    ensure new_to.id   == to.id

    return Ok((new_from, new_to))
}
```

---

## 三个契约原语

### `intent` — 语义意图

```anna
intent "简洁的一行文字描述函数做什么"
```

- **位置**：函数体第一条语句
- **格式**：双引号字符串，一句话，不超过 120 字符
- **语气**：动词开头，描述行为而非实现
- **强制性**：对 `@public` 函数强制要求，其余建议

AI 在修改一个函数前，会**先读 `intent`** 来理解函数目的，  
再制定 patch 方案，从而避免"修改了代码但破坏了原意"。

```anna
intent "计算订单总价，含税"       // ✅ 清晰描述目标
intent "遍历列表然后相加"         // ❌ 描述实现而非意图
intent "see comments above"      // ❌ 无意义引用
```

### `require` — 前置条件

```anna
require <布尔表达式> @msg("可选的错误消息")
```

调用方必须满足 `require` 中的条件，否则行为未定义（实现可直接 panic 或返回 Err）。

```anna
fn divide(dividend: Float64, divisor: Float64) -> Float64 {
    intent "浮点除法"

    require divisor != 0.0                @msg("除数不能为零")
    require !Float64::is_nan(dividend)    @msg("被除数不得为 NaN")
    require !Float64::is_nan(divisor)     @msg("除数不得为 NaN")
    require Float64::is_finite(dividend)  @msg("被除数必须有限")

    return dividend / divisor
}
```

**AI 使用 `require` 的方式**：在生成函数调用代码时，工具链读取被调用函数的 `require` 列表，自动检查调用处是否满足前置条件，不满足则给出警告或拒绝生成 patch。

### `ensure` — 后置条件

```anna
ensure <布尔表达式> @msg("可选说明")
```

函数保证在正常返回时满足 `ensure` 中的条件。  
工具链在应用 patch（替换函数体）后，会验证新实现是否仍然满足所有 `ensure`。

```anna
fn sort(data: Vec<Int64>) -> Vec<Int64> {
    intent "返回排好序的向量（不修改原向量）"

    let result = ...  // 某种排序实现

    ensure result.len() == data.len()           @msg("长度不变")
    ensure is_sorted(result)                    @msg("结果必须有序")
    ensure result.contains_same_elements(data)  @msg("不得丢失或重复元素")

    return result
}
```

---

## 命名块（`@block`）

命名块是契约系统的延伸——它让函数内部的逻辑分区在结构路径中可寻址，  
使 AI 能精确地"替换验证逻辑"而不影响"转换逻辑"。

```anna
fn process_payment(order: Order, card: CardToken) -> Result<Receipt, PayError>
    !IO !Network
{
    intent "处理支付，返回收据"

    require order.amount > 0
    require order.status == OrderStatus::Pending

    @block("validation")
    let validated_card = {
        // AI patch 可单独替换这个块
        require card.expiry > current_timestamp()  @msg("卡已过期")
        require card.cvv_verified                  @msg("CVV 未验证")
        card
    }

    @block("authorization")
    let auth_result = {
        // AI patch 可单独替换这个块
        let resp = payment_gateway.authorize(validated_card, order.amount)?
        require resp.authorized  @msg("支付网关拒绝授权")
        resp
    }

    @block("settlement")
    return Ok(Receipt {
        order_id:    order.id,
        auth_code:   auth_result.code,
        settled_at:  current_timestamp(),
        amount:      order.amount,
    })
}
```

AI 可以这样 patch 单个块：

```anna
patch #payment.process_payment.body.authorization
    @reason("切换到新的支付网关 SDK")
    @confidence(0.89)
{
    replace_with {
        let resp = new_gateway.charge(validated_card, order.amount, order.currency)?
        require resp.status == "authorized"
        resp
    }
}
```

---

## 接口契约（cross-function invariants）

跨函数的不变量可以写在独立的 `.contract.anna` 文件中：

```anna
// contracts/cart.contract.anna

contract CartInvariants {
    // 任何返回 Cart 的函数都必须满足
    invariant "购物车总价不能为负" {
        forall cart: Cart => total_price(cart) >= 0
    }

    invariant "空购物车 items 为空向量，而非 None" {
        forall cart: Cart where cart.items.is_empty() =>
            cart.items.len() == 0
    }

    // add_item 的语义不变量
    invariant "添加商品后购物车商品种类不减少" {
        forall cart: Cart, item: CartItem =>
            add_item(cart, item).map(|c| c.items.len()) >= cart.items.len()
    }
}
```

---

## 契约与 Patch 的交互

当 AI 生成一个 `replace_with` patch 时，工具链会：

1. 提取原函数的所有 `require` 和 `ensure`
2. 对新实现运行静态验证
3. 若 `ensure` 无法被新实现满足，拒绝 patch 并报告原因
4. 若新实现引入了旧实现没有的 `require`，警告调用方可能不满足新的前置条件

```
[PatchValidator] 检查 patch #auth.login.body...
  ✓ require user_id > 0          — 新实现保留
  ✓ require password.len() > 0   — 新实现保留
  ✗ ensure session.user_id == user_id — 新实现无法静态验证此条件
  
  → Patch 被阻止。请更新新实现以满足 ensure，或降低 @confidence。
```

---

## Proof 验证块（v1.1）

`proof` 是语言级别的**形式化验证用例**，是 `ensure` 的可执行补充：

```anna
proof "当库存不足时应拒绝添加"
    for #ecommerce.cart.add_item
{
    case "正常流程" {
        given { cart.items = [], product.stock = 10, quantity = 2 }
        expect Ok(cart) where cart.items.len() == 1
    }

    case "库存不足" {
        given { cart.items = [], product.stock = 1, quantity = 5 }
        expect Err(CartError::OutOfStock)
    }

    case "数量为 0 拒绝" {
        given { quantity = 0 }
        expect Err(CartError::InvalidQuantity)
    }
}
```

**与 `ensure` 的区别**：

| 特性 | `ensure` 契约 | `proof` 验证块 |
|------|--------------|---------------|
| 表达方式 | 逻辑命题 | 具体输入/输出用例 |
| 执行方式 | 静态分析 / 运行时断言 | 自动化测试执行 |
| AI 使用 | 描述不变量 | 生成并运行可重复验证 |
| Patch 后行为 | 自动检查契约是否保持 | 自动运行所有关联 proof |

**Patch 与 Proof 的协同**：每当 AI 应用一个 patch，工具链自动找到所有引用该目标路径的 `proof` 块并重新执行。若有 proof 失败，patch 被拒绝并将失败的 AST 与结果结构化返回给 AI：

```
[ProofFailed] patch #ecommerce.cart.add_item 应用后：
  proof "当库存不足时应拒绝添加" › case "库存不足"
    expected:  Err(CartError::OutOfStock)
    actual:    Ok(cart)       ← stock 检查逻辑被意外删除

  → Patch 回滚。请修复库存检查逻辑后重新提交。
```

AI 收到结构化的失败信息（而不是文本日志），可直接定位问题并生成修正 patch。

