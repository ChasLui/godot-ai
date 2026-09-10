"""Exercise the update driver's HTTP status polling against real socket failures."""

from __future__ import annotations

import json
import os
import socket
import socketserver
import subprocess
import threading
import time

import pytest

from tests.integration._self_update_fixture import godot_bin_or_skip, write_driver_support

pytestmark = pytest.mark.editor


def test_status_driver_quietly_rejects_interrupted_and_invalid_responses(tmp_path):
    nonce = "fixture-status-instance"
    valid = json.dumps({"instance_id": nonce, "server_version": "4.0.5"}).encode()
    responses = [
        valid,
        b'{"broken":',
        valid,
        b"x" * (64 * 1024 + 1),
        json.dumps({"instance_id": "wrong"}).encode(),
        valid,
    ]
    observed = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = self.request.recv(4096)
                if not chunk:
                    return
                request += chunk
            index = len(observed)
            observed.append(b"Authorization: Bearer fixture-status-auth" in request)
            body = responses[index]
            size = len(body) + 10 if index == 2 else len(body)
            self.request.sendall(
                f"HTTP/1.1 200 OK\r\nContent-Length: {size}\r\nConnection: close\r\n\r\n".encode()
            )
            if index == 2:
                # Give Godot time to enter STATUS_BODY before the connection drops.
                time.sleep(0.05)
            self.request.sendall(body)
            if index == 2:
                time.sleep(0.05)
                self.request.shutdown(socket.SHUT_RDWR)

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            (tmp_path / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            write_driver_support(tmp_path)
            capabilities = tmp_path / "local/godot-ai/capabilities"
            capabilities.mkdir(parents=True)
            (capabilities / f"http-{port}.json").write_text(
                json.dumps({"http": "fixture-status-auth", "instance_nonce": nonce}),
                encoding="utf-8",
            )
            driver = tmp_path / "driver.gd"
            driver.write_text(
                'extends SceneTree\nconst Support = preload("res://_test_self_update_driver_support.gd")\n'
                "func _initialize() -> void:\n"
                f"\tvar first := Support.fetch_status({port})\n"
                '\tassert(first.get("server_version") == "4.0.5")\n'
                "\tfor _index in range(4):\n"
                f"\t\tassert(Support.fetch_status({port}).is_empty())\n"
                f'\tassert(Support.fetch_status({port}).get("instance_id") == "{nonce}")\n'
                '\tprint("STATUS_DRIVER_SOCKET_CASES_PASSED")\n\tquit()\n',
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "LOCALAPPDATA": str(tmp_path / "local"),
                "GODOT_AI_CAPABILITY_DIR": str(capabilities),
                "GODOT_AI_DISABLE_TELEMETRY": "true",
            }
            result = subprocess.run(
                [
                    godot_bin_or_skip(),
                    "--headless",
                    "--path",
                    str(tmp_path),
                    "--script",
                    str(driver),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            output = result.stdout + result.stderr
            assert result.returncode == 0, output
            assert "ERROR" not in output, output
            assert "STATUS_DRIVER_SOCKET_CASES_PASSED" in output
            assert observed == [True] * len(responses)
        finally:
            server.shutdown()
            thread.join(timeout=5)
