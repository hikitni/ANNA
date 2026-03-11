"""
ANNA Language — Prototype Lexer
anna/lexer.py

将 ANNA 源码转换为 Token 流。
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator


# ─────────────────────────────────────────────
# Token 类型
# ─────────────────────────────────────────────

class TK(Enum):
    # 字面量
    INTEGER    = auto()
    FLOAT      = auto()
    STRING     = auto()
    RAW_STRING = auto()
    BOOL       = auto()
    UNIT       = auto()       # ()

    # 标识符族
    IDENT      = auto()       # snake_case
    TYPE_IDENT = auto()       # PascalCase
    CONST_IDENT= auto()       # SCREAMING_SNAKE
    ANNOT      = auto()       # @name
    STRUCT_REF = auto()       # #path.sub.leaf

    # 关键字
    KW_FN          = auto()
    KW_TYPE        = auto()
    KW_CONST       = auto()
    KW_LET         = auto()
    KW_MUT         = auto()
    KW_RETURN      = auto()
    KW_IF          = auto()
    KW_ELSE        = auto()
    KW_MATCH       = auto()
    KW_LOOP        = auto()
    KW_WHILE       = auto()
    KW_FOR         = auto()
    KW_BREAK       = auto()
    KW_CONTINUE    = auto()
    KW_IN          = auto()
    KW_MODULE      = auto()
    KW_USE         = auto()
    KW_AS          = auto()
    KW_WHERE       = auto()
    KW_INTENT      = auto()
    KW_REQUIRE     = auto()
    KW_ENSURE      = auto()
    KW_PATCH       = auto()
    KW_PATCH_GROUP = auto()
    KW_QUERY       = auto()
    KW_FIND        = auto()
    KW_LIMIT       = auto()
    KW_AND         = auto()
    KW_OR          = auto()

    # Patch 操作关键字
    KW_REPLACE_WITH     = auto()
    KW_INSERT_BEFORE    = auto()
    KW_INSERT_AFTER     = auto()
    KW_INSERT_CASE      = auto()
    KW_DELETE           = auto()
    KW_RENAME_TO        = auto()
    KW_EXTRACT_RANGE    = auto()
    KW_INLINE           = auto()
    KW_BEFORE           = auto()
    KW_AFTER            = auto()
    KW_ADD_PARAM        = auto()
    KW_REMOVE_PARAM     = auto()
    KW_RENAME_PARAM     = auto()
    KW_CHANGE_TYPE      = auto()
    KW_CHANGE_PARAM_TYPE= auto()
    KW_ADD_FIELD        = auto()
    KW_REMOVE_FIELD     = auto()
    KW_RENAME_FIELD     = auto()

    # 高级重构 Patch 原语（v1.1, Section 5）
    KW_MOVE_TO          = auto()
    KW_COPY_TO          = auto()
    KW_WRAP_WITH        = auto()
    KW_EXTRACT_INTERFACE= auto()
    KW_RESOLVE_PATCH    = auto()

    # 验证块（v1.1, Section 4）
    KW_PROOF            = auto()   # proof ... for #path 中 for 复用 KW_FOR

    # Query 关键字
    KW_FIND_FN      = auto()
    KW_FIND_TYPE    = auto()
    KW_FIND_CONST   = auto()
    KW_FIND_PATCH   = auto()
    KW_FIND_MODULE  = auto()
    KW_FIND_FIELD   = auto()
    KW_FIND_PARAM   = auto()

    # 符号
    LBRACE   = auto()   # {
    RBRACE   = auto()   # }
    LPAREN   = auto()   # (
    RPAREN   = auto()   # )
    LBRACKET = auto()   # [
    RBRACKET = auto()   # ]
    COMMA       = auto()   # ,
    COLON       = auto()   # :
    COLONCOLON  = auto()   # ::
    SEMI        = auto()   # ;
    DOT      = auto()   # .
    PIPE     = auto()   # |
    ARROW    = auto()   # ->
    FAT_ARROW= auto()   # =>
    DOTDOT   = auto()   # ..
    DOTDOTEQ = auto()   # ..=
    PIPELINE = auto()   # |>
    BANG     = auto()   # !
    AT       = auto()   # @  (standalone)
    QUESTION = auto()   # ?
    APPROX   = auto()   # ≈

    # 运算符
    PLUS    = auto()   # +
    MINUS   = auto()   # -
    STAR    = auto()   # *
    SLASH   = auto()   # /
    PERCENT = auto()   # %
    EQ      = auto()   # =
    EQEQ    = auto()   # ==
    NEQ     = auto()   # !=
    LT      = auto()   # <
    GT      = auto()   # >
    LEQ     = auto()   # <=
    GEQ     = auto()   # >=
    ANDAND  = auto()   # &&
    OROR    = auto()   # ||
    AMP     = auto()   # &
    CARET   = auto()   # ^
    SHL     = auto()   # <<
    SHR     = auto()   # >>
    TILDE   = auto()   # ~

    # 特殊
    EOF     = auto()
    NEWLINE = auto()   # 保留用于错误报告


KEYWORDS: dict[str, TK] = {
    "fn":            TK.KW_FN,
    "type":          TK.KW_TYPE,
    "const":         TK.KW_CONST,
    "let":           TK.KW_LET,
    "mut":           TK.KW_MUT,
    "return":        TK.KW_RETURN,
    "if":            TK.KW_IF,
    "else":          TK.KW_ELSE,
    "match":         TK.KW_MATCH,
    "loop":          TK.KW_LOOP,
    "while":         TK.KW_WHILE,
    "for":           TK.KW_FOR,
    "break":         TK.KW_BREAK,
    "continue":      TK.KW_CONTINUE,
    "in":            TK.KW_IN,
    "module":        TK.KW_MODULE,
    "use":           TK.KW_USE,
    "as":            TK.KW_AS,
    "where":         TK.KW_WHERE,
    "intent":        TK.KW_INTENT,
    "require":       TK.KW_REQUIRE,
    "ensure":        TK.KW_ENSURE,
    "patch":         TK.KW_PATCH,
    "patch_group":   TK.KW_PATCH_GROUP,
    "query":         TK.KW_QUERY,
    "find":          TK.KW_FIND,
    "limit":         TK.KW_LIMIT,
    "and":           TK.KW_AND,
    "or":            TK.KW_OR,
    "true":          TK.BOOL,
    "false":         TK.BOOL,
    # Patch ops
    "replace_with":      TK.KW_REPLACE_WITH,
    "insert_before":     TK.KW_INSERT_BEFORE,
    "insert_after":      TK.KW_INSERT_AFTER,
    "insert_case":       TK.KW_INSERT_CASE,
    "delete":            TK.KW_DELETE,
    "rename_to":         TK.KW_RENAME_TO,
    "extract_range":     TK.KW_EXTRACT_RANGE,
    "inline":            TK.KW_INLINE,
    "before":            TK.KW_BEFORE,
    "after":             TK.KW_AFTER,
    "add_param":         TK.KW_ADD_PARAM,
    "remove_param":      TK.KW_REMOVE_PARAM,
    "rename_param":      TK.KW_RENAME_PARAM,
    "change_type":       TK.KW_CHANGE_TYPE,
    "change_param_type": TK.KW_CHANGE_PARAM_TYPE,
    "add_field":         TK.KW_ADD_FIELD,
    "remove_field":      TK.KW_REMOVE_FIELD,
    "rename_field":      TK.KW_RENAME_FIELD,
    # 高级重构原语
    "move_to":            TK.KW_MOVE_TO,
    "copy_to":            TK.KW_COPY_TO,
    "wrap_with":          TK.KW_WRAP_WITH,
    "extract_interface":  TK.KW_EXTRACT_INTERFACE,
    "resolve_patch":      TK.KW_RESOLVE_PATCH,
    # 验证块
    "proof":              TK.KW_PROOF,
}


# ─────────────────────────────────────────────
# Token 数据类
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Token:
    kind:   TK
    value:  str
    line:   int
    col:    int

    def __repr__(self) -> str:
        return f"Token({self.kind.name}, {self.value!r}, {self.line}:{self.col})"


# ─────────────────────────────────────────────
# 词法错误
# ─────────────────────────────────────────────

class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int):
        super().__init__(f"[LexError {line}:{col}] {msg}")
        self.line = line
        self.col  = col


# ─────────────────────────────────────────────
# Lexer
# ─────────────────────────────────────────────

# 多字符符号（按长度降序优先匹配）
MULTI_CHAR_SYMBOLS: list[tuple[str, TK]] = sorted([
    ("..=",  TK.DOTDOTEQ),
    ("->",   TK.ARROW),
    ("=>",   TK.FAT_ARROW),
    ("|>",   TK.PIPELINE),
    ("..",   TK.DOTDOT),
    ("::",   TK.COLONCOLON),
    ("==",   TK.EQEQ),
    ("!=",   TK.NEQ),
    ("<=",   TK.LEQ),
    (">=",   TK.GEQ),
    ("&&",   TK.ANDAND),
    ("||",   TK.OROR),
    ("<<",   TK.SHL),
    (">>",   TK.SHR),
], key=lambda x: -len(x[0]))

SINGLE_CHAR_SYMBOLS: dict[str, TK] = {
    '{': TK.LBRACE,
    '}': TK.RBRACE,
    '(': TK.LPAREN,
    ')': TK.RPAREN,
    '[': TK.LBRACKET,
    ']': TK.RBRACKET,
    ',': TK.COMMA,
    ':': TK.COLON,   # note: :: is matched before : in multi-char
    ';': TK.SEMI,
    '.': TK.DOT,
    '|': TK.PIPE,
    '!': TK.BANG,
    '@': TK.AT,
    '?': TK.QUESTION,
    '≈': TK.APPROX,
    '+': TK.PLUS,
    '-': TK.MINUS,
    '*': TK.STAR,
    '/': TK.SLASH,
    '%': TK.PERCENT,
    '=': TK.EQ,
    '<': TK.LT,
    '>': TK.GT,
    '&': TK.AMP,
    '^': TK.CARET,
    '~': TK.TILDE,
}

_IDENT_RE        = re.compile(r'[a-z_][a-z0-9_]*(?:_[a-z0-9]+)*')
_TYPE_IDENT_RE   = re.compile(r'[A-Z][A-Za-z0-9]*')
_CONST_IDENT_RE  = re.compile(r'[A-Z_][A-Z0-9_]+')
_INTEGER_RE      = re.compile(r'0x[0-9a-fA-F]+|[0-9]+')
_FLOAT_RE        = re.compile(r'[0-9]+\.[0-9]+(?:[eE][+-]?[0-9]+)?')
# 支持隐式索引扩展（v1.1 Section 1）：
#   #module.fn/closure@1   —— 第 1 处闭包
#   #module.fn/match[2]    —— 第 2 个 match 块
_STRUCT_REF_RE   = re.compile(r'#[a-zA-Z_][a-zA-Z0-9_.]*(?:/[a-zA-Z_]+(?:@[0-9]+|\[[0-9]+\]))?')


class Lexer:
    """
    ANNA 词法分析器。
    
    usage:
        tokens = list(Lexer(source).tokenize())
    """

    def __init__(self, source: str, filename: str = "<anon>"):
        self.source   = source
        self.filename = filename
        self.pos      = 0
        self.line     = 1
        self.col      = 1

    # ── 位置辅助 ──────────────────────────────

    @property
    def _remaining(self) -> str:
        return self.source[self.pos:]

    @property
    def _current(self) -> str:
        return self.source[self.pos] if self.pos < len(self.source) else ""

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else ""

    def _advance(self, n: int = 1) -> str:
        chunk = self.source[self.pos: self.pos + n]
        for ch in chunk:
            if ch == '\n':
                self.line += 1
                self.col   = 1
            else:
                self.col  += 1
        self.pos += n
        return chunk

    def _here(self) -> tuple[int, int]:
        return self.line, self.col

    def _match_re(self, pattern: re.Pattern) -> re.Match | None:
        return pattern.match(self.source, self.pos)

    # ── 主入口 ────────────────────────────────

    def tokenize(self) -> Iterator[Token]:
        while self.pos < len(self.source):
            tok = self._next_token()
            if tok is not None:
                yield tok
        yield Token(TK.EOF, "", self.line, self.col)

    # ── 逐 token 解析 ─────────────────────────

    def _next_token(self) -> Token | None:
        self._skip_whitespace_and_comments()
        if self.pos >= len(self.source):
            return None

        line, col = self._here()
        ch = self._current

        # --- 结构路径引用 #path.sub ---
        if ch == '#':
            m = _STRUCT_REF_RE.match(self.source, self.pos)
            if m:
                val = m.group()
                self._advance(len(val))
                return Token(TK.STRUCT_REF, val, line, col)
            raise LexError(f"无效的结构路径: {self.source[self.pos:self.pos+8]!r}", line, col)

        # --- 注解 @name ---
        if ch == '@':
            self._advance()
            m = _IDENT_RE.match(self.source, self.pos)
            if m:
                name = m.group()
                self._advance(len(name))
                # 处理多词关键字注解参数中的 snake_case
                return Token(TK.ANNOT, "@" + name, line, col)
            return Token(TK.AT, "@", line, col)

        # --- 原始字符串 `...` ---
        if ch == '`':
            return self._lex_raw_string(line, col)

        # --- 普通字符串 "..." ---
        if ch == '"':
            return self._lex_string(line, col)

        # --- 数字 ---
        if ch.isdigit() or (ch == '0' and self._peek(1) == 'x'):
            return self._lex_number(line, col)

        # --- 标识符 & 关键字 ---
        if ch.isalpha() or ch == '_':
            return self._lex_ident(line, col)

        # --- 多字符符号 ---
        for sym, tk in MULTI_CHAR_SYMBOLS:
            if self._remaining.startswith(sym):
                self._advance(len(sym))
                return Token(tk, sym, line, col)

        # --- 单字符符号 ---
        if ch in SINGLE_CHAR_SYMBOLS:
            self._advance()
            return Token(SINGLE_CHAR_SYMBOLS[ch], ch, line, col)

        # --- Unicode 特殊字符 ---
        if ch == '≈':
            self._advance()
            return Token(TK.APPROX, '≈', line, col)

        raise LexError(f"未知字符: {ch!r}", line, col)

    # ── 辅助解析器 ────────────────────────────

    def _skip_whitespace_and_comments(self) -> None:
        while self.pos < len(self.source):
            ch = self._current
            # 空白
            if ch in (' ', '\t', '\r', '\n'):
                self._advance()
            # 行注释 // 或 #!
            elif self._remaining.startswith('//') or self._remaining.startswith('#!'):
                while self.pos < len(self.source) and self._current != '\n':
                    self._advance()
            # 块注释 /* ... */
            elif self._remaining.startswith('/*'):
                self._advance(2)
                while self.pos < len(self.source) - 1:
                    if self._remaining.startswith('*/'):
                        self._advance(2)
                        break
                    self._advance()
                else:
                    raise LexError("块注释未闭合", self.line, self.col)
            else:
                break

    def _lex_string(self, line: int, col: int) -> Token:
        self._advance()  # consume "
        parts: list[str] = []
        while self.pos < len(self.source):
            ch = self._current
            if ch == '"':
                self._advance()
                return Token(TK.STRING, ''.join(parts), line, col)
            if ch == '\\':
                self._advance()
                esc = self._advance()
                parts.append({'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\'}.get(esc, esc))
            else:
                parts.append(self._advance())
        raise LexError("字符串未闭合", line, col)

    def _lex_raw_string(self, line: int, col: int) -> Token:
        self._advance()  # consume `
        start = self.pos
        while self.pos < len(self.source) and self._current != '`':
            self._advance()
        if self.pos >= len(self.source):
            raise LexError("原始字符串未闭合", line, col)
        val = self.source[start:self.pos]
        self._advance()  # consume closing `
        return Token(TK.RAW_STRING, val, line, col)

    def _lex_number(self, line: int, col: int) -> Token:
        # 先尝试浮点（必须含小数点）
        mf = _FLOAT_RE.match(self.source, self.pos)
        if mf:
            val = mf.group()
            self._advance(len(val))
            return Token(TK.FLOAT, val, line, col)
        mi = _INTEGER_RE.match(self.source, self.pos)
        if mi:
            val = mi.group()
            self._advance(len(val))
            return Token(TK.INTEGER, val, line, col)
        raise LexError(f"无效数字: {self._current!r}", line, col)

    def _lex_ident(self, line: int, col: int) -> Token:
        # 优先匹配全大写常量（SCREAMING_SNAKE），再匹配 PascalCase，最后 snake_case
        start = self.pos
        # 贪婪读取合法标识符字符
        while self.pos < len(self.source) and (self._current.isalnum() or self._current == '_'):
            self._advance()
        val = self.source[start:self.pos]

        # 关键字优先（关键字均小写或 snake_case）
        if val in KEYWORDS:
            return Token(KEYWORDS[val], val, line, col)

        # 分类标识符
        if val == "()":
            return Token(TK.UNIT, val, line, col)
        if val[0].isupper() and '_' not in val:
            return Token(TK.TYPE_IDENT, val, line, col)
        if val.isupper() or (val.replace('_', '').isupper() and '_' in val and val[0].isupper()):
            return Token(TK.CONST_IDENT, val, line, col)
        return Token(TK.IDENT, val, line, col)


# ─────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────

def tokenize(source: str, filename: str = "<anon>") -> list[Token]:
    """将 ANNA 源码字符串转换为 Token 列表。"""
    return list(Lexer(source, filename).tokenize())


# ─────────────────────────────────────────────
# CLI 调试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        src = """
module math.utils @version("1.0.0") {
    intent "数学工具函数集合"

    @public
    fn add(a: Int64, b: Int64) -> Int64 {
        intent "整数加法"
        return a + b
    }
}
"""
        print("=== ANNA Lexer Demo ===")
        print(f"源码:\n{src}\n")
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            src = f.read()

    tokens = tokenize(src)
    print("Tokens:")
    for tok in tokens:
        print(f"  {tok}")
