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
no byte. Parsing a text format manufactures those, and JSON is only today's way
of doing it, so the rule is on what a provider **returns**, not on how it got
there: every installed provider is exercised, and one that invented a surrogate
with YAML, a custom decoder or `ast.literal_eval` fails the same test as one
using `json.loads`.

A one-time scan is not an invariant: a fourth spawn site, or a provider parsing
something new, could reintroduce either defect with every existing test still
green, because nothing that exists today would exercise it. Nor is a rule keyed
on source spelling — `json.loads` and `json.load` are the same defect, which is
why the upstream half no longer reads source at all.

Import aliases are resolved rather than assumed away — `import subprocess as sp`
and `from subprocess import run` are the same spawn as `subprocess.run`, and a
gate that only matched the dotted spelling would be a gate you could walk around
by renaming an import.

Enforced structure is run, not read.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest

from devops_ai.secrets import ResolveContext, SecretResolutionError, resolver
from devops_ai.secrets.resolver import installed_providers

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "devops_ai"
PROVIDERS = SRC / "secrets" / "providers"

ENCODE_ENV = "encode_env"
# A surrogate *inside* the range `surrogateescape` handles. U+D800 would raise
# on the way out and be noticed; U+DCFF silently becomes byte 0xFF — a
# different secret, with nothing reported. The dangerous half of the class, and
# the half a test using U+D800 alone would miss.
SECRET_BODY = "recognisable-secret-body"
INVENTED_SURROGATE = f"\udcff{SECRET_BODY}"
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
# Where `encode_env` may legitimately come from, so a call to it can be resolved
# to an import rather than merely matched by name. Split by `ImportFrom.level`
# because `.module` drops the leading dots: `from ..environ import encode_env`
# (the real spelling in both providers) and `from environ import encode_env` (an
# unrelated top-level module this gate must not vouch for) are both `"environ"`
# here, and only the level tells them apart.
ENCODER_MODULES_RELATIVE = {"environ"}
ENCODER_MODULES_ABSOLUTE = {"devops_ai.secrets", "devops_ai.secrets.environ"}
# `env` is the 11th parameter of `Popen`, and `run`/`call`/`check_*` forward
# their positional arguments to it — so `Popen(cmd, ..., raw_env)` passes an
# environment without ever writing `env=`. Verified against
# `inspect.signature(subprocess.Popen)` rather than remembered, and pinned by
# `test_the_positional_environment_slot_is_where_this_gate_thinks_it_is`.
ENV_POSITION = 10


class Spawn(NamedTuple):
    """One watched spawn call, with the resolver that read its module."""

    path: Path
    node: ast.Call
    module: str
    attr: str
    bindings: Resolver


def source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


