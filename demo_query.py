"""
ANNA Language — Query Engine End-to-End Demo (v0.3)
───────────────────────────────────────────────────
覆盖 examples/03_ai_queries.anna 中的全部 8 种查询场景。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anna.parser import parse
from anna.query_engine import QueryEngine
from anna.ast_nodes import QueryDef

# ─── 综合测试源码 ──────────────────────────────
# 包含函数（纯函数 + IO + Network）、类型、模块元数据、契约，
# 以及全部 8 个 query 定义，用于端到端验证。

TEST_SOURCE = """
module my.service
    @version("2.0.0")
    @stability(stable)
    @owner("team-backend")
    @ai_context(`
        这是一个综合测试模块。
        包含各种函数和类型，用于验证 Query Engine。
    `)
{
    type User {
        id:       UInt64
        name:     Str
        email:    Str
    }

    type Order {
        id:       UInt64
        user:     User
        total:    Int64
    }

    fn pure_add(a: Int64, b: Int64) -> Int64 {
        return a + b
    }

    @public
    fn read_file(path: Str) -> Result<Str, IoError> !IO {
        intent "读取文件内容"
        require path.len() > 0
        return "mock"
    }

    fn slow_network_call() -> Bytes !Network !IO {
        intent "调用慢速网络接口"
        return []
    }

    @public
    fn complex_fn(a: Int64, b: Str, c: Bool, d: Float64, e: UInt32) -> Str {
        intent "测试参数过多的函数"
        return ""
    }

    @public
    fn get_user(id: UInt64) -> Result<User, Str> !IO {
        intent "通过 ID 获取用户"
        require id > 0
        return Ok(User { id: id, name: "test", email: "t@t.com" })
    }

    fn process_order(order: Order) -> Result<Order, Str> {
        return Ok(order)
    }

    // ── Queries ──

    query @id("q-io-functions") {
        find fn
        where has_effect(!IO)
        return [path, signature, intent]
    }

    query @id("q-missing-contracts") {
        find fn
        where !has_contract
        return [path, intent, module]
    }

    query @id("q-user-deps") {
        find fn
        where references(User)
        return [path, kind]
    }

    query @id("q-too-many-params") {
        find fn
        where param_count > 4
        return [path, param_count, intent]
    }

    query @id("q-missing-ai-context") {
        find module
        where !has_annotation(@ai_context)
        return [path, owner, version]
    }

    query @id("q-has-ai-context") {
        find module
        where has_annotation(@ai_context)
        return [path, owner, stability]
    }

    query @id("q-all-types") {
        find type
        return [path, kind]
    }

    query @id("q-circular-deps") {
        find module
        where has_circular_dependency
        return [path]
    }
}
"""


def main():
    print("=" * 60)
    print("ANNA v0.3 — Query Engine E2E Verification")
    print("=" * 60)

    ast = parse(TEST_SOURCE, filename="<e2e-test>")
    engine = QueryEngine(ast)

    # 使用 execute_all 自动执行所有嵌入的查询
    all_results = engine.execute_all()

    pass_count = 0
    fail_count = 0

    # ── q-io-functions：应命中 read_file, slow_network_call, get_user ──
    r = all_results.get("q-io-functions", [])
    names = {res.path.split(".")[-1] for res in r}
    expect = {"read_file", "slow_network_call", "get_user"}
    ok = expect == names
    _report("q-io-functions", ok, f"Expected {expect}, got {names}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── q-missing-contracts：没有 intent/require/ensure 的函数 ──
    r = all_results.get("q-missing-contracts", [])
    names = {res.path.split(".")[-1] for res in r}
    # pure_add 和 process_order 没有任何契约声明
    expect = {"pure_add", "process_order"}
    ok = expect == names
    _report("q-missing-contracts", ok, f"Expected {expect}, got {names}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── q-user-deps：直接引用 User 类型的函数 → get_user (返回类型含 User) ──
    r = all_results.get("q-user-deps", [])
    names = {res.path.split(".")[-1] for res in r}
    expect = {"get_user"}
    ok = expect == names
    _report("q-user-deps", ok, f"Expected {expect}, got {names}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── q-too-many-params：complex_fn (5 params) ──
    r = all_results.get("q-too-many-params", [])
    names = {res.path.split(".")[-1] for res in r}
    expect = {"complex_fn"}
    ok = expect == names
    _report("q-too-many-params", ok, f"Expected {expect}, got {names}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── q-missing-ai-context：模块有 @ai_context，应返回空 ──
    r = all_results.get("q-missing-ai-context", [])
    ok = len(r) == 0
    _report("q-missing-ai-context", ok, f"Expected 0 results, got {len(r)}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── q-has-ai-context：模块有 @ai_context，应命中 ──
    r = all_results.get("q-has-ai-context", [])
    ok = len(r) == 1 and r[0].path == "#my.service"
    _report("q-has-ai-context", ok, f"Expected 1 result (#my.service), got {[x.path for x in r]}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── q-all-types：User, Order ──
    r = all_results.get("q-all-types", [])
    names = {res.path.split(".")[-1] for res in r}
    expect = {"User", "Order"}
    ok = expect == names
    _report("q-all-types", ok, f"Expected {expect}, got {names}")
    pass_count, fail_count = (pass_count + ok, fail_count + (not ok))

    # ── q-circular-deps：原型不支持，应返回空 ──
    r = all_results.get("q-circular-deps", [])
    ok = len(r) == 0
    _report("q-circular-deps", ok, f"Expected 0 (prototype), got {len(r)}")
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
