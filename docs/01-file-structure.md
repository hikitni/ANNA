# ANNA 项目文件结构与词法规则

> 对应原则：**P3 — 无歧义语法（Zero Ambiguity）**

---

## 项目文件结构

一个 ANNA 项目由以下目录组成：

```
project/
├── anna.manifest              # 项目元数据与依赖声明
├── src/
│   ├── *.anna                 # 业务源代码
│   └── *.patch.anna           # AI 生成的补丁文件
├── contracts/
│   └── *.contract.anna        # 独立契约文件（可跨模块引用）
└── history/
    └── *.log.anna             # 变更历史（工具链自动生成，勿手动编辑）
```

### anna.manifest

```toml
[project]
name    = "ecommerce"
version = "1.0.0"
anna    = ">=0.1.0"

[dependencies]
std     = "0.1.0"
net     = "0.2.0"

[ai]
default_confidence_threshold = 0.85   # 低于此值自动触发人类审查
auto_review                  = true
```

---

## 词法规则

### 标识符分类

ANNA 使用三类标识符，通过命名约定区分语义，无需额外关键字：

| 类型 | 规则 | 用于 | 示例 |
|------|------|------|------|
| 普通标识符 | `[a-z_][a-z0-9_]*` | 变量、函数、模块段 | `user_id`, `add_item` |
| 类型标识符 | `[A-Z][A-Za-z0-9]*` | 类型、枚举变体 | `Cart`, `Option`, `IoError` |
| 常量标识符 | `[A-Z_][A-Z0-9_]+` | 编译期常量 | `MAX_ITEMS`, `PI` |

```ebnf
IDENT       ::= [a-z_][a-z0-9_]*
TYPE_IDENT  ::= [A-Z][A-Za-z0-9]*
CONST_IDENT ::= [A-Z_][A-Z0-9_]+
```

### 特殊标识符

```ebnf
annotation  ::= '@' IDENT          # @public, @ai_context, @confidence
struct_ref  ::= '#' IDENT ('.' IDENT)*   # #auth.User.email
```

- `@name` — 注解，附加在声明上的元数据
- `#path` — 结构路径引用，全局唯一地址，见 [05-structural-addressing.md](05-structural-addressing.md)

---

## 字面量

```ebnf
# 整数（十进制 / 十六进制）
integer  ::= [0-9]+
           | '0x' [0-9a-fA-F]+

# 浮点
float    ::= [0-9]+ '.' [0-9]+ ( 'e' [+-]? [0-9]+ )?

# 标准字符串（支持转义）
string   ::= '"' ( [^"\\] | '\\' . )* '"'

# 原始字符串（无转义，常用于 @ai_context）
rawstr   ::= '`' [^`]* '`'

# 布尔
bool     ::= 'true' | 'false'

# 单元值（Unit 类型的唯一值）
unit     ::= '()'
```

**设计说明**：原始字符串使用反引号，避免在 `@ai_context` 里频繁转义引号，  
让 AI 写入多行上下文文本时无需关心转义规则。

---

## 注释

ANNA 有三种注释，语义不同：

```anna
// 行注释 — 供人类阅读，工具链忽略

/* 块注释 — 供人类阅读，工具链忽略 */

#! 机器注释 — 供 AI/工具链读取，参与语义分析
#! 例如：#!deprecated since="1.2.0" use="#auth.login_v2"
```

`#!` 机器注释的内容会被工具链解析，可触发警告、迁移提示等行为。

---

## 运算符

### 二元运算符

所有二元表达式在歧义时**必须显式括号化**，没有歧义优先级规则：

```anna
// 错误（歧义）：
let x = a + b * c        // 编译报错：请加括号

// 正确（显式）：
let x = a + (b * c)
let y = (a + b) * c
```

| 类别 | 运算符 |
|------|-------|
| 算术 | `+` `-` `*` `/` `%` |
| 比较 | `==` `!=` `<` `>` `<=` `>=` |
| 近似相等 | `≈`（可附 `@tolerance`）|
| 逻辑 | `&&` `\|\|` |
| 位运算 | `&` `\|` `^` `<<` `>>` `~` |
| 管道 | `\|>` |
| 范围 | `..` `..=` |

### 特殊运算符

```anna
// 管道运算符：将左侧值作为右侧函数的第一个参数
let result = data |> decode_utf8 |> parse_json |> validate

// 近似相等（用于浮点契约断言）
ensure (result * divisor) ≈ dividend @tolerance(1e-10)

// 范围
for i in 0..10 { ... }      // 不含末端
for i in 0..=10 { ... }     // 含末端
```

---

## 关键字完整列表

```
// 声明
fn  type  const  module  use  as

// 控制流
let  mut  return  if  else  match  loop  while  for  in  break  continue

// 契约
intent  require  ensure  where

// Patch 系统
patch  patch_group
replace_with  insert_before  insert_after  insert_case  delete
rename_to  extract_range  inline  before  after
add_param  remove_param  rename_param  change_param_type
add_field  remove_field  rename_field  change_type

// 查询系统
query  find  limit

// 字面量
true  false
```

所有关键字均为小写，不可用作普通标识符。