class Resolver:
    """Local names back to the module attribute they actually name.

    `import subprocess as sp` makes `sp.run` a spawn; `from subprocess import
    run` makes a bare `run(...)` one. Both are resolved here so the checks below
    can ask one question of a call rather than three.
    """

    def __init__(self, tree: ast.AST) -> None:
        self.modules: dict[str, str] = {}       # local name -> "subprocess"|"os"
        self.functions: dict[str, tuple[str, str]] = {}  # local name -> (mod, attr)
        self.encoders: set[str] = set()         # local names bound to encode_env
        self.wildcards: set[str] = set()        # watched modules imported with `*`
        rebound: set[str] = set()               # names this module defines itself
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in WATCHED:
                        self.modules[alias.asname or alias.name] = root
                        # `import os.path` also binds the name `os`.
                        if alias.asname is None:
                            self.modules[root] = root
            elif isinstance(node, ast.ImportFrom):
                # Absolute or relative is not cosmetic here: `.module` omits the
                # dots, so `from .subprocess import run` — a sibling module that
                # is not the stdlib — would otherwise register as a real spawn,
                # and `from environ import encode_env` as this package's helper.
                absolute = node.level == 0
                if absolute and node.module in WATCHED:
                    for alias in node.names:
                        if alias.name == "*":
                            # `from subprocess import *` binds names that cannot
                            # be enumerated from the AST, so a later bare
                            # `run(...)` would be invisible to the walk and the
                            # gate would report a clean sweep. Recorded so it
                            # fails closed, like `*args` and `**kwargs`.
                            self.wildcards.add(node.module)
                        else:
                            self.functions[alias.asname or alias.name] = (
                                node.module, alias.name
                            )
                elif (
                    node.module in ENCODER_MODULES_ABSOLUTE
                    if absolute
                    else node.module in ENCODER_MODULES_RELATIVE
                ):
                    for alias in node.names:
                        if alias.name == ENCODE_ENV:
                            self.encoders.add(alias.asname or alias.name)
            elif isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ):
                rebound.add(node.name)
            elif isinstance(node, ast.arg):
                rebound.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                rebound.add(node.id)
        # A name the module binds itself is not the import any more. Lexical
        # scoping would say *where* the shadow applies; an architecture gate does
        # not need that machinery to fail closed — dropping the name entirely
        # refuses to vouch for it anywhere, which is the safe direction. Only
        # `encoders` is narrowed: dropping a shadowed *spawn* name would make the
        # gate watch less, which is the unsafe one.
        self.encoders -= rebound

    def is_encoder(self, node: ast.expr) -> bool:
        """A call to *this package's* `encode_env`, resolved rather than spelled.

        Matching the attribute name alone accepted `wrapper.encode_env(raw)` —
        any object with a method of that name satisfied a gate whose invariant
        names `devops_ai.secrets.encode_env` specifically. So the binding is
        resolved to the import that made it, exactly as a spawn's is: a local
        name that came from this package's `environ` module, under whatever
        alias. An attribute call is no longer accepted at all — all three real
        sites import the name, and an unresolvable dotted path is precisely the
        thing that cannot be vouched for.
        """
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in self.encoders
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


