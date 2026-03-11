"""
ANNA v0.3.5 — 高级重构原语 Parser + Engine 验证
──────────────────────────────────────────────────
覆盖 v1.1 规范中的 7 种新增 patch 操作的解析与引擎执行。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anna.parser import parse
from anna.patch_engine import PatchEngine
from anna.ast_nodes import (
    PatchDef, PatchGroupDef, PatchMoveTo, PatchCopyTo, PatchWrapWith,
    PatchExtractInterface, PatchResolvePatch, PatchModifyParams, PatchModifyFields,
)

BASE_SOURCE = """
module refactor.demo @version("1.0") {

    type PaymentGateway {
        charge:     Str
        refund:     Str
        get_status: Str
    }

    fn helper_fn(a: Int64, b: Str) -> Str {
        intent "辅助函数"
        return ""
    }

    fn main_fn(x: Int64) -> Int64 {
        intent "主函数"
        return x
    }
}
"""

# ── 1. move_to ──
PATCH_MOVE = """
module refactor.demo @version("1.0") {
    patch #refactor.demo.helper_fn
        @reason("迁移到 utils 模块")
    {
        move_to #refactor.utils @cascade(true)
    }
}
"""

# ── 2. copy_to ──
PATCH_COPY = """
module refactor.demo @version("1.0") {
    patch #refactor.demo.main_fn
        @reason("为 v2 API 创建副本")
    {
        copy_to #refactor.v2 new_name: main_fn_v2
    }
}
"""

# ── 3. wrap_with ──
PATCH_WRAP = """
module refactor.demo @version("1.0") {
    patch #refactor.demo.main_fn
        @reason("添加追踪")
    {
        wrap_with {
            let _span = tracer.start("main_fn")
            let result = { __BODY__ }
            _span.end()
            result
        }
    }
}
"""

# ── 4. extract_interface ──
PATCH_EXTRACT_IFACE = """
module refactor.demo @version("1.0") {
    patch #refactor.demo.PaymentGateway
        @reason("提取接口")
    {
        extract_interface PaymentGatewayTrait methods: [charge, refund, get_status]
    }
}
"""

# ── 5. resolve_patch ──
PATCH_RESOLVE = """
module refactor.demo @version("1.0") {
    patch #conflict_001
        @reason("采用右侧方案")
    {
        resolve_patch(conflict_id: "conflict_001", resolution: "apply_right")
    }
}
"""

# ── 6. add_param ──
PATCH_ADD_PARAM = """
module refactor.demo @version("1.0") {
    patch #refactor.demo.helper_fn.params
        @reason("添加来源参数")
    {
        add_param source: Str
    }
}
"""

# ── 7. add_field + change_type ──
PATCH_FIELD_OPS = """
module refactor.demo @version("1.0") {
    patch #refactor.demo.PaymentGateway.fields
        @reason("添加时间戳字段")
    {
        add_field created_at: UInt64
    }
}
"""

PATCH_CHANGE_TYPE = """
module refactor.demo @version("1.0") {
    patch #refactor.demo.PaymentGateway.fields
        @reason("升级类型")
    {
        change_type charge: Str => Bytes
    }
}
"""


def _parse_patches(source: str):
    ast = parse(source, filename="<test>")
    return [i for i in ast.items if isinstance(i, (PatchDef, PatchGroupDef))]


def _apply(base_src: str, patch_src: str):
    base = parse(base_src, filename="<base>")
    patches = _parse_patches(patch_src)
    engine = PatchEngine(base)
    return engine.apply_all(patches)


def main():
    print("=" * 60)
    print("ANNA v0.3.5 — Advanced Patch Ops Verification")
    print("=" * 60)

    pc, fc = 0, 0

    # 1. move_to
    patches = _parse_patches(PATCH_MOVE)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchMoveTo)
    if ok:
        ok = patches[0].op.dest_path == "#refactor.utils" and patches[0].op.cascade is True
    _r("parse-move_to", ok, f"Got {patches[0].op if patches else 'none'}")
    pc, fc = pc + ok, fc + (not ok)

    session = _apply(BASE_SOURCE, PATCH_MOVE)
    ok = session.results[0].success
    _r("exec-move_to", ok, f"{session.results[0].message}")
    pc, fc = pc + ok, fc + (not ok)

    # 2. copy_to
    patches = _parse_patches(PATCH_COPY)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchCopyTo)
    if ok:
        ok = patches[0].op.new_name == "main_fn_v2"
    _r("parse-copy_to", ok, f"Got {patches[0].op if patches else 'none'}")
    pc, fc = pc + ok, fc + (not ok)

    session = _apply(BASE_SOURCE, PATCH_COPY)
    ok = session.results[0].success
    _r("exec-copy_to", ok, f"{session.results[0].message}")
    pc, fc = pc + ok, fc + (not ok)

    # 3. wrap_with
    patches = _parse_patches(PATCH_WRAP)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchWrapWith)
    if ok:
        ok = "__BODY__" in patches[0].op.template
    _r("parse-wrap_with", ok, f"template contains __BODY__: {ok}")
    pc, fc = pc + ok, fc + (not ok)

    session = _apply(BASE_SOURCE, PATCH_WRAP)
    ok = session.results[0].success
    _r("exec-wrap_with", ok, f"{session.results[0].message}")
    pc, fc = pc + ok, fc + (not ok)

    # 4. extract_interface
    patches = _parse_patches(PATCH_EXTRACT_IFACE)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchExtractInterface)
    if ok:
        op = patches[0].op
        ok = op.interface_name == "PaymentGatewayTrait" and len(op.methods) == 3
    _r("parse-extract_interface", ok, f"Got {patches[0].op if patches else 'none'}")
    pc, fc = pc + ok, fc + (not ok)

    session = _apply(BASE_SOURCE, PATCH_EXTRACT_IFACE)
    ok = session.results[0].success
    _r("exec-extract_interface", ok, f"{session.results[0].message}")
    pc, fc = pc + ok, fc + (not ok)

    # 5. resolve_patch
    patches = _parse_patches(PATCH_RESOLVE)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchResolvePatch)
    if ok:
        ok = patches[0].op.conflict_id == "conflict_001" and patches[0].op.resolution == "apply_right"
    _r("parse-resolve_patch", ok, f"Got {patches[0].op if patches else 'none'}")
    pc, fc = pc + ok, fc + (not ok)

    # 6. add_param
    patches = _parse_patches(PATCH_ADD_PARAM)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchModifyParams)
    if ok:
        ok = patches[0].op.ops[0].kind == "add" and patches[0].op.ops[0].name == "source"
    _r("parse-add_param", ok, f"Got {patches[0].op if patches else 'none'}")
    pc, fc = pc + ok, fc + (not ok)

    # 7. add_field
    patches = _parse_patches(PATCH_FIELD_OPS)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchModifyFields)
    if ok:
        ok = patches[0].op.ops[0].kind == "add" and patches[0].op.ops[0].name == "created_at"
    _r("parse-add_field", ok, f"Got {patches[0].op if patches else 'none'}")
    pc, fc = pc + ok, fc + (not ok)

    # 8. change_type
    patches = _parse_patches(PATCH_CHANGE_TYPE)
    ok = len(patches) == 1 and isinstance(patches[0].op, PatchModifyFields)
    if ok:
        fop = patches[0].op.ops[0]
        ok = fop.kind == "change_type" and fop.name == "charge"
    _r("parse-change_type", ok, f"Got {patches[0].op if patches else 'none'}")
    pc, fc = pc + ok, fc + (not ok)

    print("\n" + "=" * 60)
    total = pc + fc
    print(f"Results: {pc}/{total} passed, {fc} failed")
    if fc == 0:
        print("ALL TESTS PASSED")
    print("=" * 60)


def _r(name, passed, detail):
    s = "PASS" if passed else "FAIL"
    print(f"\n  [{s}] {name}")
    if not passed:
        print(f"          {detail}")


if __name__ == "__main__":
    main()
