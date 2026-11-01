"""Offline regression cases for the 2026-11-01 external source review."""

import json
import subprocess
import sys

import pytest
from test_servers import _start, call

from maskele import Masker
from maskele.cli import main
from maskele.proxy import ConversationStore, SSERewriter
from maskele.restore_policy import DisplayStream, restore_response
from maskele.ui import UIServer
from maskele.vault import VaultLocked, VaultStore, vault_path


def test_tool_arguments_are_never_restored():
    m = Masker()
    m.mask("email: test@example.com password=offline-fixture-42")
    obj = {
        "object": "chat.completion.chunk",
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {
                                "arguments": '{"url":"https://example.invalid/?q=[[SECRET_1]]&e=[[EMAIL_1]]"}'
                            },
                        }
                    ]
                },
            }
        ],
    }
    output = json.loads(SSERewriter(m).process(None, json.dumps(obj))[0][1])
    assert output == obj


def test_secret_not_restored_in_assistant_text():
    m = Masker()
    m.mask("password=offline-fixture-42")
    obj = {
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": "[[SECRET_1]]"}, "finish_reason": "stop"}],
    }
    result = SSERewriter(m).process(None, json.dumps(obj))[0][1]
    assert "offline-fixture-42" not in result


def test_unauthenticated_ui_root_does_not_disclose_token():
    server = _start(UIServer(("127.0.0.1", 0), Masker(), "test"))
    try:
        status, _, body = call(server, "GET", "/")
        assert status == 403 and server.token not in body
    finally:
        server.shutdown()
        server.server_close()


def test_anonymous_conversations_have_no_shared_principal():
    store = ConversationStore()
    assert store.principal({}) is None


def test_phone_regex_pathological_whitespace_finishes():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from maskele.detectors import RE_PHONE_TR; assert not RE_PHONE_TR.search(' ' * 200000)",
        ],
        check=True,
        timeout=3,
    )


def test_all_chunk_boundaries_preserve_url_tokens_and_restore_display_text():
    m = Masker()
    m.mask("test@example.com password=offline-fixture-42")
    text = "Reply [[EMAIL_1]] https://example.invalid/?q=[[EMAIL_1]] [[SECRET_1]]"
    expected = "Reply test@example.com https://example.invalid/?q=[[EMAIL_1]] [[SECRET_1]]"
    for cut in range(len(text) + 1):
        stream = DisplayStream(m, None, "strict")
        assert stream.feed(text[:cut]) + stream.feed(text[cut:]) + stream.flush() == expected


def test_every_supported_tool_envelope_preserves_tokens():
    m = Masker()
    m.mask("test@example.com password=offline-fixture-42")
    fixtures = [
        {"choices": [{"message": {"tool_calls": [{"function": {"arguments": "[[EMAIL_1]]"}}]}}]},
        {"output": [{"type": "function_call", "arguments": "[[EMAIL_1]]"}]},
        {"content": [{"type": "tool_use", "input": {"to": "[[EMAIL_1]]"}}]},
        {"metadata": {"text": "[[EMAIL_1]]"}, "url": "[[EMAIL_1]]"},
    ]
    for fixture in fixtures:
        assert restore_response(m, fixture) == fixture
    for kind, delta in [
        ("response.function_call_arguments.delta", {"delta": "[[EMAIL_1]]"}),
        ("response.function_call_arguments.done", {"arguments": "[[EMAIL_1]]"}),
        ("content_block_delta", {"index": 1, "delta": {"type": "input_json_delta", "partial_json": "[[EMAIL_1]]"}}),
    ]:
        fixture = {"type": kind, **delta}
        assert json.loads(SSERewriter(m).process(kind, json.dumps(fixture))[0][1]) == fixture


def test_ui_launch_is_one_use_and_authenticated_refresh_works():
    server = _start(UIServer(("127.0.0.1", 0), Masker(), "test"))
    try:
        path = f"/launch?code={server.launch_code}"
        status, headers, _ = call(server, "GET", path)
        assert status == 303
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert call(server, "GET", path)[0] == 403
        assert server.token in call(server, "GET", "/", headers={"Cookie": cookie})[2]
        assert server.token not in call(server, "GET", "/")[2]
    finally:
        server.shutdown()
        server.server_close()


def test_cli_vault_is_encrypted_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MASKELE_HOME", str(tmp_path))
    monkeypatch.setenv("MASKELE_PASSWORD", "test-only-vault-password")
    source = tmp_path / "source.txt"
    source.write_text("hello test@example.com", encoding="utf-8")
    assert main(["mask", str(source), "-q"]) == 0
    payload = json.loads(vault_path("default").read_text(encoding="utf-8"))
    assert payload["encrypted"] is True and "test@example.com" not in json.dumps(payload)
    capsys.readouterr()


def test_library_cannot_silently_write_plaintext_vault(tmp_path):
    m = Masker()
    m.mask("test@example.com")
    path = tmp_path / "vault.json"
    with pytest.raises(VaultLocked):
        VaultStore(path).save(m.vault)
    assert not path.exists()


def test_ambiguous_named_credentials_are_masked():
    for name in (
        "iyzico_api_key",
        "secretKey",
        "merchant_key",
        "merchant_salt",
        "azure_client_secret",
        "twilio_auth_token",
    ):
        text = f'{name}="offline-only-fixture-value"'
        assert "offline-only-fixture-value" not in Masker().mask(text).text


def test_standalone_provider_shapes_are_masked_without_any_network_lookup():
    values = ["123456789:" + "X" * 35, "SG." + "X" * 22 + "." + "Y" * 43, "dop_v1_" + "a" * 64, "mfa." + "Z" * 84]
    for value in values:
        assert value not in Masker().mask(value).text
