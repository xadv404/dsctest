#create by Kaiz

import requests
import time
import sys
import json
import os
from datetime import datetime

# ================= CONFIG =================
TARGET_USERNAMES = [
    "shadow"
]

WEBHOOK_FILE       = "webhooks.json"
WEBHOOK_KEY        = "checker"   # clé dans webhooks.json pour ce script
CHECK_INTERVAL_SEC = 300         # 5 minutes

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def load_webhook_url():
    if not os.path.exists(WEBHOOK_FILE):
        print(f"[ERROR] {WEBHOOK_FILE} introuvable. Crée-le depuis webhooks.example.json")
        sys.exit(1)
    with open(WEBHOOK_FILE, "r") as f:
        data = json.load(f)
    url = data.get(WEBHOOK_KEY)
    if not url:
        print(f"[ERROR] Clé '{WEBHOOK_KEY}' absente dans {WEBHOOK_FILE}")
        sys.exit(1)
    return url


# ================= COLORS =================
class Colors:
    RED    = '\033[91m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    CYAN   = '\033[96m'
    END    = '\033[0m'


# ================= WEBHOOK =================
def send_webhook(username, webhook_url):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    payload = {
        "content": f"# 🚨 @everyone A LA DATE DU {now}, TON USERNAME **{username}** EST DISPONIBLE !"
    }

    for attempt in range(3):
        try:
            r = requests.post(webhook_url, json=payload, timeout=10)
            if r.status_code in (200, 204):
                return
            if r.status_code == 429:
                retry_after = 1.0
                try:
                    retry_after = float(r.json().get("retry_after", 1.0))
                except Exception:
                    pass
                print(f"{Colors.YELLOW}[WEBHOOK] Rate limit, retry dans {retry_after:.1f}s...{Colors.END}")
                time.sleep(retry_after)
            else:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"{Colors.RED}[WEBHOOK ERROR] {e}, retry {attempt + 1}/3{Colors.END}")
            time.sleep(2 ** attempt)

    print(f"{Colors.RED}[WEBHOOK] ❌ Échec après 3 tentatives pour → {username}{Colors.END}")


# ================= CHECK =================
def check_username(username):
    url = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"

    try:
        r = requests.post(url, json={"username": username}, headers=HEADERS, timeout=10)

        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("taken"), bool):
                return not data["taken"]
            return None

        if r.status_code == 429:
            retry_after = 2.0
            try:
                retry_after = float(r.json().get("retry_after", 2.0))
            except Exception:
                pass
            print(f"{Colors.YELLOW}[RATE LIMIT] Attente {retry_after:.1f}s...{Colors.END}")
            time.sleep(retry_after)
            return None

        return None

    except Exception as e:
        print(f"{Colors.RED}[ERROR] {e}{Colors.END}")
        return None


# ================= MAIN LOOP =================
def run():
    webhook_url  = load_webhook_url()
    already_sent = set()

    print(f"{Colors.CYAN}Starting Discord username checker...{Colors.END}")

    while True:
        for username in TARGET_USERNAMES:
            available = check_username(username)
            now = datetime.now().strftime("%H:%M:%S")

            if available is True:
                # Double-check pour éviter les faux positifs
                time.sleep(1)
                available = check_username(username)

            if available is True:
                print(f"{Colors.GREEN}[{now}] AVAILABLE → {username}{Colors.END}")
                if username not in already_sent:
                    send_webhook(username, webhook_url)
                    already_sent.add(username)

            elif available is False:
                print(f"{Colors.RED}[{now}] NOT AVAILABLE → {username}{Colors.END}")

            else:
                print(f"{Colors.YELLOW}[{now}] UNKNOWN / ERROR → {username}{Colors.END}")

        print(f"\n{Colors.CYAN}Waiting {CHECK_INTERVAL_SEC} seconds...\n{Colors.END}")
        time.sleep(CHECK_INTERVAL_SEC)


# ================= START =================
if __name__ == "__main__":
    run()
