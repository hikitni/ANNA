# ANNA 语言设计需求改进意见稿 v1.1

基于对 ANNA (v0.1.0) 核心设计哲学与架构原型的深入评审，为了使项目在进入下一阶段（特别是对接真实大模型和处理复杂工程化场景）时具备更高的稳定性和可用性，特提出以下需求改进建议，供后续规范迭代参考。

---

## 一、 结构路径系统（Addressing System）的边界增强

**当前痛点**：当前通过结构化路径追踪（如 `#module.fn.body`）对于具名层级非常有效。但现代编程中存在大量的高阶函数逻辑和匿名闭包，如果每个都需要手动打 `@block` 标签，不仅违背了语言的直觉，也会极大增加 AI 的生成负担。

**改进需求**：
1. **隐式索引扩展**：规范层需要定义一套针对未命名块和闭包的确定性隐式寻址。例如：
   - `#module.fn.body/closure@1`（按文本出现顺序索引的第一处闭包）
   - `#module.fn.body/match[2]`（函数体中的第二个模式匹配块）
2. **相对路径 Patch（上下文定锚）**：支持在 `patch` 原语中使用相对参考量。如在极度复杂的长函数体中，支持 `patch inside #module.fn before "return true" { ... }` 这种局部锚定法，以防绝对层级过深。

## 二、 Patch 系统的并发控制与版本管理

**当前痛点**：多个 AI Agent 并行工作（如前端 Agent 改类型，后端 Agent 写逻辑）时，独立的 `.patch.anna` 文件可能在应用阶段产生“语义冲突”。简单的幂等性不能解决深层的逻辑冲突。

**改进需求**：
1. **依赖图与语义哈希检查点**：
   - 建议在 `patch_group` 和 `patch` 原语中引入类似于 Git 的 `base_hash` 或 `requires_state` 约束。
   - 例：`patch #auth.User.age @requires(#auth.User.age == Int32) { change_type Int32 => Int64 }`。在施加 patch 前能够动态断言当前 AST 的状态。
2. **冲突解决原语**：当多个 patch 冲突时，系统应能自动生成 `ConflictNode` 语法树节点，允许一个专门的“冲突解决 Agent”执行特定的 `resolve_patch`。

## 三、 Token 经济学与认知负担优化（Token Economics）

**当前痛点**：零歧义（Zero Ambiguity）和高度强制的契约（Contract）让所有的设计更加明确，但也导致语法比传统语言更冗长。无论是对于大模型的上下文计算（Token 消耗），还是对于阅读该代码的人类开发者来说，都显得过于繁杂。

**改进需求**：
1. **对于人类（视图层分离）**：
   - 语言不需要改，但在 LSP（v0.5）的需求中必须明确规定“**投影视图**（Projected View）”的能力。
   - 在 IDE 中，开发者可以选择“Human Mode”，自动隐藏 `@ai_context`、`@confidence` 以及繁杂的 Effect 标记，还原出简洁的伪代码视角。
2. **对于 AI（局部编译域）**：
   - 允许 AI 在生成阶段返回“宏（Macro）”或“简写 Patch”，由编译器的预处理工具将其展开成完全正规的 ANNA AST。减少生成完整长文件的 Token 使用量量。

## 四、 AI 测试反馈闭环的语言级支持

**当前痛点**：假设 AI 发出了一个合法的 Patch 并已应用，但该逻辑破坏了业务连贯性。目前的契约（Contracts）能够防备运行时出错，但缺乏一种原生的方式让 AI 写出和执行验证条件。

**改进需求**：
1. **第一公民的验证用例（Proof）**：
   - 将“测试用例”变身为“形式化验证块（Proof）”集成入语言特性：`proof "当库存不足时应拒绝" for #ecommerce.cart.add_item { ... }`。
   - 当应用 Patch 后，系统会自动运行所有相关的 `proof`，并将失败的 AST 与结果结构化地折返给 AI。

## 五、 高级重构 Patch 原语的补充

建议在 v0.2/v0.3 阶段的规范中引入以下复合 Patch 操作：
1. `move_to` / `copy_to`：支持跨模块的节点迁移。
2. `wrap_with`：高频的异常处理和日志监控逻辑注入（如选定某个块，用 `try-catch` 结构将其包裹）。
3. `extract_interface`：基于现有的结构体自动推导并生成一套接口契约（Trait / Typeclass）。