def read_source(path: Path) -> ast.AST:
    # Never a bare `read_text()`: that decodes with the *locale's* codec, so
    # under the `LC_ALL=C` this change is validated in, this gate died on the
    # first em dash in `src/` before checking anything. The third site of the
    # harness's own version of #58, after `run_child`'s `text=True` and the
    # repo-path test's `Path.mkdir` — source is UTF-8 by PEP 3120, so say so.
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def watched_spawns(
    tree: ast.AST, bindings: Resolver
) -> Iterator[tuple[ast.Call, str, str]]:
    """Each call in `tree` that reaches a watched spawn, however it is spelled."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = bindings.target(node)
        if target is None:
            continue
        module, attr = target
        if attr in WATCHED[module]:
            yield node, module, attr


def spawns_passing_an_environment() -> list[Spawn]:
    """Every watched spawn call in `src/`, with the module and attribute named."""
    found = []
    for path in source_files():
        tree = read_source(path)
        bindings = Resolver(tree)
        for node, module, attr in watched_spawns(tree, bindings):
            found.append(Spawn(path, node, module, attr, bindings))
    return found


def offenders_in(tree: ast.AST, where: str) -> list[str]:
    """Every way this module could hand a child a locale-encoded environment.

    Takes a tree rather than walking `src/` so each rule below can be falsified
    against source written for the purpose, instead of only by planting a real
    offender in the package and putting it back afterwards.
    """
    offenders: list[str] = []
    bindings = Resolver(tree)
    for wildcarded in sorted(bindings.wildcards):
        # `from subprocess import *` leaves an alias literally named `*`. Every
        # name it binds is invisible, so a later bare `run(cmd, env=raw)` is not
        # a spawn as far as this walk is concerned and the gate would report a
        # clean sweep of a file it never understood.
        offenders.append(
            f"{where} does `from {wildcarded} import *` — the names it binds "
            f"cannot be read here, so a spawn written as a bare call would be "
            f"invisible to this gate; import explicitly"
        )
    for node, module, attr in watched_spawns(tree, bindings):
        where_at = f"{where}:{node.lineno}"
        if module == "subprocess":
            # A splatted `*args` can carry the environment into the positional
            # slot below without any of it being readable here.
            if any(isinstance(a, ast.Starred) for a in node.args):
                offenders.append(
                    f"{where_at} {module}.{attr}(*args) — arguments that cannot be "
                    f"read here cannot be vouched for; pass "
                    f"env={ENCODE_ENV}(...) explicitly"
                )
            elif len(node.args) > ENV_POSITION and not bindings.is_encoder(
                node.args[ENV_POSITION]
            ):
                offenders.append(
                    f"{where_at} {module}.{attr}() passes an environment in "
                    f"positional slot {ENV_POSITION} without {ENCODE_ENV}(): "
                    f"`env=` is not the only way to hand a child an environment"
                )
            for keyword in node.keywords:
                if keyword.arg is None:
                    offenders.append(
                        f"{where_at} {module}.{attr}(**kwargs) — an environment that "
                        f"cannot be read here cannot be vouched for; pass "
                        f"env={ENCODE_ENV}(...) explicitly"
                    )
                elif keyword.arg == "env" and not bindings.is_encoder(keyword.value):
                    offenders.append(
                        f"{where_at} {module}.{attr}(env=...) does not go through "
                        f"{ENCODE_ENV}(): the child's environment would be encoded "
                        f"with the locale's codec"
                    )
        else:
            # "Some argument is encode_env(...)" was never a check on *the*
            # environment: `os.execve(path, encode_env(argv), raw_env)` satisfied
            # it while handing the child a raw environment, because the encoded
            # argument was the argv. Each of these APIs puts the environment in a
            # different slot (`execve(path, args, env)` but `spawnve(mode, path,
            # args, env)`), and none is called anywhere in `src/` — so a slot
            # table here would be guesswork no call site exercises. Refused
            # outright instead, which is what the note on OS_SPAWNS always
            # claimed to buy: adding the first one is a decision, and part of
            # that decision is teaching this gate where its environment goes.
            offenders.append(
                f"{where_at} {module}.{attr}() hands a child an environment in a "
                f"positional slot this gate does not track. No {module} spawn "
                f"exists in src/ today; adding the first one means teaching "
                f"this gate its environment slot, deliberately"
            )
    return offenders


def test_every_spawn_that_passes_an_environment_encodes_it() -> None:
    offenders: list[str] = []
    for path in source_files():
        offenders += offenders_in(read_source(path), str(path.relative_to(ROOT)))
    assert not offenders, (
        "a child's environment must be built by devops_ai.secrets.encode_env, "
        "never by the locale's codec:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "provider", installed_providers(), ids=lambda p: p.SCHEME
)
def test_no_provider_can_hand_a_child_a_value_it_cannot_receive(
    provider: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every provider, exercised — not every provider that spells it `json.loads`.

    The defect is a value, so the rule is on the value. A provider is made to
    return a lone surrogate and the resolver must refuse it, whatever the
    provider parsed and however it spelled the call. A provider added tomorrow
    is covered by existing, because the parametrisation walks the package.
    """
    monkeypatch.setattr(resolver, "provider_for", lambda ref: provider)
    monkeypatch.setattr(provider, "resolve", lambda ref, ctx: INVENTED_SURROGATE)
    ref = f"{provider.SCHEME}whatever"

    if getattr(provider, resolver.INHERITS_OS_BYTES, False):
        assert resolver.resolve("K", ref, ResolveContext()) == INVENTED_SURROGATE
        return

    with pytest.raises(SecretResolutionError) as caught:
        resolver.resolve("K", ref, ResolveContext())
    message = caught.value.message
    assert "unpaired surrogate" in message
    assert SECRET_BODY not in message, "the refusal quoted the value"
    assert "dcff" not in message.lower(), "not even as an escape"


def test_the_inherited_bytes_opt_out_is_exactly_one_scheme() -> None:
    """Widening it is a decision about what a child may receive, not a detail.

    Pinned rather than merely asserted non-empty: every scheme listed here is a
    provider whose values skip the check above, so adding one has to be a line
    someone chose to write and a reviewer chose to accept.
    """
    opted_out = {
        p.SCHEME for p in installed_providers()
        if getattr(p, resolver.INHERITS_OS_BYTES, False)
    }
    assert opted_out == {"env://"}


