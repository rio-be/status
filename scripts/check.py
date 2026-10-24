import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITE = "https://brabo.team"
OUT = Path(__file__).resolve().parents[1] / "status.json"
HEARTBEAT = timedelta(hours=6)


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def fetch(path: str, tries: int = 3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(SITE + path, headers={"User-Agent": "brabo-status-check"})
            started = time.monotonic()
            with urllib.request.urlopen(req, timeout=15) as res:
                return res.status, res.read(), round((time.monotonic() - started) * 1000)
        except Exception as exc:
            last = exc
            time.sleep(5 * (attempt + 1))
    raise last


def check() -> dict:
    try:
        code, _, ms = fetch("/api/health")
        server = {"state": "ok" if code < 500 else "down", "detail": f"answered in {ms} ms" if code < 500 else f"answered {code}"}
    except Exception as exc:
        server = {"state": "down", "detail": f"no answer ({type(exc).__name__})"}

    edges = {"watched": None, "down": [], "pops": [], "checked_at": None}
    if server["state"] == "ok":
        try:
            _, body, _ = fetch("/api/status")
            data = json.loads(body)
            edges = {
                "watched": data.get("edges_watched"),
                "down": data.get("edges_down") or [],
                "pops": data.get("pops") or [],
                "checked_at": data.get("checked_at"),
            }
        except Exception:
            pass

    overall = "down" if server["state"] == "down" else "degraded" if edges["down"] else "ok"
    return {"overall": overall, "server": server, "edges": edges}


def main() -> None:
    previous = json.loads(OUT.read_text()) if OUT.exists() else {}
    state = check()
    same = {k: previous.get(k) for k in ("overall", "server", "edges")}
    comparable = lambda s: {**s, "server": {"state": s["server"]["state"]} if s.get("server") else None,
                            "edges": {"down": [(e.get("pop"), e.get("since")) for e in (s.get("edges") or {}).get("down", [])]}}
    changed = not previous or comparable(same) != comparable(state)
    stamp = now()
    last_check = datetime.fromisoformat(previous["checked_at"]) if previous.get("checked_at") else None
    if not changed and last_check and stamp - last_check < HEARTBEAT:
        print("no change")
        return
    OUT.write_text(json.dumps({
        **state,
        "changed_at": stamp.isoformat() if changed else previous.get("changed_at", stamp.isoformat()),
        "checked_at": stamp.isoformat(),
    }, indent=2) + "\n")
    print("changed" if changed else "heartbeat", state["overall"])


if __name__ == "__main__":
    main()
