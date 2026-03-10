# ANNA 设计哲学与核心原则

> 本文档阐述 ANNA 语言的存在理由、根本假设和七大设计原则。

---

## 为什么需要 ANNA？

现有编程语言在设计时的核心假设：

| 假设 | 现有语言 | ANNA |
|------|---------|------|
| 代码的**作者** | 人类 | AI |
| 代码的**执行者** | 机器 | 机器（不变）|
| 代码的**审阅者** | 人类（不变）| 人类 |
| **修改单位** | 文本行 | 语义节点 |
| **意图存放位置** | 注释（可选）| `intent`（强制）|

这一假设的转变带来了所有设计决策的不同。

---

## 七大设计原则

### P1 — 结构优先于文本（Structure over Text）

所有代码元素均可通过**结构路径**精确寻址，禁止"第 N 行"这类脆弱引用。

```anna
// 传统方式（脆弱）：
// "修改第 47 行的函数返回值"  ← 任何插入/删除都会让行号失效

// ANNA 方式（稳健）：
patch #auth.login.body replace_with { ... }
// 路径 #auth.login.body 不受其他代码变动影响
```

→ 详见 [05-structural-addressing.md](05-structural-addressing.md)

---

### P2 — 意图与实现并列（Intent ≡ Implementation）

每个可调用单元必须声明其**语义契约**：意图、前置条件、后置条件、不变量。  
这些不是注释——它们是语言一等公民，参与类型检查和 patch 验证。

```anna
fn divide(a: Float64, b: Float64) -> Float64 {
    intent  "浮点除法，保证数学语义"   // AI 读取的第一条信息
    require b != 0.0                     // 前置条件，可机器验证
    ensure  !Float64::is_nan(result)    // 后置条件
    return a / b
}
```

→ 详见 [04-contracts.md](04-contracts.md)

---

### P3 — 无歧义语法（Zero Ambiguity）

不存在以下"方便人类"但增加 AI 推理成本的特性：

- 运算符优先级歧义（所有二元表达式明确括号化）
- 隐式类型转换（所有转换显式调用）
- 可选分号（无歧义终结符）
- 可选大括号（`if` 体永远需要 `{}`）
- 字符串插值的多种写法

所有括号、类型、作用域均**显式标注**，一种语义只有一种写法。

→ 详见 [01-file-structure.md](01-file-structure.md)

---

### P4 — 原子补丁原语（Atomic Patch Primitives）

语言内置代码修改操作（`patch`），AI 对代码库的修改通过结构化 patch 表达，  
而非生成文本 diff。patch 操作是**声明式的**——描述"做什么"而非"怎么做"。

```anna
patch #ecommerce.Order.fields {
    add_field   shipped_at: Option<UInt64>
    change_type total:      Int32 => Int64   @reason("金额可能超过 21 亿分")
}
```

→ 详见 [06-patch-system.md](06-patch-system.md)

---

### P5 — 可溯源性（Full Traceability）

每个 patch、每个定义均携带结构化元数据：

```anna
patch #module.fn
    @reason("修复边界条件")   // 变更原因（必填）
    @author(@ai)              // 作者（@ai | @human | @tool）
    @confidence(0.91)         // AI 的自信度（0.0–1.0）
    @ticket("BUG-42")         // 关联工单（可选）
    @applied_at("2026-03-10") // 时间戳（自动生成）
{ ... }
```

这些元数据内嵌于语言，而非依赖外部 git 记录，支持完整的工具链分析。

→ 详见 [03-module-and-metadata.md](03-module-and-metadata.md)

---

### P6 — 幂等操作（Idempotence）

同一 patch 施加多次与施加一次效果**完全相同**，避免 AI 重复操作带来的副作用。

- `patch ... delete` 在目标不存在时静默成功（而非报错）
- `patch ... rename_to X` 在已经是 X 时无操作
- `patch ... insert_case` 使用变体名作为唯一键，重复插入被拒绝

AI 可以放心地重试失败的操作，无需检查"上次是否已经执行过"。

---

### P7 — 显式副作用（Explicit Effects）

所有 I/O、随机、状态修改、外部调用均在类型签名中**显式声明**：

```anna
fn read_config(path: Str) -> Result<Config, IoError>  !IO
fn roll_dice(sides: UInt32) -> UInt32                  !Random
fn send(url: Str, body: Bytes) -> Result<(), NetError> !IO !Network

// 无 ! 标注 = 纯函数，AI 可安全内联、重排、缓存
fn clamp(x: Float64, lo: Float64, hi: Float64) -> Float64
```

Effect 系统让 AI 在不执行代码的情况下判断：  
"这个改动会引入新的网络调用吗？" "这个函数能被安全地并行化吗？"

→ 详见 [02-type-system.md](02-type-system.md)

---

## 与现有语言的对比

| 特性 | 传统语言 | ANNA |
|------|---------|------|
| 代码修改粒度 | 文本行 | 语义节点（结构路径）|
| 意图表达 | 注释（可选）| `intent` 一等公民（必须）|
| 副作用标注 | 隐式 | Effect 类型系统显式标注 |
| 代码修改方式 | 文本 diff | 结构化 patch 原语 |
| AI 上下文 | 无 | `@ai_context` 注解 |
| 置信度 | 无 | `@confidence` + 自动审查触发 |
| 变更溯源 | git commit（外部）| patch 元数据内嵌（语言层）|
| 代码查询 | grep / AST 工具 | 内置结构化查询语言 |
| 契约 | 第三方库（非标准）| 语言内置一等公民 |
| 运算符优先级 | 复杂规则 | 完全括号化，无歧义 |

---

## 开发路线图

