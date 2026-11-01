# Publishing

The GitHub tag workflow requires green CI for the exact source commit, verifies
the tag matches `maskele.__version__`, builds wheel/sdist, checks their metadata,
and publishes a complete GitHub draft. Existing immutable assets are preserved.

No PyPI project publication is claimed. A tested GitHub wheel or source checkout
can be installed directly. A PyPI publication needs the owner's account/project
ownership. Prefer [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
with a protected environment and short-lived OIDC credentials; do not commit a
long-lived API token. Configuring that new trust requires explicit owner action.

The 0.5 default disk encryption requires the crypto extra. Test both an installed
wheel's help/assets and an encrypted round trip before publishing; keep browser
and server-memory workflows usable without the crypto dependency.
