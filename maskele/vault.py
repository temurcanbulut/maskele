"""Takma ad kasası: bellek içi eşleme + diskte (isteğe bağlı şifreli) saklama.

Şifreleme: scrypt (stdlib) ile paroladan anahtar türetilir, AES-256-GCM ile
şifrelenir. AES-GCM için `cryptography` paketi gerekir: `pip install maskele[crypto]`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

FORMAT_VERSION = 2
_AAD = b"maskele-vault-v2"
_SCRYPT = {"n": 2**15, "r": 8, "p": 1}


class VaultError(RuntimeError):
    pass


class VaultLocked(VaultError):
    """Kasa şifreli ama parola verilmedi."""


class VaultBadPassword(VaultError):
    pass


@dataclass
class Vault:
    tokens: dict[str, str] = field(default_factory=dict)  # token -> orijinal
    index: dict[str, dict[str, str]] = field(default_factory=dict)  # tür -> normalize -> token
    counters: dict[str, int] = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def token_for(self, kind: str, value: str) -> str:
        from .core import normalize

        key = normalize(kind, value)
        with self._lock:
            bucket = self.index.setdefault(kind, {})
            if key in bucket:
                return bucket[key]
            n = self.counters.get(kind, 0) + 1
            self.counters[kind] = n
            tok = f"{kind}_{n}"
            bucket[key] = tok
            self.tokens[tok] = value
            return tok

    def __len__(self) -> int:
        return len(self.tokens)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "tokens": dict(self.tokens),
                "index": {k: dict(v) for k, v in self.index.items()},
                "counters": dict(self.counters),
                "created": self.created,
            }

    @classmethod
    def from_dict(cls, d: dict) -> Vault:
        return cls(
            tokens=d.get("tokens", {}),
            index=d.get("index", {}),
            counters=d.get("counters", {}),
            created=d.get("created", time.time()),
        )

    # v0.1 uyumluluğu
    @classmethod
    def load(cls, path: Path) -> Vault:
        return VaultStore(path).load()

    def save(self, path: Path) -> None:
        VaultStore(path).save(self)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s)


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024 * 1024, dklen=32)


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:  # pragma: no cover
        raise VaultError("Şifreli kasa için `pip install maskele[crypto]` gerekli.") from e
    return AESGCM


class VaultStore:
    """Bir oturumun diskteki kasası."""

    def __init__(self, path: Path, password: str | None = None, encrypt: bool = False, ttl_hours: float = 0):
        self.path = Path(path)
        self.password = password
        self.encrypt = encrypt or password is not None
        self.ttl_hours = ttl_hours

    # --- durum ---------------------------------------------------------------
    def exists(self) -> bool:
        return self.path.exists()

    def is_encrypted(self) -> bool:
        if not self.path.exists():
            return False
        try:
            return bool(json.loads(self.path.read_text(encoding="utf-8")).get("encrypted"))
        except (ValueError, OSError):
            return False

    def expired(self) -> bool:
        if not self.ttl_hours or not self.path.exists():
            return False
        return time.time() - self.path.stat().st_mtime > self.ttl_hours * 3600

    # --- okuma / yazma -------------------------------------------------------
    def load(self) -> Vault:
        if self.expired():
            self.delete()
        if not self.path.exists():
            return Vault()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("encrypted"):
            if self.password is None:
                raise VaultLocked(f"{self.path.name} şifreli; parola gerekli (MASKELE_PASSWORD).")
            kdf = raw["kdf"]
            key = _derive(self.password, _unb64(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"])
            try:
                pt = _aesgcm()(key).decrypt(_unb64(raw["nonce"]), _unb64(raw["data"]), _AAD)
            except Exception as e:
                raise VaultBadPassword("Parola yanlış ya da kasa bozulmuş.") from e
            self.encrypt = True
            return Vault.from_dict(json.loads(pt))
        return Vault.from_dict(raw)

    def save(self, vault: Vault) -> None:
        body = vault.to_dict()
        if self.encrypt:
            if self.password is None:
                raise VaultLocked("Şifreli kayıt için parola gerekli.")
            salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
            key = _derive(self.password, salt, **_SCRYPT)
            ct = _aesgcm()(key).encrypt(nonce, json.dumps(body, ensure_ascii=False).encode(), _AAD)
            doc = {
                "version": FORMAT_VERSION,
                "encrypted": True,
                "cipher": "AES-256-GCM",
                "kdf": {"name": "scrypt", "salt": _b64(salt), **_SCRYPT},
                "nonce": _b64(nonce),
                "data": _b64(ct),
            }
        else:
            doc = {"version": FORMAT_VERSION, "encrypted": False, **body}
        self._atomic_write(json.dumps(doc, ensure_ascii=False, indent=2))

    def delete(self) -> None:
        """Kasayı siler. Önce dosyanın üzerine rastgele veri yazılır; bu EN İYİ ÇABADIR:
        SSD'ler, kopyala-yaz dosya sistemleri, anlık görüntüler ve yedekler eski blokları
        tutabilir. Gerçek koruma için şifreli kasa kullanın."""
        if self.path.exists():
            try:
                size = self.path.stat().st_size
                with open(self.path, "r+b") as f:
                    f.write(secrets.token_bytes(size))
                    f.flush()
                    os.fsync(f.fileno())
            except OSError:
                pass
            self.path.unlink(missing_ok=True)

    def _atomic_write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".vault-")
        try:
            os.fchmod(fd, 0o600) if hasattr(os, "fchmod") else None
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


SESSION_RE = re.compile(r"[\w.-]{1,64}")


def sweep_expired(ttl_hours: float) -> int:
    """Süresi dolmuş tüm oturum kasalarını siler; silinen sayısını döndürür."""
    d = sessions_dir()
    if not ttl_hours or not d.exists():
        return 0
    n = 0
    for p in d.glob("*.json"):
        st = VaultStore(p, ttl_hours=ttl_hours)
        if st.expired():
            st.delete()
            n += 1
    return n


def default_home() -> Path:
    return Path(os.environ.get("MASKELE_HOME", Path.home() / ".maskele"))


def sessions_dir() -> Path:
    return default_home() / "sessions"


def vault_path(session: str) -> Path:
    if not SESSION_RE.fullmatch(session) or session in (".", ".."):
        raise ValueError(f"Geçersiz oturum adı: {session!r}")
    return sessions_dir() / f"{session}.json"
