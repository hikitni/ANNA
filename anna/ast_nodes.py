"""
ANNA Language — AST Node Definitions
anna/ast_nodes.py

所有 AST 节点均为不可变 dataclass，支持结构化路径查询。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────
# 基础节点
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Node:
    """所有 AST 节点的基类。"""
    line: int = field(default=0, compare=False, repr=False, kw_only=True)
    col:  int = field(default=0, compare=False, repr=False, kw_only=True)

    def path_children(self) -> dict[str, "Node | list[Node]"]:
        """返回用于结构路径导航的命名子节点。子类覆盖此方法。"""
        return {}


# ─────────────────────────────────────────────
# 元数据 / 注解
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Annotation(Node):
    name: str                            # e.g. "version", "public", "ai_context"
    args: tuple[Any, ...]  = ()

@dataclass(frozen=True)
class Metadata(Node):
    """附加在 fn/type/module/patch 上的注解集合。"""
    annotations: tuple[Annotation, ...] = ()

    def get(self, name: str) -> Annotation | None:
        for a in self.annotations:
            if a.name == name:
                return a
        return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None


# ─────────────────────────────────────────────
# 类型表达式
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class TypeName(Node):
    """简单类型名，如 Int64, Str, Bool。"""
    name: str

@dataclass(frozen=True)
class GenericType(Node):
    """泛型类型，如 Vec<Int64>, Map<Str, Int64>。"""
    base: str
    params: tuple["TypeExpr", ...]

@dataclass(frozen=True)
class TupleType(Node):
    """元组类型，如 (Int64, Str)。"""
    elements: tuple["TypeExpr", ...]

@dataclass(frozen=True)
class FnType(Node):
    """函数类型，如 fn(Int64, Str) -> Bool !IO。"""
    params:  tuple["TypeExpr", ...]
    ret:     "TypeExpr"
    effects: tuple[str, ...] = ()

@dataclass(frozen=True)
class RefinedType(Node):
    """依赖/精化类型，如 Float64 where 0.0 <= self <= 1.0。"""
    base:       "TypeExpr"
    constraint: "Expr"

TypeExpr = TypeName | GenericType | TupleType | FnType | RefinedType


# ─────────────────────────────────────────────
# 表达式
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class IntLit(Node):
    value: int

@dataclass(frozen=True)
class FloatLit(Node):
    value: float

@dataclass(frozen=True)
class StrLit(Node):
    value: str
    raw: bool = False

@dataclass(frozen=True)
class BoolLit(Node):
    value: bool

@dataclass(frozen=True)
class UnitLit(Node):
    pass

@dataclass(frozen=True)
class Ident(Node):
    name: str

@dataclass(frozen=True)
class StructRef(Node):
    """结构路径引用，如 #auth.User.email。"""
    path: str         # 完整路径字符串，含 # 前缀
    parts: tuple[str, ...]  # 分解后的各段

@dataclass(frozen=True)
class BinOp(Node):
    op:    str
    left:  "Expr"
    right: "Expr"

@dataclass(frozen=True)
class UnaryOp(Node):
    op:      str
    operand: "Expr"

@dataclass(frozen=True)
class Pipeline(Node):
    """管道操作 a |> f。"""
    value: "Expr"
    fn:    "Expr"

@dataclass(frozen=True)
class Ternary(Node):
    cond:       "Expr"
    then_expr:  "Expr"
    else_expr:  "Expr"

@dataclass(frozen=True)
class Call(Node):
    callee: "Expr"
    args:   tuple["CallArg", ...]

@dataclass(frozen=True)
class CallArg(Node):
    value:  "Expr"
    label:  str | None = None   # 命名参数

@dataclass(frozen=True)
class MethodCall(Node):
    receiver: "Expr"
    method:   str
    args:     tuple["CallArg", ...]

@dataclass(frozen=True)
class BlockExpr(Node):
    stmts:      tuple["Stmt", ...]
    final_expr: "Expr | None" = None

@dataclass(frozen=True)
class TupleExpr(Node):
    elements: tuple["Expr", ...]

@dataclass(frozen=True)
class ArrayExpr(Node):
    elements: tuple["Expr", ...]

