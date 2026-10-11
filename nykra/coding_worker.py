"""Restricted callable worker for explicitly approved, local coding evaluations.

This is defense in depth for accidental unsafe code, NOT a hardened sandbox.
Host supplies only tests' input arguments. Expected results never enter worker.
"""
from __future__ import annotations
import ast
import json
import sys

BUILTINS = {"abs":abs, "all":all, "any":any, "bool":bool, "dict":dict,
            "enumerate":enumerate, "int":int, "len":len, "list":list,
            "max":max, "min":min, "range":range, "reversed":reversed,
            "set":set, "sorted":sorted, "str":str, "sum":sum, "tuple":tuple,
            "zip":zip}

FORBIDDEN = (ast.Import,ast.ImportFrom,ast.Attribute,ast.ClassDef,ast.AsyncFunctionDef,
             ast.Lambda,ast.Global,ast.Nonlocal,ast.With,ast.AsyncWith,ast.Try,
             ast.Raise,ast.Delete,ast.Yield,ast.YieldFrom,ast.Await,ast.NamedExpr,
             ast.While,ast.Match,ast.Assert,ast.FunctionDef)  # top-level sole function handled separately


def validate_source(source: str) -> None:
    if not isinstance(source,str) or not 1 <= len(source.encode("utf-8")) <= 4500:
        raise ValueError("candidate source length invalid")
    tree=ast.parse(source)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):
        raise ValueError("exactly one solve function required")
    fn=tree.body[0]
    if fn.name!="solve" or fn.decorator_list or fn.returns is not None or getattr(fn, "type_params", ()):
        raise ValueError("solve function signature invalid")
    if fn.args.defaults or fn.args.kw_defaults or fn.args.kwarg or fn.args.vararg:
        raise ValueError("function defaults and variadic arguments disallowed")
    for node in ast.walk(tree):
        if node is fn: continue
        if isinstance(node, FORBIDDEN):
            raise ValueError("prohibited code construct")
        if isinstance(node,ast.Name) and (node.id.startswith("_") or "__" in node.id):
            raise ValueError("private names are disallowed")
        if isinstance(node,ast.arg) and (node.arg.startswith("_") or "__" in node.arg):
            raise ValueError("private arguments disallowed")
        if isinstance(node,ast.Call) and not (
            isinstance(node.func,ast.Name) and node.func.id in BUILTINS
        ):
            raise ValueError("only restricted built-in calls are allowed")


def run(payload: dict) -> dict:
    if not isinstance(payload,dict) or set(payload)!={"source","inputs"}:
        raise ValueError("invalid worker input schema")
    source=payload["source"]
    validate_source(source)
    inputs=payload["inputs"]
    if not isinstance(inputs,list) or len(inputs)>100:
        raise ValueError("too many inputs")
    scope={"__builtins__":BUILTINS}
    exec(compile(source,"<candidate>","exec"),scope)
    fn=scope["solve"]
    outputs=[]
    for arguments in inputs:
        if not isinstance(arguments,list) or len(arguments)>3:
            raise ValueError("invalid task arguments")
        try:
            result=fn(*arguments)
            json.dumps(result,allow_nan=False)
            outputs.append({"value":result})
        except Exception:
            outputs.append({"error":"candidate_exception"})
    return {"outputs":outputs}


if __name__=="__main__":
    try:
        request=json.loads(sys.stdin.read(100000))
        print(json.dumps(run(request),separators=(",",":"),allow_nan=False))
    except Exception:
        # Do not print source, task contents, or error messages.
        sys.exit(2)
