"""`ksecret write`: what each backend is handed, and what is refused before it.

The seam is the subprocess, as in `test_secrets_akv`: a real `az` and a real `op`
on the PATH the provider is given, recording their argv *and* their stdin. That
makes the one invariant the brief could only ask a reviewer to check — a secret
never reaches a command line — something this suite runs on every commit.

The happy paths against real backends live in the acceptance suite. What is
worth pinning here is everything it cannot reach: the refusals, the spellings,
and which of two call shapes a provider chose.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from devops_ai.secrets import ProviderError, ResolveContext, resolve, write
from devops_ai.secrets.providers import azurekeyvault, dotenv, onepassword

VALUE = "s3cr3t-value-aa11"
CALLS = "calls.json"


# --------------------------------------------------------------- fake CLIs


def fake_cli(directory: Path, name: str, answers: dict[str, dict]) -> Path:
    """A `name` on `directory` that logs each call and answers as scripted.

    `answers` maps a space-joined argv prefix ("item create") to
    `{"stdout", "stderr", "code"}`; the longest matching prefix wins. Calls are
    appended to one log so a test can assert the *sequence* a provider made,
    which is where the create-or-update decision actually shows.
    """
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / name
    log = directory / CALLS
    program.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        f"log = pathlib.Path({str(log)!r})\n"
        f"answers = json.loads({json.dumps(json.dumps(answers))})\n"
        "argv = sys.argv[1:]\n"
        # Only the calls that take a template are read from: `subprocess.run`
        # leaves stdin inherited otherwise, and a read of it would block.
        "stdin = None\n"
        "if '-' in argv or (len(argv) > 1 and argv[1] in ('edit', 'set')):\n"
        "    stdin = sys.stdin.read()\n"
        # The file a value travels in is recorded as it was at call time: mode
        # included, because 0600 is the property that makes the file allowable,
        # and after the call the file is gone.
        "carried = None\n"
        "if '--file' in argv:\n"
        "    path = argv[argv.index('--file') + 1]\n"
        "    carried = {'text': pathlib.Path(path).read_text('utf-8'),\n"
        "               'mode': os.stat(path).st_mode & 0o777, 'path': path}\n"
        "calls = json.loads(log.read_text()) if log.exists() else []\n"
        "calls.append({'argv': argv, 'stdin': stdin, 'file': carried})\n"
        "log.write_text(json.dumps(calls))\n"
        "answer = {}\n"
        "for prefix, scripted in answers.items():\n"
        "    parts = prefix.split(' ') if prefix else []\n"
        "    if argv[:len(parts)] != parts: continue\n"
        "    if len(parts) >= len(answer.get('_', [])):\n"
        "        answer = dict(scripted, _=parts)\n"
        "sys.stdout.write(answer.get('stdout', ''))\n"
        "sys.stderr.write(answer.get('stderr', ''))\n"
        "sys.exit(answer.get('code', 0))\n",
        encoding="utf-8",
    )
    program.chmod(0o755)
    return log


def calls_of(log: Path) -> list[dict]:
    return json.loads(log.read_text()) if log.exists() else []


def on_path(directory: Path) -> ResolveContext:
    """A context whose PATH holds only the fake CLI."""
    return ResolveContext(env={"PATH": str(directory)})


# ------------------------------------------------------------ the dispatch


class TestWhatTheWriterDispatchesTo:
    def test_a_literal_is_refused_without_being_echoed_back(self) -> None:
        """A literal *is* its value, so naming it in the refusal leaks it.

        The same reason a bare `read` of a literal prints `ok (literal)` rather
        than the reference (M1 amendment, 2026-09-12).
        """
        literal = "postgres://user:hunter2@db/app"

        with pytest.raises(ProviderError) as caught:
            write(literal, VALUE)

        assert literal not in str(caught.value)
        assert "hunter2" not in str(caught.value)
        assert "not a secret reference" in str(caught.value)

    def test_a_provider_that_only_reads_is_refused_by_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The contract for a backend added later that has no write.

        Exercised through a stub rather than left to be discovered by an
        `AttributeError` in someone's terminal: `write` is optional on a
        provider by design, so the sentence for a provider without one is part
        of the surface and not a fallback nobody reads.
        """

        class ReadOnly:
            SCHEME = "readonly://"

        monkeypatch.setattr(
            "devops_ai.secrets.writer.provider_for", lambda ref: ReadOnly()
        )

        with pytest.raises(ProviderError) as caught:
            write("readonly://a/b", VALUE)

        assert "readonly://" in str(caught.value)
        assert "cannot be written" in str(caught.value)

    def test_the_host_environment_says_why_it_cannot_be_written(self) -> None:
        for ref in ("env://SOME_NAME", "$SOME_NAME"):
            with pytest.raises(ProviderError) as caught:
                write(ref, VALUE)
            assert "read-only" in str(caught.value)
            assert ref in str(caught.value)
            assert VALUE not in str(caught.value)