@dataclass(frozen=True)
class StructLit(Node):
    name:   str
    fields: tuple[tuple[str, "Expr"], ...]
    spread: "Expr | None" = None    # ..other

@dataclass(frozen=True)
class ClosureExpr(Node):
    params: tuple["Param", ...]
    body:   "Expr | BlockExpr"

@dataclass(frozen=True)
class ApproxEq(Node):
    """近似相等 a ≈ b，可选容差。"""
    left:      "Expr"
    right:     "Expr"
    tolerance: "Expr | None" = None

Expr = (IntLit | FloatLit | StrLit | BoolLit | UnitLit | Ident | StructRef |
        BinOp | UnaryOp | Pipeline | Ternary | Call | MethodCall |
        BlockExpr | TupleExpr | ArrayExpr | StructLit | ClosureExpr | ApproxEq)


# ─────────────────────────────────────────────
# 语句
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class LetStmt(Node):
    name:    str
    ty:      TypeExpr | None
    value:   "Expr"
    mutable: bool = False

@dataclass(frozen=True)
class ReturnStmt(Node):
    value: "Expr | None" = None

@dataclass(frozen=True)
class ExprStmt(Node):
    expr: "Expr"

@dataclass(frozen=True)
class IfStmt(Node):
    cond:      "Expr"
    then_body: BlockExpr
    else_body: "IfStmt | BlockExpr | None" = None

@dataclass(frozen=True)
class MatchStmt(Node):
    scrutinee: "Expr"
    arms:      tuple["MatchArm", ...]

@dataclass(frozen=True)
class MatchArm(Node):
    pattern: "Pattern"
    body:    "Expr | BlockExpr"

@dataclass(frozen=True)
class LoopStmt(Node):
    body: BlockExpr

@dataclass(frozen=True)
class WhileStmt(Node):
    cond: "Expr"
    body: BlockExpr

@dataclass(frozen=True)
class ForStmt(Node):
    pattern: "Pattern"
    iterable: "Expr"
    body:     BlockExpr

@dataclass(frozen=True)
class BreakStmt(Node):
    value: "Expr | None" = None

@dataclass(frozen=True)
class ContinueStmt(Node):
    pass

Stmt = LetStmt | ReturnStmt | ExprStmt | IfStmt | MatchStmt | LoopStmt | WhileStmt | ForStmt | BreakStmt | ContinueStmt


# ─────────────────────────────────────────────
# 模式
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class WildcardPattern(Node):
    pass

@dataclass(frozen=True)
class IdentPattern(Node):
    name: str

@dataclass(frozen=True)
class LiteralPattern(Node):
    literal: "Expr"

@dataclass(frozen=True)
class StructPattern(Node):
    type_name: str
    fields:    tuple[tuple[str, "Pattern | None"], ...]   # (field_name, sub_pattern | None)

Pattern = WildcardPattern | IdentPattern | LiteralPattern | StructPattern


# ─────────────────────────────────────────────
# 函数相关
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Param(Node):
    name:    str
    ty:      TypeExpr
    default: "Expr | None" = None

@dataclass(frozen=True)
class IntentDecl(Node):
    text: str

@dataclass(frozen=True)
class RequireDecl(Node):
    condition:   "Expr"
    annotations: tuple[Annotation, ...] = ()

@dataclass(frozen=True)
class EnsureDecl(Node):
    condition:   "Expr"
    annotations: tuple[Annotation, ...] = ()

@dataclass(frozen=True)
class NamedBlock(Node):
    """@block("name") { ... }"""
    block_id: str
    body:     BlockExpr

FnBodyItem = IntentDecl | RequireDecl | EnsureDecl | NamedBlock | Stmt

@dataclass(frozen=True)
class FnBody(Node):
    items: tuple[FnBodyItem, ...]

@dataclass(frozen=True)
class FnDef(Node):
    name:     str
    params:   tuple[Param, ...]
    ret:      TypeExpr | None
    effects:  tuple[str, ...]
    body:     FnBody
    metadata: Metadata

    def path_children(self):
        return {
            "params": list(self.params),
            "body":   self.body,
        }


# ─────────────────────────────────────────────
# 类型定义
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class FieldDef(Node):
    name:     str
    ty:       TypeExpr
    metadata: Metadata

