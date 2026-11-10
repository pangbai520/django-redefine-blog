import ast
from pathlib import Path

from django.test import SimpleTestCase

BLOG_DIR = Path(__file__).resolve().parent.parent


class CodeStyleTests(SimpleTestCase):
    def test_func_names(self):
        failures = []
        for path in BLOG_DIR.rglob("*.py"):
            if "migrations" in path.parts:
                continue

            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                # Django requires this exact hook name when customizing its
                # token generator. Keep the naming rule for project-owned APIs.
                if (
                    path.relative_to(BLOG_DIR).as_posix() == "services/tokens.py"
                    and node.name == "_make_hash_value"
                ):
                    continue
                if node.name.count("_") > 2:
                    relative = path.relative_to(BLOG_DIR.parent)
                    failures.append(f"{relative}:{node.lineno} {node.name}")

        self.assertFalse(
            failures,
            "Function names may contain no more than two underscores:\n"
            + "\n".join(failures),
        )