def test_the_gate_sees_the_sites_it_is_meant_to_guard() -> None:
    """The control: a gate that matched nothing would pass just as quietly.

    Counts what the walks actually reach, so an AST change that stopped finding
    the known sites fails here instead of reporting a clean sweep of an empty
    set.
    """
    guarded = [
        f"{p.relative_to(ROOT)}:{n.lineno}"
        for p, n, module, _, _b in spawns_passing_an_environment()
        if module == "subprocess" and any(k.arg == "env" for k in n.keywords)
    ]
    assert len(guarded) >= 3, (
        f"expected at least the three known env-passing spawn sites "
        f"(ksecret run, op://, akv://), the walk found {guarded}"
    )

    # The parametrised rule above would run zero cases, silently, if the walk
    # over the providers package ever came back empty — a green sweep of
    # nothing. Counted here rather than trusted.
    schemes = {p.SCHEME for p in installed_providers()}
    assert {"env://", "dotenv://", "op://", "akv://", "bao://"} <= schemes, (
        f"the provider walk no longer reaches the known schemes: {sorted(schemes)}"
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


def test_a_lookalike_encode_env_does_not_satisfy_the_gate() -> None:
    """The gate names `devops_ai.secrets.encode_env`, so only that may satisfy it.

    Matching the trailing attribute accepted `wrapper.encode_env(raw)` from any
    object at all — a gate whose invariant is a specific function but whose
    check was a spelling. Resolved to the import that made the binding, under
    whatever alias, with a lookalike as the control.
    """
    real = ast.parse(
        "from devops_ai.secrets import encode_env\n"
        "subprocess.run(cmd, env=encode_env(raw))\n"
    )
    aliased = ast.parse(
        "from ..environ import encode_env as enc\n"
        "subprocess.run(cmd, env=enc(raw))\n"
    )
    lookalike = ast.parse(
        "import wrapper\nsubprocess.run(cmd, env=wrapper.encode_env(raw))\n"
    )
    unimported = ast.parse("subprocess.run(cmd, env=encode_env(raw))\n")

    def env_argument(tree: ast.AST) -> ast.expr:
        call = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and any(k.arg == "env" for k in n.keywords)
        )
        return next(k.value for k in call.keywords if k.arg == "env")

    assert Resolver(real).is_encoder(env_argument(real))
    assert Resolver(aliased).is_encoder(env_argument(aliased))
    assert not Resolver(lookalike).is_encoder(env_argument(lookalike)), (
        "any object's .encode_env satisfied the gate"
    )
    assert not Resolver(unimported).is_encoder(env_argument(unimported)), (
        "a name this module never imported satisfied the gate"
    )


# Three ways this gate could vouch for a binding it cannot actually prove — one
# mechanism, three spellings. Each below is a resolution the AST does not
# support, so each fails closed rather than guessing.


def test_a_relative_import_is_not_the_absolute_one_that_shares_its_tail() -> None:
    """`ImportFrom.module` omits the dots, so `level` is the only separator.

    Both tables read it. `from ..environ import encode_env` is how both
    providers import the real helper; `from environ import encode_env` is some
    unrelated top-level module, and the two arrive here spelled identically.
    The mirror image is on the spawn side: `from .subprocess import run` is a
    sibling module, not the stdlib spawn this gate watches.
    """
    def accepts_encoder(source: str) -> bool:
        tree = ast.parse(source + f"{ENCODE_ENV}(raw)\n")
        call = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == ENCODE_ENV
        )
        return Resolver(tree).is_encoder(call)

    # The two spellings that exist in src/, plus the absolute ones tests use.
    assert accepts_encoder("from .environ import encode_env\n")
    assert accepts_encoder("from ..environ import encode_env\n")
    assert accepts_encoder("from devops_ai.secrets import encode_env\n")
    assert accepts_encoder("from devops_ai.secrets.environ import encode_env\n")
    # An unrelated top-level `environ`, indistinguishable once the dots are gone.
    assert not accepts_encoder("from environ import encode_env\n"), (
        "any top-level module named environ could vouch for the environment"
    )
    # And the same confusion on the spawn table, in the other direction.
    assert Resolver(ast.parse("from subprocess import run\n")).functions == {
        "run": ("subprocess", "run")
    }
    assert Resolver(ast.parse("from .subprocess import run\n")).functions == {}


