"""
ANNA Language — Patch Engine  (v1.1)
anna/patch_engine.py

结构化 Patch 应用引擎：
- 解析 PatchDef 节点
- 在 AST 上定位目标节点（含 v1.1 隐式索引路径）
- 应用变更并生成新 AST
- @requires_state 并发检查点（v1.1 Section 2）
- 高级重构原语：move_to / copy_to / wrap_with / extract_interface / resolve_patch（v1.1 Section 5）
- 输出 patch 操作日志
"""

from __future__ import annotations
import json
import re
import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .ast_nodes import (
    Program, FnDef, TypeDef, ConstDef, PatchDef, PatchGroupDef,
    PatchTarget, PatchOp, PatchReplace, PatchInsertBefore, PatchInsertAfter,
    PatchInsertCase, PatchDelete, PatchRename, PatchExtract, PatchInline,
    PatchModifyParams, PatchModifyFields,
    PatchMoveTo, PatchCopyTo, PatchWrapWith, PatchExtractInterface, PatchResolvePatch,
    ConflictDef, ProofDef,
    StructTypeDef, EnumTypeDef, AliasTypeDef, TypeName, GenericType,
    EnumVariant, FieldDef, Metadata, Annotation, Param,
    TopLevelItem,
)

# ── @requires_state 约束正则 ───────────────────
# 格式 1: "#auth.User.id == Int32"  (字段类型断言)
_RS_FIELD_TYPE_RE = re.compile(
    r'#([\w.]+)\.(\w+)\s*(==|!=)\s*(\w+)'
)
# 格式 2: "#path exists"
_RS_EXISTS_RE = re.compile(
    r'#([\w.]+)\s+exists'
)
# 格式 3: "#path.variant_count == N"
_RS_VARIANT_COUNT_RE = re.compile(
    r'#([\w.]+)\.variant_count\s*(==|!=|>|<|>=|<=)\s*(\d+)'
)


def _type_name_str(ty: Any) -> str:
    """将 TypeExpr 转为简短字符串（用于断言比对）。"""
    if ty is None:
        return "?"
    if isinstance(ty, TypeName):
        return ty.name
    if isinstance(ty, GenericType):
        inner = ", ".join(_type_name_str(p) for p in ty.params)
        return f"{ty.base}<{inner}>"
    return str(ty)


def _rs_compare(a: int, op: str, b: int) -> bool:
    if op == "==": return a == b
    if op == "!=": return a != b
    if op == ">":  return a > b
    if op == "<":  return a < b
    if op == ">=": return a >= b
    if op == "<=": return a <= b
    return False


# ─────────────────────────────────────────────
# 操作结果
# ─────────────────────────────────────────────

@dataclass
class PatchResult:
    """单个 patch 操作的结果。"""
    patch_id:    str
    target:      str
    operation:   str
    success:     bool
    message:     str
    applied_at:  str = ""

    def __post_init__(self):
        if not self.applied_at:
            self.applied_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "patch_id":   self.patch_id,
            "target":     self.target,
            "operation":  self.operation,
            "success":    self.success,
            "message":    self.message,
            "applied_at": self.applied_at,
        }


@dataclass
class PatchSession:
    """一组 patch 操作的会话记录。"""
    session_id:  str
    results:     list[PatchResult]
    program:     Program

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.success)

    def report(self) -> str:
        lines = [
            f"=== ANNA Patch Session: {self.session_id} ===",
            f"Applied: {self.success_count}  Failed: {self.failure_count}",
            "",
        ]
        for r in self.results:
            status = "✓" if r.success else "✗"
            lines.append(f"  {status} [{r.operation}] {r.target}")
            lines.append(f"    {r.message}")
        return '\n'.join(lines)


# ─────────────────────────────────────────────
# 错误
# ─────────────────────────────────────────────

class PatchError(Exception):
    def __init__(self, msg: str, target: str = ""):
        super().__init__(f"[PatchError] {target}: {msg}")
        self.target = target


