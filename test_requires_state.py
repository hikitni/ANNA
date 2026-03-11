"""
ANNA v0.3.5 — @requires_state 断言验证测试
──────────────────────────────────────────
覆盖三种约束格式：
  1. "#path.field == TypeName" — 字段类型断言
  2. "#path exists"           — 节点存在性
  3. "#path.variant_count == N" — 枚举变体数量
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anna.parser import parse
from anna.patch_engine import PatchEngine, PatchResult
from anna.ast_nodes import PatchDef, PatchGroupDef

# ─── 基础测试源码 ──────────────────────────────

SOURCE = """
module test.state @version("1.0") {

    type User {
        id:    Int32
        name:  Str
        email: Str
    }

    type Status {
        | Ok
        | Error
        | Pending
    }

    fn get_user(id: Int32) -> User !IO {
        intent "通过 ID 获取用户"
        return User { id: id, name: "", email: "" }
    }

    fn helper() -> Str {
        return "ok"
    }
}
"""

# ─── Patch 源码（含各种 @requires_state）──────

PATCHES_PASS = """
module test.state @version("1.0") {

    // Patch 1: 字段类型断言 — 应通过（id 确实是 Int32）
    patch #test.state.User
        @requires_state("#test.state.User.id == Int32")
        @reason("重命名 User 类型")
    {
        rename_to UserV2
    }

    // Patch 2: 节点存在性断言 — 应通过
    patch #test.state.helper
        @requires_state("#test.state.helper exists")
        @reason("删除废弃辅助函数")
    {
        delete
    }
}
"""

PATCHES_FAIL_FIELD = """
module test.state @version("1.0") {

    // 字段类型断言 — 应失败（id 不是 Int64）
    patch #test.state.User
        @requires_state("#test.state.User.id == Int64")
        @reason("尝试双重升级")
    {
        delete
    }
}
"""

PATCHES_FAIL_EXISTS = """
module test.state @version("1.0") {

    // 存在性断言 — 应失败（节点不存在）
    patch #test.state.nonexistent
        @requires_state("#test.state.nonexistent exists")
        @reason("操作不存在的节点")
    {
        delete
    }
}
"""

PATCHES_VARIANT_COUNT = """
module test.state @version("1.0") {

    // 变体数量断言 — 应通过（Status 有 3 个变体）
    patch #test.state.Status
        @requires_state("#test.state.Status.variant_count == 3")
        @reason("验证后重命名")
    {
        rename_to StatusV2
    }
}
"""

PATCHES_VARIANT_COUNT_FAIL = """
module test.state @version("1.0") {

    // 变体数量断言 — 应失败（实际 3 != 2）
    patch #test.state.Status
        @requires_state("#test.state.Status.variant_count == 2")
        @reason("变体数量预期不匹配")
    {
        rename_to StatusV2
    }
}
"""


def _run_patches(base_source: str, patch_source: str) -> list[PatchResult]:
    """解析并应用 patch，返回结果列表。"""
    base_ast = parse(base_source, filename="<base>")
    patch_ast = parse(patch_source, filename="<patches>")

    patches = [
        item for item in patch_ast.items
        if isinstance(item, (PatchDef, PatchGroupDef))
    ]

    engine = PatchEngine(base_ast)
    session = engine.apply_all(patches)
    return session.results


def main():
    print("=" * 60)
    print("ANNA v0.3.5 — @requires_state Verification")
    print("=" * 60)

    pass_count = 0
    fail_count = 0

    # ── Test 1: 字段类型断言通过 + 存在性断言通过 ──
    results = _run_patches(SOURCE, PATCHES_PASS)
    # Patch 1 应成功（字段断言通过）
    ok = len(results) >= 1 and results[0].success
    _report("field-type-pass", ok, f"Expected success, got {results[0] if results else 'no results'}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # Patch 2 应成功（存在性断言通过）
    ok = len(results) >= 2 and results[1].success
    _report("exists-pass", ok, f"Expected success, got {results[1] if len(results) > 1 else 'no results'}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── Test 2: 字段类型断言失败 ──
    results = _run_patches(SOURCE, PATCHES_FAIL_FIELD)
    ok = len(results) >= 1 and not results[0].success
    detail = results[0].message if results else "no results"
    ok = ok and "断言失败" in detail
    _report("field-type-fail", ok, f"Expected failure with assertion message, got: {detail}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── Test 3: 存在性断言失败 ──
    results = _run_patches(SOURCE, PATCHES_FAIL_EXISTS)
    ok = len(results) >= 1 and not results[0].success
    detail = results[0].message if results else "no results"
    ok = ok and ("不存在" in detail or "断言失败" in detail)
    _report("exists-fail", ok, f"Expected failure, got: {detail}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── Test 4: 变体数量断言通过 ──
    results = _run_patches(SOURCE, PATCHES_VARIANT_COUNT)
    ok = len(results) >= 1 and results[0].success
    _report("variant-count-pass", ok, f"Expected success, got: {results[0] if results else 'no results'}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── Test 5: 变体数量断言失败 ──
    results = _run_patches(SOURCE, PATCHES_VARIANT_COUNT_FAIL)
    ok = len(results) >= 1 and not results[0].success
    detail = results[0].message if results else "no results"
    ok = ok and "断言失败" in detail
    _report("variant-count-fail", ok, f"Expected failure, got: {detail}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── 汇总 ──
    print("\n" + "=" * 60)
    total = pass_count + fail_count
    print(f"Results: {pass_count}/{total} passed, {fail_count} failed")
    if fail_count == 0:
        print("ALL TESTS PASSED")
    print("=" * 60)


def _report(name: str, passed: bool, detail: str):
    status = "PASS" if passed else "FAIL"
    print(f"\n  [{status}] {name}")
    if not passed:
        print(f"          {detail}")


if __name__ == "__main__":
    main()