@dataclass(frozen=True)
class EnumVariant(Node):
    name:   str
    fields: tuple[FieldDef, ...]    # struct-like variant
    types:  tuple[TypeExpr, ...]    # tuple variant

@dataclass(frozen=True)
class StructTypeDef(Node):
    name:     str
    generics: tuple[str, ...]
    fields:   tuple[FieldDef, ...]
    metadata: Metadata

@dataclass(frozen=True)
class EnumTypeDef(Node):
    name:     str
    generics: tuple[str, ...]
    variants: tuple[EnumVariant, ...]
    metadata: Metadata

@dataclass(frozen=True)
class AliasTypeDef(Node):
    name:       str
    generics:   tuple[str, ...]
    target:     TypeExpr
    constraint: "Expr | None"
    metadata:   Metadata

TypeDef = StructTypeDef | EnumTypeDef | AliasTypeDef


# ─────────────────────────────────────────────
# 常量定义
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class ConstDef(Node):
    name:     str
    ty:       TypeExpr
    value:    "Expr"
    metadata: Metadata


# ─────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class ImportStmt(Node):
    path:  str         # 完整模块路径
    items: tuple[tuple[str, str | None], ...]  # (name, alias)
    glob:  bool = False


# ─────────────────────────────────────────────
# Patch 系统
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class PatchTarget(Node):
    """结构路径，指向被 patch 的代码元素。"""
    path: str
    parts: tuple[str, ...]

@dataclass(frozen=True)
class PatchReplace(Node):
    content: str      # 原始源码片段（暂用字符串，后续 parse 为 AST）

@dataclass(frozen=True)
class PatchInsertBefore(Node):
    content: str

@dataclass(frozen=True)
class PatchInsertAfter(Node):
    content: str

@dataclass(frozen=True)
class PatchInsertCase(Node):
    position:   str     # "before" | "after"
    anchor_ref: str     # 参考变体路径
    variants:   tuple[EnumVariant, ...]

@dataclass(frozen=True)
class PatchDelete(Node):
    pass

@dataclass(frozen=True)
class PatchRename(Node):
    new_name: str
    cascade:  bool = True

@dataclass(frozen=True)
class PatchExtract(Node):
    block_id:  str
    into_name: str

@dataclass(frozen=True)
class PatchInline(Node):
    target_ref: str

@dataclass(frozen=True)
class ParamPatchOp(Node):
    kind:     str    # add | remove | rename | change_type
    name:     str
    ty:       TypeExpr | None = None
    new_name: str | None = None
    new_ty:   TypeExpr | None = None
    default:  "Expr | None" = None
    annotations: tuple[Annotation, ...] = ()

@dataclass(frozen=True)
class FieldPatchOp(Node):
    kind:        str
    name:        str
    ty:          TypeExpr | None = None
    new_name:    str | None = None
    new_ty:      TypeExpr | None = None
    annotations: tuple[Annotation, ...] = ()

@dataclass(frozen=True)
class PatchModifyParams(Node):
    ops: tuple[ParamPatchOp, ...]

@dataclass(frozen=True)
class PatchModifyFields(Node):
    ops: tuple[FieldPatchOp, ...]


# ── 高级重构原语（v1.1 Section 5） ───────────────────────

@dataclass(frozen=True)
class PatchMoveTo(Node):
    """将节点迁移（剪切）到另一个模块中的指定位置。"""
    dest_path: str        # 目标路径（接收方）
    cascade:   bool = True

@dataclass(frozen=True)
class PatchCopyTo(Node):
    """将节点复制到另一个模块，保留原始节点。"""
    dest_path: str
    new_name:  str | None = None    # None 表示保持原名

@dataclass(frozen=True)
class PatchWrapWith(Node):
    """用一段模板代码包裹目标块。PLACEHOLDER 标记原始内容的插入位置。"""
    template:  str    # 包裹模板，含 __BODY__ 占位符

@dataclass(frozen=True)
class PatchExtractInterface(Node):
    """基于结构体自动推导 trait/接口并生成。"""
    interface_name: str
    methods:        tuple[str, ...] = ()  # 空=推导所有公共方法

