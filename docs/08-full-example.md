# 完整示例：电商购物车系统

本节通过一个完整的电商购物车实现，展示 ANNA 各设计原则如何协同工作。  
每处代码标注了对应的设计原则（P1–P7）。

---

## 项目结构

```
ecommerce/
├── anna.manifest          # 项目元信息（P3）
├── cart.anna              # 购物车模块（P2, P5, P7）
├── product.anna           # 商品模块（P1, P3）
└── patches/
    ├── v1.1-add-expiry.patch.anna    # 添加购物车过期（P4, P6）
    └── v1.2-tax-calc.patch.anna      # 添加税费计算（P4）
```

---

## `anna.manifest`

```toml
[project]
name    = "ecommerce"
version = "1.1.0"
anna    = "0.1"

[ai_policy]
confidence_threshold = 0.85     # 低于此置信度的 patch 需要人工审核（P5）
require_reason       = true      # 所有 patch 必须填写 @reason（P5）
require_ticket       = false     # ticket 可选
```

---

## `product.anna`（商品模块）

```anna
// ── 模块声明 ─────────────────────────────────────── P3, P5
module ecommerce.product
    @version("1.1.0")
    @stability(stable)
    @ai_context("商品领域模型。Price 单位为分（避免浮点误差）。")

// ── 类型定义 ──────────────────────────────────────── P7, P3
type ProductId = UInt64

type Price = UInt64     // 分，永不使用 Float64 存储货币

type Category =
    | Electronics { warranty_years: UInt8 }
    | Clothing    { size: Str, material: Str }
    | Food        { expires_in_days: UInt16 }
    | Digital

// P1：每个类型、每个变体都有独立路径，可独立 patch
// 例：#ecommerce.product.Category.Food

type Product = {
    id:        ProductId,
    name:      Str,
    price:     Price,
    category:  Category,
    in_stock:  Bool,
    version:   UInt32,      // 乐观锁版本号
}

type ProductError =
    | NotFound      { id: ProductId }
    | OutOfStock    { id: ProductId }
    | PriceInvalid  { price: Price, reason: Str }

// ── 函数 ──────────────────────────────────────────── P2, P7
fn validate_price(price: Price) -> Result<Price, ProductError>
    @ai_context("价格合法性校验。0 分允许（赠品），上限 1000 万分。")
    intent "校验价格在合法范围内"
    require { price >= 0 }
    ensure  { result is Ok => result.value == price }
{
    if price > 10_000_000 {
        return Err(ProductError::PriceInvalid {
            price,
            reason: "价格超过单品上限（1000 万分）",
        })
    }
    Ok(price)
}

fn get_product(id: ProductId) -> Result<Product, ProductError>
    effects [!IO, !DB]      // P7：明确声明副作用
    @ai_context("按 ID 查询商品。不存在时返回 NotFound，不抛出异常。")
    intent "从数据库获取商品信息"
    require { id > 0 }
    ensure  { result is Err(NotFound) => result.err.id == id }
{
    db.find(Product, id)
        .ok_or(ProductError::NotFound { id })
}
```

---

## `cart.anna`（购物车模块）

```anna
// ── 模块声明 ──────────────────────────────────────── P3, P5
module ecommerce.cart
    @version("1.1.0")
    @stability(stable)
    @ai_context("购物车核心逻辑。金额单位统一为分。税费在 checkout 时计算。")

import ecommerce.product { Product, ProductId, ProductError, Price }

// ── 类型 ──────────────────────────────────────────── P7, P3
type CartId = UInt64

type CartItem = {
    product_id: ProductId,
    quantity:   UInt16,
    unit_price: Price,       // 加入购物车时锁定价格（P3：零歧义）
}

type Cart = {
    id:         CartId,
    owner_id:   UInt64,
    items:      List<CartItem>,
    created_at: UInt64,
    expires_at: Option<UInt64>,   // v1.1 新增（P6：幂等 patch 结果）
}

type CartError =
    | ProductNotFound  { product_id: ProductId }
    | OutOfStock       { product_id: ProductId }
    | InvalidQuantity  { quantity: UInt16 }
    | CartNotFound     { cart_id: CartId }
    | CartExpired      { cart_id: CartId, expired_at: UInt64 }

// ── 核心函数 ───────────────────────────────────────── P2
fn add_item(
    cart:       Cart,
    product_id: ProductId,
    quantity:   UInt16,
) -> Result<Cart, CartError>
    effects [!IO, !DB]     // P7：有 IO 和 DB 副作用
    @author(@ai)
    @confidence(0.95)
    @reason("购物车添加商品核心逻辑")
    intent "向购物车添加指定数量的商品"
    require {
        quantity >= 1,
        quantity <= 999,
    }
    ensure {
        result is Ok =>
            result.value.items.count(_.product_id == product_id) >= 1
    }
{
    // ── [named block: validate_qty] ────────────────── P1：可被 patch 精确定位
    //! @id("validate_qty")
    if quantity < 1 || quantity > 999 {
        return Err(CartError::InvalidQuantity { quantity })
    }
    //! @end("validate_qty")

    // ── [named block: fetch_product] ──────────────── P1
    //! @id("fetch_product")
    let product = get_product(product_id)
        .map_err(|e| match e {
            | ProductError::NotFound { id } => CartError::ProductNotFound { product_id: id }
            | ProductError::OutOfStock { id } => CartError::OutOfStock { product_id: id }
            | _ => CartError::ProductNotFound { product_id }
        })?
    //! @end("fetch_product")

    // ── [named block: merge_or_add] ───────────────── P1
    //! @id("merge_or_add")
    let new_items = if let Some(idx) = cart.items.find_index(_.product_id == product_id) {
        cart.items.update(idx, |item| CartItem {
            ..item,
            quantity: item.quantity + quantity,
        })
    } else {
        cart.items.append(CartItem {
            product_id,
            quantity,
            unit_price: product.price,
        })
    }
    //! @end("merge_or_add")

    Ok(Cart { ..cart, items: new_items })
}

fn total_price(cart: Cart) -> Price
    @ai_context("合计价格 = Σ(单价 × 数量)，不含税。含税价格由 checkout 模块计算。")
    intent "计算购物车商品总价（分）"
    ensure { result >= 0 }
{
    cart.items.fold(0, |acc, item| acc + item.unit_price * UInt64(item.quantity))
}

fn checkout(cart: Cart) -> Result<Order, CartError>
    effects [!IO, !DB, !Net]    // P7：网络副作用（调用支付API）
    @ai_context("发起结账流程。调用支付服务，生成订单。")
    intent "结账并生成订单"
    require {
        cart.items.len() > 0,
    }
{
    // ── [named block: expiry_check] ──────────────── P1：v1.1 新增过期检查
    //! @id("expiry_check")
    if let Some(exp) = cart.expires_at {
        if current_timestamp() > exp {
            return Err(CartError::CartExpired { cart_id: cart.id, expired_at: exp })
        }
    }
    //! @end("expiry_check")

    let total = total_price(cart)
    payment.charge(cart.owner_id, total)
        .map(|payment_id| Order {
            cart_id:    cart.id,
            payment_id,
            total,
            created_at: current_timestamp(),
        })
        .map_err(|_| CartError::CartNotFound { cart_id: cart.id })
}
```

