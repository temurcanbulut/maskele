"""maskele — LLM'e göndermeden önce hassas veriyi maskele, cevabı geri çevir."""

__version__ = "0.4.2"

from .config import Config, load_config  # noqa: E402
from .core import HINT, Masker, StreamUnmasker  # noqa: E402
from .detectors import ALL_KINDS, DEFAULT_KINDS, detect  # noqa: E402
from .vault import Vault, VaultStore  # noqa: E402

__all__ = [
    "Masker",
    "StreamUnmasker",
    "Vault",
    "VaultStore",
    "Config",
    "load_config",
    "detect",
    "ALL_KINDS",
    "DEFAULT_KINDS",
    "HINT",
    "__version__",
]
