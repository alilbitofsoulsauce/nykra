"""Deterministic adapter for model replies with import-only Python preambles.

Only a sole top-level function plus optional strictly allowlisted stdlib
imports is accepted. The imports are relocated into the function to satisfy
the one-function repair evaluator contract. This is a source transformation,
not a model-authored repair or a hidden-test-guided edit. Record both hashes.
"""
from __future__ import annotations

import ast
import copy

from .repair_feedback import validate_replacement

_ALLOWED = {"re", "urllib.parse", "urllib", "posixpath", "os.path"}


def normalize_function_imports(text: str, *, name: str, original: str) -> dict:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 10000:
        return {"status": "unrecognized_source", "source": text,
                "import_statements_moved": 0}
    try:
        tree = ast.parse(text, feature_version=(3, 8))
    except (SyntaxError, ValueError, TypeError):
        return {"status": "unrecognized_source", "source": text,
                "import_statements_moved": 0}
    body = tree.body
    if (not body or type(body[-1]) is not ast.FunctionDef or
            body[-1].name != name or
            any(type(n) not in (ast.Import, ast.ImportFrom) for n in body[:-1])):
        return {"status": "unrecognized_source", "source": text,
                "import_statements_moved": 0}
    original_problem = validate_replacement(
        text, name=name, original=original)
    if original_problem is None:
        return {"status": "unchanged", "source": text,
                "import_statements_moved": 0}
    if len(body) == 1:
        return {"status": "unrecognized_source", "source": text,
                "import_statements_moved": 0}
    for node in body[:-1]:
        if type(node) is ast.Import:
            modules = [n.name for n in node.names]
        elif type(node) is ast.ImportFrom:
            modules = [node.module]
            if node.level:
                return {"status": "unrecognized_source", "source": text,
                        "import_statements_moved": 0}
        else:
            return {"status": "unrecognized_source", "source": text,
                    "import_statements_moved": 0}
        if any(module not in _ALLOWED for module in modules):
            return {"status": "unrecognized_source", "source": text,
                    "import_statements_moved": 0}
        if any(alias.name == "*" for alias in node.names):
            return {"status": "unrecognized_source", "source": text,
                    "import_statements_moved": 0}
    method = copy.deepcopy(body[-1])
    # Preserve the original function's docstring: inserting an import before
    # it would silently change __doc__, a meaningful behavioral mutation.
    first = method.body[:1]
    docstring = bool(first and isinstance(first[0], ast.Expr)
                     and isinstance(first[0].value, ast.Constant)
                     and isinstance(first[0].value.value, str))
    insertion = 1 if docstring else 0
    method.body[insertion:insertion] = copy.deepcopy(body[:-1])
    output = ast.unparse(ast.fix_missing_locations(method)) + "\n"
    check = validate_replacement(output, name=name, original=original)
    if check is not None:
        return {"status": "unrecognized_source", "source": text,
                "import_statements_moved": 0}
    return {"status": "normalized_stdlib_imports", "source": output,
            "import_statements_moved": len(body)-1}