# ------------------------------------------------------------------ dotenv


def wrote(tmp_path: Path, ref: str, value: str) -> str:
    """Write, then read the whole file back *untranslated*.

    `newline=""` on purpose: `read_text` maps every CRLF to an LF, so a test
    asserting that a CRLF file stayed one would pass against a writer that had
    flattened it.
    """
    write(ref, value, ResolveContext(base_dir=tmp_path))
    path = tmp_path / ref.split("#")[0][len(dotenv.SCHEME):]
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.read()


class TestTheDotenvFile:
    def test_only_the_target_line_changes(self, tmp_path: Path) -> None:
        original = (
            "# a comment\n"
            "\n"
            "export KEEP='single quoted'\n"
            "TARGET=old\n"
            "AFTER=after\n"
        )
        (tmp_path / "f.env").write_text(original)

        after = wrote(tmp_path, "dotenv://f.env#TARGET", VALUE)

        assert after == original.replace("TARGET=old", f"TARGET={VALUE}")

    def test_an_export_prefix_survives_the_line_that_is_replaced(
        self, tmp_path: Path
    ) -> None:
        """Dropping the word changes what the file *does* when it is sourced,
        which is well outside "set this key". Falsified by rebuilding the line
        as `KEY=value`: this fails, and nothing else does."""
        (tmp_path / "f.env").write_text("  export TARGET=old\nB=2\n")

        after = wrote(tmp_path, "dotenv://f.env#TARGET", VALUE)

        assert after == f"  export TARGET={VALUE}\nB=2\n"

    def test_crlf_endings_survive_the_line_that_is_replaced(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "f.env").write_text("A=1\r\nTARGET=old\r\nB=2\r\n", newline="")

        after = wrote(tmp_path, "dotenv://f.env#TARGET", VALUE)

        assert after == f"A=1\r\nTARGET={VALUE}\r\nB=2\r\n"

    def test_a_file_that_ends_without_a_newline_gains_one_before_the_append(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "f.env").write_text("A=1")

        after = wrote(tmp_path, "dotenv://f.env#NEW", VALUE)

        assert after == f"A=1\nNEW={VALUE}\n"

    def test_duplicate_lines_for_the_key_collapse_to_one(
        self, tmp_path: Path
    ) -> None:
        """Both would otherwise be read — the last one wins — and a stale first
        line is a value someone will later believe."""
        (tmp_path / "f.env").write_text("K=first\nOTHER=x\nK=second\n")

        after = wrote(tmp_path, "dotenv://f.env#K", VALUE)

        assert after == f"K={VALUE}\nOTHER=x\n"

    @pytest.mark.parametrize(
        "value",
        [
            "plain",
            "  leading and trailing  ",
            '"already quoted"',
            "'single'",
            "has=equals",
            "has#hash",
            "$NOT_A_REFERENCE",
            "",
            '"',
            '""',
            "'",
            "  ",
            "=",
            "#",
            "café-中文",
            "\ttab",
        ],
        ids=lambda v: repr(v)[:24],
    )
    def test_a_value_is_written_only_in_a_spelling_that_reads_back(
        self, tmp_path: Path, value: str
    ) -> None:
        wrote(tmp_path, "dotenv://f.env#K", value)

        assert resolve("K", "dotenv://f.env#K", ResolveContext(base_dir=tmp_path)) == (
            value
        )

    @pytest.mark.parametrize(
        "value",
        [
            "two\nlines",
            "trailing\n",
            "carriage\rreturn",
            # `str.splitlines` — which is what the reader splits on — counts
            # these too, so a writer that only looked for \n or \r would put a
            # value into this file that reads back cut in half.
            "vertical\vtab",
            "line\u2028separator",
        ],
    )
    def test_a_value_the_format_cannot_hold_is_refused_not_mangled(
        self, tmp_path: Path, value: str
    ) -> None:
        (tmp_path / "f.env").write_text("K=old\n")

        with pytest.raises(ProviderError) as caught:
            write("dotenv://f.env#K", value, ResolveContext(base_dir=tmp_path))

        assert value not in str(caught.value)
        assert "line break" in str(caught.value)
        assert (tmp_path / "f.env").read_text() == "K=old\n", "the file is untouched"

    def test_a_created_file_is_owner_only_and_an_existing_one_keeps_its_mode(
        self, tmp_path: Path
    ) -> None:
        write("dotenv://new.env#K", VALUE, ResolveContext(base_dir=tmp_path))
        assert stat.S_IMODE(os.stat(tmp_path / "new.env").st_mode) == 0o600

        (tmp_path / "old.env").write_text("K=old\n")
        os.chmod(tmp_path / "old.env", 0o644)
        write("dotenv://old.env#K", VALUE, ResolveContext(base_dir=tmp_path))
        assert stat.S_IMODE(os.stat(tmp_path / "old.env").st_mode) == 0o644

    def test_a_symlink_is_followed_rather_than_replaced(self, tmp_path: Path) -> None:
        real = tmp_path / "real.env"
        real.write_text("K=old\n")
        (tmp_path / "link.env").symlink_to(real)

        write("dotenv://link.env#K", VALUE, ResolveContext(base_dir=tmp_path))

        assert (tmp_path / "link.env").is_symlink(), "the link is still a link"
        assert real.read_text() == f"K={VALUE}\n"

    def test_a_file_that_is_not_text_is_not_rewritten(self, tmp_path: Path) -> None:
        (tmp_path / "f.env").write_bytes(b"K=\xff\xfe\n")

        with pytest.raises(ProviderError) as caught:
            write("dotenv://f.env#K", VALUE, ResolveContext(base_dir=tmp_path))

        assert "not valid UTF-8" in str(caught.value)
        assert (tmp_path / "f.env").read_bytes() == b"K=\xff\xfe\n"

    @pytest.mark.parametrize("key", [" K ", "K=1", "#K", "export K"])
    def test_a_name_that_is_not_a_key_blames_the_key_not_the_value(
        self, tmp_path: Path, key: str
    ) -> None:
        """These are refused either way; the defect was the sentence, which sent
        someone looking at the value for a problem in the reference."""
        with pytest.raises(ProviderError) as caught:
            write(f"dotenv://f.env#{key}", VALUE, ResolveContext(base_dir=tmp_path))

        assert f"{key} cannot be a key" in str(caught.value)
        assert "value containing a line break" not in str(caught.value)
        assert not (tmp_path / "f.env").exists()

    def test_a_reference_with_no_key_says_what_was_expected(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ProviderError) as caught:
            write("dotenv://f.env", VALUE, ResolveContext(base_dir=tmp_path))

        assert "Malformed reference" in str(caught.value)

    def test_no_temporary_file_is_left_beside_the_target(
        self, tmp_path: Path
    ) -> None:
        write("dotenv://f.env#K", VALUE, ResolveContext(base_dir=tmp_path))

        assert sorted(p.name for p in tmp_path.iterdir()) == ["f.env"]


