"""
ANNA Language — Interactive Demo
demo.py

演示词法分析、语法解析和 Patch 引擎的完整流程。
"""

import sys
import os

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anna.lexer        import tokenize, TK
from anna.parser       import parse
from anna.patch_engine import PatchEngine, apply_patches
from anna.query_engine import QueryEngine
from anna.ast_nodes    import (
    PatchDef, PatchGroupDef, PatchTarget, PatchDelete, PatchRename,
    PatchInsertCase, EnumVariant, FieldDef, TypeName, Metadata,
    Annotation, Program, QueryDef
)


# ─────────────────────────────────────────────
# 示例 ANNA 源码
# ─────────────────────────────────────────────

SAMPLE_SOURCE = """
module ecommerce.product
    @version("1.0.0")
    @stability(stable)
    @ai_context(`
        商品模块管理商品目录、库存和定价。
        price 单位为分（Int64）。
        status 枚举控制商品生命周期。
    `)
{
    type ProductStatus {
        | Draft
        | Active   { since: UInt64 }
        | Inactive { reason: Str }
    }

    type Product {
        id:       UInt64
        name:     Str
        price:    Int64 where self >= 0
        stock:    UInt32
        status:   ProductStatus
    }

    type ProductError {
        | InvalidPrice   { given: Int64 }
        | OutOfStock     { product_id: UInt64, available: UInt32 }
        | StatusConflict { required: ProductStatus, actual: ProductStatus }
    }

    @public
    fn create_product(name: Str, price: Int64, initial_stock: UInt32) -> Result<Product, ProductError> {
        intent "创建新商品，初始状态为草稿"

        require price >= 0
            @msg("价格不能为负")
        require name.len() > 0
            @msg("商品名称不能为空")

        return Ok(Product {
            id:     generate_id(),
            name:   name,
            price:  price,
            stock:  initial_stock,
            status: ProductStatus::Draft,
        })
    }

    @public
    fn deduct_stock(product: Product, quantity: UInt32) -> Result<Product, ProductError> {
        intent "扣减商品库存"

        require quantity > 0
        require product.stock >= quantity
            @msg("库存不足")

        return Ok(Product {
            stock: product.stock - quantity,
            ..product
        })
    }

    @public
    fn activate(product: Product) -> Result<Product, ProductError> {
        intent "将草稿商品激活上架"

        require product.price > 0
            @msg("激活商品价格必须大于零")

        return Ok(Product {
            status: ProductStatus::Active { since: current_timestamp() },
            ..product
        })
    }
}
"""


# ─────────────────────────────────────────────
# 演示函数
# ─────────────────────────────────────────────

def demo_lexer(source: str):
    print("=" * 60)
    print("§1  词法分析（Lexer）")
    print("=" * 60)
    tokens = tokenize(source)
    # 只显示前 40 个 token
    for tok in tokens[:40]:
        print(f"  {tok.kind.name:<20} {tok.value!r:<30} ({tok.line}:{tok.col})")
    if len(tokens) > 40:
        print(f"  ... （共 {len(tokens)} 个 Token）")
    print()


def demo_parser(source: str) -> Program:
    print("=" * 60)
    print("§2  语法解析（Parser）")
    print("=" * 60)
    program = parse(source)

    print(f"  模块: {program.module.path if program.module else '(无)'}")
    print(f"  顶级元素: {len(program.items)} 个")
    print()

    for item in program.items:
        kind = type(item).__name__
        name = getattr(item, 'name', '?')
        print(f"  [{kind}] {name}")

        # 打印函数详情
        from anna.ast_nodes import FnDef, StructTypeDef, EnumTypeDef
        if isinstance(item, FnDef):
            params_str = ', '.join(f"{p.name}: {_type_str(p.ty)}" for p in item.params)
            ret_str    = f" -> {_type_str(item.ret)}" if item.ret else ""
            effects    = ' '.join(f"!{e}" for e in item.effects) if item.effects else ""
            print(f"    fn({params_str}){ret_str} {effects}")
            # 打印 intent
            from anna.ast_nodes import IntentDecl
            for body_item in item.body.items:
                if isinstance(body_item, IntentDecl):
                    print(f"    intent: {body_item.text!r}")
                    break

        elif isinstance(item, StructTypeDef):
            for f in item.fields:
                print(f"    .{f.name}: {_type_str(f.ty)}")

        elif isinstance(item, EnumTypeDef):
            for v in item.variants:
                fields_str = ', '.join(f"{f.name}: {_type_str(f.ty)}" for f in v.fields)
                print(f"    | {v.name} {{ {fields_str} }}" if fields_str else f"    | {v.name}")

    print()
    return program