@dataclass(frozen=True)
class PatchResolvePatch(Node):
    """由冲突解决 Agent 执行的冲突解决操作（v1.1 Section 2）。"""
    conflict_id: str    # ConflictDef 的 ID
    resolution:  str    # 解决策略客户端内容（展展后处理）


PatchOp = (PatchReplace | PatchInsertBefore | PatchInsertAfter | PatchInsertCase |
           PatchDelete | PatchRename | PatchExtract | PatchInline |
           PatchModifyParams | PatchModifyFields |
           PatchMoveTo | PatchCopyTo | PatchWrapWith | PatchExtractInterface | PatchResolvePatch)

@dataclass(frozen=True)
class PatchDef(Node):
    target:   PatchTarget
    op:       "PatchOp"
    metadata: Metadata

@dataclass(frozen=True)
class PatchGroupDef(Node):
    patches:  tuple[PatchDef, ...]
    metadata: Metadata


# ── 并发冲突节点（v1.1 Section 2） ───────────────────────

@dataclass(frozen=True)
class ConflictDef(Node):
    """
    当两个 Patch 产生语义冲突时由系统自动生成。
    冲突解决 Agent 可对其执行 PatchResolvePatch。
    """
    conflict_id:  str
    target_path:  str
    left_patch:   PatchDef      # 第一个 patch
    right_patch:  PatchDef      # 与其冲突的 patch
    description:  str = ""


# ── 验证块（v1.1 Section 4） ──────────────────────────────

@dataclass(frozen=True)
class ProofCase(Node):
    """单个验证用例：输入 + 预期输出。"""
    label:       str
    given:       tuple["Expr", ...]   # 输入条件
    expect:      "Expr"               # 预期结果表达式

@dataclass(frozen=True)
class ProofDef(Node):
    """
    形式化验证块，馈合到目标函数。

    proof "\u5f53\u5e93\u5b58\u4e0d\u8db3\u65f6\u62d2\u7edd\u52a0购" for #ecommerce.cart.add_item {
        case "\u6b63\u5e38\u6d41\u7a0b" given { quantity = 2, stock = 10 } expect Ok(...)
        case "\u5e93\u5b58\u4e0d\u8db3" given { quantity = 11, stock = 10 } expect Err(OutOfStock)
    }
    """
    description:  str
    target_path:  str            # 被验证函数的结构路径
    cases:        tuple[ProofCase, ...]
    metadata:     Metadata


# ─────────────────────────────────────────────
# Query 系统
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class QueryFind(Node):
    target: str     # fn | type | const | patch | module | field | param

@dataclass(frozen=True)
class QueryWhere(Node):
    predicate: str   # 原始字符串，后续解析为谓词 AST

@dataclass(frozen=True)
class QueryReturn(Node):
    fields: tuple[str, ...]

@dataclass(frozen=True)
class QueryLimit(Node):
    count: int

@dataclass(frozen=True)
class QueryDef(Node):
    find:     QueryFind
    where_clauses: tuple[QueryWhere, ...]
    ret:      QueryReturn
    limit:    QueryLimit | None
    metadata: Metadata


# ─────────────────────────────────────────────
# 模块 & 程序
# ─────────────────────────────────────────────

TopLevelItem = FnDef | TypeDef | ConstDef | ImportStmt | PatchDef | PatchGroupDef | QueryDef | ProofDef | ConflictDef

@dataclass(frozen=True)
class ModuleDecl(Node):
    path:     str
    metadata: Metadata

@dataclass(frozen=True)
class Program(Node):
    module:  ModuleDecl | None
    items:   tuple[TopLevelItem, ...]

    def find_fn(self, name: str) -> FnDef | None:
        for item in self.items:
            if isinstance(item, FnDef) and item.name == name:
                return item
        return None

    def find_type(self, name: str) -> TypeDef | None:
        for item in self.items:
            if isinstance(item, (StructTypeDef, EnumTypeDef, AliasTypeDef)) and item.name == name:
                return item
        return None

    def find_patches(self) -> list[PatchDef]:
        result = []
        for item in self.items:
            if isinstance(item, PatchDef):
                result.append(item)
            elif isinstance(item, PatchGroupDef):
                result.extend(item.patches)
        return result