| 版本 | 目标 | 状态 |
|------|------|------|
| v0.1 | 语言规范 + 词法/语法解析器原型（Python） | ✅ 完成 |
| v0.2 | Patch 引擎（结构化 diff/apply） | ✅ 完成 |
| **v1.1** | **隐式索引寻址 · `@requires_state` · `proof` · 高级重构原语** | ✅ **完成** |
| v0.3 | 查询引擎（`query { find fn where ... }` 可执行） | 🔲 计划中 |
| v0.4 | 类型检查器 + **Effect 自动传播引擎** + Rust 增量解析器 | 🔲 计划中 |
| v0.5 | LSP 服务（供 AI 工具调用）· **天然语言 Diff 渲染（Human Mode）** | 🔲 计划中 |
| v0.6 | 宏/简写 Patch 展开（Token 经济学优化） | 🔲 计划中 |
| v1.0+ | 完全自举 + **轻量级二进制 AST 序列化（彻底绕开文本 Token 损耗）** | 🔲 长期目标 |

---

## 已知挑战与解决路径

以下四个问题是 ANNA 在向生产级工具链演进过程中必须正面解决的核心矛盾。

---

### 挑战 1 — Token 经济学："语法冗长税"

**问题根源**：P3（无歧义语法）强制所有括号、类型、作用域显式标注，  
在 Context Window 昂贵的阶段直接推高 LLM 的 token 消耗与注意力稀释。

**分层解决方案**：

| 层次 | 方案 | 计划版本 |
|------|------|----------|
| 文本层 | **宏/简写 Patch 展开**：AI 输出紧凑简写，预处理器展开为完整 AST | v0.6 |
| IDE 层 | **投影视图（Human Mode）**：隐藏 `@ai_context`、Effect 标注等冗余信息 | v0.5 |
| 传输层 | **轻量级二进制 AST 序列化**：AI 工具链与 ANNA 引擎之间直接交换结构化 AST 二进制流（类 WebAssembly 格式），彻底绕开文本符号层，token 消耗趋近于零 | v1.0+ |

简写 Patch 展开示例：
```
// AI 生成（简写）
!rename #auth.login -> authenticate

// 展开后（完整 ANNA）
patch #auth.login
    @reason("统一命名规范")
    @author(@ai)
    @confidence(0.95)
{ rename_to authenticate @cascade }
```

---

### 挑战 2 — Effect 系统的级联爆炸（Colored Function Problem）

**问题根源**：P7 要求副作用沿调用链向上传播。当 AI 在深层纯函数中引入 `!IO`，  
整条调用链均须补充签名，产生大量连锁 patch，消耗正比于调用深度的算力。

**解决方案**：Effect 自动传播引擎（v0.4）

```
[EffectPropagation] #payment.process_payment 新增 !IO
  自动追踪调用链：
    #payment.process_payment  → 新增 !IO  ✓ (已更新)
    #checkout.finalize        → 新增 !IO  ✓ (自动)
    #order.submit             → 新增 !IO  ✓ (自动)

  生成 patch_group @atomic [effect-cascade-2026031001]
  共计 3 个函数签名自动更新，AI 无需手动枚举。
```

AI 只需提交底层 patch，引擎**自动计算并生成**调用链的级联 patch_group，  
以 `@author(@system)` 标注以与 AI 生成区分，并在 Review 界面单独呈现。  
详见 [02-type-system.md](02-type-system.md#effect-级联传播)

---

### 挑战 3 — 人类审查的认知摩擦

**问题根源**：人类工程师擅长阅读红绿 Diff，但难以理解嵌套的结构化 patch 操作序列。  
若 Reviewer 无法直观看到变更全貌，代码合入将极其困难。

**解决方案**：LSP 实时反向编译（v0.5）

```
Patch 操作视图（AI 提交）          Human Diff 视图（LSP 渲染）
─────────────────────────          ─────────────────────────
insert_before #auth.login.body {   + let _limit = rate_limiter.check(id)?  // 新增
  check_rate_limit(id)?            + if _limit.exceeded { return Err(...) } // 新增
}                                    fn login(id, pwd) -> ...               // 不变
rename_to authenticate @cascade  - fn login(...)    // 旧
                                 + fn authenticate(...)  // 新
```

LSP 将结构化 patch 序列实时渲染为：
- **双栏差异视图**（类 GitHub PR 界面）
- **交互式折叠**：AI 元数据（`@confidence`、`@reason`）折叠到 tooltip
- **影响范围地图**：高亮所有 `@cascade` 引用的变动位置

详见 [06-patch-system.md](06-patch-system.md#人类审查与-lsp-diff-渲染)

---

### 挑战 4 — 解析引擎的并发性能

**问题根源**：Python 原型在多 Agent 并发场景（数十个微型重构同时触发）下，  
`@requires_state` 状态断言和 AST 锁竞争会成为性能瓶颈，  
无法满足百万行企业级代码库的实时 AST 解析需求。

**解决方案**：Rust 核心引擎（v0.4–v0.5）

| 组件 | 当前（Python） | 目标（Rust） |
|------|--------------|-------------|
| AST 解析速度 | ~10K 行/秒 | ~1M 行/秒 |
| 增量寻址延迟 | 50–200ms | < 1ms |
| 并发 patch 吞吐 | 单线程 | 无锁并发（MVCC-AST）|
| `@requires_state` 断言 | 顺序执行 | 并行快照隔离 |

Rust 引擎策略：
- **MVCC-AST（多版本并发控制）**：每个 patch 操作在 AST 快照上执行，  
  冲突在提交阶段检测，而非持有全局锁，彻底解决并发瓶颈
- Python 工具链保留为开发/调试层，Rust 引擎通过 FFI 无缝对接
- 路线图：v0.4 Rust 增量解析器 → v0.5 LSP 服务 → v1.0 完全自举

