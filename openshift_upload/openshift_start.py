import base64
import os
from pathlib import Path


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

import admin_bot  # noqa: E402
import asyncio  # noqa: E402


asyncio.run(admin_bot.main())
