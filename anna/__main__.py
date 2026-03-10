"""
ANNA Language — CLI Entry Point
"""

import sys
from .lexer  import tokenize, LexError
from .parser import parse, ParseError


def main():
    if len(sys.argv) < 2:
        print("ANNA Language Prototype v0.1.0")
        print("Usage: anna <command> [file]")
        print()
        print("Commands:")
        print("  lex   <file>    词法分析，输出 Token 列表")
        print("  parse <file>    语法解析，输出 AST 摘要")
        print("  demo            运行内置演示")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "demo":
        import subprocess, os
        demo = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo.py")
        subprocess.run([sys.executable, demo])
        return

    if len(sys.argv) < 3:
        print(f"错误：{cmd} 命令需要提供文件路径")
        sys.exit(1)

    filepath = sys.argv[2]
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except FileNotFoundError:
        print(f"错误：找不到文件 {filepath!r}")
        sys.exit(1)

    if cmd == "lex":
        try:
            tokens = tokenize(source, filepath)
            for tok in tokens:
                print(f"{tok.kind.name:<20} {tok.value!r:<40} {tok.line}:{tok.col}")
        except LexError as e:
            print(f"词法错误: {e}")
            sys.exit(1)

    elif cmd == "parse":
        try:
            program = parse(source, filepath)
            print(f"模块: {program.module.path if program.module else '(无)'}")
            print(f"顶级元素: {len(program.items)} 个")
            for item in program.items:
                print(f"  [{type(item).__name__}] {getattr(item, 'name', '?')}")
        except (LexError, ParseError) as e:
            print(f"解析错误: {e}")
            sys.exit(1)

    else:
        print(f"未知命令: {cmd!r}")
        sys.exit(1)


if __name__ == "__main__":
    main()
