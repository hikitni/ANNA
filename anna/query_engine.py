"""
ANNA Language — Query Engine
anna/query_engine.py

结构化查询引擎 (v0.3)
────────────────────
- 遍历 Program AST 中的 fn / type / module / patch 节点
- 解析并求值 where 谓词（has_effect, references, confidence, param_count...）
- 支持 and/or 组合与否定 (!)
- 按 return 声明的字段抽取属性
- 支持 limit 截断
"""

from __future__ import annotations
import re
from typing import Any, List, Dict, Callable, Sequence
from dataclasses import dataclass, field

from .ast_nodes import (
    Program, FnDef, TypeDef, StructTypeDef, EnumTypeDef, AliasTypeDef,
    ConstDef, PatchDef, PatchGroupDef, QueryDef, ModuleDecl,
    IntentDecl, RequireDecl, EnsureDecl, Metadata, Annotation,
    TypeName, GenericType, TopLevelItem,
)


# ─────────────────────────────────────────────
# 查询结果
# ─────────────────────────────────────────────

@dataclass
class QueryResult:
    path: str
    kind: str
    attributes: Dict[str, Any]

    def __repr__(self) -> str:
        attrs = ", ".join(f"{k}={v!r}" for k, v in self.attributes.items())
        return f"QueryResult({self.path}, {self.kind}, {attrs})"


# ─────────────────────────────────────────────
# 谓词求值器
# ─────────────────────────────────────────────

class Predicate:
    """将 where 子句的原始字符串编译为可执行的谓词函数。"""

    # 解析一条 where 子句为 (negated, pred_fn)
    @staticmethod
    def compile(predicate_str: str, program: Program) -> Callable[[Any], bool]:
        raw = predicate_str.strip()

        # ── 规范化：解析器以空格拼接 token，这里压缩为紧凑形式 ──
        raw = re.sub(r'\s*\(\s*', '(', raw)   # func ( x ) → func(x)
        raw = re.sub(r'\s*\)\s*', ')', raw)   # 同上
        raw = re.sub(r'!\s+(?=[a-zA-Z])', '!', raw)  # ! IO → !IO (保留 !=)

        # ── 否定前缀 ──
        negated = False
        if raw.startswith("!") and not raw.startswith("!="):
            negated = True
            raw = raw[1:].strip()

        fn = Predicate._compile_single(raw, program)
        if negated:
            return lambda node, _fn=fn: not _fn(node)
        return fn

    @staticmethod
    def _compile_single(raw: str, program: Program) -> Callable[[Any], bool]:
        # ── has_effect(!IO) ──
        m = re.match(r'has_effect\(\s*!?\s*(\w+)\s*\)', raw)
        if m:
            eff = m.group(1)
            return lambda node, _e=eff: (
                isinstance(node, FnDef) and _e in node.effects
            )

        # ── has_annotation(@xxx) ── 无比较值
        m = re.match(r'has_annotation\(\s*@(\w+)\s*\)$', raw)
        if m:
            ann_name = m.group(1)
            return lambda node, _a=ann_name: _has_annotation(node, _a)

        # ── has_annotation(@xxx) == value ──
        m = re.match(r'has_annotation\(\s*@(\w+)\s*\)\s*==\s*(.+)$', raw)
        if m:
            ann_name = m.group(1)
            compare_val = m.group(2).strip().strip('"').strip("'")
            return lambda node, _a=ann_name, _v=compare_val: _annotation_eq(node, _a, _v)

        # ── has_contract ──
        if raw == "has_contract":
            return lambda node: _has_any_contract(node)

        # ── has_circular_dependency ──
        if raw == "has_circular_dependency":
            # v0.3 原型：始终返回 False（需要完整的依赖图分析）
            return lambda node: False

        # ── param_count > N / param_count == N ──
        m = re.match(r'param_count\s*(>|<|>=|<=|==|!=)\s*(\d+)', raw)
        if m:
            op_str, num_str = m.group(1), m.group(2)
            num = int(num_str)
            return lambda node, _op=op_str, _n=num: (
                isinstance(node, FnDef) and _compare(len(node.params), _op, _n)
            )

        # ── confidence < 0.9 ──
        m = re.match(r'confidence\s*(>|<|>=|<=|==|!=)\s*([\d.]+)', raw)
        if m:
            op_str, num_str = m.group(1), m.group(2)
            num = float(num_str)
            return lambda node, _op=op_str, _n=num: (
                _compare(_get_confidence(node), _op, _n)
            )

        # ── references(#path) 或 references(TypeName) ──
        m = re.match(r'references\(\s*#?([\w.]+)\s*\)', raw)
        if m:
            ref_path = m.group(1)
            return lambda node, _r=ref_path, _p=program: _references(node, _r, _p)

        # ── path != "xxx" / path == "xxx" ──
        m = re.match(r'path\s*(!=|==)\s*["\']?(\w[\w.]*)["\']?', raw)
        if m:
            op_str, val = m.group(1), m.group(2)
            return lambda node, _op=op_str, _v=val: _path_compare(node, _op, _v)

        # ── stability != xxx / stability == xxx ──
        m = re.match(r'stability\s*(!=|==)\s*(\w+)', raw)
        if m:
            op_str, val = m.group(1), m.group(2)
            return lambda node, _op=op_str, _v=val: _stability_compare(node, _op, _v)

        # ── 通配：无法识别的谓词默认通过（宽容模式） ──
        return lambda node: True