# ─────────────────────────────────────────────
# 路径解析器
# ─────────────────────────────────────────────

class PathResolver:
    """
    将结构路径（如 #math.geometry.area）解析为 Program 中的节点。

    v1.1 新增：支持隐式索引路径（Section 1）：
        #module.fn/closure@1    第 1 处闭包
        #module.fn/match[2]     第 2 个 match 块
    """

    def __init__(self, program: Program):
        self.program = program

    def resolve(self, path: str) -> tuple[str, Any] | None:
        """
        返回 (resolved_kind, node) 或 None（未找到）。
        resolved_kind: 'fn' | 'type' | 'const' | 'field' | 'variant' | 'body' | 'implicit_indexed'

        支持路径格式：
            #TypeOrFn                          → 1 段
            #module.TypeOrFn                   → 2 段
            #ns.module.TypeOrFn                → 3 段
            #ns.module.TypeOrFn.member         → 4 段（字段/变体）
            #module.fn/closure@1               → 隐式闭包索引（v1.1）
            #module.fn/match[2]                → 隐式 match 索引（v1.1）
        """
        # 分离隐式索引后缀（v1.1 Section 1）
        implicit_suffix: str | None = None
        clean_path = path
        if '/' in path.lstrip('#'):
            base, implicit_suffix = path.lstrip('#').split('/', 1)
            clean_path = '#' + base
        else:
            clean_path = path

        raw   = clean_path.lstrip('#')
        parts = raw.split('.')

        # 1 段：直接查找
        if len(parts) == 1:
            fn = self.program.find_fn(parts[0])
            if fn: return ('fn', fn)
            ty = self.program.find_type(parts[0])
            if ty: return ('type', ty)
            return None

        # 最后段为成员（>= 3 段时）
        if len(parts) >= 3:
            type_name   = parts[-2]
            member_name = parts[-1]
            ty = self.program.find_type(type_name)
            if ty:
                if isinstance(ty, StructTypeDef):
                    for f in ty.fields:
                        if f.name == member_name:
                            return ('field', f)
                elif isinstance(ty, EnumTypeDef):
                    for v in ty.variants:
                        if v.name == member_name:
                            return ('variant', v)

        # 从右往左查找 fn/type（忽略模块前缀）
        for i in range(len(parts) - 1, -1, -1):
            candidate = parts[i]
            fn = self.program.find_fn(candidate)
            if fn:
                suffix = parts[i+1:]
                if not suffix:
                    # 有隐式索引后缀时返回 implicit_indexed
                    if implicit_suffix is not None:
                        return ('implicit_indexed', (fn, implicit_suffix))
                    return ('fn', fn)
                if suffix[0] == 'body':
                    return ('body', fn.body)
                if suffix[0] == 'params':
                    return ('params', fn.params)
            ty = self.program.find_type(candidate)
            if ty:
                suffix = parts[i+1:]
                if not suffix:
                    return ('type', ty)
                if len(suffix) == 1:
                    member = suffix[0]
                    if isinstance(ty, StructTypeDef):
                        for f in ty.fields:
                            if f.name == member:
                                return ('field', f)
                    elif isinstance(ty, EnumTypeDef):
                        for v in ty.variants:
                            if v.name == member:
                                return ('variant', v)

        # 有隐式索引但路径无法进一步解析时，返回宿主函数
        if implicit_suffix is not None:
            for i in range(len(parts) - 1, -1, -1):
                fn = self.program.find_fn(parts[i])
                if fn:
                    return ('implicit_indexed', (fn, implicit_suffix))

        return None


# ─────────────────────────────────────────────
# Patch 应用引擎
# ─────────────────────────────────────────────

