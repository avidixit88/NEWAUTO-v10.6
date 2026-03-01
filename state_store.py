"""Best-effort local persistence for Streamlit Community Cloud.

Important:
- This is NOT a durable database. The filesystem on Streamlit Community Cloud can be wiped
  on sleep/restart/redeploy.
- It *does* improve survivability across Streamlit reruns and some transient session resets.
- Broker truth (positions/orders) remains the source of truth for trading decisions.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

# Streamlit Community Cloud generally allows /tmp writes.
STATE_PATH = os.environ.get("ZTOCKLY_STATE_PATH", "/tmp/ztockly_autoexec_state.json")
BAK1_PATH = STATE_PATH + ".bak1"
BAK2_PATH = STATE_PATH + ".bak2"
TMP_PATH = STATE_PATH + ".tmp"

SCHEMA_VERSION = 1


def _now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _safe_read(path: str) -> Optional[Dict[str, Any]]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_state() -> Optional[Dict[str, Any]]:
    """Load best-effort persisted state from local disk.

    Attempts main file, then backups.
    Returns None if nothing usable exists.
    """
    for p in (STATE_PATH, BAK1_PATH, BAK2_PATH):
        raw = _safe_read(p)
        if isinstance(raw, dict) and raw.get("_schema_version") == SCHEMA_VERSION:
            # Strip metadata wrapper if present
            return raw.get("state") if isinstance(raw.get("state"), dict) else None
    return None


def save_state(state: Dict[str, Any]) -> bool:
    """Atomically save state to local disk (best-effort)."""
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    except Exception:
        # /tmp may not have a parent directory to create; ignore
        pass

    wrapper = {
        "_schema_version": SCHEMA_VERSION,
        "_saved_utc": _now_ts(),
        "state": state,
    }

    try:
        # Rotate backups (best-effort)
        try:
            if os.path.exists(BAK1_PATH):
                try:
                    os.replace(BAK1_PATH, BAK2_PATH)
                except Exception:
                    pass
            if os.path.exists(STATE_PATH):
                try:
                    os.replace(STATE_PATH, BAK1_PATH)
                except Exception:
                    pass
        except Exception:
            pass

        payload = json.dumps(wrapper, ensure_ascii=False, separators=(",", ":"))
        with open(TMP_PATH, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(TMP_PATH, STATE_PATH)
        return True
    except Exception:
        # Cleanup tmp if left behind
        try:
            if os.path.exists(TMP_PATH):
                os.remove(TMP_PATH)
        except Exception:
            pass
        return False
