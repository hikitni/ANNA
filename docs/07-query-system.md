# ANNA 查询系统

> 对应原则：**P1 — 结构优于文本** · **P5 — 完整可追溯**

---

## 为什么需要查询语言？

AI 在对代码库施加 patch 之前，需要先**理解**代码库的结构：

- "哪些函数有 IO 副作用但没有错误契约？"
- "哪些类型引用了 `UserId` 但没有标注 `@ai_context`？"
- "最近 30 天内，哪些函数被 patch 超过 3 次？"

传统方式需要 AI 解析自由文本源码。ANNA 的结构化存储让这些问题可以用声明式查询精确表达。

---

## 查询语法

```anna
query {
    find   <目标类型>
    where  <条件列表>
    return [<字段列表>]
    limit  <N>
}
```

### 目标类型

| 目标 | 说明 |
|------|------|
| `fn` | 函数定义 |
| `type` | 类型定义（结构体、枚举） |
| `const` | 常量 |
| `module` | 模块 |
| `patch` | 历史 patch 记录 |
| `field` | 结构体字段 |
| `param` | 函数参数 |

---

## 查询谓词

### Effect 过滤

```anna
// 有 IO 副作用
has_effect(!IO)

// 无任何副作用（纯函数）
has_effect()

// 有 IO 但无 DB 副作用
has_effect(!IO) and !has_effect(!DB)
```

### 引用检查

```anna
// 函数参数中引用了某类型
references(#ecommerce.Cart)

// 函数体中调用了某函数（传递性引用）
references(#payment.charge, transitive: true)
```

### 结构约束

```anna
// 参数数量
param_count(>= 4)
param_count(== 0)

// 有/无契约
has_contract(require)
has_contract(ensure)
!has_contract(intent)

// 有/无注解
has_annotation(@deprecated)
has_annotation(@ai_context)
!has_annotation(@reviewed)
```

### 置信度与溯源

```anna
// 置信度低于阈值
confidence(< 0.8)

// 指定作者
author(@ai)
author(@human)

// 在时间范围内被修改
modified_after(2025-01-01)
modified_before(2025-06-01)

// 被 patch 的次数
patch_count(>= 3)
```

### 模块过滤

```anna
// 属于特定模块
in_module(#auth)

// 模块稳定性等级
stability(unstable)
stability(stable)
```

---

## 示例查询

### 示例 1：找出高风险 AI 修改

找到 **AI 添加、置信度低于 90% 且有 IO 副作用** 的所有函数——需要人工审核：

```anna
query {
    find   fn
    where  author(@ai)
       and confidence(< 0.9)
       and has_effect(!IO)
    return [path, confidence, @reason, @ticket]
    limit  50
}
```

示例输出：

```
#auth.login              confidence=0.82  reason="切换到新 token 格式"
#payment.charge          confidence=0.87  reason="添加 Stripe v3 支持"
#notification.send_email confidence=0.71  reason="邮件模板升级"
```

---

### 示例 2：找出契约不完整的纯函数

找出**没有 `require` 前置条件却有复杂参数（>= 3 个参数）** 的函数——建议补充契约：

```anna
query {
    find   fn
    where  !has_contract(require)
       and param_count(>= 3)
       and !has_effect(!IO)
       and !has_effect(!DB)
    return [path, param_count, @reason]
    limit  100
}
```

---

### 示例 3：追踪高频修改热点

找出**最近 90 天内被修改超过 5 次、且不稳定** 的模块——可能存在设计问题：

```anna
query {
    find   module
    where  patch_count(>= 5)
       and modified_after(2025-03-01)
       and stability(unstable)
    return [path, patch_count, stability, last_modified]
    limit  20
}
```

---

### 示例 4：找出破坏性类型修改的影响面

找出所有**引用了 `UserId` 且有 DB 副作用** 的函数——在修改 UserId 类型前评估影响：

```anna
query {
    find   fn
    where  references(#auth.UserId)
       and has_effect(!DB)
    return [path, module, confidence]
}
```

---

## 查询的用途

| 场景 | 说明 |
|------|------|
| **Patch 前分析** | 评估修改的影响范围（`references` + `has_effect`） |
| **代码审计** | 找出低置信度、无契约、高副作用的高风险区域 |
| **技术债追踪** | 找出高频修改、不稳定模块 |
| **API 迁移辅助** | 找出所有调用了将被废弃函数的位置 |
| **测试覆盖分析** | 找出有 IO 副作用但无 `require` 的函数（测试难点）|

---

## 查询与 Patch 的协同工作流

典型的 AI 修改流程：

```
1. [查询] 找出受影响的结构路径
         query { find fn where references(#auth.UserId) }

2. [查询] 验证修改前提条件
         query { find fn where path == #auth.login and has_contract(require) }

3. [施加 Patch] 精确结构化修改
         patch #auth.login { ... }

4. [查询] 验证 Patch 后状态
         query { find fn where path == #auth.login return [confidence, @reason] }
```

这种模式保证 AI 在修改前充分理解上下文，在修改后可验证结果，而不是盲目输出文本 diff。