def test_a_wildcard_import_of_a_spawn_module_fails_closed() -> None:
    """`from subprocess import *` binds names that cannot be enumerated here.

    A later bare `run(cmd, env=raw)` is then not a spawn as far as the walk is
    concerned, and the gate reports a clean sweep of a file it never understood.
    """
    wildcarded = offenders_in(
        ast.parse("from subprocess import *\nrun(cmd, env=raw_env)\n"), "w.py"
    )
    assert len(wildcarded) == 1, wildcarded
    assert "import *" in wildcarded[0]

    # Control: the same spawn imported explicitly and encoded is clean, so
    # "offends on everything" cannot satisfy the assertion above.
    assert offenders_in(
        ast.parse(
            "from devops_ai.secrets import encode_env\n"
            "from subprocess import run\n"
            "run(cmd, env=encode_env(raw_env))\n"
        ),
        "n.py",
    ) == []


def test_an_encode_env_the_module_rebinds_is_not_vouched_for() -> None:
    """An imported name the module redefines is not that import any more.

    The binding tables come from `ast.walk`, which has no notion of scope, so a
    local `def encode_env` or a parameter of that name satisfied a gate whose
    invariant names `devops_ai.secrets.encode_env` specifically.
    """
    imported = (
        "from devops_ai.secrets import encode_env\n"
        "import subprocess\n"
        "subprocess.run(cmd, env=encode_env(raw_env))\n"
    )
    assert offenders_in(ast.parse(imported), "m.py") == []

    shadowed_by_a_def = imported + "def encode_env(x):\n    return x\n"
    shadowed_by_a_param = (
        "from devops_ai.secrets import encode_env\n"
        "import subprocess\n"
        "def f(encode_env):\n"
        "    subprocess.run(cmd, env=encode_env(raw_env))\n"
    )
    shadowed_by_assignment = (
        "from devops_ai.secrets import encode_env\n"
        "import subprocess\n"
        "encode_env = str\n"
        "subprocess.run(cmd, env=encode_env(raw_env))\n"
    )
    for source in (shadowed_by_a_def, shadowed_by_a_param, shadowed_by_assignment):
        # The *reason*, not merely "some offender": a bare `!= []` would be
        # satisfied by an unrelated rule firing, and could not tell the shadow
        # being caught from the file being rejected for something else.
        offenders = offenders_in(ast.parse(source), "m.py")
        assert len(offenders) == 1, (source, offenders)
        assert f"does not go through {ENCODE_ENV}()" in offenders[0], offenders


def test_an_os_spawn_is_refused_rather_than_guessed_at() -> None:
    """"Some argument is `encode_env(...)`" was never a check on *the* argument.

    `os.execve(path, encode_env(argv), raw_env)` satisfied it while handing the
    child a raw environment — the encoded argument was the argv. The slot
    differs per API (`execve(path, args, env)` but `spawnve(mode, path, args,
    env)`) and none is called in `src/`, so there is no call site to check a
    slot table against. Refused outright instead.
    """
    encoded_argv_raw_env = offenders_in(
        ast.parse(
            "from devops_ai.secrets import encode_env\n"
            "import os\n"
            "os.execve(path, encode_env(argv), raw_env)\n"
        ),
        "m.py",
    )
    assert len(encoded_argv_raw_env) == 1, encoded_argv_raw_env
    assert "does not track" in encoded_argv_raw_env[0]

    # Control: an `os` call outside the spawn family is not touched.
    assert offenders_in(ast.parse("import os\nos.getcwd()\n"), "m.py") == []


def test_the_positional_environment_slot_is_where_this_gate_thinks_it_is() -> None:
    """`ENV_POSITION` is read off `Popen`, never remembered.

    `env=` is not the only way to hand a child an environment: `Popen` takes it
    positionally and `run`/`call`/`check_*` forward positional arguments to it,
    so a spawn written that way passed a gate that only read `node.keywords`.
    If CPython ever reorders those parameters this fails here rather than
    quietly guarding the wrong slot.
    """
    import inspect
    import subprocess

    assert list(inspect.signature(subprocess.Popen).parameters).index("env") == (
        ENV_POSITION
    )

    # A positive and a negative, not one of each shape. Asserting only that a
    # raw name is refused would pass against a wholly broken `is_encoder`: the
    # synthetic tree imports nothing, so `encoders` is empty and every node is
    # refused. The encoded form has to be *accepted* for the pair to mean
    # anything — self-review caught that assertion proving nothing.
    raw = ast.parse("subprocess.run(a,b,c,d,e,f,g,h,i,j,raw_env)\n")
    encoded = ast.parse(
        "from devops_ai.secrets import encode_env\n"
        "subprocess.run(a,b,c,d,e,f,g,h,i,j,encode_env(raw_env))\n"
    )

    def env_slot(tree: ast.AST) -> ast.expr:
        spawn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and len(n.args) > ENV_POSITION
        )
        return spawn.args[ENV_POSITION]

    assert not Resolver(raw).is_encoder(env_slot(raw))
    assert Resolver(encoded).is_encoder(env_slot(encoded)), (
        "the encoded positional form must be accepted, or the negative above "
        "proves nothing"
    )