# ------------------------------------------------------------ Azure Key Vault


class TestWhatAzIsHanded:
    def test_the_value_travels_in_a_0600_file_and_never_in_argv(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(tmp_path / "bin", "az", {"keyvault secret set": {}})

        canonical = write("akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"))

        call = calls_of(log)[0]
        assert canonical == "akv://a-vault/a-secret"
        assert VALUE not in " ".join(call["argv"]), "a value in argv is readable"
        assert "--value" not in call["argv"]
        assert call["file"]["text"] == VALUE
        assert call["file"]["mode"] == 0o600
        assert not Path(call["file"]["path"]).exists(), "removed after az exits"

    def test_nothing_is_printed_for_az_to_put_a_secret_on(
        self, tmp_path: Path
    ) -> None:
        """`az keyvault secret set` answers with the secret object by default."""
        log = fake_cli(tmp_path / "bin", "az", {"keyvault secret set": {}})

        write("akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"))

        assert calls_of(log)[0]["argv"][-3:] == [
            "--output", "none", "--only-show-errors",
        ]

    def test_the_value_file_is_removed_when_az_fails(self, tmp_path: Path) -> None:
        log = fake_cli(
            tmp_path / "bin",
            "az",
            {"keyvault secret set": {"code": 1, "stderr": "ERROR: (Forbidden) no\n"}},
        )

        with pytest.raises(ProviderError):
            write("akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"))

        assert not Path(calls_of(log)[0]["file"]["path"]).exists()

    def test_a_pinned_version_is_refused_before_az_is_spawned(
        self, tmp_path: Path
    ) -> None:
        version = "3a7f1c9e2b4d5068a1c3e5f7092b4d6e"
        log = fake_cli(tmp_path / "bin", "az", {"keyvault secret set": {}})

        with pytest.raises(ProviderError) as caught:
            write(
                f"akv://a-vault/a-secret/{version}", VALUE, on_path(tmp_path / "bin")
            )

        assert "pins a version" in str(caught.value)
        assert calls_of(log) == [], "az was never called"

    def test_a_carriage_return_is_refused_because_az_would_rewrite_it(
        self, tmp_path: Path
    ) -> None:
        """Measured against a live vault: `az` reads `--file` as text, so CRLF
        and CR arrive as LF and the secret no longer reads back as written."""
        log = fake_cli(tmp_path / "bin", "az", {"keyvault secret set": {}})

        with pytest.raises(ProviderError) as caught:
            write("akv://a-vault/a-secret", "a\r\nb", on_path(tmp_path / "bin"))

        assert "carriage return" in str(caught.value)
        assert calls_of(log) == [], "az was never called"

    def test_a_name_azure_would_refuse_never_reaches_az(self, tmp_path: Path) -> None:
        log = fake_cli(tmp_path / "bin", "az", {"keyvault secret set": {}})

        with pytest.raises(ProviderError):
            write("akv://kv/my_secret", VALUE, on_path(tmp_path / "bin"))

        assert calls_of(log) == []

    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            (
                "ERROR: (Conflict) Secret s is currently being deleted and "
                "cannot be re-created; retry later.\nCode: Conflict\n",
                "recover",
            ),
            (
                "ERROR: (Forbidden) Caller is not authorized\nCode: Forbidden\n",
                "Secrets Officer",
            ),
            (
                "ERROR: Please run 'az login' to setup account.\n",
                "cannot be written",
            ),
        ],
        ids=["soft-deleted", "rbac", "logged-out"],
    )
    def test_a_failure_is_diagnosed_in_the_terms_of_a_write(
        self, tmp_path: Path, stderr: str, expected: str
    ) -> None:
        fake_cli(
            tmp_path / "bin",
            "az",
            {"keyvault secret set": {"code": 1, "stderr": stderr}},
        )

        with pytest.raises(ProviderError) as caught:
            write("akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"))

        assert expected in str(caught.value)
        assert VALUE not in str(caught.value)

    def test_the_read_role_is_not_offered_for_a_refused_write(
        self, tmp_path: Path
    ) -> None:
        """Key Vault Secrets *User* cannot write, so suggesting it is advice
        that cannot work."""
        fake_cli(
            tmp_path / "bin",
            "az",
            {
                "keyvault secret set": {
                    "code": 1,
                    "stderr": "ERROR: (Forbidden) denied\nCode: Forbidden\n",
                }
            },
        )

        with pytest.raises(ProviderError) as caught:
            write("akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"))

        assert "Secrets User" not in str(caught.value)

    def test_a_read_still_names_the_read_role(self, tmp_path: Path) -> None:
        """The control for the test above: the flag changed one branch, not
        the module's behaviour for everything else."""
        fake_cli(
            tmp_path / "bin",
            "az",
            {
                "keyvault secret show": {
                    "code": 1,
                    "stderr": "ERROR: (Forbidden) denied\nCode: Forbidden\n",
                }
            },
        )

        with pytest.raises(Exception) as caught:
            resolve("K", "akv://a-vault/a-secret", on_path(tmp_path / "bin"))

        assert "Secrets User" in str(caught.value)


