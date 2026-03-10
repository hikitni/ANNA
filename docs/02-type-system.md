# ANNA 类型系统

> 对应原则：**P7 — 显式副作用（Explicit Effects）** · **P3 — 无歧义语法**

---

## 基础类型

所有数值类型**显式标注位宽**，禁止平台相关的 `int` / `long` 等模糊类型：

```anna
// 有符号整数
Int8   Int16   Int32   Int64

// 无符号整数
UInt8  UInt16  UInt32  UInt64

// 浮点（IEEE 754）
Float32   Float64

// 其他
Bool       // true | false
Str        // UTF-8 字符串（不可变）
Bytes      // 原始字节序列
Unit       // 空类型，唯一值为 ()
Never      // 底类型，表示不可达（如 panic、无限循环）
```

**设计说明**：AI 在生成数值类型时往往不清楚平台的默认字长，  
显式位宽让 AI 精确表达意图，避免 int 溢出类 bug。

---

## 复合类型

```anna
// 元组 — 固定长度、异构、按位置访问
(Int64, Str, Bool)

// 数组 — 固定长度，编译期已知
[UInt8; 32]

// 向量 — 动态长度
Vec<Int64>

// 映射 — 键值对
Map<Str, Int64>

// 可选 — 消灭 null
Option<T>     // 变体：Some(T) | None

// 结果 — 消灭异常
Result<T, E>  // 变体：Ok(T) | Err(E)
```

### 为什么没有 null / 异常？

null 和异常都是 AI 推理的噩梦：
- 任何函数都可能返回 null，AI 无法通过签名判断
- 异常可以在调用栈任意位置抛出，AI 无法静态分析控制流

`Option<T>` 和 `Result<T, E>` 将"可能失败"编码进类型，AI 必须在签名层面处理。

---

## 代数数据类型（Sum Types）

```anna
type Shape {
    | Circle    { radius: Float64 }
    | Rectangle { width: Float64, height: Float64 }
    | Triangle  { base: Float64, height: Float64 }
}

type NetworkError {
    | Timeout     { after_ms: UInt32 }
    | Refused     { host: Str, port: UInt16 }
    | TlsFailure  { reason: Str }
    | Unknown     { code: Int32, message: Str }
}
```

### 穷举 match

对 sum type 的 `match` 必须覆盖所有变体，否则编译错误：

```anna
fn describe(shape: Shape) -> Str {
    intent "返回形状的文字描述"
    match shape {
        | Circle    { radius }        => "圆形，半径 " + Float64::to_str(radius)
        | Rectangle { width, height } => "矩形，" + ...
        | Triangle  { base, height }  => "三角形，" + ...
        // 若新增 Ellipse 变体但未在此处理，编译报错
    }
}
```

这让 AI 在通过 patch 向枚举添加变体后，工具链能立刻指出所有需要更新的 match 表达式。

---

## Effect 类型系统

**这是 ANNA 中最重要的 AI 辅助特性之一。**

所有函数的副作用在签名中以 `!EffectName` 显式声明：

```anna
// 纯函数（无副作用）— 可安全并行、缓存、重排
fn clamp(x: Float64, lo: Float64, hi: Float64) -> Float64

// 文件 I/O
fn read_file(path: Str) -> Result<Str, IoError>  !IO
fn write_file(path: Str, data: Bytes) -> Result<(), IoError>  !IO

// 网络
fn fetch(url: Str) -> Result<Response, NetError>  !IO !Network

// 随机数
fn roll_dice(sides: UInt32) -> UInt32  !Random

// 数据库
fn query_user(id: UInt64) -> Result<User, DbError>  !IO !Database

// 时间（获取当前时间也是副作用）
fn now() -> UInt64  !Clock

// 多个 effect
fn send_with_retry(url: Str) -> Result<Response, NetError>
    !IO !Network !Clock !Random
```

### Effect 传播

调用有副作用的函数，调用者必须在签名中声明相同的 effect：

```anna
fn process_and_save(data: Str, path: Str) -> Result<(), IoError>  !IO {
    // 内部调用了带 !IO 的函数，所以本函数也必须声明 !IO
    let parsed = parse(data)          // 纯函数，无 effect
    return write_file(path, parsed)   // !IO，传播到本函数签名
}
```

