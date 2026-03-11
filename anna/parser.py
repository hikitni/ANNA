"""
ANNA Language — Recursive Descent Parser
anna/parser.py

将 Token 流转换为 AST。
"""

from __future__ import annotations
from typing import Callable
from .lexer import Token, TK, tokenize
from .ast_nodes import *


class ParseError(Exception):
    def __init__(self, msg: str, tok: Token):
        super().__init__(f"[ParseError {tok.line}:{tok.col}] {msg} (got {tok.kind.name} {tok.value!r})")
        self.token = tok


class Parser:
    """
    ANNA 递归下降解析器。

    usage:
        ast = Parser(tokens).parse()
    """

    def __init__(self, tokens: list[Token]):
        self._tokens = tokens
        self._pos    = 0

    # ── 位置辅助 ──────────────────────────────

    @property
    def _cur(self) -> Token:
        return self._tokens[self._pos]

    def _peek(self, offset: int = 1) -> Token:
        idx = self._pos + offset
        return self._tokens[idx] if idx < len(self._tokens) else self._tokens[-1]

    def _advance(self) -> Token:
        tok = self._cur
        if tok.kind != TK.EOF:
            self._pos += 1
        return tok

    def _expect(self, kind: TK) -> Token:
        if self._cur.kind != kind:
            raise ParseError(f"期望 {kind.name}", self._cur)
        return self._advance()

    def _check(self, *kinds: TK) -> bool:
        return self._cur.kind in kinds

    def _match(self, *kinds: TK) -> Token | None:
        if self._cur.kind in kinds:
            return self._advance()
        return None

    def _at_end(self) -> bool:
        return self._cur.kind == TK.EOF

    def _here(self) -> tuple[int, int]:
        return self._cur.line, self._cur.col

    # ── 主入口 ────────────────────────────────

    def parse(self) -> Program:
        line, col = self._here()
        module = None
        if self._check(TK.KW_MODULE):
            module = self._parse_module_decl()

        # 模块可能有 { ... } 包裹体，也可能没有
        has_brace = bool(self._match(TK.LBRACE))

        items: list[TopLevelItem] = []
        stop = (TK.RBRACE, TK.EOF) if has_brace else (TK.EOF,)
        while not self._check(*stop):
            items.append(self._parse_top_level())

        if has_brace:
            self._expect(TK.RBRACE)

        return Program(module=module, items=tuple(items), line=line, col=col)

    # ── 模块声明 ──────────────────────────────

    def _parse_module_decl(self) -> ModuleDecl:
        line, col = self._here()
        self._expect(TK.KW_MODULE)
        path = self._parse_module_path()
        meta = self._parse_metadata()
        # 可选的 { ... } 块（顶级模块无块体时，后续项直接跟随）
        if self._check(TK.LBRACE):
            # 此处简化：顶级 module 块解析留给 parse() 递归处理
            pass
        return ModuleDecl(path=path, metadata=meta, line=line, col=col)

    def _parse_module_path(self) -> str:
        parts = [self._expect(TK.IDENT).value]
        while self._check(TK.DOT) and self._peek().kind == TK.IDENT:
            self._advance()
            parts.append(self._expect(TK.IDENT).value)
        return '.'.join(parts)

    # ── 顶级元素 ──────────────────────────────

    def _parse_top_level(self) -> TopLevelItem:
        annots = self._parse_annotations()

        if self._check(TK.KW_FN):
            return self._parse_fn_def(annots)
        if self._check(TK.KW_TYPE):
            return self._parse_type_def(annots)
        if self._check(TK.KW_CONST):
            return self._parse_const_def(annots)
        if self._check(TK.KW_USE):
            return self._parse_import()
        if self._check(TK.KW_PATCH_GROUP):
            return self._parse_patch_group(annots)
        if self._check(TK.KW_PATCH):
            return self._parse_patch_def(annots)
        if self._check(TK.KW_QUERY):
            return self._parse_query_def(annots)

        raise ParseError("期望顶级声明（fn/type/const/use/patch/query）", self._cur)

    # ── 注解 ──────────────────────────────────

    def _parse_annotations(self) -> Metadata:
        line, col = self._here()
        annots: list[Annotation] = []
        while self._check(TK.ANNOT):
            tok = self._advance()
            name = tok.value[1:]  # strip @
            args: list = []
            if self._check(TK.LPAREN):
                self._advance()
                while not self._check(TK.RPAREN, TK.EOF):
                    args.append(self._parse_ann_arg())
                    self._match(TK.COMMA)
                self._expect(TK.RPAREN)
            annots.append(Annotation(name=name, args=tuple(args), line=tok.line, col=tok.col))
        return Metadata(annotations=tuple(annots), line=line, col=col)

    def _parse_ann_arg(self):
        if self._check(TK.STRING):
            return self._advance().value
        if self._check(TK.RAW_STRING):
            return self._advance().value
        if self._check(TK.INTEGER):
            return int(self._advance().value)
        if self._check(TK.FLOAT):
            return float(self._advance().value)
        if self._check(TK.BOOL):
            return self._advance().value == "true"
        if self._check(TK.ANNOT):
            return self._advance().value   # @ai 等引用
        if self._check(TK.STRUCT_REF):
            return self._advance().value
        # 嵌套括号（如 confidence < 0.8）
        if self._check(TK.IDENT):
            return self._advance().value
        return str(self._advance().value)

    def _parse_metadata(self) -> Metadata:
        return self._parse_annotations()

    # ── 函数定义 ──────────────────────────────

    def _parse_fn_def(self, meta: Metadata) -> FnDef:
        line, col = self._here()
        self._expect(TK.KW_FN)
        name = self._expect(TK.IDENT).value

        self._expect(TK.LPAREN)
        params = self._parse_param_list()
        self._expect(TK.RPAREN)

        ret = None
        if self._match(TK.ARROW):
            ret = self._parse_type_expr()

        effects = self._parse_effects()

        body = self._parse_fn_body()
        return FnDef(name=name, params=params, ret=ret, effects=effects,
                     body=body, metadata=meta, line=line, col=col)

    def _parse_param_list(self) -> tuple[Param, ...]:
        params: list[Param] = []
        while not self._check(TK.RPAREN, TK.EOF):
            params.append(self._parse_param())
            if not self._match(TK.COMMA):
                break
        return tuple(params)

    def _parse_param(self) -> Param:
        line, col = self._here()
        name = self._expect(TK.IDENT).value
        self._expect(TK.COLON)
        ty = self._parse_type_expr()
        default = None
        if self._match(TK.EQ):
            default = self._parse_expr()
        return Param(name=name, ty=ty, default=default, line=line, col=col)

    def _parse_effects(self) -> tuple[str, ...]:
        effects = []
        while self._check(TK.BANG):
            self._advance()
            # Effect可以是普通的snake_case IDENT，也可以是大写的TYPE_IDENT(如 IO)
            tok = self._match(TK.IDENT, TK.TYPE_IDENT)
            if not tok:
                raise ParseError("期望 Effect 名称 (IDENT 或 TYPE_IDENT)", self._cur)
            effects.append(tok.value)
        return tuple(effects)

    def _parse_fn_body(self) -> FnBody:
        line, col = self._here()
        self._expect(TK.LBRACE)
        items: list[FnBodyItem] = []
        while not self._check(TK.RBRACE, TK.EOF):
            item = self._parse_fn_body_item()
            if item is not None:
                items.append(item)
        self._expect(TK.RBRACE)
        return FnBody(items=tuple(items), line=line, col=col)

    def _parse_fn_body_item(self) -> FnBodyItem | None:
        if self._check(TK.KW_INTENT):
            return self._parse_intent()
        if self._check(TK.KW_REQUIRE):
            return self._parse_require()
        if self._check(TK.KW_ENSURE):
            return self._parse_ensure()
        # @block("name") { ... }
        if self._check(TK.ANNOT) and self._cur.value == "@block":
            return self._parse_named_block()
        return self._parse_stmt()

    def _parse_intent(self) -> IntentDecl:
        line, col = self._here()
        self._expect(TK.KW_INTENT)
        text = self._expect(TK.STRING).value
        return IntentDecl(text=text, line=line, col=col)

    def _parse_require(self) -> RequireDecl:
        line, col = self._here()
        self._expect(TK.KW_REQUIRE)
        cond = self._parse_expr()
        annots = self._parse_annotations()
        return RequireDecl(condition=cond, annotations=annots.annotations, line=line, col=col)

    def _parse_ensure(self) -> EnsureDecl:
        line, col = self._here()
        self._expect(TK.KW_ENSURE)
        cond = self._parse_expr()
        annots = self._parse_annotations()
        return EnsureDecl(condition=cond, annotations=annots.annotations, line=line, col=col)

    def _parse_named_block(self) -> NamedBlock:
        line, col = self._here()
        self._advance()  # consume @block
        self._expect(TK.LPAREN)
        block_id = self._expect(TK.STRING).value
        self._expect(TK.RPAREN)
        body = self._parse_block_expr()
        return NamedBlock(block_id=block_id, body=body, line=line, col=col)

    # ── 语句 ──────────────────────────────────

    def _parse_stmt(self) -> Stmt:
        if self._check(TK.KW_LET):
            return self._parse_let()
        if self._check(TK.KW_RETURN):
            return self._parse_return()
        if self._check(TK.KW_IF):
            return self._parse_if()
        if self._check(TK.KW_MATCH):
            return self._parse_match()
        if self._check(TK.KW_LOOP):
            return self._parse_loop()
        if self._check(TK.KW_WHILE):
            return self._parse_while()
        if self._check(TK.KW_FOR):
            return self._parse_for()
        if self._check(TK.KW_BREAK):
            return self._parse_break()
        if self._check(TK.KW_CONTINUE):
            line, col = self._here()
            self._advance()
            return ContinueStmt(line=line, col=col)
        # 表达式语句
        line, col = self._here()
        expr = self._parse_expr()
        return ExprStmt(expr=expr, line=line, col=col)

    def _parse_let(self) -> LetStmt:
        line, col = self._here()
        self._expect(TK.KW_LET)
        mutable = bool(self._match(TK.KW_MUT))
        name = self._expect(TK.IDENT).value
        ty = None
        if self._match(TK.COLON):
            ty = self._parse_type_expr()
        self._expect(TK.EQ)
        value = self._parse_expr()
        return LetStmt(name=name, ty=ty, value=value, mutable=mutable, line=line, col=col)

    def _parse_return(self) -> ReturnStmt:
        line, col = self._here()
        self._expect(TK.KW_RETURN)
        val = None
        if not self._check(TK.RBRACE, TK.EOF):
            val = self._parse_expr()
        return ReturnStmt(value=val, line=line, col=col)

    def _parse_if(self) -> IfStmt:
        line, col = self._here()
        self._expect(TK.KW_IF)
        cond = self._parse_expr()
        then_body = self._parse_block_expr()
        else_body = None
        if self._match(TK.KW_ELSE):
            if self._check(TK.KW_IF):
                else_body = self._parse_if()
            else:
                else_body = self._parse_block_expr()
        return IfStmt(cond=cond, then_body=then_body, else_body=else_body, line=line, col=col)

    def _parse_match(self) -> MatchStmt:
        line, col = self._here()
        self._expect(TK.KW_MATCH)
        scrutinee = self._parse_expr()
        self._expect(TK.LBRACE)
        arms: list[MatchArm] = []
        while not self._check(TK.RBRACE, TK.EOF):
            arms.append(self._parse_match_arm())
        self._expect(TK.RBRACE)
        return MatchStmt(scrutinee=scrutinee, arms=tuple(arms), line=line, col=col)

    def _parse_match_arm(self) -> MatchArm:
        line, col = self._here()
        self._expect(TK.PIPE)
        pattern = self._parse_pattern()
        self._expect(TK.FAT_ARROW)
        if self._check(TK.LBRACE):
            body = self._parse_block_expr()
        else:
            body = self._parse_expr()
        return MatchArm(pattern=pattern, body=body, line=line, col=col)

    def _parse_pattern(self) -> Pattern:
        line, col = self._here()
        if self._check(TK.IDENT) and self._cur.value == '_':
            self._advance()
            return WildcardPattern(line=line, col=col)
        if self._check(TK.TYPE_IDENT):
            type_name = self._advance().value
            fields: list[tuple[str, Pattern | None]] = []
            if self._check(TK.LBRACE):
                self._advance()
                while not self._check(TK.RBRACE, TK.EOF):
                    fname = self._expect(TK.IDENT).value
                    subpat = None
                    if self._match(TK.COLON):
                        subpat = self._parse_pattern()
                    fields.append((fname, subpat))
                    self._match(TK.COMMA)
                self._expect(TK.RBRACE)
            return StructPattern(type_name=type_name, fields=tuple(fields), line=line, col=col)
        if self._check(TK.IDENT):
            name = self._advance().value
            return IdentPattern(name=name, line=line, col=col)
        # Literal pattern
        expr = self._parse_primary()
        return LiteralPattern(literal=expr, line=line, col=col)

    def _parse_loop(self) -> LoopStmt:
        line, col = self._here()
        self._expect(TK.KW_LOOP)
        body = self._parse_block_expr()
        return LoopStmt(body=body, line=line, col=col)

    def _parse_while(self) -> WhileStmt:
        line, col = self._here()
        self._expect(TK.KW_WHILE)
        cond = self._parse_expr()
        body = self._parse_block_expr()
        return WhileStmt(cond=cond, body=body, line=line, col=col)

    def _parse_for(self) -> ForStmt:
        line, col = self._here()
        self._expect(TK.KW_FOR)
        pattern = self._parse_pattern()
        self._expect(TK.KW_IN)
        iterable = self._parse_expr()
        body = self._parse_block_expr()
        return ForStmt(pattern=pattern, iterable=iterable, body=body, line=line, col=col)

    def _parse_break(self) -> BreakStmt:
        line, col = self._here()
        self._expect(TK.KW_BREAK)
        val = None
        if not self._check(TK.RBRACE, TK.EOF):
            val = self._parse_expr()
        return BreakStmt(value=val, line=line, col=col)

    # ── 表达式（Pratt Parser）──────────────────

    _BINARY_PREC: dict[TK, int] = {
        TK.OROR:    10,
        TK.ANDAND:  20,
        TK.PIPE:    25,
        TK.CARET:   26,
        TK.AMP:     27,
        TK.EQEQ:    30,  TK.NEQ:    30,
        TK.LT:      40,  TK.GT:     40,  TK.LEQ:    40,  TK.GEQ:    40,
        TK.APPROX:  40,
        TK.SHL:     50,  TK.SHR:    50,
        TK.DOTDOT:  55,  TK.DOTDOTEQ: 55,
        TK.PLUS:    60,  TK.MINUS:  60,
        TK.STAR:    70,  TK.SLASH:  70,  TK.PERCENT: 70,
        TK.PIPELINE: 5,
    }

    _BINARY_OPS = set(_BINARY_PREC.keys())

    def _parse_expr(self, min_prec: int = 0) -> Expr:
        line, col = self._here()
        left = self._parse_unary()

        while True:
            if self._cur.kind not in self._BINARY_OPS:
                break
            prec = self._BINARY_PREC[self._cur.kind]
            if prec <= min_prec:
                break
            op_tok = self._advance()
            op = op_tok.value

            if op_tok.kind == TK.PIPELINE:
                right = self._parse_unary()
                left = Pipeline(value=left, fn=right, line=line, col=col)
            elif op_tok.kind == TK.APPROX:
                right = self._parse_unary()
                tolerance = None
                # @tolerance(...)
                if self._check(TK.ANNOT) and self._cur.value == "@tolerance":
                    self._advance()
                    self._expect(TK.LPAREN)
                    tolerance = self._parse_expr()
                    self._expect(TK.RPAREN)
                left = ApproxEq(left=left, right=right, tolerance=tolerance, line=line, col=col)
            else:
                right = self._parse_expr(prec)
                left = BinOp(op=op, left=left, right=right, line=line, col=col)

        return left

    def _parse_unary(self) -> Expr:
        line, col = self._here()
        if self._check(TK.MINUS):
            self._advance()
            return UnaryOp(op='-', operand=self._parse_unary(), line=line, col=col)
        if self._check(TK.BANG):
            self._advance()
            return UnaryOp(op='!', operand=self._parse_unary(), line=line, col=col)
        if self._check(TK.TILDE):
            self._advance()
            return UnaryOp(op='~', operand=self._parse_unary(), line=line, col=col)
        return self._parse_postfix()

    def _parse_postfix(self) -> Expr:
        expr = self._parse_primary()
        while True:
            if self._check(TK.DOT):
                self._advance()
                method = self._expect(TK.IDENT).value
                if self._check(TK.LPAREN):
                    self._advance()
                    args = self._parse_call_args()
                    self._expect(TK.RPAREN)
                    expr = MethodCall(receiver=expr, method=method, args=args,
                                      line=expr.line, col=expr.col)
                else:
                    # field access — 视作 ident
                    expr = MethodCall(receiver=expr, method=method, args=(),
                                      line=expr.line, col=expr.col)
            elif self._check(TK.LPAREN) and isinstance(expr, Ident):
                self._advance()
                args = self._parse_call_args()
                self._expect(TK.RPAREN)
                expr = Call(callee=expr, args=args, line=expr.line, col=expr.col)
            else:
                break
        return expr

    def _parse_call_args(self) -> tuple[CallArg, ...]:
        args: list[CallArg] = []
        while not self._check(TK.RPAREN, TK.EOF):
            line, col = self._here()
            label = None
            if self._check(TK.IDENT) and self._peek().kind == TK.COLON:
                label = self._advance().value
                self._advance()  # colon
            val = self._parse_expr()
            args.append(CallArg(value=val, label=label, line=line, col=col))
            if not self._match(TK.COMMA):
                break
        return tuple(args)

    def _parse_primary(self) -> Expr:
        line, col = self._here()

        if self._check(TK.INTEGER):
            val = int(self._advance().value, 0)
            return IntLit(value=val, line=line, col=col)

        if self._check(TK.FLOAT):
            val = float(self._advance().value)
            return FloatLit(value=val, line=line, col=col)

        if self._check(TK.STRING):
            val = self._advance().value
            return StrLit(value=val, line=line, col=col)

        if self._check(TK.RAW_STRING):
            val = self._advance().value
            return StrLit(value=val, raw=True, line=line, col=col)

        if self._check(TK.BOOL):
            val = self._advance().value == "true"
            return BoolLit(value=val, line=line, col=col)

        if self._check(TK.STRUCT_REF):
            tok = self._advance()
            parts = tuple(tok.value[1:].split('.'))
            return StructRef(path=tok.value, parts=parts, line=line, col=col)

        if self._check(TK.LBRACE):
            return self._parse_block_expr()

        if self._check(TK.IDENT):
            name = self._advance().value
            return Ident(name=name, line=line, col=col)

        if self._check(TK.TYPE_IDENT):
            name = self._advance().value
            # 作用域访问 TypeName::Member（枚举变体构造）
            if self._check(TK.COLONCOLON):
                self._advance()  # consume ::
                member = self._cur.value
                self._advance()  # consume member name
                full_name = f"{name}::{member}"
                # 可能还有 { ... } 的结构体字面量
                if self._check(TK.LBRACE):
                    return self._parse_struct_lit(full_name, line, col)
                return Ident(name=full_name, line=line, col=col)
            # 结构体字面量 TypeName { ... }
            if self._check(TK.LBRACE):
                return self._parse_struct_lit(name, line, col)
            return Ident(name=name, line=line, col=col)

        if self._check(TK.LPAREN):
            self._advance()
            if self._check(TK.RPAREN):
                self._advance()
                return UnitLit(line=line, col=col)
            first = self._parse_expr()
            if self._match(TK.COMMA):
                elems = [first]
                while not self._check(TK.RPAREN, TK.EOF):
                    elems.append(self._parse_expr())
                    if not self._match(TK.COMMA):
                        break
                self._expect(TK.RPAREN)
                return TupleExpr(elements=tuple(elems), line=line, col=col)
            self._expect(TK.RPAREN)
            return first

        if self._check(TK.LBRACKET):
            self._advance()
            elems: list[Expr] = []
            while not self._check(TK.RBRACKET, TK.EOF):
                elems.append(self._parse_expr())
                if not self._match(TK.COMMA):
                    break
            self._expect(TK.RBRACKET)
            return ArrayExpr(elements=tuple(elems), line=line, col=col)

        if self._check(TK.PIPE):
            return self._parse_closure()

        raise ParseError("期望表达式", self._cur)

    def _parse_block_expr(self) -> BlockExpr:
        line, col = self._here()
        self._expect(TK.LBRACE)
        stmts: list[Stmt] = []
        final_expr = None
        while not self._check(TK.RBRACE, TK.EOF):
            # 简化：所有均视为语句
            stmts.append(self._parse_stmt())
        self._expect(TK.RBRACE)
        return BlockExpr(stmts=tuple(stmts), final_expr=final_expr, line=line, col=col)

    def _parse_struct_lit(self, name: str, line: int, col: int) -> StructLit:
        self._expect(TK.LBRACE)
        fields: list[tuple[str, Expr]] = []
        spread = None
        while not self._check(TK.RBRACE, TK.EOF):
            if self._check(TK.DOTDOT):
                self._advance()
                spread = self._parse_expr()
                break
            fname = self._expect(TK.IDENT).value
            self._expect(TK.COLON)
            fval = self._parse_expr()
            fields.append((fname, fval))
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RBRACE)
        return StructLit(name=name, fields=tuple(fields), spread=spread, line=line, col=col)

    def _parse_closure(self) -> ClosureExpr:
        line, col = self._here()
        self._expect(TK.PIPE)
        params: list[Param] = []
        while not self._check(TK.PIPE, TK.EOF):
            params.append(self._parse_param())
            if not self._match(TK.COMMA):
                break
        self._expect(TK.PIPE)
        if self._check(TK.LBRACE):
            body = self._parse_block_expr()
        else:
            body = self._parse_expr()
        return ClosureExpr(params=tuple(params), body=body, line=line, col=col)

    # ── 类型表达式 ────────────────────────────

    def _parse_type_expr(self) -> TypeExpr:
        line, col = self._here()

        if self._check(TK.LPAREN):
            # 元组类型
            self._advance()
            types: list[TypeExpr] = []
            while not self._check(TK.RPAREN, TK.EOF):
                types.append(self._parse_type_expr())
                if not self._match(TK.COMMA):
                    break
            self._expect(TK.RPAREN)
            if len(types) == 1:
                return types[0]
            return TupleType(elements=tuple(types), line=line, col=col)

        if self._check(TK.KW_FN):
            return self._parse_fn_type()

        if self._check(TK.TYPE_IDENT):
            name = self._advance().value
            # 泛型
            if self._check(TK.LT):
                self._advance()
                params: list[TypeExpr] = []
                while not self._check(TK.GT, TK.EOF):
                    params.append(self._parse_type_expr())
                    if not self._match(TK.COMMA):
                        break
                self._expect(TK.GT)
                base = GenericType(base=name, params=tuple(params), line=line, col=col)
            else:
                base = TypeName(name=name, line=line, col=col)

            # 精化类型 where
            if self._check(TK.KW_WHERE):
                self._advance()
                constraint = self._parse_expr()
                return RefinedType(base=base, constraint=constraint, line=line, col=col)
            return base

        raise ParseError("期望类型表达式", self._cur)

    def _parse_fn_type(self) -> FnType:
        line, col = self._here()
        self._expect(TK.KW_FN)
        self._expect(TK.LPAREN)
        params: list[TypeExpr] = []
        while not self._check(TK.RPAREN, TK.EOF):
            params.append(self._parse_type_expr())
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RPAREN)
        self._expect(TK.ARROW)
        ret = self._parse_type_expr()
        effects = self._parse_effects()
        return FnType(params=tuple(params), ret=ret, effects=effects, line=line, col=col)

    # ── 类型定义 ──────────────────────────────

    def _parse_type_def(self, meta: Metadata) -> TypeDef:
        line, col = self._here()
        self._expect(TK.KW_TYPE)
        name = self._expect(TK.TYPE_IDENT).value
        generics = self._parse_generic_params()

        # 别名 type Foo = Bar
        if self._match(TK.EQ):
            target = self._parse_type_expr()
            constraint = None
            if self._match(TK.KW_WHERE):
                constraint = self._parse_expr()
            return AliasTypeDef(name=name, generics=generics, target=target,
                                constraint=constraint, metadata=meta, line=line, col=col)

        self._expect(TK.LBRACE)

        # 枚举 vs 结构体：枚举以 | 开头
        if self._check(TK.PIPE):
            variants: list[EnumVariant] = []
            while self._check(TK.PIPE):
                variants.append(self._parse_enum_variant())
            self._expect(TK.RBRACE)
            return EnumTypeDef(name=name, generics=generics, variants=tuple(variants),
                               metadata=meta, line=line, col=col)

        # 结构体
        fields: list[FieldDef] = []
        while not self._check(TK.RBRACE, TK.EOF):
            field_meta = self._parse_metadata()
            fname = self._expect(TK.IDENT).value
            self._expect(TK.COLON)
            fty = self._parse_type_expr()
            fields.append(FieldDef(name=fname, ty=fty, metadata=field_meta,
                                   line=self._cur.line, col=self._cur.col))
            self._match(TK.COMMA)
        self._expect(TK.RBRACE)
        return StructTypeDef(name=name, generics=generics, fields=tuple(fields),
                             metadata=meta, line=line, col=col)

    def _parse_generic_params(self) -> tuple[str, ...]:
        if not self._check(TK.LT):
            return ()
        self._advance()
        params: list[str] = []
        while not self._check(TK.GT, TK.EOF):
            params.append(self._expect(TK.TYPE_IDENT).value)
            if not self._match(TK.COMMA):
                break
        self._expect(TK.GT)
        return tuple(params)

    def _parse_enum_variant(self) -> EnumVariant:
        line, col = self._here()
        self._expect(TK.PIPE)
        name = self._expect(TK.TYPE_IDENT).value
        fields: list[FieldDef] = []
        types: list[TypeExpr] = []
        if self._check(TK.LBRACE):
            self._advance()
            while not self._check(TK.RBRACE, TK.EOF):
                meta = self._parse_metadata()
                fname = self._expect(TK.IDENT).value
                self._expect(TK.COLON)
                fty = self._parse_type_expr()
                fields.append(FieldDef(name=fname, ty=fty, metadata=meta,
                                       line=self._cur.line, col=self._cur.col))
                self._match(TK.COMMA)
            self._expect(TK.RBRACE)
        elif self._check(TK.LPAREN):
            self._advance()
            while not self._check(TK.RPAREN, TK.EOF):
                types.append(self._parse_type_expr())
                if not self._match(TK.COMMA):
                    break
            self._expect(TK.RPAREN)
        return EnumVariant(name=name, fields=tuple(fields), types=tuple(types),
                           line=line, col=col)

    # ── 常量定义 ──────────────────────────────

    def _parse_const_def(self, meta: Metadata) -> ConstDef:
        line, col = self._here()
        self._expect(TK.KW_CONST)
        name = self._expect(TK.CONST_IDENT).value
        self._expect(TK.COLON)
        ty = self._parse_type_expr()
        self._expect(TK.EQ)
        val = self._parse_expr()
        return ConstDef(name=name, ty=ty, value=val, metadata=meta, line=line, col=col)

    # ── Import ────────────────────────────────

    def _parse_import(self) -> ImportStmt:
        line, col = self._here()
        self._expect(TK.KW_USE)
        path = self._parse_module_path()
        items: list[tuple[str, str | None]] = []
        glob = False
        if self._check(TK.DOT):
            self._advance()
            if self._check(TK.LBRACE):
                self._advance()
                while not self._check(TK.RBRACE, TK.EOF):
                    name = self._expect(TK.IDENT).value
                    alias = None
                    if self._match(TK.KW_AS):
                        alias = self._expect(TK.IDENT).value
                    items.append((name, alias))
                    if not self._match(TK.COMMA):
                        break
                self._expect(TK.RBRACE)
            elif self._check(TK.STAR):
                self._advance()
                glob = True
        return ImportStmt(path=path, items=tuple(items), glob=glob, line=line, col=col)

    # ── Patch ────────────────────────────────

    def _parse_patch_def(self, meta: Metadata) -> PatchDef:
        line, col = self._here()
        self._expect(TK.KW_PATCH)
        target_tok = self._expect(TK.STRUCT_REF)
        target_path = target_tok.value
        target_parts = tuple(target_path[1:].split('.'))
        target = PatchTarget(path=target_path, parts=target_parts,
                             line=target_tok.line, col=target_tok.col)
        extra_meta = self._parse_metadata()
        # 合并 meta
        all_annots = meta.annotations + extra_meta.annotations
        merged_meta = Metadata(annotations=all_annots, line=meta.line, col=meta.col)

        self._expect(TK.LBRACE)
        op = self._parse_patch_op()
        self._expect(TK.RBRACE)
        return PatchDef(target=target, op=op, metadata=merged_meta, line=line, col=col)

    def _parse_patch_op(self) -> "PatchOp":
        line, col = self._here()
        if self._check(TK.KW_REPLACE_WITH):
            self._advance()
            content = self._read_raw_block()
            return PatchReplace(content=content, line=line, col=col)
        if self._check(TK.KW_INSERT_BEFORE):
            self._advance()
            content = self._read_raw_block()
            return PatchInsertBefore(content=content, line=line, col=col)
        if self._check(TK.KW_INSERT_AFTER):
            self._advance()
            content = self._read_raw_block()
            return PatchInsertAfter(content=content, line=line, col=col)
        if self._check(TK.KW_DELETE):
            self._advance()
            return PatchDelete(line=line, col=col)
        if self._check(TK.KW_RENAME_TO):
            self._advance()
            # rename_to 的新名称可能是 IDENT (snake_case) 或 TYPE_IDENT (PascalCase)
            if self._check(TK.TYPE_IDENT):
                new_name = self._advance().value
            else:
                new_name = self._expect(TK.IDENT).value
            meta = self._parse_metadata()
            cascade = True
            if ann := meta.get("cascade"):
                cascade = ann.args[0] if ann.args else True
            return PatchRename(new_name=new_name, cascade=cascade, line=line, col=col)
        if self._check(TK.KW_INSERT_CASE):
            return self._parse_insert_case(line, col)

        # ── v1.1 高级重构原语 ──

        # move_to #dest.path @cascade(true)
        if self._check(TK.KW_MOVE_TO):
            self._advance()
            dest = self._expect(TK.STRUCT_REF).value
            meta = self._parse_metadata()
            cascade = True
            if ann := meta.get("cascade"):
                val = ann.args[0] if ann.args else True
                cascade = val if isinstance(val, bool) else str(val).lower() == "true"
            return PatchMoveTo(dest_path=dest, cascade=cascade, line=line, col=col)

        # copy_to #dest.path new_name: name
        if self._check(TK.KW_COPY_TO):
            self._advance()
            dest = self._expect(TK.STRUCT_REF).value
            new_name = None
            if self._check(TK.IDENT) and self._cur.value == "new_name":
                self._advance()
                self._expect(TK.COLON)
                if self._check(TK.TYPE_IDENT):
                    new_name = self._advance().value
                else:
                    new_name = self._expect(TK.IDENT).value
            return PatchCopyTo(dest_path=dest, new_name=new_name, line=line, col=col)

        # wrap_with { template __BODY__ template }
        if self._check(TK.KW_WRAP_WITH):
            self._advance()
            template = self._read_raw_block()
            return PatchWrapWith(template=template, line=line, col=col)

        # extract_interface TraitName methods: [m1, m2]
        if self._check(TK.KW_EXTRACT_INTERFACE):
            self._advance()
            if self._check(TK.TYPE_IDENT):
                iface_name = self._advance().value
            else:
                iface_name = self._expect(TK.IDENT).value
            methods: list[str] = []
            if self._check(TK.IDENT) and self._cur.value == "methods":
                self._advance()
                self._expect(TK.COLON)
                self._expect(TK.LBRACKET)
                while not self._check(TK.RBRACKET, TK.EOF):
                    methods.append(self._expect(TK.IDENT).value)
                    if not self._match(TK.COMMA):
                        break
                self._expect(TK.RBRACKET)
            return PatchExtractInterface(interface_name=iface_name, methods=tuple(methods), line=line, col=col)

        # resolve_patch(conflict_id: "...", resolution: "...")
        if self._check(TK.KW_RESOLVE_PATCH):
            self._advance()
            self._expect(TK.LPAREN)
            conflict_id = ""
            resolution = ""
            while not self._check(TK.RPAREN, TK.EOF):
                key = self._expect(TK.IDENT).value
                self._expect(TK.COLON)
                val = self._expect(TK.STRING).value
                if key == "conflict_id":
                    conflict_id = val
                elif key == "resolution":
                    resolution = val
                if not self._match(TK.COMMA):
                    break
            self._expect(TK.RPAREN)
            return PatchResolvePatch(conflict_id=conflict_id, resolution=resolution, line=line, col=col)

        # ── 参数/字段修改操作（可包含多条子操作） ──

        # add_param name: Type = default @position(last)
        if self._check(TK.KW_ADD_PARAM):
            self._advance()
            ops = [self._parse_param_patch_op("add")]
            return PatchModifyParams(ops=tuple(ops), line=line, col=col)

        # remove_param name
        if self._check(TK.KW_REMOVE_PARAM):
            self._advance()
            name = self._expect(TK.IDENT).value
            return PatchModifyParams(
                ops=(ParamPatchOp(kind="remove", name=name, line=line, col=col),),
                line=line, col=col
            )

        # add_field name: Type
        if self._check(TK.KW_ADD_FIELD):
            self._advance()
            ops = [self._parse_field_patch_op("add")]
            return PatchModifyFields(ops=tuple(ops), line=line, col=col)

        # remove_field name
        if self._check(TK.KW_REMOVE_FIELD):
            self._advance()
            name = self._expect(TK.IDENT).value
            return PatchModifyFields(
                ops=(FieldPatchOp(kind="remove", name=name, line=line, col=col),),
                line=line, col=col
            )

        # change_type name: OldType => NewType
        if self._check(TK.KW_CHANGE_TYPE):
            self._advance()
            name = self._expect(TK.IDENT).value
            self._expect(TK.COLON)
            old_ty = self._parse_type_expr()
            self._expect(TK.FAT_ARROW)
            new_ty = self._parse_type_expr()
            meta = self._parse_metadata()
            return PatchModifyFields(
                ops=(FieldPatchOp(kind="change_type", name=name, ty=old_ty, new_ty=new_ty,
                                  annotations=meta.annotations, line=line, col=col),),
                line=line, col=col
            )

        raise ParseError(
            "期望 Patch 操作（replace_with / insert_before / insert_after / delete / "
            "rename_to / insert_case / move_to / copy_to / wrap_with / "
            "extract_interface / resolve_patch / add_param / remove_param / "
            "add_field / remove_field / change_type）",
            self._cur
        )

    def _parse_insert_case(self, line: int, col: int) -> PatchInsertCase:
        self._expect(TK.KW_INSERT_CASE)
        position = "after"
        if self._check(TK.KW_BEFORE):
            self._advance(); position = "before"
        elif self._check(TK.KW_AFTER):
            self._advance(); position = "after"
        anchor_tok = self._expect(TK.STRUCT_REF)
        self._expect(TK.LBRACE)
        variants: list[EnumVariant] = []
        while self._check(TK.PIPE):
            variants.append(self._parse_enum_variant())
        self._expect(TK.RBRACE)
        return PatchInsertCase(position=position, anchor_ref=anchor_tok.value,
                               variants=tuple(variants), line=line, col=col)

    def _parse_param_patch_op(self, kind: str) -> ParamPatchOp:
        """解析 add_param 的参数: name: Type = default @position(...)"""
        line, col = self._here()
        name = self._expect(TK.IDENT).value
        self._expect(TK.COLON)
        ty = self._parse_type_expr()
        default_val = None
        if self._match(TK.EQ):
            # 简单处理：读取默认值为单token
            default_val = self._advance().value
        meta = self._parse_metadata()
        return ParamPatchOp(kind=kind, name=name, ty=ty, default=default_val,
                            annotations=meta.annotations, line=line, col=col)

    def _parse_field_patch_op(self, kind: str) -> FieldPatchOp:
        """解析 add_field 的字段: name: Type"""
        line, col = self._here()
        name = self._expect(TK.IDENT).value
        self._expect(TK.COLON)
        ty = self._parse_type_expr()
        meta = self._parse_metadata()
        return FieldPatchOp(kind=kind, name=name, ty=ty,
                            annotations=meta.annotations, line=line, col=col)

    def _read_raw_block(self) -> str:
        """读取 { ... } 块的原始文本（用于 patch 内容暂存）。"""
        depth = 0
        start = self._cur.col
        parts: list[str] = []
        while not self._at_end():
            tok = self._cur
            if tok.kind == TK.LBRACE:
                depth += 1
                parts.append('{')
            elif tok.kind == TK.RBRACE:
                if depth == 0:
                    break
                depth -= 1
                parts.append('}')
            else:
                parts.append(tok.value)
            self._advance()
            if depth == 0 and parts and parts[-1] == '}':
                break
        return ' '.join(parts)

    # ── Patch Group ───────────────────────────

    def _parse_patch_group(self, meta: Metadata) -> PatchGroupDef:
        line, col = self._here()
        self._expect(TK.KW_PATCH_GROUP)
        extra_meta = self._parse_metadata()
        all_annots = meta.annotations + extra_meta.annotations
        merged_meta = Metadata(annotations=all_annots, line=meta.line, col=meta.col)

        self._expect(TK.LBRACE)
        patches: list[PatchDef] = []
        while not self._check(TK.RBRACE, TK.EOF):
            patch_annots = self._parse_annotations()
            patches.append(self._parse_patch_def(patch_annots))
        self._expect(TK.RBRACE)
        return PatchGroupDef(patches=tuple(patches), metadata=merged_meta, line=line, col=col)

    # ── Query ────────────────────────────────

    def _parse_query_def(self, meta: Metadata) -> QueryDef:
        line, col = self._here()
        self._expect(TK.KW_QUERY)
        extra_meta = self._parse_metadata()
        all_annots = meta.annotations + extra_meta.annotations
        merged_meta = Metadata(annotations=all_annots, line=meta.line, col=meta.col)

        self._expect(TK.LBRACE)
        find_clause: QueryFind | None = None
        where_clauses: list[QueryWhere] = []
        ret_clause: QueryReturn | None = None
        limit_clause: QueryLimit | None = None

        while not self._check(TK.RBRACE, TK.EOF):
            if self._check(TK.KW_FIND):
                self._advance()
                target = self._expect(TK.IDENT).value
                find_clause = QueryFind(target=target, line=self._cur.line, col=self._cur.col)
            elif self._check(TK.KW_WHERE):
                self._advance()
                # 读取到换行或下一个关键字前的内容（简化：读取表达式串）
                pred = self._read_until_keyword()
                where_clauses.append(QueryWhere(predicate=pred,
                                                line=self._cur.line, col=self._cur.col))
            elif self._check(TK.KW_RETURN):
                self._advance()
                self._expect(TK.LBRACKET)
                fields: list[str] = []
                while not self._check(TK.RBRACKET, TK.EOF):
                    fields.append(self._expect(TK.IDENT).value)
                    self._match(TK.COMMA)
                self._expect(TK.RBRACKET)
                ret_clause = QueryReturn(fields=tuple(fields),
                                        line=self._cur.line, col=self._cur.col)
            elif self._check(TK.KW_LIMIT):
                self._advance()
                count = int(self._expect(TK.INTEGER).value)
                limit_clause = QueryLimit(count=count, line=self._cur.line, col=self._cur.col)
            else:
                self._advance()  # skip unknown

        self._expect(TK.RBRACE)

        if find_clause is None:
            raise ParseError("query 缺少 find 子句", self._cur)
        if ret_clause is None:
            ret_clause = QueryReturn(fields=(), line=line, col=col)

        return QueryDef(find=find_clause, where_clauses=tuple(where_clauses),
                        ret=ret_clause, limit=limit_clause, metadata=merged_meta,
                        line=line, col=col)

    def _read_until_keyword(self) -> str:
        """读取直到遇到下一个关键字或 } 为止，返回原始文本。"""
        _STOP = {TK.KW_FIND, TK.KW_WHERE, TK.KW_RETURN, TK.KW_LIMIT, TK.RBRACE, TK.EOF}
        parts: list[str] = []
        while self._cur.kind not in _STOP:
            parts.append(self._cur.value)
            self._advance()
        return ' '.join(parts)


    # ── Query 分析（v0.3） ──────────────────────────

    def _parse_query_def(self, meta: Metadata) -> QueryDef:
        line, col = self._here()
        self._expect(TK.KW_QUERY)
        
        # 允许多余的 metadata （例如 query @id("...")）
        extra_meta = self._parse_metadata()
        # print("DEBUG extra_meta:", extra_meta)
        merged_meta = Metadata(annotations=meta.annotations + extra_meta.annotations, line=meta.line, col=meta.col)
        
        self._expect(TK.LBRACE)

        # find <target>
        self._expect(TK.KW_FIND)
        find_target_token = self._advance()
        find_target = find_target_token.value

        # where <clauses>
        where_clauses = []
        while self._check(TK.KW_WHERE):
            w_line, w_col = self._here()
            self._advance()
            
            # 由于 Query 的 where 语法可以是带有函数的断言：has_effect(!IO), param_count(> 4) 等
            # 为了 v0.3 的简易性，这里先用简单的 token 序列将其保存为字符串形式
            pred_tokens = []
            while not self._check(TK.KW_WHERE, TK.KW_RETURN, TK.KW_LIMIT, TK.RBRACE, TK.EOF):
                tok = self._advance()
                pred_tokens.append(str(tok.value))
            where_clauses.append(QueryWhere(predicate=" ".join(pred_tokens), line=w_line, col=w_col))

        # return [<fields>]
        self._expect(TK.KW_RETURN)
        self._expect(TK.LBRACKET)
        fields = []
        while not self._check(TK.RBRACKET, TK.EOF):
            if self._check(TK.AT):
                at_tok = self._advance()
                if self._check(TK.IDENT):
                    fields.append(f"@{self._advance().value}")
                else:
                    fields.append("@")
            elif self._check(TK.ANNOT):
                fields.append(str(self._advance().value))
            else:
                fields.append(str(self._advance().value))
                
            if not self._match(TK.COMMA):
                break
        self._expect(TK.RBRACKET)

        # limit <count>
        limit_node = None
        if self._match(TK.KW_LIMIT):
            count_tok = self._expect(TK.INTEGER)
            limit_node = QueryLimit(count=int(count_tok.value), line=count_tok.line, col=count_tok.col)
            
        self._expect(TK.RBRACE)

        return QueryDef(
            find=QueryFind(target=find_target, line=line, col=col),
            where_clauses=tuple(where_clauses),
            ret=QueryReturn(fields=tuple(fields), line=line, col=col),
            limit=limit_node,
            metadata=merged_meta,
            line=line, col=col
        )


# ─────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────

def parse(source: str, filename: str = "<anon>") -> Program:
    """将 ANNA 源码字符串解析为 AST Program。"""
    tokens = tokenize(source, filename)
    return Parser(tokens).parse()


# ─────────────────────────────────────────────
# CLI 调试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json

    src = """
module math.geometry @version("1.0.0") {

    type Shape {
        | Circle    { radius: Float64 }
        | Rectangle { width: Float64, height: Float64 }
    }

    @public
    fn area(shape: Shape) -> Float64 {
        intent "计算形状面积"
        require true
        match shape {
            | Circle { radius } => radius * radius
            | Rectangle { width, height } => width * height
        }
    }
}
"""

    if len(sys.argv) >= 2:
        with open(sys.argv[1], encoding="utf-8") as f:
            src = f.read()

    ast = parse(src)
    print("=== ANNA Parser Output ===")
    print(repr(ast))