# ─────────────────────────────────────────────
# 谓词辅助函数
# ─────────────────────────────────────────────

def _compare(a: float | int, op: str, b: float | int) -> bool:
    if op == ">":  return a > b
    if op == "<":  return a < b
    if op == ">=": return a >= b
    if op == "<=": return a <= b
    if op == "==": return a == b
    if op == "!=": return a != b
    return False


def _get_metadata(node: Any) -> Metadata | None:
    return getattr(node, 'metadata', None)


def _has_annotation(node: Any, name: str) -> bool:
    meta = _get_metadata(node)
    return meta.has(name) if meta else False


def _annotation_eq(node: Any, name: str, value: str) -> bool:
    meta = _get_metadata(node)
    if not meta:
        return False
    ann = meta.get(name)
    if not ann or not ann.args:
        return False
    return str(ann.args[0]).strip("@\"'") == value.strip("@\"'")


def _has_any_contract(node: Any) -> bool:
    if isinstance(node, FnDef):
        return any(
            isinstance(x, (IntentDecl, RequireDecl, EnsureDecl))
            for x in node.body.items
        )
    return False


def _get_confidence(node: Any) -> float:
    meta = _get_metadata(node)
    if meta:
        ann = meta.get("confidence")
        if ann and ann.args:
            try:
                return float(ann.args[0])
            except (ValueError, TypeError):
                pass
    return 1.0  # 默认满置信度


def _references(node: Any, ref_path: str, program: Program) -> bool:
    """
    检查节点是否引用了某个结构路径。
    v0.3 实现会检查：
      - 函数参数类型中是否含有目标类型名
      - 函数返回类型
      - 结构体字段类型
    """
    ref_name = ref_path.lstrip('#').split('.')[-1]  # 取最后一段作为类型名

    if isinstance(node, FnDef):
        # 检查参数类型
        for p in node.params:
            if _type_contains(p.ty, ref_name):
                return True
        # 检查返回值类型
        if node.ret and _type_contains(node.ret, ref_name):
            return True
        return False

    if isinstance(node, (StructTypeDef,)):
        for f in node.fields:
            if _type_contains(f.ty, ref_name):
                return True
        return False

    if isinstance(node, ModuleDecl):
        # 搜索整个模块的 items
        for item in program.items:
            if _references(item, ref_path, program):
                return True
        return False

    return False


def _type_contains(ty: Any, name: str) -> bool:
    """递归遍历 TypeExpr 检查是否包含指定类型名。"""
    if ty is None:
        return False
    if isinstance(ty, TypeName):
        return ty.name == name
    if isinstance(ty, GenericType):
        if ty.base == name:
            return True
        return any(_type_contains(p, name) for p in ty.params)
    return False


def _path_compare(node: Any, op: str, val: str) -> bool:
    node_path = getattr(node, 'path', getattr(node, 'name', ''))
    if op == "!=":
        return val not in str(node_path)
    if op == "==":
        return val in str(node_path)
    return False


def _stability_compare(node: Any, op: str, val: str) -> bool:
    meta = _get_metadata(node)
    if not meta:
        return op == "!="  # 无 stability 注解时
    ann = meta.get("stability")
    stab = str(ann.args[0]) if ann and ann.args else "unknown"
    if op == "!=":
        return stab != val
    if op == "==":
        return stab == val
    return False


# ─────────────────────────────────────────────
# 查询引擎
# ─────────────────────────────────────────────

