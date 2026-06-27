import webview
import threading
import json
import os
import itertools
import time
import base64
from datetime import datetime

from main import (
    ProxyManager, Logger, generate_usernames, count_usernames,
    check_username, send_webhook,
    PROXY_FILE, WEBHOOK_FILE, WEBHOOK_COOLDOWN, BASE_DIR, load_webhooks,
)

MODE_LABELS = {
    "2":  "2 characters",
    "3":  "3 characters",
    "4a": "4 chiffres",
    "4b": "4 lettres",
    "4c": "3 chiffres + i/l",
    "4d": "3 chiffres + _",
    "4e": "3 lettres + _",
    "4f": "3 chiffres + .",
    "4g": "3 lettres + .",
    "5a": "5 lettres",
    "5b": "5 chiffres",
}


class API:
    def __init__(self):
        self._window      = None
        self._scan_thread = None
        self._stop_event  = threading.Event()
        self._scanning    = False

    def set_window(self, window):
        self._window = window

    def _push(self, event, data):
        payload = json.dumps({"event": event, "data": data})
        b64     = base64.b64encode(payload.encode()).decode()
        if self._window:
            try:
                self._window.evaluate_js(f"onPythonEvent(JSON.parse(atob('{b64}')))")
            except Exception:
                pass

    # ── SCAN ──────────────────────────────────────────────────────────
    def start_scan(self, mode):
        if self._scanning:
            return {"ok": False, "error": "Scan déjà en cours"}
        self._stop_event.clear()
        self._scanning = True
        self._scan_thread = threading.Thread(
            target=self._scan_worker, args=(mode,), daemon=True
        )
        self._scan_thread.start()
        return {"ok": True}

    def stop_scan(self):
        self._stop_event.set()
        return {"ok": True}

    def is_scanning(self):
        return self._scanning

    def reset_progress(self, mode):
        try:
            logger = Logger(mode)
            logger.reset()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_saved_progress(self, mode):
        mode_dir  = os.path.join(BASE_DIR, mode)
        prog_file = os.path.join(mode_dir, f"progress_{mode}.json")
        if not os.path.exists(prog_file):
            return {"last_index": 0, "total_found": 0}
        try:
            with open(prog_file, "r") as f:
                return json.load(f)
        except Exception:
            return {"last_index": 0, "total_found": 0}

    # ── HISTORY ───────────────────────────────────────────────────────
    def get_history(self):
        results = []
        if not os.path.exists(BASE_DIR):
            return results
        for mode_dir in os.listdir(BASE_DIR):
            avail_file = os.path.join(BASE_DIR, mode_dir, f"available_{mode_dir}.txt")
            if not os.path.exists(avail_file):
                continue
            with open(avail_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("] ", 1)
                    if len(parts) == 2:
                        results.append({
                            "username": parts[1],
                            "date":     parts[0].lstrip("["),
                            "mode":     mode_dir,
                        })
                    else:
                        results.append({"username": line, "date": "", "mode": mode_dir})
        results.sort(key=lambda x: x["date"], reverse=True)
        return results

    def clear_history(self):
        try:
            if not os.path.exists(BASE_DIR):
                return {"ok": True}
            for mode_dir in os.listdir(BASE_DIR):
                for fname in [f"available_{mode_dir}.txt", f"sent_{mode_dir}.txt"]:
                    path = os.path.join(BASE_DIR, mode_dir, fname)
                    if os.path.exists(path):
                        os.remove(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── SETTINGS ──────────────────────────────────────────────────────
    def get_settings(self):
        if not os.path.exists(WEBHOOK_FILE):
            return {}
        try:
            with open(WEBHOOK_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self, settings):
        try:
            with open(WEBHOOK_FILE, "w") as f:
                json.dump(settings, f, indent=4)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_proxy_count(self):
        if not os.path.exists(PROXY_FILE):
            return 0
        count = 0
        with open(PROXY_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    count += 1
        return count

    # ── SCAN WORKER ───────────────────────────────────────────────────
    def _scan_worker(self, mode):
        try:
            webhooks = load_webhooks()

            self._push("log", {"text": "Chargement des proxies...", "type": "info"})
            proxy_manager = ProxyManager(PROXY_FILE)
            alive = proxy_manager.total_loaded - len(proxy_manager.dead_proxies)
            self._push("log", {"text": f"{alive} proxies chargés.", "type": "info"})
            self._push("proxy_status", {"alive": alive, "total": proxy_manager.total_loaded})

            logger        = Logger(mode)
            already_done  = logger.progress["last_index"]
            already_found = logger.progress["total_found"]

            self._push("log", {"text": f"Comptage des usernames pour le mode {mode}...", "type": "info"})
            total = count_usernames(mode)
            self._push("log", {
                "text": f"Total : {total:,} | Reprise à : {already_done:,} | Déjà trouvés : {already_found}",
                "type": "info",
            })
            self._push("progress", {
                "checked": already_done,
                "total":   total,
                "found":   already_found,
                "speed":   "—",
                "eta":     "—",
                "pct":     round(already_done / total * 100, 2) if total > 0 else 0,
            })

            start_time    = datetime.now()
            session_check = 0
            total_checked = already_done
            total_found   = already_found

            scan_gen = itertools.islice(generate_usernames(mode), already_done, None)

            for index, username in enumerate(scan_gen, start=already_done):
                if self._stop_event.is_set():
                    break

                if logger.is_checked(username):
                    continue

                available = check_username(username, proxy_manager)
                now_str   = datetime.now().strftime("%H:%M:%S")

                total_checked  += 1
                session_check  += 1

                if available is True:
                    time.sleep(0.5)
                    available = check_username(username, proxy_manager)

                if available is True:
                    total_found += 1
                    self._push("log", {"text": f"[{now_str}] ✅ DISPONIBLE → {username}", "type": "success"})
                    self._push("username_found", {"username": username, "mode": mode})
                    logger.save_available(username)
                    if not logger.is_sent(username):
                        send_webhook(username, mode, MODE_LABELS.get(mode, mode), webhooks)
                        logger.mark_sent(username)
                        time.sleep(WEBHOOK_COOLDOWN)

                elif available is False:
                    self._push("log", {"text": f"[{now_str}] ❌ {username}", "type": "taken"})

                else:
                    self._push("log", {"text": f"[{now_str}] ⚠️  Erreur → {username}", "type": "warning"})

                logger.mark_checked(username)
                logger.save_progress(index + 1, total_checked, total_found)

                if session_check % 10 == 0:
                    elapsed   = max((datetime.now() - start_time).total_seconds(), 1)
                    speed     = session_check / elapsed
                    remaining = total - total_checked
                    eta_sec   = int(remaining / speed) if speed > 0 else 0
                    eta_str   = f"{eta_sec // 3600}h {(eta_sec % 3600) // 60}m {eta_sec % 60}s"
                    pct       = round(total_checked / total * 100, 2) if total > 0 else 0
                    self._push("progress", {
                        "checked": total_checked,
                        "total":   total,
                        "found":   total_found,
                        "speed":   f"{speed:.1f}",
                        "eta":     eta_str,
                        "pct":     pct,
                    })

            else:
                self._push("log", {
                    "text": f"✅ Scan terminé — {total_checked:,} vérifiés, {total_found} trouvés.",
                    "type": "success",
                })
                self._push("scan_complete", {"total_checked": total_checked, "total_found": total_found})

        except Exception as e:
            self._push("log", {"text": f"[ERREUR] {e}", "type": "error"})

        finally:
            self._scanning = False
            self._push("scan_ended", {})


def main():
    api     = API()
    ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

    window = webview.create_window(
        title="Discord Username Checker",
        url=ui_path,
        js_api=api,
        width=1020,
        height=700,
        resizable=True,
        min_size=(800, 540),
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    main()
