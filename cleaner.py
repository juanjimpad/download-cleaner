"""
qbit-private-cleanup

Borra de qBittorrent y de Transmission los torrents de la categoria "private"
cuyo fichero ya no existe en disco -- p.ej. porque se borro a mano desde
Emby/Finder antes de que ningun *arr* (que no gestiona esa categoria)
pudiera hacerse cargo. Los dos clientes se usan para esa categoria en este
homelab, asi que hay que vigilar ambos.

Solo actua tras ver el mismo torrent "missing" en dos pasadas seguidas, para
no disparar por un fallo puntual de NFS (ya ha pasado en este homelab:
Stale file handle en el montaje downloads-rw).

Config por variables de entorno, ver README.md del proyecto.
"""

import json
import os
import time
from pathlib import Path

import requests

CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "1800"))
STATE_FILE = Path(os.environ.get("STATE_FILE", "/config/state.json"))

QBIT_URL = os.environ["QBIT_URL"].rstrip("/")
QBIT_API_KEY = os.environ["QBIT_API_KEY"]
QBIT_CATEGORY = os.environ.get("QBIT_CATEGORY", "private")
QBIT_HEADERS = {"Authorization": f"Bearer {QBIT_API_KEY}"}

TRANSMISSION_URL = os.environ.get("TRANSMISSION_URL", "").rstrip("/")
TRANSMISSION_RPC_PATH = os.environ.get("TRANSMISSION_RPC_PATH", "/transmission/rpc")
TRANSMISSION_PRIVATE_DIR = os.environ.get(
    "TRANSMISSION_PRIVATE_DIR", "/downloads/complete/private"
)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


# ---------------------------------------------------------------- qBittorrent

def qbit_fetch_torrents() -> list[dict]:
    resp = requests.get(
        f"{QBIT_URL}/api/v2/torrents/info",
        params={"category": QBIT_CATEGORY},
        headers=QBIT_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return [
        {"key": f"qbit:{t['hash']}", "name": t["name"], "path": t["content_path"]}
        for t in resp.json()
    ]


def qbit_delete_torrent(key: str) -> None:
    torrent_hash = key.split(":", 1)[1]
    resp = requests.get(
        f"{QBIT_URL}/api/v2/torrents/delete",
        params={"hashes": torrent_hash, "deleteFiles": "true"},
        headers=QBIT_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------- Transmission

_tr_session_id = None


def _tr_rpc(method: str, arguments: dict) -> dict:
    global _tr_session_id
    url = f"{TRANSMISSION_URL}{TRANSMISSION_RPC_PATH}"
    headers = {"X-Transmission-Session-Id": _tr_session_id} if _tr_session_id else {}
    resp = requests.post(
        url, headers=headers, json={"method": method, "arguments": arguments}, timeout=30
    )
    if resp.status_code == 409:
        _tr_session_id = resp.headers["X-Transmission-Session-Id"]
        headers = {"X-Transmission-Session-Id": _tr_session_id}
        resp = requests.post(
            url, headers=headers, json={"method": method, "arguments": arguments}, timeout=30
        )
    resp.raise_for_status()
    return resp.json()


def transmission_fetch_torrents() -> list[dict]:
    if not TRANSMISSION_URL:
        return []
    data = _tr_rpc(
        "torrent-get", {"fields": ["hashString", "name", "downloadDir"]}
    )
    out = []
    for t in data["arguments"]["torrents"]:
        if t["downloadDir"] != TRANSMISSION_PRIVATE_DIR:
            continue
        out.append(
            {
                "key": f"tr:{t['hashString']}",
                "name": t["name"],
                "path": f"{t['downloadDir']}/{t['name']}",
            }
        )
    return out


def transmission_delete_torrent(key: str) -> None:
    tr_hash = key.split(":", 1)[1]
    _tr_rpc("torrent-remove", {"ids": [tr_hash], "delete-local-data": True})


# ---------------------------------------------------------------------- core

CLIENTS = [
    ("qBittorrent", qbit_fetch_torrents, qbit_delete_torrent),
    ("Transmission", transmission_fetch_torrents, transmission_delete_torrent),
]


def run_once(state: dict) -> dict:
    new_state = {}
    for label, fetch, delete in CLIENTS:
        try:
            items = fetch()
        except requests.RequestException as e:
            print(f"ERROR hablando con {label}: {e}")
            # conserva el estado que ya tuviera este cliente, para no perder strikes
            new_state.update({k: v for k, v in state.items() if k.split(":", 1)[0] in ("qbit", "tr")})
            continue

        print(f"[{label}] {len(items)} torrents en 'private'")
        for item in items:
            key, name, path = item["key"], item["name"], item["path"]
            if os.path.exists(path):
                continue

            if key in state:
                print(f"BORRANDO en {label} (missing en 2 pasadas seguidas): {name} ({path})")
                try:
                    delete(key)
                except requests.RequestException as e:
                    print(f"  ERROR al borrar {key}: {e}")
                    new_state[key] = state[key]
            else:
                print(f"sospechoso en {label} (1a pasada, sin fichero): {name} ({path})")
                new_state[key] = time.time()

    return new_state


def main() -> None:
    print(
        f"qbit-private-cleanup arrancando: intervalo={CHECK_INTERVAL_SECONDS}s, "
        f"qbit={QBIT_URL} (cat={QBIT_CATEGORY}), "
        f"transmission={TRANSMISSION_URL or '(desactivado)'} (dir={TRANSMISSION_PRIVATE_DIR})"
    )
    state = load_state()
    while True:
        try:
            state = run_once(state)
            save_state(state)
        except Exception as e:  # nunca queremos que el bucle muera
            print(f"ERROR inesperado en la pasada: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
