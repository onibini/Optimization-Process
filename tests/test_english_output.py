"""화면 출력·오류 메시지는 영어로만 씁니다 (계산용 PC의 run.log에서 한국어가 깨지지 않게).

main.py, src/, scripts/의 문자열 상수 중 docstring이 아닌 것에 한글이 있으면 실패합니다.
주석과 docstring은 검사하지 않습니다.
"""

import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANGUL = re.compile("[가-힣ㄱ-ㆎ]")


def python_files():
    yield os.path.join(ROOT, "main.py")
    for folder in ("src", "scripts"):
        for base, _, names in os.walk(os.path.join(ROOT, folder)):
            for name in names:
                if name.endswith(".py"):
                    yield os.path.join(base, name)


def korean_strings(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and HANGUL.search(node.value)
        ):
            yield node.lineno, node.value


class TestEnglishOutput(unittest.TestCase):
    def test_no_korean_in_string_literals(self):
        found = [
            f"{os.path.relpath(path, ROOT)}:{line}: {text!r}"
            for path in python_files()
            for line, text in korean_strings(path)
        ]
        self.assertEqual(found, [], "\n".join(found))


if __name__ == "__main__":
    unittest.main()
