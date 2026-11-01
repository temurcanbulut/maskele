# Source-review follow-up — 2026-11-01

User-supplied external static review, independently checked against main. No CVE,
independent penetration test, human data review or assurance certificate is claimed.

| Finding | Resolution | Regression |
|---|---|---|
| M1 executable-output restore oracle | Proxy-only display allowlist; never restore tool arguments/input, URL, metadata, or SECRET/PASSWORD/API_KEY/JWT/PRIVATE_KEY | Chat/Responses/Anthropic JSON and SSE; all text chunk cut positions |
| M2 pathological phone whitespace | Bounded separator repetition; key/value overlapping whitespace also bounded | Time-bounded subprocess on 200,000 spaces |
| M3 unauthenticated localhost root | One-use 5-minute capability exchanged for HttpOnly SameSite=Strict browser session; unauthenticated root returns 403 | token disclosure, reuse and authenticated refresh cases |
| M4 plaintext persistence | CLI and library disk writes encrypt by default; plaintext requires explicit opt-out | default ciphertext and no-password fail-closed tests |
| M5 detection coverage | Telegram, Discord, SendGrid, DigitalOcean shapes; named iyzico/PayTR/Azure/Twilio credentials | Offline manufactured fixtures, no provider queries |
| M6 anonymous shared principal | No credential means no conversation-store read/write; per-request vault still works | Anonymous principal regression; credential isolation preserved |

## Migration to 0.5

Tool-calling agents must accept opaque placeholders or perform a separate,
explicitly authorized local lookup after validating the tool, destination and
purpose. The proxy does not authorize execution, detect all prompt injection or
enforce an egress allowlist. Human-facing PII can still be restored into prose;
an agent must not treat that prose as trusted executable input.

`maskele ui` and the proxy stay memory-only by default. Persistent CLI sessions
need `pip install -e ".[crypto]"` and a password prompt or `MASKELE_PASSWORD`.
Library persistence is `VaultStore(path, password=...).save(vault)`; plaintext is
explicit `VaultStore(path, encrypt=False)` or `vault.save(path, plaintext=True)`.
CLI `--plaintext-vault` is deliberate unencrypted storage and cannot downgrade
an existing encrypted vault. Existing plaintext files are not secretly rewritten
or deleted; a subsequent normal encrypted save migrates them. Protect/retire old
copies yourself. Windows chmod alone is not an inherited-ACL boundary.

Use the exact UI launch link printed in your terminal; the bare root is protected.
The one-use link is a capability: do not share terminal output or browser cookies.
This does not protect against the same OS identity, administrator, malicious
browser extensions or malware with access to the user's browser/process.

## Detection scope

Provider-shaped matches are heuristics, not proof a credential is active.
Azure, Twilio and local payment keys without a distinctive prefix require a
recognized key/value context or an explicit custom pattern. Generic entropy
redaction is not enabled: hashes and build identifiers would generate false
positives. Card matches are checked with Luhn and issuer-shape constraints.
Name coverage remains dictionary based; no NER model was installed or run and
the old benchmark's known foreign/lowercase-name misses are not claimed fixed.

Format references: [Telegram](https://core.telegram.org/bots/tutorial),
[DigitalOcean token prefixes](https://docs.digitalocean.com/reference/api/),
[iyzico authentication](https://docs.iyzico.com/en/getting-started/preliminaries/authentication/hmacsha256-auth),
[PayTR](https://dev.paytr.com/en/platform-transfer-talebi/transfer-talimatinin-sonucunun-alinmasi).
No documentation example key was copied into a test or queried against a service.
