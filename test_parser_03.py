import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anna.parser import parse

def main():
    with open("examples/03_ai_queries.anna", "r", encoding="utf-8") as f:
        src = f.read()

    ast = parse(src, filename="03_ai_queries.anna")
    print("Parsed successfully!")
    print(f"Items found: {len(ast.items)}")
    
    for item in ast.items:
        if type(item).__name__ == "QueryDef":
            qid = item.metadata.get("id").args[0] if item.metadata.has("id") else "unknown"
            print(f" - query: {qid}")

if __name__ == "__main__":
    main()