### 纯函数的价值

无任何 `!` 标注的函数保证：
- 相同输入永远产生相同输出
- 可安全内联、提取、重排
- 可无条件并行化
- AI 可以安全重构，无需担心外部状态

---

## 函数类型

```anna
// 一等函数
type Transformer = fn(Str) -> Str
type Validator   = fn(Int64) -> Bool
type Handler     = fn(Request) -> Result<Response, ApiError>  !IO !Network

// 使用示例
fn apply(f: fn(Int64) -> Int64, x: Int64) -> Int64 {
    intent "将函数应用于值"
    return f(x)
}
```

---

## 依赖类型（轻量精化类型）

在类型名后接 `where` 子句，对值域施加约束：

```anna
type NonEmptyStr  = Str     where self.len() > 0
type NonEmpty<T>  = Vec<T>  where self.len() > 0
type Probability  = Float64 where 0.0 <= self && self <= 1.0
type Port         = UInt16  where 1 <= self && self <= 65535
type PositiveInt  = Int64   where self > 0

// 用于字段
type Cart {
    items:    NonEmpty<CartItem>   // 保证购物车非空
    version:  UInt32 where self > 0
}

// 用于参数
fn connect(host: Str, port: Port) -> Result<Connection, NetError>  !IO !Network {
    intent "建立 TCP 连接"
    // port 类型已保证 1–65535，无需在函数体内再次校验
    ...
}
```

精化类型让 AI 在生成代码时，把业务约束提升到类型层，  
而不是散落在各处的 `if x < 0 { panic!() }`。

---

## 泛型

```anna
type Stack<T> {
    items:    Vec<T>
    capacity: UInt32
}

fn map<A, B>(vec: Vec<A>, f: fn(A) -> B) -> Vec<B> {
    intent "将函数映射到向量的每个元素"
    // ...
}

fn find<T>(vec: Vec<T>, pred: fn(T) -> Bool) -> Option<T> {
    intent "返回满足谓词的第一个元素"
    // ...
}
```

---

## Effect 级联传播

### 问题：Colored Function Problem

P7 要求副作用沿调用链向上传播。当 AI 在深层纯函数中引入 `!IO`，
整条调用链均需更新签名——在复杂业务系统中可能引发几十个连锁 patch。

```anna
// 底层函数新增 !IO
fn compute_risk_score(data: RiskData) -> Float64  !IO  // 添加了日志

// 必须逐层向上传播
fn evaluate_application(app: Application) -> Decision  !IO   // 需要修改
fn process_loan(req: LoanRequest) -> Result<Loan, Err>  !IO   // 需要修改
fn handle_request(r: HttpRequest) -> HttpResponse  !IO         // 需要修改
```

### 解决方案：Effect 自动传播引擎（v0.4）

AI 只需提交底层（`compute_risk_score`）的 patch，引擎自动完成剩余工作：

```
[EffectPropagation] #risk.compute_risk_score 新增副作用 !IO
  调用链：
    #risk.evaluate_application    → 新增 !IO  ✓ 待自动应用
    #loan.process_loan            → 新增 !IO  ✓ 待自动应用
    #api.handle_request           → 新增 !IO  ✓ 待自动应用

  生成 patch_group @atomic [sys-effect-cascade-001]
    @author(@system)   ← 系统生成，与 AI 手动链路区分
    @confidence(1.0)   ← 纯算法推断，置信度 1.0
```

**级联传播的封隶规则**：

| 场景 | 行为 |
|------|------|
| 添加 `!X` | 自动向上传播到所有调用者 |
| 删除 `!X` | 检查调用者是否有其他路径引入 `!X`，没有则自动向上移除 |
| `@suppress_effect(!X)` | 显式封隶，适用于故意包裹副作用（如 Try‑Catch 层） |
| `@system` 生成的级联 patch | 在 Reviewer 界面喜补展开，不占用 AI 上下文 |

### `@suppress_effect` 使用示例

```anna
fn safe_log(msg: Str) -> ()  @suppress_effect(!IO) {
    intent "封装日志副作用，调用方无需关心 !IO"
    // 内部对 !IO 进行了统一封装，对外表现为纯函数
    log_buffer.push(msg)  // 内官封隶
}