---

## `patches/v1.1-add-expiry.patch.anna`

为购物车添加过期时间支持（P4 + P6）：

```anna
// P4：原子操作；P6：幂等——字段已存在时报告冲突而非重复添加
patch_group
    @id("v1.1-add-cart-expiry")
    @atomic
    @reason("购物车过期清理：未结账的购物车 24 小时后自动失效，减少孤儿数据")
    @ticket("FEAT-55")
    @author(@ai)
    @confidence(0.93)
{
    // P4: add_field 原语
    patch #ecommerce.cart.Cart.fields {
        add_field expires_at: Option<UInt64>
                  @reason("过期时间戳（秒）。None = 永不过期。")
    }

    // P4: insert_case 原语
    patch #ecommerce.cart.CartError {
        insert_case after #ecommerce.cart.CartError.CartNotFound {
            | CartExpired { cart_id: CartId, expired_at: UInt64 }
        }
    }

    // P4：在命名块内精确插入，不影响其他逻辑
    patch #ecommerce.cart.checkout.body
        @target_block("expiry_check")
    {
        insert_before {
            //! @id("expiry_check")
            if let Some(exp) = cart.expires_at {
                if current_timestamp() > exp {
                    return Err(CartError::CartExpired {
                        cart_id:    cart.id,
                        expired_at: exp,
                    })
                }
            }
            //! @end("expiry_check")
        }
    }
}
```

---

## `patches/v1.2-tax-calc.patch.anna`

添加税费计算（P4）：

```anna
patch #ecommerce.cart.total_price
    @reason("Rename: 语义更精确 — 函数只计算不含税总价")
    @confidence(0.99)
    @author(@ai)
    @ticket("TAX-01")
{
    rename_to subtotal @cascade(true)   // P4 + P1：级联更新所有引用路径
}

patch #ecommerce.cart
    @reason("新增含税价格计算。税率由外部 tax_service 提供。")
    @ticket("TAX-01")
    @author(@ai)
    @confidence(0.91)
{
    insert_after #ecommerce.cart.subtotal {
        fn total_with_tax(cart: Cart, tax_rate: Float64) -> Price
            effects [!IO]
            @ai_context("含税价格 = 不含税总价 × (1 + tax_rate)。tax_rate 为小数，如 0.08 表示 8%。")
            intent "计算含税总价"
            require { tax_rate >= 0.0, tax_rate <= 1.0 }
            ensure  { result >= subtotal(cart) }
        {
            let base = subtotal(cart)
            let tax  = Float64(base) * tax_rate
            base + UInt64(tax)
        }
    }
}
```

---

## 设计原则在示例中的体现

| 原则 | 在本示例中的体现 |
|------|----------------|
| **P1 结构优于文本** | 命名块 `@id("validate_qty")`、`@id("fetch_product")` 等提供精确 patch 目标 |
| **P2 意图即实现** | 每个函数都有 `intent` + `require` + `ensure` 三件套 |
| **P3 零歧义** | `Price = UInt64`（分）避免浮点误差；注释明确说明单位、取值范围 |
| **P4 原子原语** | v1.1 patch 使用 `add_field`、`insert_case`、`insert_before`，而不是文本 diff |
| **P5 完整溯源** | 每个 patch 有 `@reason`、`@ticket`、`@author`、`@confidence` |
| **P6 幂等操作** | `add_field expires_at` 若字段已存在则报冲突，不重复添加 |
| **P7 显式副作用** | `effects [!IO, !DB]`、`effects [!IO, !DB, !Net]` 明确标注每个函数的副作用边界 |
