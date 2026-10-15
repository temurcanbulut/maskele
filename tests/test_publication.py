"""HTTP framing regressions found during publication checks."""

import socket
import threading

import pytest

from maskele import Masker
from maskele.ui import UIServer


@pytest.mark.parametrize(
    "framing",
    [
        b"Content-Length: -1\r\n",
        b"Content-Length: invalid\r\n",
        b"Content-Length: 2\r\nContent-Length: 2\r\n",
        b"Transfer-Encoding: chunked\r\n",
    ],
)
def test_ui_rejects_ambiguous_body_before_reading(framing):
    server = UIServer(("127.0.0.1", 0), Masker(), "framing-test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            client.sendall(
                b"POST /api/mask HTTP/1.1\r\n"
                + f"Host: 127.0.0.1:{port}\r\nX-Maskele-Token: {server.token}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + framing
                + b"\r\n"
            )
            # No body is sent: rejection must precede reading it.
            assert client.recv(1024).startswith(b"HTTP/1.0 400 ")
        assert len(server.app.masker.vault) == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
