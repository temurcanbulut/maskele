# Publication verification — 2026-10-16

Version: **0.4.2**. These checks describe the tested scope; they do not certify complete detection or real provider compatibility.

| Check | Local result | Scope |
|---|---|---|
| Python suite | 201 passed | Detection, vaults, configuration, CLI, mock-provider protocols, security regressions and browser build |
| Ruff | Passed | Configured lint rules and formatting |
| Synthetic benchmark | 114 / 4,556 values exposed (2.50%); 0 / 38 negative lines flagged | Seed `20261015`, 3,000 constructed samples |
| Package | Wheel and source distribution built | Installed wheel imports and masks from an isolated interpreter; bundled UI assets present |
| Browser engine | Passed | Actual Pyodide build; mask, manual rule, consistent tokens, commit and restoration |
| Unicode preview | Passed | Emoji before name, TCKN and IBAN; preview text and highlighted source spans checked |
| Mobile layout | Passed | Actual 375 CSS-pixel viewport; no horizontal overflow |
| Browser console | No errors observed | Recorded synthetic workflow and Unicode preview |
| Python dependency audit | No known vulnerabilities reported | Local verification environment after updating its pip; not a guarantee against unknown vulnerabilities |

[Machine-readable benchmark](verification/benchmark.json) · [Demo source record](images/workflow-source.json) · [GitHub Actions](https://github.com/temurcanbulut/maskele/actions).

## Corrections made during preparation

The archive's first Windows run had 194 passing and three failing tests. Two assumed POSIX permission bits on Windows. Those assertions now run only on POSIX; the persistence and encrypted-vault behavior still run on every platform. The rejected-connection test now also accepts an immediate Windows reset/abort, while timeouts still fail.

The local UI now rejects invalid, negative, repeated and transfer-encoded request lengths before reading a body. Four raw-socket regression cases verify rejection without sending a body or changing the vault. The browser presentation now interprets Python's code-point spans correctly when JavaScript strings contain surrogate pairs.

CI retains Linux/macOS/Windows and Python 3.11–3.13 coverage. A separate package job checks a built wheel. Pages builds use a pinned Pyodide archive SHA256 and run the real browser smoke test, including an emoji-containing exact-output check, before deployment.

## Limits

- No real customer data or production provider API keys were used.
- Real OpenAI/Anthropic/provider behavior was not tested. Protocol integration tests use local mock servers.
- No Docker runtime test was performed in this workspace.
- The synthetic corpus is a regression set, not a representative independent privacy evaluation.
- Windows ACL restriction is not implemented by POSIX permission bits; use a private directory and encryption. See [architecture](ARCHITECTURE.md#file-permissions).
