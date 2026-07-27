"""Sandbox for the Python files in /player.

Two layers:

1. A static AST pass that rejects anything a behaviour script has no business
   doing - imports, dunder access, `exec`/`eval`/`open`/`getattr`, `while`
   loops, generators, decorators and so on.
2. A runtime guard that caps how many lines a single `decide()` call may
   execute and how long it may run, so a pathological `for` loop cannot wedge
   the match.

The point is that text typed into a public webpage, however hostile, can at
worst produce a fighter that plays badly. It cannot touch the filesystem, the
network, or the process running the match.
"""
from __future__ import annotations

import ast
import math
import random
import sys
import time
from dataclasses import dataclass, field

from . import api

MAX_SOURCE_BYTES = 24_000
LINE_BUDGET = 20_000            # traced lines per decide() call
TIME_BUDGET = 0.05              # seconds per decide() call
LOAD_LINE_BUDGET = 60_000
LOAD_TIME_BUDGET = 0.5
MAX_CONSECUTIVE_ERRORS = 25


class ScriptError(Exception):
    """Script is not acceptable, or blew up while running."""


class ScriptTimeout(ScriptError):
    pass


# ------------------------------------------------------------------ AST pass
_ALLOWED_NODES = {
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign,
    ast.FunctionDef, ast.Return, ast.Pass, ast.If, ast.For, ast.Break,
    ast.Continue, ast.Try, ast.ExceptHandler, ast.Raise, ast.Assert,
    ast.ClassDef, ast.Delete,
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Lambda, ast.IfExp, ast.Dict,
    ast.Set, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.Compare, ast.Call, ast.Constant, ast.Attribute, ast.Subscript,
    ast.Starred, ast.Name, ast.List, ast.Tuple, ast.Slice, ast.JoinedStr,
    ast.FormattedValue, ast.NamedExpr,
    ast.Load, ast.Store, ast.Del, ast.comprehension, ast.arguments, ast.arg,
    ast.keyword, ast.alias, ast.withitem,
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.LShift, ast.RShift, ast.BitOr, ast.BitXor,
    ast.BitAnd, ast.MatMult, ast.Invert, ast.Not, ast.UAdd, ast.USub,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot,
    ast.In, ast.NotIn,
}

_BANNED_NAMES = {
    "eval", "exec", "compile", "open", "input", "__import__", "globals",
    "locals", "vars", "dir", "getattr", "setattr", "delattr", "hasattr",
    "breakpoint", "exit", "quit", "help", "memoryview", "super", "object",
    "classmethod", "staticmethod", "property", "type", "id", "hash",
}

_NODE_REASON = {
    ast.Import: "imports are not allowed",
    ast.ImportFrom: "imports are not allowed",
    ast.While: "`while` loops are not allowed (use `for` with a range)",
    ast.With: "`with` blocks are not allowed",
    ast.AsyncFunctionDef: "async code is not allowed",
    ast.Await: "async code is not allowed",
    ast.AsyncFor: "async code is not allowed",
    ast.AsyncWith: "async code is not allowed",
    ast.Yield: "generators are not allowed",
    ast.YieldFrom: "generators are not allowed",
    ast.Global: "`global` is not allowed",
    ast.Nonlocal: "`nonlocal` is not allowed",
}


def validate_source(source: str) -> list[str]:
    """Return a list of problems. Empty list means the script is acceptable."""
    problems: list[str] = []

    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        return [f"script is too large (limit {MAX_SOURCE_BYTES} bytes)"]

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"syntax error on line {e.lineno}: {e.msg}"]

    for node in ast.walk(tree):
        kind = type(node)

        reason = _NODE_REASON.get(kind)
        if reason:
            problems.append(f"line {getattr(node, 'lineno', '?')}: {reason}")
            continue

        if kind not in _ALLOWED_NODES:
            problems.append(
                f"line {getattr(node, 'lineno', '?')}: `{kind.__name__}` is not allowed"
            )
            continue

        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            problems.append(
                f"line {node.lineno}: attribute `{node.attr}` is not allowed "
                "(underscore-prefixed attributes are blocked)"
            )

        if isinstance(node, ast.Name):
            if node.id in _BANNED_NAMES:
                problems.append(f"line {node.lineno}: `{node.id}` is not allowed")
            elif node.id.startswith("__"):
                problems.append(f"line {node.lineno}: `{node.id}` is not allowed")

        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.decorator_list:
            problems.append(f"line {node.lineno}: decorators are not allowed")

        if isinstance(node, ast.keyword) and node.arg is None:
            problems.append(f"line {getattr(node, 'lineno', '?')}: `**kwargs` unpacking is not allowed")

    if not any(isinstance(n, ast.FunctionDef) and n.name == "decide"
               for n in ast.walk(tree)):
        problems.append("script must define `decide(me, world)`")

    return problems[:12]


# -------------------------------------------------------------- safe globals
_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "divmod": divmod, "enumerate": enumerate, "filter": filter, "float": float,
    "format": format, "frozenset": frozenset, "int": int, "isinstance": isinstance,
    "len": len, "list": list, "map": map, "max": max, "min": min, "pow": pow,
    "range": range, "repr": repr, "reversed": reversed, "round": round,
    "set": set, "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip, "abs": abs,
    "True": True, "False": False, "None": None,
    "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "ZeroDivisionError": ZeroDivisionError,
    "AttributeError": AttributeError, "Exception": Exception,
}


