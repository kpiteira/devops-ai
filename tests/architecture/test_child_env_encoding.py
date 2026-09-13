"""Structural gate: a resolved value reaches a child as its own UTF-8, or not at all.

Two halves of one promise (#58), both enforced by AST on every run rather than
by an inventory taken once:

*Downstream* — `subprocess` bridges Python's str environment to POSIX bytes with
`os.fsencode`, which follows the locale: ASCII under `LC_ALL=C`, where a
non-ASCII secret cannot be passed at all and the resulting `UnicodeEncodeError`
quotes a character of it. Every spawn that passes an environment must build it
with `encode_env`.

*Upstream* — `encode_env` encodes with `surrogateescape`, which is right for the
inherited values `env://` resolves to and wrong for a surrogate that stands for
no byte. Only parsing JSON can manufacture one (every other string here came
from a strict UTF-8 decode), so every provider that parses JSON must put its
value through `_text.utf8_text`.

A one-time scan is not an invariant: a fourth spawn site, or a third JSON
provider, could reintroduce either defect with every existing test still green,
because nothing that exists today would exercise it.

Import aliases are resolved rather than assumed away — `import subprocess as sp`
and `from subprocess import run` are the same spawn as `subprocess.run`, and a
gate that only matched the dotted spelling would be a gate you could walk around
by renaming an import.

Enforced structure is run, not read.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "devops_ai"
PROVIDERS = SRC / "secrets" / "providers"

ENCODE_ENV = "encode_env"
UTF8_TEXT = "utf8_text"
# Every spelling that turns a `\uD800` escape into a lone surrogate. `loads`
# alone would be a gate you walk around by parsing from the stream instead —
# the same evasion by spelling that import aliases were below. `.decode()` is
# deliberately not here: it is `bytes.decode` far more often than
# `JSONDecoder.decode`, so the class name is watched instead of the method.
JSON_PARSERS = {"loads", "load", "JSONDecoder"}
# `subprocess` spawns that accept an environment.
SUBPROCESS_SPAWNS = {"run", "Popen", "call", "check_call", "check_output"}
# `os` spawns that take one positionally. None are used today; the gate is what
# makes adding one a decision rather than an accident.
OS_SPAWNS = {
    "execve", "execvpe", "execle", "execlpe",
    "posix_spawn", "posix_spawnp",
    "spawnve", "spawnvpe", "spawnle", "spawnlpe",
}
WATCHED = {"subprocess": SUBPROCESS_SPAWNS, "os": OS_SPAWNS}


def source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def provider_modules() -> list[Path]:
    """One module per provider; `_`-prefixed modules are shared code."""
    return sorted(
        p for p in PROVIDERS.glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )


class Resolver:
    """Local names back to the module attribute they actually name.

    `import subprocess as sp` makes `sp.run` a spawn; `from subprocess import
    run` makes a bare `run(...)` one. Both are resolved here so the checks below
    can ask one question of a call rather than three.
    """

    def __init__(self, tree: ast.AST) -> None:
        self.modules: dict[str, str] = {}       # local name -> "subprocess"|"os"
        self.functions: dict[str, tuple[str, str]] = {}  # local name -> (mod, attr)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in WATCHED:
                        self.modules[alias.asname or alias.name] = root
                        # `import os.path` also binds the name `os`.
                        if alias.asname is None:
                            self.modules[root] = root
            elif isinstance(node, ast.ImportFrom) and node.module in WATCHED:
                for alias in node.names:
                    self.functions[alias.asname or alias.name] = (
                        node.module, alias.name
                    )

    def target(self, node: ast.Call) -> tuple[str, str] | None:
        """(`module`, `attribute`) this call spawns through, if any."""
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = self.modules.get(func.value.id)
            if module is not None:
                return module, func.attr
        elif isinstance(func, ast.Name):
            return self.functions.get(func.id)
        return None


def _calls_any_of(tree: ast.AST, names: set[str]) -> bool:
    """True if any of `names` is called anywhere, however it was imported."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in names:
            return True
        if isinstance(func, ast.Attribute) and func.attr in names:
            return True
    return False


def parses_json(path: Path) -> bool:
    return _calls_any_of(ast.parse(path.read_text(), str(path)), JSON_PARSERS)


