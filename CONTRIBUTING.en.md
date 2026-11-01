# Contributing

Small fixes can go straight to a pull request. Discuss a new detector, optional
model integration or a breaking protocol change in an issue first. The Turkish
guide is [CONTRIBUTING.md](CONTRIBUTING.md).

```sh
python -m venv .venv
python -m pip install -e ".[dev]"
pytest -q
ruff check .
ruff format --check .
```

Use manufactured fixtures, never a user's identity or a live provider key. A
provider-shaped string is not proof a key is active; never validate it online.
New patterns need positive and benign-lookalike cases, bounded runtime and an
explanation of false positives. Keep core dependencies zero; encryption and any
future model integration belong in explicit extras. Do not log original values.

Proxy response restoration has a separate threat boundary from explicit local
CLI/UI unmask. Tools, URLs, metadata and secret kinds must stay opaque in proxy
responses, for buffered JSON and split streaming tokens. Test every supported
provider envelope when changing that boundary.

CI runs Windows/macOS/Linux tests, lint/format, a self-scan and wheel installation
outside the checkout. Security fixes must run CI; do not skip it. Release tags
must reference a commit with successful exact-source CI. Preserve honest history,
real limitations and the provenance of demos/benchmarks.

CLI/UI copy is currently Turkish; the English readme, architecture/security notes
and this guide support international review. A complete runtime localization is
a separate compatibility change, not implied by translated documentation.
