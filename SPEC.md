# ANNA Language Specification
# AI-Native Notation & Action Language
# Version 0.1.0 | Designed for AI agents, not humans

---

## 设计哲学

现有编程语言的核心假设：
- 代码由**人类**书写，由**机器**执行
- 修改单位是**文本行**
- 意图隐藏在实现中

ANNA 的核心假设：
- 代码由**AI**生成与修改，由**机器**执行，由**人类**审阅
- 修改单位是**语义节点**
- 意图与实现**同等一等公民**

---

## 核心设计原则

### P1 — 结构优先于文本（Structure over Text）
所有代码元素均可通过结构路径精确寻址，禁止"第N行"这类脆弱引用。

### P2 — 意图与实现并列（Intent ≡ Implementation）
每个可调用单元必须声明其语义契约（前置条件、后置条件、不变量）。

### P3 — 无歧义语法（Zero Ambiguity）
不存在运算符优先级歧义、隐式类型转换、可选分号等"方便人类"但增加AI推理难度的特性。
所有括号、类型、作用域均显式标注。

### P4 — 原子补丁原语（Atomic Patch Primitives）
语言内置代码修改操作（patch），AI 对代码库的修改通过结构化 patch 表达，而非文本替换。

### P5 — 可溯源性（Full Traceability）
每个 patch、每个定义均携带元数据：作者、时间戳、原因、置信度。

### P6 — 幂等操作（Idempotence）
同一 patch 施加多次与施加一次效果相同，避免 AI 重复操作带来副作用。

### P7 — 显式副作用（Explicit Effects）
所有 I/O、状态修改、外部调用均在类型签名中显式声明（Effect System）。

---

## 文件结构

```
project/
├── anna.manifest          # 项目元数据与依赖
├── src/
│   ├── *.anna             # 源代码文件
│   └── *.patch.anna       # 补丁文件（AI 生成的变更）
├── contracts/
│   └── *.contract.anna    # 独立契约文件
└── history/
    └── *.log.anna         # 变更历史（自动生成）
```

---

## 词法规则

### 标识符
```
id       ::= [a-z_][a-z0-9_]*          # 普通标识符（snake_case）
TypeId   ::= [A-Z][A-Za-z0-9]*         # 类型标识符（PascalCase）
CONST_ID ::= [A-Z_][A-Z0-9_]+          # 常量标识符（SCREAMING_SNAKE）
@annot   ::= '@' id                     # 注解标识符
#ref     ::= '#' id ('.' id)*           # 结构路径引用
```

### 字面量
```
integer  ::= [0-9]+ | '0x' [0-9a-fA-F]+
float    ::= [0-9]+ '.' [0-9]+ ('e' [+-]? [0-9]+)?
string   ::= '"' ([^"\\] | '\\' .)* '"'      # 标准字符串
rawstr   ::= '`' [^`]* '`'                    # 原始字符串（无转义）
bool     ::= 'true' | 'false'
unit     ::= '()'
```

### 注释
```
// 行注释（人类阅读）
/* 块注释 */
#! 机器注释（AI 元信息，参与语义）
```

---

## 类型系统

### 基础类型
```anna
Int8, Int16, Int32, Int64      # 有符号整数（位宽显式）
UInt8, UInt16, UInt32, UInt64  # 无符号整数
Float32, Float64               # IEEE 754 浮点
Bool                           # 布尔
Str                            # UTF-8 字符串
Bytes                          # 原始字节序列
Unit                           # 空类型（唯一值 ()）
Never                          # 底类型（不可达）
```

### 复合类型
```anna
# 元组（固定长度，异构）
(Int64, Str, Bool)

# 数组（固定长度）
[Int64; 16]

# 向量（动态长度）
Vec<Int64>

# 映射
Map<Str, Int64>

# 可选
Option<T>   # 等价于 Some(T) | None

# 结果
Result<T, E>  # 等价于 Ok(T) | Err(E)
```

### 代数数据类型
```anna
type Shape {
    | Circle    { radius: Float64 }
    | Rectangle { width: Float64, height: Float64 }
    | Triangle  { base: Float64, height: Float64 }
}
```

### Effect 类型（副作用系统）
```anna
# 函数签名中显式声明副作用
fn read_file(path: Str) -> Result<Str, IoError> !IO
fn random_int(max: Int64) -> Int64 !Random
fn send_request(url: Str) -> Result<Response, NetworkError> !IO !Network

# 纯函数（无副作用，便于 AI 安全重构）
fn add(a: Int64, b: Int64) -> Int64  # 无 ! 标注 = 纯函数
```