def demo_patch_engine(program: Program):
    print("=" * 60)
    print("§3  Patch 引擎")
    print("=" * 60)

    from anna.ast_nodes import (
        PatchModifyFields, FieldPatchOp, TypeName
    )

    # ── Patch 1：向 ProductError 枚举添加新变体 ──
    new_variant = EnumVariant(
        name="Discontinued",
        fields=(
            FieldDef(
                name="product_id",
                ty=TypeName(name="UInt64"),
                metadata=Metadata(annotations=()),
            ),
        ),
        types=(),
    )

    patch1 = PatchDef(
        target=PatchTarget(path="#ecommerce.product.ProductError",
                           parts=("ecommerce", "product", "ProductError")),
        op=PatchInsertCase(
            position="after",
            anchor_ref="#ecommerce.product.ProductError.StatusConflict",
            variants=(new_variant,),
        ),
        metadata=Metadata(annotations=(
            Annotation(name="reason",     args=("添加商品下架错误类型",)),
            Annotation(name="author",     args=("@ai",)),
            Annotation(name="confidence", args=(0.96,)),
        )),
    )

    # ── Patch 2：重命名函数 ──────────────────────
    patch2 = PatchDef(
        target=PatchTarget(path="#ecommerce.product.activate",
                           parts=("ecommerce", "product", "activate")),
        op=PatchRename(new_name="publish", cascade=True),
        metadata=Metadata(annotations=(
            Annotation(name="reason",     args=("'activate' 在产品语言中改为 'publish'",)),
            Annotation(name="author",     args=("@ai",)),
            Annotation(name="confidence", args=(0.99,)),
        )),
    )

    # ── Patch 3：修改结构体字段 ─────────────────
    patch3 = PatchDef(
        target=PatchTarget(path="#ecommerce.product.Product",
                           parts=("ecommerce", "product", "Product")),
        op=PatchModifyFields(ops=(
            FieldPatchOp(kind="add", name="sku",
                         ty=TypeName(name="Str"),
                         annotations=(Annotation(name="reason", args=("添加 SKU 字段用于库存管理",)),)),
            FieldPatchOp(kind="change_type", name="price",
                         ty=TypeName(name="Int64"),
                         new_ty=TypeName(name="UInt64")),
        )),
        metadata=Metadata(annotations=(
            Annotation(name="reason",     args=("扩展 Product 结构体",)),
            Annotation(name="author",     args=("@ai",)),
            Annotation(name="confidence", args=(0.93,)),
        )),
    )

    # ── Patch 4：删除辅助函数 ────────────────────
    patch4 = PatchDef(
        target=PatchTarget(path="#ecommerce.product.deduct_stock",
                           parts=("ecommerce", "product", "deduct_stock")),
        op=PatchDelete(),
        metadata=Metadata(annotations=(
            Annotation(name="reason",     args=("库存扣减移至 inventory 模块统一处理",)),
            Annotation(name="author",     args=("@ai",)),
            Annotation(name="confidence", args=(0.87,)),
        )),
    )

    patches = [patch1, patch2, patch3, patch4]

    print(f"  准备应用 {len(patches)} 个 patch...\n")

    session = apply_patches(program, patches)
    print(session.report())
    print()

    # 展示应用 patch 后的 AST 变化
    print("  ── 应用 Patch 后的 AST ────────────────────")
    for item in session.program.items:
        from anna.ast_nodes import FnDef, StructTypeDef, EnumTypeDef
        kind = type(item).__name__
        name = getattr(item, 'name', '?')
        print(f"  [{kind}] {name}")

        if isinstance(item, EnumTypeDef):
            for v in item.variants:
                fstr = ', '.join(f"{f.name}: {_type_str(f.ty)}" for f in v.fields)
                print(f"    | {v.name}" + (f" {{ {fstr} }}" if fstr else ""))

        elif isinstance(item, StructTypeDef):
            for f in item.fields:
                print(f"    .{f.name}: {_type_str(f.ty)}")

    print()


def demo_query():
    print("=" * 60)
    print("§4  Query 系统（概念展示）")
    print("=" * 60)

    queries = [
        ("q-io-functions",
         "find fn\nwhere has_effect(!IO)\nreturn [path, intent]",
         "查找所有有 IO 副作用的函数"),

        ("q-missing-contracts",
         "find fn\nwhere has_annotation(@public)\nwhere !has_contract\nreturn [path, module]",
         "查找缺少契约的公开函数"),

        ("q-low-confidence-patches",
         "find patch\nwhere @author == @ai\nwhere confidence < 0.9\nreturn [id, target, confidence]\nlimit 10",
         "查找 AI 生成但置信度低的 patches"),
    ]

    for qid, body, desc in queries:
        print(f"  @id({qid!r})")
        print(f"  描述: {desc}")
        print(f"  query {{")
        for line in body.split('\n'):
            print(f"    {line}")
        print(f"  }}")
        print()


def _type_str(ty) -> str:
    """将类型节点转换为简短字符串（用于显示）。"""
    if ty is None:
        return "Unit"
    from anna.ast_nodes import TypeName, GenericType, RefinedType, FnType, TupleType
    if isinstance(ty, TypeName):
        return ty.name
    if isinstance(ty, GenericType):
        params = ', '.join(_type_str(p) for p in ty.params)
        return f"{ty.base}<{params}>"
    if isinstance(ty, RefinedType):
        return f"{_type_str(ty.base)} where ..."
    if isinstance(ty, FnType):
        params = ', '.join(_type_str(p) for p in ty.params)
        return f"fn({params}) -> {_type_str(ty.ret)}"
    if isinstance(ty, TupleType):
        elems = ', '.join(_type_str(e) for e in ty.elements)
        return f"({elems})"
    return repr(ty)


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           ANNA Language — Prototype Demo v0.1           ║")
    print("║     AI-Native Notation & Action Language                 ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    source = SAMPLE_SOURCE

    # 如果提供了文件路径，读取文件
    if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], encoding="utf-8") as f:
            source = f.read()
        print(f"  [从文件加载] {sys.argv[1]}\n")

    try:
        demo_lexer(source)
        program = demo_parser(source)
        demo_patch_engine(program)
        demo_query()

        print("=" * 60)
        print("  Demo 完成。")
        print("  ANNA 设计目标：让 AI 以结构语义而非文本行操作代码。")
        print("=" * 60)

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