class QueryEngine:
    """
    ANNA 结构化查询引擎。

    工作流：
      1. 接收 QueryDef（由 Parser 从 query { ... } 语法产出）
      2. 按 find target 获取候选节点集
      3. 将每条 where 编译为可执行谓词并逐节点过滤
      4. 按 return 声明的字段抽取属性
      5. 按 limit 截断
    """

    def __init__(self, program: Program):
        self.program = program

    # ── 主入口 ────────────────────────────────

    def execute(self, query: QueryDef) -> List[QueryResult]:
        target_kind = query.find.target

        # 1. 获取候选集
        candidates = self._gather_candidates(target_kind)

        # 2. 编译谓词
        predicates = [
            Predicate.compile(w.predicate, self.program)
            for w in query.where_clauses
        ]

        # 3. 过滤
        results: List[QueryResult] = []
        for node in candidates:
            if all(p(node) for p in predicates):
                path_val = self._resolve_path(node, target_kind)
                attrs = self._extract_fields(node, query.ret.fields, path_val)
                results.append(QueryResult(path=path_val, kind=target_kind, attributes=attrs))

                if query.limit and len(results) >= query.limit.count:
                    break

        return results

    # ── 批量执行 ──────────────────────────────

    def execute_all(self) -> Dict[str, List[QueryResult]]:
        """执行 Program 中所有嵌入的 QueryDef，返回 {query_id: results}。"""
        out: Dict[str, List[QueryResult]] = {}
        for item in self.program.items:
            if isinstance(item, QueryDef):
                qid = "unknown"
                if item.metadata.has("id"):
                    qid = str(item.metadata.get("id").args[0])
                out[qid] = self.execute(item)
        return out

    # ── 候选集 ────────────────────────────────

    def _gather_candidates(self, kind: str) -> Sequence[Any]:
        if kind == "fn":
            return [i for i in self.program.items if isinstance(i, FnDef)]
        if kind == "type":
            return [i for i in self.program.items if isinstance(i, (StructTypeDef, EnumTypeDef, AliasTypeDef))]
        if kind == "const":
            return [i for i in self.program.items if isinstance(i, ConstDef)]
        if kind == "patch":
            return self.program.find_patches()
        if kind == "module":
            # 模块级查询：以 ModuleDecl 本身作为单一候选
            return [self.program.module] if self.program.module else []
        return []

    # ── 路径生成 ──────────────────────────────

    def _resolve_path(self, node: Any, kind: str) -> str:
        mod_prefix = f"{self.program.module.path}." if self.program.module else ""
        if isinstance(node, FnDef):
            return f"#{mod_prefix}{node.name}"
        if isinstance(node, (StructTypeDef, EnumTypeDef, AliasTypeDef)):
            return f"#{mod_prefix}{node.name}"
        if isinstance(node, ConstDef):
            return f"#{mod_prefix}{node.name}"
        if isinstance(node, PatchDef):
            return node.target.path
        if isinstance(node, ModuleDecl):
            return f"#{node.path}"
        return "#unknown"

    # ── 字段抽取 ──────────────────────────────

    def _extract_fields(self, node: Any, fields: tuple[str, ...], path_val: str) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {}
        for f in fields:
            val = self._extract_single(node, f, path_val)
            attrs[f] = val
        return attrs

    def _extract_single(self, node: Any, field_name: str, path_val: str) -> Any:
        # ── 通用字段 ──
        if field_name == "path":
            return path_val
        if field_name == "kind":
            return type(node).__name__
        if field_name == "module":
            return self.program.module.path if self.program.module else ""

        # ── 函数相关 ──
        if isinstance(node, FnDef):
            if field_name == "signature":
                params_str = ", ".join(f"{p.name}: {_type_str(p.ty)}" for p in node.params)
                ret_str = f" -> {_type_str(node.ret)}" if node.ret else ""
                eff_str = " ".join(f"!{e}" for e in node.effects)
                return f"fn {node.name}({params_str}){ret_str} {eff_str}".rstrip()
            if field_name == "intent":
                intent_node = next((x for x in node.body.items if isinstance(x, IntentDecl)), None)
                return intent_node.text if intent_node else ""
            if field_name == "param_count":
                return len(node.params)

        # ── Patch 相关 ──
        if isinstance(node, PatchDef):
            if field_name == "id":
                return path_val
            if field_name == "target":
                return node.target.path
            if field_name == "operation":
                return type(node.op).__name__
            if field_name == "success":
                return True  # 在查询阶段，所有 patch 被视为已应用

        # ── 元数据字段 ──
        if field_name.startswith("@"):
            ann_name = field_name[1:]
            meta = _get_metadata(node)
            if meta:
                ann = meta.get(ann_name)
                if ann:
                    return ann.args[0] if ann.args else True
            return None

        # ── Metadata 相关通用字段 ──
        if field_name == "confidence":
            return _get_confidence(node)
        if field_name == "reason":
            meta = _get_metadata(node)
            if meta and meta.has("reason"):
                return str(meta.get("reason").args[0])
            return ""
        if field_name == "applied_at":
            meta = _get_metadata(node)
            if meta and meta.has("applied_at"):
                return str(meta.get("applied_at").args[0])
            return ""
        if field_name == "version":
            meta = _get_metadata(node)
            if meta and meta.has("version"):
                return str(meta.get("version").args[0])
            return ""
        if field_name == "owner":
            meta = _get_metadata(node)
            if meta and meta.has("owner"):
                return str(meta.get("owner").args[0])
            return ""
        if field_name == "stability":
            return _stability_value(node)

        # 其他
        return None


def _type_str(ty: Any) -> str:
    if ty is None:
        return "?"
    if isinstance(ty, TypeName):
        return ty.name
    if isinstance(ty, GenericType):
        inner = ", ".join(_type_str(p) for p in ty.params)
        return f"{ty.base}<{inner}>"
    return "?"


def _stability_value(node: Any) -> str:
    meta = _get_metadata(node)
    if not meta:
        return "unknown"
    ann = meta.get("stability")
    return str(ann.args[0]) if ann and ann.args else "unknown"

