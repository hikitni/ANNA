# ANNA Language — 文档索引

**AI-Native Notation & Action Language** | v0.1.0 → **v1.1 改进版**

ANNA 是专为 AI 设计的编程语言。现有语言假设代码由人类书写、机器执行；  
ANNA 的假设是：代码由 **AI 生成与修改**，由**机器执行**，由**人类审阅**。

---

## v1.1 改进摘要（2026-03）

基于 [improvement-proposal-1.1.md](improvement-proposal-1.1.md) 实施：

| Section | 改进 | 影响文档 |
|---------|------|---------|
| S1：寻址增强 | 隐式索引路径（`/closure@1`, `/match[2]`）| [05](05-structural-addressing.md) |
| S2：并发控制 | `@requires_state` 断言 · `ConflictDef` · `resolve_patch` | [06](06-patch-system.md) |
| S3：Token 经济学 | 投影视图（IDE Human Mode）· 宏展开（规划中） | [00](00-overview.md) |
| S4：AI 测试闭环 | `proof` 验证块作为一等公民 | [04](04-contracts.md) |
| S5：高级重构原语 | `move_to` · `copy_to` · `wrap_with` · `extract_interface` | [06](06-patch-system.md) |

---

## 文档目录

| 文档 | 主题 | 对应原则 |
|------|------|---------|
| [00-overview.md](00-overview.md) | 设计哲学 · 七大原则 · 对比 · 路线图 · **四大已知挑战** | 全局 |
| [01-file-structure.md](01-file-structure.md) | 项目文件结构 · 词法规则 | P3 无歧义 |
| [02-type-system.md](02-type-system.md) | 类型系统 · Effect 系统 · **Effect 级联传播** | P7 显式副作用 |
| [03-module-and-metadata.md](03-module-and-metadata.md) | 模块系统 · 元数据注解 · 置信度 | P5 可溯源性 |
| [04-contracts.md](04-contracts.md) | 契约系统 · intent · require · ensure · proof | P2 意图≡实现 |
| [05-structural-addressing.md](05-structural-addressing.md) | 结构路径 · 命名块 · 隐式索引寻址 | P1 结构优先 |
| [06-patch-system.md](06-patch-system.md) | Patch 原语 · 并发控制 · 高级重构 · **人类审查 LSP 渲染** | P4 原子补丁 · P6 幂等 |
| [07-query-system.md](07-query-system.md) | 结构化查询语言 · 查询谓词 | AI 专用 |
| [08-full-example.md](08-full-example.md) | 完整示例：电商购物车 | 综合 |

### 四大已知挑战（快速索引）

| 挑战 | 解决方案 | 详细位置 |
|------|---------|---------|
| Token 经济学 / 语法冗长税 | 分层优化：宏展开 → 投影视图 → 二进制 AST 序列化 | [00-overview.md § 挑战1](00-overview.md) |
| Effect 级联爆炸（Colored Function） | v0.4 Effect 自动传播引擎，`@system` 生成级联 patch_group | [02-type-system.md § Effect 级联传播](02-type-system.md) |
| 人类审查认知摩擦 | v0.5 LSP 实时反向编译，Patch 序列 → 标准双栏 Diff | [06-patch-system.md § 人类审查](06-patch-system.md) |
| 解析引擎并发性能 | v0.4 Rust 内核 + MVCC-AST 无锁并发 | [00-overview.md § 挑战4](00-overview.md) |

---

## 路线图概览（v0.3 构建中）

```
P1  Structure over Text        结构路径寻址，禁止行号引用
P2  Intent ≡ Implementation    intent 与 require/ensure 强制声明
P3  Zero Ambiguity             无隐式转换，无可选分号，全显式
P4  Atomic Patch Primitives    内置结构化 patch 操作原语
P5  Full Traceability          每个变更携带 reason/author/confidence
P6  Idempotence                patch 幂等，重复施加无副作用
P7  Explicit Effects           !IO !Network 在签名中显式标注
```

---

## 快速上手

```anna
module hello.world @version("0.1.0") {

    @public
    fn greet(name: Str) -> Str {
        intent "生成问候语"
        require name.len() > 0 @msg("名称不能为空")
        return "Hello, " + name + "!"
    }
}
```

```anna
// AI 修改代码的方式：结构化 patch，而非文本替换
patch #hello.world.greet
    @reason("支持多语言问候")
    @author(@ai)
    @confidence(0.94)
{
    replace_with {
        intent "生成多语言问候语"
        require name.len() > 0
        require lang == "zh" || lang == "en"
        return match lang {
            | "zh" => "你好，" + name + "！"
            | _    => "Hello, " + name + "!"
        }
    }
}
```