def _is_call_to(node: ast.expr, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == name
    return isinstance(func, ast.Attribute) and func.attr == name


def spawns_passing_an_environment() -> list[tuple[Path, ast.Call, str, str]]:
    """Every watched spawn call in `src/`, with the module and attribute named."""
    found = []
    for path in source_files():
        tree = ast.parse(path.read_text(), str(path))
        resolver = Resolver(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = resolver.target(node)
            if target is None:
                continue
            module, attr = target
            if attr in WATCHED[module]:
                found.append((path, node, module, attr))
    return found


def test_every_spawn_that_passes_an_environment_encodes_it() -> None:
    offenders: list[str] = []
    for path, node, module, attr in spawns_passing_an_environment():
        where = f"{path.relative_to(ROOT)}:{node.lineno}"
        if module == "subprocess":
            for keyword in node.keywords:
                if keyword.arg is None:
                    offenders.append(
                        f"{where} {module}.{attr}(**kwargs) — an environment that "
                        f"cannot be read here cannot be vouched for; pass "
                        f"env={ENCODE_ENV}(...) explicitly"
                    )
                elif keyword.arg == "env" and not _is_call_to(
                    keyword.value, ENCODE_ENV
                ):
                    offenders.append(
                        f"{where} {module}.{attr}(env=...) does not go through "
                        f"{ENCODE_ENV}(): the child's environment would be encoded "
                        f"with the locale's codec"
                    )
        else:
            args: list[ast.expr] = list(node.args)
            args += [k.value for k in node.keywords if k.arg is not None]
            if not any(_is_call_to(a, ENCODE_ENV) for a in args):
                offenders.append(
                    f"{where} {module}.{attr}() takes an environment and none of "
                    f"its arguments is {ENCODE_ENV}(...)"
                )
    assert not offenders, (
        "a child's environment must be built by devops_ai.secrets.encode_env, "
        "never by the locale's codec:\n  " + "\n  ".join(offenders)
    )


def test_every_provider_that_parses_json_refuses_lone_surrogates() -> None:
    """`json.loads` is the only way a resolved value can carry a surrogate.

    Every other string in the package came from a strict UTF-8 decode, which no
    surrogate survives. A JSON escape is not a decode.
    """
    offenders = []
    for path in provider_modules():
        if not parses_json(path):
            continue
        if not _calls_any_of(
            ast.parse(path.read_text(), str(path)), {UTF8_TEXT}
        ):
            offenders.append(
                f"{path.relative_to(ROOT)} parses JSON but never calls "
                f"{UTF8_TEXT}(): a `\\uD800` escape would reach the child as a "
                f"raw byte instead of the value's UTF-8"
            )
    assert not offenders, "\n  ".join(offenders)


def test_the_gate_sees_the_sites_it_is_meant_to_guard() -> None:
    """The control: a gate that matched nothing would pass just as quietly.

    Counts what the walks actually reach, so an AST change that stopped finding
    the known sites fails here instead of reporting a clean sweep of an empty
    set.
    """
    guarded = [
        f"{p.relative_to(ROOT)}:{n.lineno}"
        for p, n, module, _ in spawns_passing_an_environment()
        if module == "subprocess" and any(k.arg == "env" for k in n.keywords)
    ]
    assert len(guarded) >= 3, (
        f"expected at least the three known env-passing spawn sites "
        f"(ksecret run, op://, akv://), the walk found {guarded}"
    )

    # A superset, never an equality: pinning the exact list would turn the
    # legitimate addition of a third JSON provider into a red that reads as
    # "the walk is broken". The rule above is what a new provider has to
    # satisfy; this only proves the walk still reaches the known two.
    json_providers = {p.name for p in provider_modules() if parses_json(p)}
    missing = {"azurekeyvault.py", "openbao.py"} - json_providers
    assert not missing, (
        f"the walk no longer sees {sorted(missing)} as JSON-speaking, so the "
        f"rule above would pass them without checking anything"
    )


def test_an_aliased_import_is_resolved_rather_than_missed() -> None:
    """The gate's own blind spot, closed and kept closed.

    `import subprocess as sp` and `from subprocess import run` spawn exactly as
    `subprocess.run` does. Asserted on synthetic source rather than by waiting
    for someone to write it, because the day it is written is the day the gate
    has to already work.
    """
    aliased = ast.parse("import subprocess as sp\nsp.run(cmd, env=raw)\n")
    bare = ast.parse("from subprocess import run\nrun(cmd, env=raw)\n")
    renamed = ast.parse("from subprocess import run as go\ngo(cmd, env=raw)\n")
    dotted = ast.parse("import subprocess\nsubprocess.run(cmd, env=raw)\n")

    for tree in (aliased, bare, renamed, dotted):
        resolver = Resolver(tree)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        assert [resolver.target(c) for c in calls] == [("subprocess", "run")]

    unrelated = ast.parse("import shutil\nshutil.run(cmd, env=raw)\n")
    resolver = Resolver(unrelated)
    calls = [n for n in ast.walk(unrelated) if isinstance(n, ast.Call)]
    assert [resolver.target(c) for c in calls] == [None]
