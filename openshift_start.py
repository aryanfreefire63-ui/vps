import base64
import os
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):  # noqa: A003
        return


def start_health_server() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Health server listening on {port}")


def restore_base64_file(env_name: str, path: str) -> None:
    value = os.getenv(env_name, "").strip()
    if not value:
        return
    Path(path).write_bytes(base64.b64decode(value))
    print(f"Restored {path} from {env_name}")


def restore_text_file(env_name: str, path: str) -> None:
    value = os.getenv(env_name, "").strip()
    if not value:
        return
    Path(path).write_text(value, encoding="utf-8")
    print(f"Restored {path} from {env_name}")


restore_base64_file("PREMIUM_SESSION_B64", "premium_account.session")
restore_text_file("ADMIN_CONFIG_JSON", "admin_config.json")
restore_text_file("PREDICTION_STATE_JSON", "prediction_state.json")
start_health_server()

import admin_bot  # noqa: E402
import asyncio  # noqa: E402


asyncio.run(admin_bot.main())