# ---------------------------------------------------------------- 1Password


LOGIN_TEMPLATE = json.dumps(
    {
        "title": "",
        "category": "LOGIN",
        "fields": [
            {
                "id": "username",
                "type": "STRING",
                "purpose": "USERNAME",
                "label": "username",
                "value": "",
            },
            {
                "id": "password",
                "type": "CONCEALED",
                "purpose": "PASSWORD",
                "label": "password",
                "value": "",
            },
        ],
    }
)


def op_answers(**overrides: dict) -> dict[str, dict]:
    answers: dict[str, dict] = {
        "item list": {"stdout": "[]"},
        "item template get": {"stdout": LOGIN_TEMPLATE},
        "item create": {"stdout": json.dumps({"id": "newitemid00000000000000001"})},
        "item get": {"stdout": LOGIN_TEMPLATE},
        "item edit": {},
    }
    answers.update(overrides)
    return answers


class TestWhatOpIsHanded:
    def test_a_new_item_is_created_with_the_value_on_stdin(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(tmp_path / "bin", "op", op_answers())

        canonical = write(
            "op://a-vault/my-item/password", VALUE, on_path(tmp_path / "bin")
        )

        made = calls_of(log)
        assert [call["argv"][:2] for call in made] == [
            ["item", "list"], ["item", "template"], ["item", "create"],
        ]
        create = made[-1]
        assert VALUE not in " ".join(create["argv"]), "a value in argv is readable"
        assert "-" in create["argv"], "the template arrives on stdin"
        assert json.loads(create["stdin"])["title"] == "my-item"
        assert canonical == "op://a-vault/newitemid00000000000000001/password"

    def test_a_built_in_field_is_merged_rather_than_added_beside(
        self, tmp_path: Path
    ) -> None:
        """Two fields named `password` and `op read` returns the wrong one —
        measured against a real vault before this was written."""
        log = fake_cli(tmp_path / "bin", "op", op_answers())

        write("op://a-vault/my-item/password", VALUE, on_path(tmp_path / "bin"))

        sent = json.loads(calls_of(log)[-1]["stdin"])
        named = [f for f in sent["fields"] if f["label"] == "password"]
        assert len(named) == 1
        assert named[0]["value"] == VALUE
        assert named[0]["purpose"] == "PASSWORD", "the built-in field, not a new one"

    def test_a_field_the_category_does_not_have_is_added_concealed(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(tmp_path / "bin", "op", op_answers())

        write("op://a-vault/my-item/auth-token", VALUE, on_path(tmp_path / "bin"))

        sent = json.loads(calls_of(log)[-1]["stdin"])
        added = [f for f in sent["fields"] if f["label"] == "auth-token"]
        assert added == [
            {
                "id": "auth-token",
                "type": "CONCEALED",
                "label": "auth-token",
                "value": VALUE,
            }
        ]

    def test_an_existing_item_is_edited_in_place_and_sent_back_whole(
        self, tmp_path: Path
    ) -> None:
        """A template carrying one field deletes every custom field it omits,
        so the update is the fetched item with one value changed."""
        existing = json.dumps(
            {
                "id": "existingid0000000000000001",
                "title": "my-item",
                "category": "LOGIN",
                "fields": [
                    {"id": "other", "label": "other", "value": "keep-me"},
                    {"id": "password", "label": "password", "value": "old"},
                ],
            }
        )
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps(
                            [{"id": "existingid0000000000000001", "title": "my-item"}]
                        )
                    },
                    "item get": {"stdout": existing},
                }
            ),
        )

        canonical = write(
            "op://a-vault/my-item/password", VALUE, on_path(tmp_path / "bin")
        )

        made = calls_of(log)
        assert [call["argv"][:2] for call in made] == [
            ["item", "list"], ["item", "get"], ["item", "edit"],
        ]
        sent = json.loads(made[-1]["stdin"])
        assert {f["label"]: f["value"] for f in sent["fields"]} == {
            "other": "keep-me",
            "password": VALUE,
        }
        assert VALUE not in " ".join(made[-1]["argv"])
        assert canonical == "op://a-vault/existingid0000000000000001/password"

    def test_an_item_named_by_its_id_is_edited_not_duplicated(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps(
                            [{"id": "existingid0000000000000001", "title": "a title"}]
                        )
                    }
                }
            ),
        )

        write(
            "op://a-vault/existingid0000000000000001/password",
            VALUE,
            on_path(tmp_path / "bin"),
        )

        assert [call["argv"][:2] for call in calls_of(log)] == [
            ["item", "list"], ["item", "get"], ["item", "edit"],
        ]

    def test_every_field_of_a_name_is_set_when_an_item_already_carries_two(
        self, tmp_path: Path
    ) -> None:
        """Which one `op read` returns is not something this can know, so both
        are set and the read that follows is no longer a coin toss."""
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps([{"id": "dup00000000000000000000001",
                                                "title": "my-item"}])
                    },
                    "item get": {
                        "stdout": json.dumps(
                            {
                                "id": "dup00000000000000000000001",
                                "fields": [
                                    {"id": "password", "label": "password",
                                     "purpose": "PASSWORD", "value": "a"},
                                    {"id": "password", "label": "password",
                                     "value": "b"},
                                ],
                            }
                        )
                    },
                }
            ),
        )

        write("op://a-vault/my-item/password", VALUE, on_path(tmp_path / "bin"))

        sent = json.loads(calls_of(log)[-1]["stdin"])
        assert [f["value"] for f in sent["fields"]] == [VALUE, VALUE]

    def test_a_field_of_the_same_name_inside_a_section_is_left_alone(
        self, tmp_path: Path
    ) -> None:
        """Measured against a real item (op 2.39.0): section fields share the
        flat `fields` array, and `op read op://v/item/token` returns the
        *top-level* one. Matching by label alone set both, overwriting a
        credential the reference could not even name — `_parse` refuses the
        four-segment form that addresses it.

        Note the shape: a top-level field carries `"section": null`, it does
        not omit the key.
        """
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps(
                            [{"id": "sectioned000000000000001", "title": "my-item"}]
                        )
                    },
                    "item get": {
                        "stdout": json.dumps(
                            {
                                "id": "sectioned000000000000001",
                                "fields": [
                                    {"id": "toplevel", "label": "token",
                                     "section": None, "value": "old"},
                                    {"id": "insection", "label": "token",
                                     "section": {"id": "s", "label": "Section"},
                                     "value": "a-different-credential"},
                                ],
                            }
                        )
                    },
                }
            ),
        )

        write("op://a-vault/my-item/token", VALUE, on_path(tmp_path / "bin"))

        sent = json.loads(calls_of(log)[-1]["stdin"])
        assert [f["value"] for f in sent["fields"]] == [
            VALUE,
            "a-different-credential",
        ]

    def test_two_items_of_the_same_title_are_refused_rather_than_guessed(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps(
                            [
                                {"id": "one0000000000000000000001", "title": "shared"},
                                {"id": "two0000000000000000000002", "title": "shared"},
                            ]
                        )
                    }
                }
            ),
        )

        with pytest.raises(ProviderError) as caught:
            write("op://a-vault/shared/password", VALUE, on_path(tmp_path / "bin"))

        assert "2 items" in str(caught.value)
        assert [call["argv"][:2] for call in calls_of(log)] == [["item", "list"]]

    @pytest.mark.parametrize(
        "ref",
        [
            "op://a-vault/my-item",
            "op://a-vault/my-item/section/field",
            "op://a-vault//password",
            "op://a-vault/my-item/password?attribute=otp",
        ],
    )
    def test_a_reference_with_nothing_to_store_behind_it_is_refused(
        self, tmp_path: Path, ref: str
    ) -> None:
        log = fake_cli(tmp_path / "bin", "op", op_answers())

        with pytest.raises(ProviderError) as caught:
            write(ref, VALUE, on_path(tmp_path / "bin"))

        assert "Cannot write" in str(caught.value)
        assert calls_of(log) == [], "op was never called"

    def test_op_s_own_words_are_never_relayed_from_a_call_carrying_a_template(
        self, tmp_path: Path
    ) -> None:
        """What was sent *is* the secret, so a tool reporting what it could not
        parse would be reporting part of it."""
        leaked = f"invalid json near {VALUE}"
        fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(**{"item create": {"code": 1, "stderr": leaked}}),
        )

        with pytest.raises(ProviderError) as caught:
            write("op://a-vault/my-item/password", VALUE, on_path(tmp_path / "bin"))

        assert VALUE not in str(caught.value)
        assert "op item create --help" in str(caught.value)

    def test_a_missing_signin_is_named_as_one(self, tmp_path: Path) -> None:
        fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{"item list": {"code": 1, "stderr": "[ERROR] you are not signed in"}}
            ),
        )

        with pytest.raises(ProviderError) as caught:
            write("op://a-vault/my-item/password", VALUE, on_path(tmp_path / "bin"))

        assert "op signin" in str(caught.value)


