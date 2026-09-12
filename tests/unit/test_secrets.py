"""Tests for the secret reference resolver and its providers.

No patching: a ResolveContext carries the environment and the base directory, so
every case here runs the real code against a real directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devops_ai.secrets import (
    ERROR,
    LITERAL,
    OK,
    ResolveContext,
    SecretResolutionError,
    check,
    parse_env_file,
    provider_for,
    resolve,
    resolve_all,
    schemes,
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "\n"
        "PLAIN=plain-value\n"
        'DOUBLE="double-value"\n'
        "SINGLE='single-value'\n"
        "export EXPORTED=exported-value\n"
        "  SPACED  =  spaced-value  \n"
        "WITH_EQUALS=a=b=c\n"
        "EMPTY=\n"
        "not-an-assignment\n"
    )
    return tmp_path


def ctx(base: Path, **env: str) -> ResolveContext:
    return ResolveContext(base_dir=base, env=env)


# --- The KEY=value format ---


class TestEnvFileFormat:
    def test_parses_every_accepted_line_shape(self, project: Path) -> None:
        values = parse_env_file((project / ".env").read_text())
        assert values == {
            "PLAIN": "plain-value",
            "DOUBLE": "double-value",
            "SINGLE": "single-value",
            "EXPORTED": "exported-value",
            "SPACED": "spaced-value",
            "WITH_EQUALS": "a=b=c",
            "EMPTY": "",
        }

    def test_a_hash_inside_a_value_is_not_a_comment(self) -> None:
        assert parse_env_file("TOKEN=abc#def") == {"TOKEN": "abc#def"}

    def test_mismatched_quotes_are_left_alone(self) -> None:
        assert parse_env_file("K=\"half'") == {"K": "\"half'"}

    def test_later_lines_win(self) -> None:
        assert parse_env_file("K=first\nK=second\n") == {"K": "second"}


# --- Host environment, with the .env fallback ---


class TestHostEnvironment:
    def test_exported_variable_wins_over_the_file(self, project: Path) -> None:
        context = ctx(project, PLAIN="from-shell")
        assert resolve("K", "$PLAIN", context) == "from-shell"
        assert resolve("K", "env://PLAIN", context) == "from-shell"

    def test_falls_back_to_the_env_file(self, project: Path) -> None:
        context = ctx(project)
        assert resolve("K", "$PLAIN", context) == "plain-value"
        assert resolve("K", "env://PLAIN", context) == "plain-value"

    def test_missing_everywhere_names_the_variable(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError) as exc:
            resolve("MY_KEY", "$ABSENT", ctx(project))
        assert "ABSENT" in exc.value.message
        assert exc.value.message.startswith("MY_KEY: ")
        assert "not set" in exc.value.message

    def test_missing_fallback_file_is_not_an_error_by_itself(
        self, tmp_path: Path
    ) -> None:
        assert resolve("K", "$PRESENT", ctx(tmp_path, PRESENT="v")) == "v"
        with pytest.raises(SecretResolutionError, match="not set"):
            resolve("K", "$ABSENT", ctx(tmp_path))

    def test_the_scheme_is_claimed_even_when_malformed(self, project: Path) -> None:
        """A typo must not resolve to itself — that is how a scheme is claimed."""
        assert provider_for("env://") is not None
        with pytest.raises(SecretResolutionError, match="Malformed"):
            resolve("K", "env://", ctx(project))

    def test_a_bare_dollar_is_a_literal(self, project: Path) -> None:
        assert resolve("K", "$", ctx(project)) == "$"
        assert provider_for("$") is None


# --- A key in a named file ---


class TestDotenvReference:
    def test_reads_the_named_key(self, project: Path) -> None:
        assert resolve("K", "dotenv://.env#SINGLE", ctx(project)) == "single-value"

    def test_path_is_relative_to_the_base_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "config"
        nested.mkdir()
        (nested / "prod.env").write_text("TOKEN=nested-token\n")
        assert (
            resolve("K", "dotenv://config/prod.env#TOKEN", ctx(tmp_path))
            == "nested-token"
        )

    def test_absolute_paths_are_left_alone(self, tmp_path: Path) -> None:
        target = tmp_path / "abs.env"
        target.write_text("TOKEN=absolute-token\n")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        assert (
            resolve("K", f"dotenv://{target}#TOKEN", ctx(elsewhere))
            == "absolute-token"
        )

    def test_missing_key_names_the_key_and_the_file(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError) as exc:
            resolve("K", "dotenv://.env#ABSENT", ctx(project))
        assert "ABSENT" in exc.value.message and ".env" in exc.value.message

    def test_missing_file_names_the_file(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError, match="not found"):
            resolve("K", "dotenv://nope.env#KEY", ctx(project))

    def test_a_reference_without_a_key_is_malformed(self, project: Path) -> None:
        with pytest.raises(SecretResolutionError, match="Malformed"):
            resolve("K", "dotenv://.env", ctx(project))


# --- Literals and unregistered schemes ---


class TestLiterals:
    @pytest.mark.parametrize(
        "value",
        ["plain-text", "", "postgres://dev:dev@db:5432/app", "weird://not/registered"],
    )
    def test_unclaimed_references_resolve_to_themselves(
        self, value: str, project: Path
    ) -> None:
        assert provider_for(value) is None
        assert resolve("K", value, ctx(project)) == value


class TestUnreadableFiles:
    """Every caller promises an actionable message, so nothing may escape as a crash."""

    def test_non_utf8_file_is_an_os_error_not_a_decode_crash(
        self, tmp_path: Path
    ) -> None:
        bad = tmp_path / "binary.env"
        bad.write_bytes(b"KEY=\xff\xfe not text\n")

        with pytest.raises(SecretResolutionError) as exc:
            resolve("K", "dotenv://binary.env#KEY", ctx(tmp_path))
        assert "binary.env" in exc.value.message
        assert "UTF-8" in exc.value.message

    def test_utf8_is_read_as_utf8_whatever_the_locale_says(
        self, tmp_path: Path
    ) -> None:
        """The reader promises UTF-8; the locale default is not a promise."""
        (tmp_path / ".env").write_bytes("K=caf\u00e9-\u00fcber\n".encode())
        assert resolve("K", "dotenv://.env#K", ctx(tmp_path)) == "caf\u00e9-\u00fcber"

    def test_the_env_fallback_survives_an_undecodable_dotenv(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".env").write_bytes(b"K=\xff\xfe\n")
        with pytest.raises(SecretResolutionError, match="UTF-8"):
            resolve("K", "$ABSENT", ctx(tmp_path))


# --- Discovery ---


class TestDiscovery:
    def test_every_milestone_scheme_has_a_provider(self) -> None:
        assert {"env://", "dotenv://", "op://"} <= set(schemes())

    def test_each_reference_is_claimed_by_exactly_one_provider(self) -> None:
        for ref in ("env://A", "$A", "dotenv://f#A", "op://v/i/f"):
            assert provider_for(ref) is not None


# --- Resolving a set of references ---


class TestResolveAll:
    def test_collects_every_failure_and_keeps_the_successes(
        self, project: Path
    ) -> None:
        resolved, errors = resolve_all(
            {
                "GOOD": "dotenv://.env#PLAIN",
                "LIT": "just-text",
                "BAD": "dotenv://.env#ABSENT",
                "WORSE": "$ABSENT",
            },
            ctx(project),
        )
        assert resolved == {"GOOD": "plain-value", "LIT": "just-text"}
        assert {e.var_name for e in errors} == {"BAD", "WORSE"}
        assert all(e.message.startswith(f"{e.var_name}: ") for e in errors)

    def test_no_value_leaks_into_an_error_message(self, project: Path) -> None:
        _, errors = resolve_all({"BAD": "dotenv://.env#ABSENT"}, ctx(project))
        assert "plain-value" not in errors[0].message


# --- Classification, without values ---


class TestCheck:
    def test_classifies_ok_literal_and_error(self, project: Path) -> None:
        context = ctx(project)
        results = [
            check("A", "dotenv://.env#PLAIN", context),
            check("C", "literal-c", context),
            check("U", "weird://not/registered", context),
            check("BAD", "dotenv://.env#ABSENT", context),
        ]
        assert [r.status for r in results] == [OK, LITERAL, LITERAL, ERROR]
        assert all("plain-value" not in r.format() for r in results)

    def test_an_error_line_carries_the_reason_once(self, project: Path) -> None:
        line = check("BAD", "dotenv://.env#ABSENT", ctx(project)).format()
        assert line.startswith("BAD: error — ")
        assert "ABSENT" in line
        assert line.count("BAD") == 1, f"the key is a column, not a prefix: {line}"

    def test_the_stderr_form_of_the_same_failure_is_labelled(
        self, project: Path
    ) -> None:
        with pytest.raises(SecretResolutionError) as exc:
            resolve("BAD", "dotenv://.env#ABSENT", ctx(project))
        assert exc.value.message == f"BAD: {exc.value.reason}"

    def test_an_ok_line_is_just_the_status(self, project: Path) -> None:
        assert check("A", "dotenv://.env#PLAIN", ctx(project)).format() == "A: ok"
