"""Structural gate: a child's environment is encoded here, or not at all.

`encode_env` exists because `subprocess` bridges Python's str environment to
POSIX bytes with `os.fsencode`, which follows the locale — ASCII under
`LC_ALL=C`, where a non-ASCII secret cannot be passed at all and the resulting
`UnicodeEncodeError` quotes a character of it (#58). Three spawn sites passed an
environment; all three now go through the one helper.

A one-time inventory is not an invariant. A fourth site added later could pass a
text environment and reintroduce the defect with every existing test still
green, because nothing that exists today would spawn it. So the inventory is
taken by AST on every run instead:

- every `subprocess` spawn that passes `env=` passes `encode_env(...)`;
- an environment handed over as `**kwargs` is refused rather than assumed, since
  nothing here can see what is in it;
- the `os` spawn-with-environment family is covered too — unused today, which is
  exactly why adding one should have to meet this gate rather than slip past it.

Enforced structure is run, not read.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "devops_ai"

HELPER = "encode_env"
# `subprocess` spawns that accept an environment.
SUBPROCESS_SPAWNS = {"run", "Popen", "call", "check_call", "check_output"}
# `os` spawns that take one positionally. None are used today; the gate is what
# makes adding one a decision rather than an accident.
OS_SPAWNS = {
    "execve", "execvpe", "execle", "execlpe",
    "posix_spawn", "posix_spawnp",
    "spawnve", "spawnvpe", "spawnle", "spawnlpe",
}


def source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _target(node: ast.Call) -> tuple[str, str] | None:
    """(`module`, `attribute`) for `module.attribute(...)`, else None."""
    func = node.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    return func.value.id, func.attr


def _is_helper_call(node: ast.expr) -> bool:
    """True for `encode_env(...)`, however the helper was imported."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == HELPER
    return isinstance(func, ast.Attribute) and func.attr == HELPER


def _offenders() -> list[str]:
    found: list[str] = []
    for path in source_files():
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _target(node)
            if target is None:
                continue
            module, attr = target
            where = f"{path.relative_to(ROOT)}:{node.lineno}"

            if module == "subprocess" and attr in SUBPROCESS_SPAWNS:
                for keyword in node.keywords:
                    if keyword.arg is None:
                        found.append(
                            f"{where} subprocess.{attr}(**kwargs) — an environment "
                            f"that cannot be read here cannot be vouched for; pass "
                            f"env={HELPER}(...) explicitly"
                        )
                    elif keyword.arg == "env" and not _is_helper_call(keyword.value):
                        found.append(
                            f"{where} subprocess.{attr}(env=...) does not go through "
                            f"{HELPER}(): the child's environment would be encoded "
                            f"with the locale's codec"
                        )

            elif module == "os" and attr in OS_SPAWNS:
                args: list[ast.expr] = list(node.args)
                args += [k.value for k in node.keywords if k.arg is not None]
                if not any(_is_helper_call(a) for a in args):
                    found.append(
                        f"{where} os.{attr}() takes an environment and none of its "
                        f"arguments is {HELPER}(...)"
                    )
    return found


def test_every_spawn_that_passes_an_environment_encodes_it() -> None:
    offenders = _offenders()
    assert not offenders, (
        "a child's environment must be built by devops_ai.secrets.encode_env, "
        "never by the locale's codec:\n  " + "\n  ".join(offenders)
    )


def test_the_gate_sees_the_spawn_sites_it_is_meant_to_guard() -> None:
    """The control: a gate that matches nothing would pass just as quietly.

    Counts the `env=`-passing `subprocess` calls the walk actually reaches, so
    an AST change that stopped finding them fails here instead of reporting a
    clean sweep of an empty set.
    """
    guarded = 0
    for path in source_files():
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            target = _target(node) if isinstance(node, ast.Call) else None
            if target == ("subprocess", "run") or (
                target and target[0] == "subprocess" and target[1] in SUBPROCESS_SPAWNS
            ):
                assert isinstance(node, ast.Call)
                if any(k.arg == "env" for k in node.keywords):
                    guarded += 1
    assert guarded >= 3, (
        f"expected at least the three known env-passing spawn sites "
        f"(ksecret run, op://, akv://), the walk found {guarded}"
    )
