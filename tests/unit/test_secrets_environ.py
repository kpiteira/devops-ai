"""`encode_env` picks UTF-8, and never the operator's locale.

macOS hardcodes its filesystem encoding to UTF-8 whatever `LC_ALL` says, so the
locale's codec and the promised one agree there and any assertion about bytes
holds either way. That is how #58 stayed invisible for as long as it did. These
are written to fail on a UTF-8 machine too.
"""

from __future__ import annotations

import os

import pytest

from devops_ai.secrets import EnvironmentEncodingError, encode_env

ACCENTED = "café-über"


def test_a_value_is_encoded_as_utf8_without_consulting_the_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`os.fsencode` *is* the locale's codec; reaching it is the defect.

    Asserting on the bytes alone would stay green on a UTF-8 machine even if
    the helper went back to `os.fsencode` — which is exactly how the product
    bug survived. This goes red there as well.
    """

    def locale_codec(_: object) -> bytes:
        raise AssertionError("encode_env went through the locale's codec")

    monkeypatch.setattr(os, "fsencode", locale_codec)

    assert encode_env({"K": ACCENTED}, utf8_keys=["K"]) == {
        b"K": b"caf\xc3\xa9-\xc3\xbcber"
    }


def test_a_name_is_encoded_the_same_way_as_a_value() -> None:
    assert encode_env({"KÉ": "v"}, utf8_keys=["KÉ"]) == {b"K\xc3\x89": b"v"}


def test_a_byte_that_was_never_utf8_survives_the_round_trip() -> None:
    """`os.environ` is decoded with surrogateescape and can hand one back.

    Encoding strictly would fail the spawn over a variable this process merely
    inherited, whose value is not even ours to fix.
    """
    # Never `os.fsdecode`: that uses the *test process's* filesystem codec, so
    # this only produced surrogates on a UTF-8 (or ASCII) runner. Under a
    # decodable non-UTF-8 locale such as ISO-8859-1 it yields the characters
    # 'ÿþ' instead, whose UTF-8 is `c3 bf c3 be` — and the assertion failed on a
    # correct implementation. Fourth site of a class this PR has now met at
    # `run_child`'s `text=True`, the repo-path test's `Path.mkdir`, and the
    # architecture gate's bare `read_text()`: the harness inherits a codec
    # instead of naming one. The value under test is "a byte `os.environ` held
    # as a surrogate", so say exactly that.
    inherited = b"\xff\xfe".decode("utf-8", "surrogateescape")
    assert inherited == "\udcff\udcfe", "the premise of this test, pinned"
    assert encode_env({"K": inherited}, utf8_keys=["K"]) == {b"K": b"\xff\xfe"}


def test_an_unencodable_value_is_named_but_never_quoted() -> None:
    """The one input left that cannot encode — and #58's leak in miniature.

    The `UnicodeEncodeError` this replaces quotes the character it choked on
    and its position. For a resolved secret, that character is the secret.
    """
    body = "recognisable-secret-body"
    with pytest.raises(EnvironmentEncodingError) as caught:
        encode_env({"API_TOKEN": f"\ud800{body}"}, utf8_keys=["API_TOKEN"])

    message = str(caught.value)
    assert "API_TOKEN" in message, "the variable has to be nameable to be fixed"
    assert body not in message
    assert "\ud800" not in message
    assert "d800" not in message.lower(), "not even as an escape"
    # `from None`: a chained UnicodeEncodeError prints under this one and
    # carries the character and position the message deliberately omits.
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_an_unencodable_name_is_refused_too() -> None:
    with pytest.raises(EnvironmentEncodingError, match="variable name"):
        encode_env({"\ud800NAME": "v"}, utf8_keys=["\ud800NAME"])


def test_an_inherited_value_goes_back_out_the_way_it_came_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`os.fsencode` is the exact inverse of the decode that produced `os.environ`.

    A variable we did not author must not be re-spelled. `PATH` is the one that
    bites: a directory whose on-disk name is the byte `E9` is not found by a
    child told to look in `C3 A9`, and under `iso8859-15` those are what the two
    encoders give. Asserting on bytes would prove nothing on a UTF-8 machine,
    where both agree — so the call itself is observed.
    """
    seen: list[str] = []
    real = os.fsencode

    def spy(text: str) -> bytes:
        seen.append(text)
        return real(text)

    monkeypatch.setattr(os, "fsencode", spy)

    encode_env({"PATH": "/a/b", "MY_SECRET": "s"}, utf8_keys=["MY_SECRET"])

    assert "/a/b" in seen, "an inherited value must go back out through fsencode"
    assert "PATH" in seen, "and so must its name"
    assert "s" not in seen, "a value we resolved must not follow the locale"
    assert "MY_SECRET" not in seen


def test_nothing_is_ours_unless_it_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default is inherit, which is the safe way round.

    A caller that forgets `utf8_keys` fails to apply the promise to its own
    values — it cannot silently re-spell a child's whole environment, which is
    the failure that actually broke `ksecret run`.
    """
    seen: list[str] = []
    real = os.fsencode
    monkeypatch.setattr(os, "fsencode", lambda t: (seen.append(t), real(t))[1])

    assert encode_env({"K": "v"}) == {b"K": b"v"}

    assert seen == ["K", "v"], "with nothing declared, everything is inherited"