class PatchEngine:
    """
    将 PatchDef 列表应用到 Program AST 上，返回新 Program。

    设计原则：
    - 不可变：每次 apply 返回新 Program，原 Program 不变
    - 事务性：patch_group @atomic 中任一失败则回滚整组
    - 可追踪：所有操作均记录在 PatchSession 中
    - v1.1：支持 @requires_state 并发检查点
    """

    def __init__(self, program: Program, session_id: str = ""):
        self.program    = program
        self.session_id = session_id or _gen_id()
        self.results:   list[PatchResult] = []

    def apply_all(self, patches: list[PatchDef | PatchGroupDef]) -> PatchSession:
        """将所有 patch 应用到当前 program，返回 PatchSession。"""
        current = self.program
        for p in patches:
            if isinstance(p, PatchGroupDef):
                current, group_results = self._apply_group(p, current)
                self.results.extend(group_results)
            else:
                current, result = self._apply_single(p, current)
                self.results.append(result)
        return PatchSession(
            session_id=self.session_id,
            results=self.results,
            program=current,
        )

    def _apply_group(
        self,
        group: PatchGroupDef,
        program: Program,
    ) -> tuple[Program, list[PatchResult]]:
        """
        原子地应用一组 patch。
        若 @atomic 注解存在，任一失败则返回原 program。
        """
        is_atomic = group.metadata.has("atomic")
        snapshot  = program
        results: list[PatchResult] = []

        for patch in group.patches:
            program, result = self._apply_single(patch, program)
            results.append(result)
            if not result.success and is_atomic:
                for r in results:
                    r.message = f"[ROLLED BACK] {r.message}"
                return snapshot, results

        return program, results

    def _apply_single(
        self,
        patch: PatchDef,
        program: Program,
    ) -> tuple[Program, PatchResult]:
        """应用单个 patch，返回新 Program 和操作结果。"""
        target_path = patch.target.path
        op          = patch.op
        op_name     = type(op).__name__

        # 元数据提取
        reason     = ""
        confidence = 1.0
        if ann := patch.metadata.get("reason"):
            reason = ann.args[0] if ann.args else ""
        if ann := patch.metadata.get("confidence"):
            confidence = float(ann.args[0]) if ann.args else 1.0

        # @requires_state 检查（v1.1 Section 2）
        if req_ann := patch.metadata.get("requires_state"):
            ok, msg = self._check_requires_state(req_ann, target_path, program)
            if not ok:
                return program, PatchResult(
                    patch_id  = _gen_id(),
                    target    = target_path,
                    operation = op_name,
                    success   = False,
                    message   = f"@requires_state 断言失败: {msg}",
                )

        try:
            new_program = self._dispatch(op, target_path, program)
            msg = f"成功 | reason: {reason!r} | confidence: {confidence:.2f}"
            return new_program, PatchResult(
                patch_id  = _gen_id(),
                target    = target_path,
                operation = op_name,
                success   = True,
                message   = msg,
            )
        except PatchError as e:
            return program, PatchResult(
                patch_id  = _gen_id(),
                target    = target_path,
                operation = op_name,
                success   = False,
                message   = str(e),
            )

    def _dispatch(self, op: PatchOp, path: str, program: Program) -> Program:
        if isinstance(op, PatchDelete):
            return self._op_delete(path, program)

        if isinstance(op, PatchRename):
            return self._op_rename(path, op, program)

        if isinstance(op, PatchInsertCase):
            return self._op_insert_case(path, op, program)

        if isinstance(op, (PatchReplace, PatchInsertBefore, PatchInsertAfter)):
            return self._op_content_patch(path, op, program)

        if isinstance(op, PatchModifyParams):
            return self._op_modify_params(path, op, program)

        if isinstance(op, PatchModifyFields):
            return self._op_modify_fields(path, op, program)

        # ── v1.1 高级重构原语（Section 5）──
        if isinstance(op, PatchMoveTo):
            return self._op_move_to(path, op, program)

        if isinstance(op, PatchCopyTo):
            return self._op_copy_to(path, op, program)

        if isinstance(op, PatchWrapWith):
            return self._op_wrap_with(path, op, program)

        if isinstance(op, PatchExtractInterface):
            return self._op_extract_interface(path, op, program)

        if isinstance(op, PatchResolvePatch):
            return self._op_resolve_patch(path, op, program)

        raise PatchError(f"不支持的 Patch 操作类型: {type(op).__name__}", path)

    # ── 路径工具 ─────────────────────────────────

    def _last_matched_name(self, path: str, program: Program) -> str | None:
        """从路径中提取在 program 中真实存在的最后一个匹配名称。"""
        clean = path.split('/')[0]  # 去掉隐式索引后缀
        parts = clean.lstrip('#').split('.')
        all_names = {getattr(item, 'name', None) for item in program.items}
        for p in reversed(parts):
            if p in all_names:
                return p
        return None

    # ── 基础操作 ──────────────────────────────────

    def _op_delete(self, path: str, program: Program) -> Program:
        """删除顶级 fn、type 或 const（目标不存在时幂等成功）。"""
        name = self._last_matched_name(path, program)
        if name is None:
            # 幂等：目标不存在视为已删除
            return program

        new_items = [
            item for item in program.items
            if not (hasattr(item, 'name') and item.name == name)
        ]
        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)

    def _op_rename(self, path: str, op: PatchRename, program: Program) -> Program:
        """重命名 fn、type 或 const（幂等：已是目标名时成功无变化）。"""
        old_name = self._last_matched_name(path, program)
        if old_name is None:
            raise PatchError("未找到目标节点", path)
        new_name = op.new_name

        new_items: list[TopLevelItem] = []
        found = False
        for item in program.items:
            if hasattr(item, 'name') and item.name == old_name:
                found = True
                item = dataclasses.replace(item, name=new_name)
            new_items.append(item)

        if not found:
            raise PatchError(f"未找到目标节点 {old_name!r}", path)

        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)

    def _op_insert_case(self, path: str, op: PatchInsertCase, program: Program) -> Program:
        """向枚举类型中插入新变体（变体名已存在时幂等拒绝）。"""
        type_name = self._last_matched_name(path, program)
        if type_name is None:
            raise PatchError("未找到枚举类型", path)

        new_items: list[TopLevelItem] = []
        found = False
        for item in program.items:
            if isinstance(item, EnumTypeDef) and item.name == type_name:
                found = True
                anchor = op.anchor_ref.lstrip('#').split('.')[-1]
                new_variants = list(item.variants)

                # 幂等检查：新变体名不得已存在
                existing_variant_names = {v.name for v in new_variants}
                for new_v in op.variants:
                    if new_v.name in existing_variant_names:
                        raise PatchError(
                            f"变体 {new_v.name!r} 已存在（幂等保护）", path
                        )

                anchor_idx = next(
                    (i for i, v in enumerate(new_variants) if v.name == anchor),
                    len(new_variants) - 1,
                )
                insert_at = anchor_idx + 1 if op.position == "after" else anchor_idx

                for v in reversed(op.variants):
                    new_variants.insert(insert_at, v)

                item = dataclasses.replace(item, variants=tuple(new_variants))
            new_items.append(item)

        if not found:
            raise PatchError(f"未找到枚举类型 {type_name!r}", path)

        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)

    def _op_content_patch(
        self,
        path: str,
        op: PatchReplace | PatchInsertBefore | PatchInsertAfter,
        program: Program,
    ) -> Program:
        """
        原型实现：将变更内容作为元数据注解记录到目标节点。
        完整实现应解析 content 为 AST 并替换对应子树。
        """
        fn_name  = self._last_matched_name(path, program)
        if fn_name is None:
            raise PatchError("未找到函数", path)
        op_label = type(op).__name__

        new_items: list[TopLevelItem] = []
        found = False
        for item in program.items:
            if isinstance(item, FnDef) and item.name == fn_name:
                found = True
                new_ann = Annotation(
                    name=f"_patch_{op_label}",
                    args=(getattr(op, 'content', ''),),
                    line=item.line, col=item.col,
                )
                old_meta = item.metadata
                new_meta = Metadata(
                    annotations=old_meta.annotations + (new_ann,),
                    line=old_meta.line, col=old_meta.col,
                )
                item = dataclasses.replace(item, metadata=new_meta)
            new_items.append(item)

        if not found:
            raise PatchError(f"未找到函数 {fn_name!r}", path)

        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)

    def _op_modify_params(self, path: str, op: PatchModifyParams, program: Program) -> Program:
        """修改函数参数列表。"""
        fn_name = self._last_matched_name(path, program)
        if fn_name is None:
            raise PatchError("未找到函数", path)

        new_items: list[TopLevelItem] = []
        found = False
        for item in program.items:
            if isinstance(item, FnDef) and item.name == fn_name:
                found = True
                params = list(item.params)
                for param_op in op.ops:
                    if param_op.kind == "add":
                        new_param = Param(
                            name=param_op.name,
                            ty=param_op.ty,
                            default=param_op.default,
                        )
                        params.append(new_param)
                    elif param_op.kind == "remove":
                        params = [p for p in params if p.name != param_op.name]
                    elif param_op.kind == "rename":
                        params = [
                            dataclasses.replace(p, name=param_op.new_name)
                            if p.name == param_op.name else p
                            for p in params
                        ]
                    elif param_op.kind == "change_type":
                        params = [
                            dataclasses.replace(p, ty=param_op.new_ty)
                            if p.name == param_op.name else p
                            for p in params
                        ]
                item = dataclasses.replace(item, params=tuple(params))
            new_items.append(item)

        if not found:
            raise PatchError(f"未找到函数 {fn_name!r}", path)

        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)

    def _op_modify_fields(self, path: str, op: PatchModifyFields, program: Program) -> Program:
        """修改结构体字段。"""
        type_name = self._last_matched_name(path, program)
        if type_name is None:
            raise PatchError("未找到类型", path)

        new_items: list[TopLevelItem] = []
        found = False
        for item in program.items:
            if isinstance(item, StructTypeDef) and item.name == type_name:
                found = True
                fields = list(item.fields)
                for fop in op.ops:
                    if fop.kind == "add":
                        # 幂等：字段名已存在时拒绝
                        if any(f.name == fop.name for f in fields):
                            raise PatchError(
                                f"字段 {fop.name!r} 已存在（幂等保护）", path
                            )
                        new_field = FieldDef(
                            name=fop.name,
                            ty=fop.ty,
                            metadata=Metadata(annotations=fop.annotations),
                        )
                        fields.append(new_field)
                    elif fop.kind == "remove":
                        fields = [f for f in fields if f.name != fop.name]
                    elif fop.kind == "rename":
                        fields = [
                            dataclasses.replace(f, name=fop.new_name)
                            if f.name == fop.name else f
                            for f in fields
                        ]
                    elif fop.kind == "change_type":
                        fields = [
                            dataclasses.replace(f, ty=fop.new_ty)
                            if f.name == fop.name else f
                            for f in fields
                        ]
                item = dataclasses.replace(item, fields=tuple(fields))
            new_items.append(item)

        if not found:
            raise PatchError(f"未找到类型 {type_name!r}", path)

        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)

    # ── @requires_state 断言检查（v1.1 Section 2 / v0.3.5 完整实现）──

    def _check_requires_state(
        self, ann: Annotation, path: str, program: Program
    ) -> tuple[bool, str]:
        """
        验证 @requires_state("constraint") 约束，返回 (passed, message)。

        支持三类断言格式：
          1. "#path.field == TypeName"  — 字段类型匹配
          2. "#path exists"             — 节点存在性
          3. "#path.variant_count == N" — 枚举变体数量
        """
        if not ann.args:
            return True, "ok"
        constraint = str(ann.args[0]).strip()
        resolver = PathResolver(program)

        # ── 格式 2: "#path exists" ──
        m = _RS_EXISTS_RE.match(constraint)
        if m:
            target = m.group(1)
            resolved = resolver.resolve(target)
            if resolved is None:
                return False, f"节点不存在: {target}"
            return True, f"ok: {target} 存在"

        # ── 格式 3: "#path.variant_count == N" ──
        m = _RS_VARIANT_COUNT_RE.match(constraint)
        if m:
            target, op_str, expected = m.group(1), m.group(2), int(m.group(3))
            resolved = resolver.resolve(target)
            if resolved is None:
                return False, f"节点不存在: {target}"
            _, node = resolved
            if isinstance(node, EnumTypeDef):
                actual = len(node.variants)
                if _rs_compare(actual, op_str, expected):
                    return True, f"ok: variant_count {actual} {op_str} {expected}"
                return False, f"variant_count 断言失败: 实际 {actual} {op_str} {expected} 不成立"
            return False, f"节点不是枚举类型: {target}"

        # ── 格式 1: "#path.field == TypeName" ──
        m = _RS_FIELD_TYPE_RE.match(constraint)
        if m:
            target, field_name, op_str, expected_type = (
                m.group(1), m.group(2), m.group(3), m.group(4)
            )
            resolved = resolver.resolve(target)
            if resolved is None:
                return False, f"节点不存在: {target}"
            _, node = resolved
            # 在结构体中查找字段
            if isinstance(node, StructTypeDef):
                for f in node.fields:
                    if f.name == field_name:
                        actual_type = _type_name_str(f.ty)
                        if op_str == "==" and actual_type == expected_type:
                            return True, f"ok: {field_name} 类型为 {actual_type}"
                        elif op_str == "!=" and actual_type != expected_type:
                            return True, f"ok: {field_name} 类型不为 {expected_type}"
                        return False, (
                            f"字段类型断言失败: {field_name} 实际类型 {actual_type}，"
                            f"期望 {op_str} {expected_type}"
                        )
                return False, f"字段 {field_name} 不存在于 {target}"
            # 在函数参数中查找
            if isinstance(node, FnDef):
                for p in node.params:
                    if p.name == field_name:
                        actual_type = _type_name_str(p.ty)
                        if op_str == "==" and actual_type == expected_type:
                            return True, f"ok: 参数 {field_name} 类型为 {actual_type}"
                        elif op_str == "!=" and actual_type != expected_type:
                            return True, f"ok: 参数 {field_name} 类型不为 {expected_type}"
                        return False, (
                            f"参数类型断言失败: {field_name} 实际类型 {actual_type}，"
                            f"期望 {op_str} {expected_type}"
                        )
                return False, f"参数 {field_name} 不存在于 {target}"
            return False, f"节点类型不支持字段断言: {type(node).__name__}"

        # ── 兜底：无法识别的约束格式 ──
        return False, f"无法解析的 @requires_state 约束: {constraint!r}"

    # ── v1.1 高级重构原语（Section 5）──────────────────────────────

    def _op_move_to(self, path: str, op: PatchMoveTo, program: Program) -> Program:
        """
        将节点从 path 剪切到 op.dest_path 指向的模块末尾。
        原型：标注 @_moved_to 元数据；完整实现需跨模块 AST 写入能力。
        """
        name = self._last_matched_name(path, program)
        if name is None:
            raise PatchError("未找到源节点", path)

        node_to_move = next(
            (item for item in program.items if hasattr(item, 'name') and item.name == name),
            None,
        )
        if node_to_move is None:
            raise PatchError(f"未找到节点 {name!r}", path)

        # 从当前位置移除，标注目标模块
        remaining = [
            item for item in program.items
            if not (hasattr(item, 'name') and item.name == name)
        ]
        moved_ann = Annotation(name="_moved_to", args=(op.dest_path,))
        old_meta  = getattr(node_to_move, 'metadata', Metadata())
        new_meta  = Metadata(annotations=old_meta.annotations + (moved_ann,))
        marked    = dataclasses.replace(node_to_move, metadata=new_meta)
        remaining.append(marked)   # 保留标记节点供 cascade 引用

        return Program(module=program.module, items=tuple(remaining),
                       line=program.line, col=program.col)

    def _op_copy_to(self, path: str, op: PatchCopyTo, program: Program) -> Program:
        """复制节点到目标路径，保留原节点（目标名已存在时幂等拒绝）。"""
        name = self._last_matched_name(path, program)
        if name is None:
            raise PatchError("未找到源节点", path)

        node = next(
            (item for item in program.items if hasattr(item, 'name') and item.name == name),
            None,
        )
        if node is None:
            raise PatchError(f"未找到节点 {name!r}", path)

        copy_name = op.new_name or f"{name}_copy"
        existing_names = {getattr(i, 'name', None) for i in program.items}
        if copy_name in existing_names:
            raise PatchError(f"copy_to 目标名 {copy_name!r} 已存在（幂等保护）", path)

        copy_node = dataclasses.replace(node, name=copy_name)
        return Program(module=program.module,
                       items=tuple(program.items) + (copy_node,),
                       line=program.line, col=program.col)

    def _op_wrap_with(self, path: str, op: PatchWrapWith, program: Program) -> Program:
        """
        用模板代码包裹函数体，__BODY__ 为原内容占位符。
        原型：将模板记录为 @_wrapped_with 注解；完整实现需 AST 级别包裹。
        """
        fn_name = self._last_matched_name(path, program)
        if fn_name is None:
            raise PatchError("未找到函数", path)

        new_items: list[TopLevelItem] = []
        found = False
        for item in program.items:
            if isinstance(item, FnDef) and item.name == fn_name:
                found = True
                wrap_ann = Annotation(name="_wrapped_with", args=(op.template,))
                new_meta = Metadata(
                    annotations=item.metadata.annotations + (wrap_ann,)
                )
                item = dataclasses.replace(item, metadata=new_meta)
            new_items.append(item)

        if not found:
            raise PatchError(f"未找到函数 {fn_name!r}", path)
        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)

    def _op_extract_interface(
        self, path: str, op: PatchExtractInterface, program: Program
    ) -> Program:
        """
        基于结构体自动推导接口定义。
        原型：创建带 @interface 注解的 AliasTypeDef 占位节点。
        完整实现需 trait/typeclass 类型系统支持。
        """
        type_name = self._last_matched_name(path, program)
        if type_name is None:
            raise PatchError("未找到类型", path)

        source_type = program.find_type(type_name)
        if not isinstance(source_type, StructTypeDef):
            raise PatchError(f"{type_name!r} 不是结构体，无法提取接口", path)

        existing_names = {getattr(i, 'name', None) for i in program.items}
        if op.interface_name in existing_names:
            raise PatchError(f"接口 {op.interface_name!r} 已存在（幂等保护）", path)

        iface_ann  = Annotation(name="interface", args=(f"从 {type_name} 提取",))
        iface_node = AliasTypeDef(
            name=op.interface_name,
            generics=(),
            target=TypeName(name=type_name),
            constraint=None,
            metadata=Metadata(annotations=(iface_ann,)),
        )
        return Program(module=program.module,
                       items=tuple(program.items) + (iface_node,),
                       line=program.line, col=program.col)

    def _op_resolve_patch(
        self, path: str, op: PatchResolvePatch, program: Program
    ) -> Program:
        """
        解决冲突节点（ConflictDef），由专用"冲突解决 Agent"调用。
        从 Program 中移除已解决的 ConflictDef 节点。
        """
        new_items: list[TopLevelItem] = []
        found = False
        for item in program.items:
            if isinstance(item, ConflictDef) and item.conflict_id == op.conflict_id:
                found = True
                continue   # 移除冲突节点
            new_items.append(item)

        if not found:
            raise PatchError(f"未找到冲突节点 {op.conflict_id!r}", path)
        return Program(module=program.module, items=tuple(new_items),
                       line=program.line, col=program.col)


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

_COUNTER = 0

def _gen_id() -> str:
    global _COUNTER
    _COUNTER += 1
    return f"anna-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{_COUNTER:04d}"


def apply_patches(program: Program, patches: list[PatchDef | PatchGroupDef]) -> PatchSession:
    """快捷函数：创建 PatchEngine 并应用所有 patch。"""
    engine = PatchEngine(program)
    return engine.apply_all(patches)

