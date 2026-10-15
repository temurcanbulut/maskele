"""Bağımlılıksız pano erişimi (macOS, Linux X11/Wayland, Windows/WSL)."""

from __future__ import annotations

import shutil
import subprocess
import sys

_COPY = [
    ["pbcopy"],
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
    ["clip.exe"],
]
_PASTE = [
    ["pbpaste"],
    ["wl-paste", "--no-newline"],
    ["xclip", "-selection", "clipboard", "-o"],
    ["xsel", "--clipboard", "--output"],
    ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
]


class ClipboardError(RuntimeError):
    pass


def _first(cmds: list[list[str]]) -> list[str]:
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"] if cmds is _PASTE else ["clip"]
    for c in cmds:
        if shutil.which(c[0]):
            return c
    raise ClipboardError("Pano aracı bulunamadı (pbcopy, wl-copy, xclip veya xsel kurun).")


def copy(text: str) -> None:
    subprocess.run(_first(_COPY), input=text.encode("utf-8"), check=True)


def paste() -> str:
    out = subprocess.run(_first(_PASTE), capture_output=True, check=True).stdout
    return out.decode("utf-8", errors="replace").replace("\r\n", "\n")