def unencodable_docstrings(tree: ast.AST, where: str) -> list[str]:
    """Docstrings in `tree` that have no UTF-8 encoding, each named by its line.

    Split out from the gate below so the *reporting* can be exercised on
    synthetic source. Detection was never the fragile half.
    """
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc is None:
            continue
        try:
            doc.encode("utf-8")
        except UnicodeEncodeError:
            # The docstring's own line, never the node's: `ast.Module` has no
            # `lineno` at all, so reading one turned a caught module-level
            # offender into an `AttributeError` from inside the gate — a red
            # that says "the gate is broken" instead of naming the file. The
            # `getattr` beside it already conceded that a module has no `name`;
            # the line needed the same concession. `get_docstring` returned a
            # string, so `body[0]` is that literal.
            offenders.append(
                f"{where}:{node.body[0].lineno} "
                f"{getattr(node, 'name', '<module>')} — double the backslash: "
                f"a docstring is a literal, so the escape builds the character"
            )
    return offenders


def test_a_module_docstring_offender_is_named_rather_than_crashing_the_gate() -> None:
    """The likeliest offender was the one the gate could not report.

    A module docstring is where documentation *about* this rule gets written —
    this file's own is one — and it is exactly the node with no `lineno`.
    Caught, then lost building the message.
    """
    module_level = ast.parse('"""bad \\ud800 doc"""\n')
    in_a_function = ast.parse('def f():\n    """bad \\ud800 doc"""\n')
    # Control: an astral character that *is* encodable, so "always reports an
    # offender" cannot satisfy the two above.
    encodable = ast.parse('"""a paired \\U0001F600 doc"""\n')

    assert unencodable_docstrings(module_level, "m.py") == [
        "m.py:1 <module> — double the backslash: "
        "a docstring is a literal, so the escape builds the character"
    ]
    assert unencodable_docstrings(in_a_function, "m.py") == [
        "m.py:2 f — double the backslash: "
        "a docstring is a literal, so the escape builds the character"
    ]
    assert unencodable_docstrings(encodable, "m.py") == []


def test_no_module_can_be_made_unimportable_by_its_own_docstring() -> None:
    """The rule this package enforces on secrets, enforced on itself.

    `_representable`'s docstring said a provider must not return a lone
    surrogate and contained one: a docstring is a string literal, so a singly
    written `\\uD800` is not a mention of a surrogate but one. On Python 3.12
    that compiles; on 3.14 the module cannot be compiled at all, and
    `pyproject.toml` says `requires-python = ">=3.11"` while CI runs only 3.12 —
    so nothing here would have said so. Measured on both, not reasoned about:
    `python3.14 -m compileall` exits 1 on a file whose docstring carries one,
    while the same escape in an assignment, an f-string, a list or a default
    argument compiles clean — which is why only this node kind is walked.

    Checked on every docstring rather than on the one that was wrong, because
    the next one is written by someone documenting the same rule.
    """
    offenders: list[str] = []
    # `src/` and `tests/` both: a docstring like this one is most likely to be
    # written by whoever is documenting the rule, and that is as often a test.
    # The gate's name says "no module", so it has to mean every module here.
    for path in source_files() + sorted((ROOT / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        offenders += unencodable_docstrings(tree, str(path.relative_to(ROOT)))
    assert not offenders, (
        "a docstring that cannot be encoded as UTF-8 makes its module "
        "uncompilable on Python 3.14:\n  " + "\n  ".join(offenders)
    )