class TestTheProvidersStillOnlyCarryOneScheme:
    """The architecture gate reads string constants; these read behaviour."""

    def test_each_provider_claims_only_its_own_references(self) -> None:
        for provider in (dotenv, onepassword, azurekeyvault):
            assert provider.handles(provider.SCHEME + "x/y")
            for other in (dotenv, onepassword, azurekeyvault):
                if other is not provider:
                    assert not provider.handles(other.SCHEME + "x/y")


# ------------------------------------------------------------- --if-absent


class TestLeavingAnExistingSecretAlone:
    """`--if-absent`: what `agent create` wants on a second run.

    Each provider asks its own backend rather than the core resolving first,
    and the point of that is the negative case: a read that fails for a reason
    other than absence must not be read as room to overwrite.
    """

    def test_a_key_that_is_there_is_not_replaced(self, tmp_path: Path) -> None:
        (tmp_path / "f.env").write_text("K=already\nOTHER=x\n")

        got = write(
            "dotenv://f.env#K", VALUE, ResolveContext(base_dir=tmp_path),
            if_absent=True,
        )

        assert got == "dotenv://f.env#K"
        assert (tmp_path / "f.env").read_text() == "K=already\nOTHER=x\n"

    def test_a_key_that_is_missing_is_still_written(self, tmp_path: Path) -> None:
        (tmp_path / "f.env").write_text("OTHER=x\n")

        write(
            "dotenv://f.env#K", VALUE, ResolveContext(base_dir=tmp_path),
            if_absent=True,
        )

        assert (tmp_path / "f.env").read_text() == f"OTHER=x\nK={VALUE}\n"

    def test_an_empty_key_counts_as_present(self, tmp_path: Path) -> None:
        """A dotenv file says what it holds; `K=` is a value someone wrote."""
        (tmp_path / "f.env").write_text("K=\n")

        write(
            "dotenv://f.env#K", VALUE, ResolveContext(base_dir=tmp_path),
            if_absent=True,
        )

        assert (tmp_path / "f.env").read_text() == "K=\n"

    def test_an_azure_secret_that_reads_is_left_alone(self, tmp_path: Path) -> None:
        log = fake_cli(
            tmp_path / "bin",
            "az",
            {"keyvault secret show": {"stdout": "https://v/secrets/s/1\n"}},
        )

        got = write(
            "akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"), if_absent=True
        )

        assert got == "akv://a-vault/a-secret"
        assert [call["argv"][2] for call in calls_of(log)] == ["show"]

    def test_the_existence_check_never_asks_for_the_value(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(
            tmp_path / "bin",
            "az",
            {"keyvault secret show": {"stdout": "https://v/secrets/s/1\n"}},
        )

        write(
            "akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"), if_absent=True
        )

        argv = calls_of(log)[0]["argv"]
        assert argv[argv.index("--query") + 1] == "id"

    def test_an_azure_secret_that_is_not_there_is_written(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(
            tmp_path / "bin",
            "az",
            {
                "keyvault secret show": {
                    "code": 3,
                    "stderr": "ERROR: (SecretNotFound) nope\nCode: SecretNotFound\n",
                },
                "keyvault secret set": {},
            },
        )

        write(
            "akv://a-vault/a-secret", VALUE, on_path(tmp_path / "bin"), if_absent=True
        )

        assert [call["argv"][2] for call in calls_of(log)] == ["show", "set"]

    def test_a_vault_that_could_not_answer_is_not_read_as_room_to_write(
        self, tmp_path: Path
    ) -> None:
        """The failure this exists to prevent: a denied read is not an absence,
        and overwriting on one would be the opposite of what was asked."""
        log = fake_cli(
            tmp_path / "bin",
            "az",
            {
                "keyvault secret show": {
                    "code": 1,
                    "stderr": "ERROR: (Forbidden) denied\nCode: Forbidden\n",
                },
                "keyvault secret set": {},
            },
        )

        with pytest.raises(ProviderError) as caught:
            write(
                "akv://a-vault/a-secret",
                VALUE,
                on_path(tmp_path / "bin"),
                if_absent=True,
            )

        assert "Access denied" in str(caught.value)
        assert [call["argv"][2] for call in calls_of(log)] == ["show"], "never set"

    def test_a_1password_field_that_already_holds_something_is_left_alone(
        self, tmp_path: Path
    ) -> None:
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps(
                            [{"id": "existingid0000000000000001", "title": "my-item"}]
                        )
                    },
                    "item get": {
                        "stdout": json.dumps(
                            {
                                "id": "existingid0000000000000001",
                                "fields": [
                                    {"id": "password", "label": "password",
                                     "value": "minted-earlier"},
                                ],
                            }
                        )
                    },
                }
            ),
        )

        got = write(
            "op://a-vault/my-item/password",
            VALUE,
            on_path(tmp_path / "bin"),
            if_absent=True,
        )

        assert [call["argv"][:2] for call in calls_of(log)] == [
            ["item", "list"], ["item", "get"],
        ]
        assert got == "op://a-vault/existingid0000000000000001/password"

    def test_an_empty_built_in_field_is_an_empty_slot_not_a_secret(
        self, tmp_path: Path
    ) -> None:
        """`op item create` gives a Login item a `password` field with no value
        at all; a reference to it names a slot, and filling it is the job."""
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps(
                            [{"id": "existingid0000000000000001", "title": "my-item"}]
                        )
                    },
                    "item get": {
                        "stdout": json.dumps(
                            {
                                "id": "existingid0000000000000001",
                                "fields": [
                                    {"id": "password", "label": "password",
                                     "purpose": "PASSWORD"},
                                ],
                            }
                        )
                    },
                }
            ),
        )

        write(
            "op://a-vault/my-item/password",
            VALUE,
            on_path(tmp_path / "bin"),
            if_absent=True,
        )

        assert [call["argv"][:2] for call in calls_of(log)][-1] == ["item", "edit"]

    def test_a_section_field_is_not_read_as_this_reference_being_set(
        self, tmp_path: Path
    ) -> None:
        """The mirror of the write defect: skipping on a section field's value
        would print the reference while the field it names stayed empty."""
        log = fake_cli(
            tmp_path / "bin",
            "op",
            op_answers(
                **{
                    "item list": {
                        "stdout": json.dumps(
                            [{"id": "sectioned000000000000001", "title": "my-item"}]
                        )
                    },
                    "item get": {
                        "stdout": json.dumps(
                            {
                                "id": "sectioned000000000000001",
                                "fields": [
                                    {"id": "toplevel", "label": "token",
                                     "section": None},
                                    {"id": "insection", "label": "token",
                                     "section": {"id": "s", "label": "Section"},
                                     "value": "a-different-credential"},
                                ],
                            }
                        )
                    },
                }
            ),
        )

        write(
            "op://a-vault/my-item/token",
            VALUE,
            on_path(tmp_path / "bin"),
            if_absent=True,
        )

        assert [call["argv"][:2] for call in calls_of(log)][-1] == ["item", "edit"]

    def test_a_vault_that_times_out_is_a_sentence_not_a_traceback(
        self, tmp_path: Path
    ) -> None:
        """`TimeoutExpired` is not a ProviderError, and neither the CLI nor the
        resolver translates anything else, so an unwrapped spawn here reached
        the operator as a traceback."""
        directory = tmp_path / "bin"
        directory.mkdir()
        (directory / "az").write_text(
            f"#!{sys.executable}\nimport time\ntime.sleep(60)\n", encoding="utf-8"
        )
        (directory / "az").chmod(0o755)
        monkeyed = azurekeyvault.TIMEOUT
        try:
            azurekeyvault.TIMEOUT = 1
            with pytest.raises(ProviderError) as caught:
                write(
                    "akv://a-vault/a-secret",
                    VALUE,
                    on_path(directory),
                    if_absent=True,
                )
        finally:
            azurekeyvault.TIMEOUT = monkeyed

        assert "timed out" in str(caught.value)
        assert "Nothing was written" in str(caught.value)

    def test_the_host_environment_refuses_either_way(self) -> None:
        with pytest.raises(ProviderError):
            write("env://SOME_NAME", VALUE, if_absent=True)