### 依赖类型（轻量）
```anna
type NonEmpty<T> = Vec<T> where len > 0
type Probability  = Float64 where 0.0 <= self <= 1.0
type Port         = UInt16 where 1 <= self <= 65535
```

---

## 模块系统

```anna
module math.geometry @version("1.2.0") @stability(stable) {

    @public
    fn area(shape: Shape) -> Float64 {
        intent "计算任意形状的面积"
        match shape {
            | Circle    { radius }           => Float64::PI * radius * radius
            | Rectangle { width, height }    => width * height
            | Triangle  { base, height }     => 0.5 * base * height
        }
    }
}
```

---

## 契约系统（Contracts）

契约是 ANNA 中与实现并列的一等公民：

```anna
fn divide(dividend: Float64, divisor: Float64) -> Float64 {
    intent  "浮点除法，保证数学语义"
    require divisor != 0.0  @msg("除数不能为零")
    require !Float64::is_nan(dividend)
    require !Float64::is_nan(divisor)

    let result = dividend / divisor

    ensure !Float64::is_nan(result)
    ensure Float64::is_infinite(result) == false
    ensure (result * divisor) ≈ dividend @tolerance(1e-10)

    return result
}
```

---

## Patch 系统（AI 核心特性）

Patch 是 ANNA 最重要的特性——AI 对代码的所有修改通过结构化 patch 而非文本差异表达。

### Patch 基础语法

```anna
patch #math.geometry.area
    @reason("增加对 Ellipse 类型的支持")
    @author(@ai)
    @confidence(0.95)
    @ticket("FEAT-42")
{
    # 操作类型：insert_case | replace | delete | rename | extract | inline

    insert_case after #Shape.Triangle {
        | Ellipse { semi_major: Float64, semi_minor: Float64 }
            => Float64::PI * semi_major * semi_minor
    }
}
```

### Patch 操作原语

```anna
# 1. 替换函数体
patch #module.function.body replace_with {
    // 新的函数体
}

# 2. 在目标前/后插入
patch #module.function.body insert_before {
    let cache_key = compute_key(args)
    if let Some(v) = cache.get(cache_key) { return Ok(v) }
}

# 3. 删除节点
patch #module.helper_fn delete
    @reason("函数已内联，不再需要")

# 4. 重命名（级联更新所有引用）
patch #module.old_name rename_to new_name
    @cascade(true)

# 5. 提取函数
patch #module.large_fn extract_range(block_id: "validation_block") into validate_input
    @reason("提取验证逻辑以提高可读性")

# 6. 修改参数列表
patch #module.function.params {
    add_param timeout: Option<Duration> = None @position(last)
    remove_param legacy_flag: Bool
}

# 7. 修改类型
patch #module.SomeStruct.fields {
    change_type user_id: Int32 => Int64
    @reason("用户ID需要支持超过21亿的量级")
}

# 8. 批量 patch（事务性，全部成功或全部回滚）
patch_group @id("refactor-session-001") @atomic {
    patch #auth.login.body replace_with { ... }
    patch #auth.Session.fields { ... }
    patch #auth.logout rename_to sign_out @cascade
}
```

### Patch 条件守卫

```anna
patch #module.function
    @when(#module.function.body contains "legacy_api")
    @when(project.version < "2.0.0")
{
    // 只在满足条件时应用
}
```

---

## 结构路径系统（Structural Addressing）

ANNA 使用树形路径精确引用任何代码元素，彻底消除对行号的依赖：

```
#module_path.TypeOrFn.member.sub_member

示例：
#auth.User.email                    → User 结构体的 email 字段
#auth.login.body                    → login 函数的函数体
#auth.login.params.password         → login 函数的 password 参数
#auth.login.body.validation_block   → 函数体内命名块
#auth.AuthError                     → AuthError 类型
#auth.AuthError.InvalidToken        → 枚举变体
```

### 命名块（用于精确 patch）

```anna
fn process_data(input: Vec<UInt8>) -> Result<Output, ProcessError> {
    intent "处理原始字节数据并返回结构化输出"

    @block("validation")
    let validated = {
        require input.len() > 0
        require input.len() <= MAX_SIZE
        input
    }

    @block("transform")
    let transformed = validated
        |> decode_utf8
        |> parse_json
        |> validate_schema

    @block("output")
    return Output::from(transformed)
}
```