class _SafeMath:
    pi = math.pi
    tau = math.tau
    e = math.e
    inf = math.inf

    def __init__(self):
        for fn in ("sqrt", "hypot", "sin", "cos", "tan", "atan", "atan2",
                   "asin", "acos", "floor", "ceil", "fabs", "copysign",
                   "log", "log2", "log10", "exp", "degrees", "radians", "fmod"):
            setattr(self, fn, getattr(math, fn))

    @staticmethod
    def clamp(v, lo, hi):
        return lo if v < lo else hi if v > hi else v

    @staticmethod
    def sign(v):
        return 0.0 if v == 0 else (1.0 if v > 0 else -1.0)

    @staticmethod
    def lerp(a, b, t):
        return a + (b - a) * t


class _SafeRandom:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def random(self):
        return self._rng.random()

    def uniform(self, a, b):
        return self._rng.uniform(a, b)

    def randint(self, a, b):
        return self._rng.randint(a, b)

    def choice(self, seq):
        return self._rng.choice(list(seq)) if seq else None

    def chance(self, p):
        """True with probability p (0-1). The one most scripts actually want."""
        return self._rng.random() < p

    def shuffled(self, seq):
        out = list(seq)
        self._rng.shuffle(out)
        return out


def build_globals(seed: int | None = None) -> dict:
    return {
        "__builtins__": dict(_SAFE_BUILTINS),
        "math": _SafeMath(),
        "random": _SafeRandom(seed),
        "Action": api.Action,
        "LIGHT": api.Action.LIGHT,
        "HEAVY": api.Action.HEAVY,
        "SHOOT": api.Action.SHOOT,
    }


# ------------------------------------------------------------- runtime guard
def _guard(line_limit: int, deadline: float):
    counter = [0]

    def trace(frame, event, arg):
        if event == "line":
            counter[0] += 1
            if counter[0] > line_limit:
                raise ScriptTimeout("script exceeded its per-frame instruction budget")
            if counter[0] % 256 == 0 and time.monotonic() > deadline:
                raise ScriptTimeout("script exceeded its per-frame time budget")
        return trace

    return trace


def run_guarded(fn, args=(), line_limit=LINE_BUDGET, time_limit=TIME_BUDGET):
    """Call `fn` under the line/time guard. Raises ScriptTimeout if it overruns."""
    previous = sys.gettrace()
    sys.settrace(_guard(line_limit, time.monotonic() + time_limit))
    try:
        return fn(*args)
    finally:
        sys.settrace(previous)


# ------------------------------------------------------------ loaded scripts
@dataclass
class LoadedScript:
    path: str
    filename: str
    name: str
    character_id: str
    source: str
    namespace: dict = field(repr=False, default_factory=dict)
    decide = None
    error: str | None = None
    consecutive_errors: int = 0
    disabled: bool = False

    def call(self, me_view, world_view) -> api.Action:
        """Run the script's decide(). Never raises - a broken script just idles."""
        if self.disabled or self.decide is None:
            return api.IDLE
        try:
            result = run_guarded(self.decide, (me_view, world_view))
            action = api.coerce_action(result)
            self.consecutive_errors = 0
            self.error = None
            return action
        except ScriptTimeout as e:
            self._fail(f"{e}")
        except Exception as e:                       # noqa: BLE001 - scripts are untrusted
            self._fail(f"{type(e).__name__}: {e}")
        return api.IDLE

    def _fail(self, message: str) -> None:
        self.error = message
        self.consecutive_errors += 1
        if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            self.disabled = True
            self.error = f"disabled after {MAX_CONSECUTIVE_ERRORS} failures: {message}"


def load_script(path, source: str, seed: int | None = None) -> LoadedScript:
    """Validate and execute a player file, returning a ready-to-call script.

    Raises ScriptError if the file is rejected or its top level blows up.
    """
    problems = validate_source(source)
    if problems:
        raise ScriptError("; ".join(problems))

    namespace = build_globals(seed)
    code = compile(source, f"<player:{getattr(path, 'name', path)}>", "exec")
    try:
        run_guarded(lambda: exec(code, namespace),
                    line_limit=LOAD_LINE_BUDGET, time_limit=LOAD_TIME_BUDGET)
    except ScriptTimeout as e:
        raise ScriptError(f"module body overran its budget: {e}") from e
    except Exception as e:                           # noqa: BLE001
        raise ScriptError(f"module body failed: {type(e).__name__}: {e}") from e

    decide = namespace.get("decide")
    if not callable(decide):
        raise ScriptError("script must define `decide(me, world)`")

    filename = getattr(path, "name", str(path))
    name = str(namespace.get("NAME") or filename.rsplit(".", 1)[0]).strip()[:24]
    character_id = str(namespace.get("CHARACTER") or "").strip().lower()

    script = LoadedScript(
        path=str(path), filename=filename, name=name or filename,
        character_id=character_id, source=source, namespace=namespace,
    )
    script.decide = decide
    return script
