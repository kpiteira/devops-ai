"""Tests for the structural-gates template (templates/test_invariants.py).

The template is the verifier that autonomous loops converge on — an enforcement
gap here is a hole optimization pressure will find. These tests load the template
as a module, point it at synthetic project trees, and prove each gate fails when
it must and stays quiet when it should.
"""

from __future__ import annotations

import ast
import importlib.util
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "test_invariants.py"


def load_gates(tmp_path: Path, **overrides: object) -> ModuleType:
    spec = importlib.util.spec_from_file_location("invariants_template", TEMPLATE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SRC_ROOT = tmp_path / "src"
    mod.TESTS_ROOT = tmp_path / "tests" / "unit"  # the template's default scope
    for key, value in overrides.items():
        setattr(mod, key, value)
    return mod


def write(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


# --- Arming: gates must fail loudly when checking nothing ---


def test_armed_fails_when_src_root_missing(tmp_path: Path) -> None:
    mod = load_gates(tmp_path)
    with pytest.raises(AssertionError, match="SRC_ROOT"):
        mod.test_gates_are_armed()


def test_armed_fails_when_src_root_empty(tmp_path: Path) -> None:
    mod = load_gates(tmp_path)
    (tmp_path / "src").mkdir()
    with pytest.raises(AssertionError, match="[Nn]o Python"):
        mod.test_gates_are_armed()


def test_armed_reports_unparseable_files(tmp_path: Path) -> None:
    # no tests/unit dir either — _test_files() must tolerate it
    mod = load_gates(tmp_path)
    write(tmp_path, "src/myapp/good.py", "x = 1\n")
    write(tmp_path, "src/myapp/broken.py", "def (\n")
    with pytest.raises(AssertionError, match="broken.py"):
        mod.test_gates_are_armed()
    # other gates skip the unparseable file instead of crashing every gate
    mod.test_module_class_caps()
    mod.test_layering_contracts()
    mod.test_pattern_uniqueness()


# --- Patch detection ---


def test_patch_calls_counts_all_forms(tmp_path: Path) -> None:
    mod = load_gates(tmp_path)
    tree = ast.parse(
        textwrap.dedent(
            """
            import mock
            from unittest.mock import patch
            from unittest.mock import patch as p

            def test_everything(mocker, monkeypatch):
                p("a")
                patch("b")
                mock.patch("c")
                patch.object(svc, "d")
                patch.dict("os.environ", {})
                mock.patch.object(svc, "e")
                mocker.patch("f")
                mocker.patch.object(svc, "g")
                monkeypatch.setattr(svc, "h", 1)
            """
        )
    )
    assert len(mod._patch_calls(tree)) == 9


def test_conftest_is_scanned_for_density(tmp_path: Path) -> None:
    mod = load_gates(tmp_path, MAX_PATCHES_PER_TEST_FILE=1)
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(
        tmp_path,
        "tests/unit/conftest.py",
        """
        from unittest.mock import patch

        def setup():
            patch("a")
            patch("b")
        """,
    )
    with pytest.raises(AssertionError, match="conftest.py"):
        mod.test_patch_density()


def test_default_scope_is_unit_tests() -> None:
    """The template's own default TESTS_ROOT must target tests/unit/ — the
    loader override above can't catch a wrong default."""
    spec = importlib.util.spec_from_file_location("invariants_default", TEMPLATE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # copied to tests/architecture/, parents[1] is tests/ — default scope is unit/
    assert mod.TESTS_ROOT == TEMPLATE_PATH.resolve().parents[1] / "unit"


def test_integration_tests_not_governed(tmp_path: Path) -> None:
    """Test honesty is the unit-test contract (tdd rule) — integration tests may
    patch freely and must not trip the gates with the default scope."""
    mod = load_gates(
        tmp_path, MAX_PATCHES_PER_TEST_FILE=1, FIRST_PARTY_PREFIXES=("myapp",)
    )
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(
        tmp_path,
        "tests/integration/test_real_adapter.py",
        """
        from unittest.mock import patch

        def test_t():
            with patch("myapp.services.save"):
                with patch("myapp.services.load"):
                    pass
        """,
    )
    mod.test_patch_density()
    mod.test_no_first_party_patching()


# --- First-party patching ---


def test_first_party_patch_object_via_from_import(tmp_path: Path) -> None:
    mod = load_gates(tmp_path, FIRST_PARTY_PREFIXES=("myapp",))
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(
        tmp_path,
        "tests/unit/test_x.py",
        """
        from unittest.mock import patch
        from myapp import services

        def test_t():
            with patch.object(services, "save"):
                pass
        """,
    )
    with pytest.raises(AssertionError, match="myapp.services"):
        mod.test_no_first_party_patching()


def test_first_party_patch_object_via_module_alias(tmp_path: Path) -> None:
    mod = load_gates(tmp_path, FIRST_PARTY_PREFIXES=("myapp",))
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(
        tmp_path,
        "tests/unit/test_x.py",
        """
        from unittest.mock import patch
        import myapp.services as services

        def test_t():
            with patch.object(services, "save"):
                pass
        """,
    )
    with pytest.raises(AssertionError, match="myapp.services"):
        mod.test_no_first_party_patching()


def test_first_party_string_requires_dot_boundary(tmp_path: Path) -> None:
    mod = load_gates(tmp_path, FIRST_PARTY_PREFIXES=("myapp",))
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(
        tmp_path,
        "tests/unit/test_x.py",
        """
        from unittest.mock import patch

        def test_t():
            with patch("myapplib.thing"):
                pass
        """,
    )
    mod.test_no_first_party_patching()  # myapplib is not myapp — must pass


def test_third_party_patching_allowed(tmp_path: Path) -> None:
    mod = load_gates(tmp_path, FIRST_PARTY_PREFIXES=("myapp",))
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(
        tmp_path,
        "tests/unit/test_x.py",
        """
        from unittest.mock import patch
        import requests

        def test_t():
            with patch.object(requests, "get"):
                pass
        """,
    )
    mod.test_no_first_party_patching()


def test_first_party_ratchet_frozen_offenders(tmp_path: Path) -> None:
    src = """
        from unittest.mock import patch
        from myapp import services

        def test_t():
            with patch.object(services, "save"):
                pass
            with patch.object(services, "load"):
                pass
        """
    # within the frozen allowance: passes
    mod = load_gates(
        tmp_path,
        FIRST_PARTY_PREFIXES=("myapp",),
        FIRST_PARTY_PATCH_RATCHET={"test_old.py": 2},
    )
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(tmp_path, "tests/unit/test_old.py", src)
    mod.test_no_first_party_patching()
    # above the frozen allowance: fails
    mod_over = load_gates(
        tmp_path,
        FIRST_PARTY_PREFIXES=("myapp",),
        FIRST_PARTY_PATCH_RATCHET={"test_old.py": 1},
    )
    with pytest.raises(AssertionError, match="ratchet"):
        mod_over.test_no_first_party_patching()


def test_first_party_ratchet_stale_entry_flagged(tmp_path: Path) -> None:
    mod = load_gates(
        tmp_path,
        FIRST_PARTY_PREFIXES=("myapp",),
        FIRST_PARTY_PATCH_RATCHET={"test_old.py": 2},
    )
    write(tmp_path, "src/myapp/a.py", "x = 1\n")
    write(tmp_path, "tests/unit/test_old.py", "def test_t():\n    pass\n")
    with pytest.raises(AssertionError, match="[Rr]atchet entries now compliant"):
        mod.test_no_first_party_patching()


# --- Layering ---


def test_layering_resolves_relative_imports(tmp_path: Path) -> None:
    mod = load_gates(
        tmp_path,
        LAYERING=[("myapp.domain", ("myapp.api",), "domain stays transport-free")],
    )
    write(tmp_path, "src/myapp/api/routes.py", "x = 1\n")
    write(tmp_path, "src/myapp/domain/logic.py", "from ..api import routes\n")
    with pytest.raises(AssertionError, match="myapp.api"):
        mod.test_layering_contracts()


def test_layering_prefix_requires_dot_boundary(tmp_path: Path) -> None:
    mod = load_gates(
        tmp_path,
        LAYERING=[("myapp.domain", ("myapp.api",), "domain stays transport-free")],
    )
    write(tmp_path, "src/myapp/domain/logic.py", "import myapp.apiclient\n")
    mod.test_layering_contracts()  # apiclient is not api — must pass


def test_layering_absolute_import_still_caught(tmp_path: Path) -> None:
    mod = load_gates(
        tmp_path,
        LAYERING=[("myapp.domain", ("myapp.api", "fastapi"), "transport-free")],
    )
    write(tmp_path, "src/myapp/domain/logic.py", "from fastapi import APIRouter\n")
    with pytest.raises(AssertionError, match="fastapi"):
        mod.test_layering_contracts()


# --- Module shape & pattern uniqueness ---


def test_class_caps_count_nested_classes(tmp_path: Path) -> None:
    mod = load_gates(tmp_path, MAX_CLASSES_PER_MODULE=1)
    write(
        tmp_path,
        "src/myapp/shapes.py",
        """
        class Outer:
            class Inner:
                pass
        """,
    )
    with pytest.raises(AssertionError, match="2 classes"):
        mod.test_module_class_caps()


def test_pattern_uniqueness_sees_nested_classes(tmp_path: Path) -> None:
    mod = load_gates(
        tmp_path,
        UNIQUE_PATTERNS=[("results.py", "Result", "result types live in results.py")],
    )
    write(
        tmp_path,
        "src/myapp/service.py",
        """
        class Service:
            class FetchResult:
                pass
        """,
    )
    with pytest.raises(AssertionError, match="FetchResult"):
        mod.test_pattern_uniqueness()


# --- File budgets ---


def test_file_budget_ratchet_growth_and_stale(tmp_path: Path) -> None:
    # frozen file may not grow past its freeze point
    mod = load_gates(
        tmp_path, MAX_FILE_LINES=2, FILE_LINES_RATCHET={"myapp/big.py": 4}
    )
    write(tmp_path, "src/myapp/big.py", "a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n")
    with pytest.raises(AssertionError, match="ratchet froze it at 4"):
        mod.test_file_budgets()
    # compliant file with a leftover ratchet entry is flagged for removal
    mod_stale = load_gates(
        tmp_path, MAX_FILE_LINES=2, FILE_LINES_RATCHET={"myapp/big.py": 4}
    )
    write(tmp_path, "src/myapp/big.py", "a = 1\n")
    with pytest.raises(AssertionError, match="[Rr]atchet entries now compliant"):
        mod_stale.test_file_budgets()