---

## 元数据系统

```anna
module my.service
    @version("2.1.0")
    @stability(experimental)   # stable | experimental | deprecated
    @owner("team-backend")
    @doc("处理用户认证相关逻辑")
    @ai_context(`
        这个模块使用 JWT 进行无状态认证。
        Session 存储在 Redis 中，TTL 为 24 小时。
        所有密码使用 Argon2id 哈希。
    `)
{
    // ...
}
```

`@ai_context` 是专门为 AI 设计的注解，提供人类不写入代码但 AI 理解代码必需的背景知识。

---

## 查询系统（AI 专用）

AI 可以对代码库执行结构化查询，而无需解析文本：

```anna
query {
    find fn
    where has_effect(!IO)
    where param_count > 5
    where !has_contract
    return [path, signature, intent]
}

query {
    find type
    where references(#auth.User)
    where module != "auth"
    return [path, kind]
}

query {
    find patch
    where @author(@ai)
    where applied_after("2026-01-01")
    where !@verified
    return [id, patch_target, reason, confidence]
}
```

---

## 验证与置信度

AI 生成代码时可附带置信度分数，工具链据此决定是否需要人类审查：

```anna
fn optimized_sort(data: Vec<Int64>) -> Vec<Int64> {
    intent "原地排序整数向量"
    @confidence(0.72)                    # AI 对此实现的置信度
    @review_required(confidence < 0.8)  # 自动触发人类审查
    @generated_from("TASK-128")

    // ...
}
```

---

## 完整示例

```anna
module ecommerce.cart
    @version("1.0.0")
    @stability(stable)
    @ai_context(`
        购物车使用乐观锁并发控制，version 字段用于冲突检测。
        价格单位为分（Int64），避免浮点误差。
        折扣优先级：用户专属 > 品类折扣 > 全场折扣。
    `)
{
    type Cart {
        id:       UInt64
        user_id:  UInt64
        items:    Vec<CartItem>
        version:  UInt32
    }

    type CartItem {
        product_id: UInt64
        quantity:   UInt32 where self > 0
        unit_price: Int64  where self >= 0   # 单位：分
    }

    @public
    fn add_item(cart: Cart, item: CartItem) -> Result<Cart, CartError> {
        intent "向购物车添加商品，若商品已存在则增加数量"

        require item.quantity > 0 @msg("数量必须大于零")
        require item.unit_price >= 0 @msg("价格不能为负")

        @block("dedup_check")
        let updated_items = {
            match cart.items.find(|i| i.product_id == item.product_id) {
                | Some(existing) => cart.items.map(|i|
                    if i.product_id == item.product_id {
                        CartItem { quantity: i.quantity + item.quantity, ..i }
                    } else { i }
                )
                | None => cart.items.append(item)
            }
        }

        let new_cart = Cart {
            items:   updated_items,
            version: cart.version + 1,
            ..cart
        }

        ensure new_cart.version == cart.version + 1
        ensure new_cart.items.len() >= cart.items.len()

        return Ok(new_cart)
    }
}
```

---

## 与现有语言的对比

| 特性               | 传统语言         | ANNA                        |
|--------------------|------------------|-----------------------------|
| 代码修改粒度       | 文本行           | 语义节点（结构路径）        |
| 意图表达           | 注释（可选）     | `intent` 一等公民（必须）   |
| 副作用             | 隐式             | Effect 类型系统显式标注     |
| 代码修改方式       | 文本 diff        | 结构化 patch 原语           |
| AI 上下文          | 无               | `@ai_context` 注解          |
| 置信度             | 无               | `@confidence` + 自动审查    |
| 变更溯源           | git commit       | patch 元数据内嵌            |
| 代码查询           | grep / AST 工具  | 内置结构化查询语言          |
| 契约               | 库（非标准）     | 语言内置一等公民            |
| 运算符优先级       | 复杂规则         | 完全括号化，无歧义          |

---

## 路线图

- [ ] v0.1 — 语言规范 + 解析器原型（Python）
- [ ] v0.2 — Patch 引擎（结构化 diff/apply）
- [ ] v0.3 — 查询引擎
- [ ] v0.4 — 类型检查器 + Effect 推断
- [ ] v0.5 — LSP 服务（供 AI 工具调用）
- [ ] v1.0 — 自举（ANNA 编译器由 ANNA 编写）
