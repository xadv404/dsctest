import requests
import time
import sys
import string
import itertools
import os
import json
import random
from datetime import datetime

# ================= CONFIG =================
WEBHOOK_FILE       = "webhooks.json"
CHECK_INTERVAL_SEC = 0
WEBHOOK_COOLDOWN   = 5
PROXY_FILE         = "proxies.txt"
BASE_DIR           = "checker_data"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Counts connus mathématiquement — évite de tout générer juste pour compter
KNOWN_COUNTS = {
    "4a": 10**4,
    "4b": 26**4,
    "4d": 2 * 10**3,
    "4e": 2 * 26**3,
    "4f": 2 * 10**3,
    "4g": 2 * 26**3,
    "5a": 26**5,
    "5b": 10**5,
}


def load_webhooks():
    if not os.path.exists(WEBHOOK_FILE):
        print(f"\033[93m⚠️  {WEBHOOK_FILE} introuvable. Crée-le depuis webhooks.example.json\033[0m")
        return {}
    try:
        with open(WEBHOOK_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"\033[91m❌ Erreur lecture {WEBHOOK_FILE} : {e}\033[0m")
        return {}


def get_mode_dir(mode):
    mode_dir = os.path.join(BASE_DIR, mode)
    os.makedirs(mode_dir, exist_ok=True)
    return mode_dir


# ================= COLORS =================
class Colors:
    RED    = '\033[91m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    CYAN   = '\033[96m'
    PURPLE = '\033[95m'
    BLUE   = '\033[94m'
    BOLD   = '\033[1m'
    END    = '\033[0m'


# ================= PROXY MANAGER =================
class ProxyManager:
    def __init__(self, proxy_file):
        self.proxy_file   = proxy_file
        self.proxies      = []
        self.dead_proxies = set()
        self.current_idx  = 0
        self.total_loaded = 0
        self._load_proxies()

    def _load_proxies(self):
        if not os.path.exists(self.proxy_file):
            print(f"{Colors.RED}❌ Fichier proxy introuvable : {self.proxy_file}{Colors.END}")
            with open(self.proxy_file, "w") as f:
                f.write("# Format : ip:port\n")
                f.write("# Format : ip:port:username:password\n")
                f.write("# Exemple:\n")
                f.write("# 185.199.228.220:7300\n")
                f.write("# 185.199.228.220:7300:monuser:monpass\n")
            print(f"{Colors.YELLOW}⚠️  Ajoute tes proxies dans '{self.proxy_file}' et relance.{Colors.END}")
            sys.exit(1)

        raw_proxies = []
        with open(self.proxy_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                raw_proxies.append(line)

        for raw in raw_proxies:
            parsed = self._parse_proxy(raw)
            if parsed:
                self.proxies.append(parsed)

        self.total_loaded = len(self.proxies)

        if self.total_loaded == 0:
            print(f"{Colors.RED}❌ Aucun proxy valide trouvé dans {self.proxy_file}{Colors.END}")
            sys.exit(1)

        random.shuffle(self.proxies)
        print(f"{Colors.GREEN}✅ {self.total_loaded} proxies chargés depuis {self.proxy_file}{Colors.END}")

    def _parse_proxy(self, raw):
        try:
            parts = raw.strip().split(":")
            if len(parts) == 2:
                ip, port = parts
                proxy_url = f"http://{ip}:{port}"
            elif len(parts) == 4:
                ip, port, user, password = parts
                proxy_url = f"http://{user}:{password}@{ip}:{port}"
            else:
                print(f"{Colors.YELLOW}[PROXY] Format invalide ignoré : {raw}{Colors.END}")
                return None
            return {"raw": raw, "url": proxy_url, "dict": {"http": proxy_url, "https": proxy_url}, "fails": 0}
        except Exception as e:
            print(f"{Colors.YELLOW}[PROXY] Erreur parsing '{raw}' : {e}{Colors.END}")
            return None

    def get_proxy(self):
        alive = [p for p in self.proxies if p["raw"] not in self.dead_proxies]
        if not alive:
            print(f"{Colors.RED}❌ Tous les proxies sont morts !{Colors.END}")
            return None
        proxy = alive[self.current_idx % len(alive)]
        self.current_idx += 1
        return proxy

    def mark_dead(self, proxy):
        if proxy:
            self.dead_proxies.add(proxy["raw"])
            alive = len(self.proxies) - len(self.dead_proxies)
            print(f"{Colors.RED}[PROXY] ☠️  Proxy mort : {proxy['raw'][:30]}... ({alive} restants){Colors.END}")

    def mark_fail(self, proxy):
        if proxy:
            proxy["fails"] += 1
            if proxy["fails"] >= 5:
                self.mark_dead(proxy)

    def mark_success(self, proxy):
        if proxy:
            proxy["fails"] = 0

    def show_status(self):
        alive = len(self.proxies) - len(self.dead_proxies)
        dead  = len(self.dead_proxies)
        print(
            f"{Colors.CYAN}[PROXY] 🔄 Total: {self.total_loaded} | "
            f"✅ Vivants: {alive} | "
            f"☠️  Morts: {dead}{Colors.END}"
        )


# ================= LOGGER =================
class Logger:
    def __init__(self, mode):
        self.mode           = mode
        self.mode_dir       = get_mode_dir(mode)
        self.progress_file  = os.path.join(self.mode_dir, f"progress_{mode}.json")
        self.checked_file   = os.path.join(self.mode_dir, f"checked_{mode}.txt")
        self.available_file = os.path.join(self.mode_dir, f"available_{mode}.txt")
        self.sent_file      = os.path.join(self.mode_dir, f"sent_{mode}.txt")
        self.progress       = self._load_progress()
        self.checked        = self._load_checked()
        self.available_set  = self._load_available()
        self.sent           = self._load_sent()

    def _load_progress(self):
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "mode":          self.mode,
            "last_index":    0,
            "total_checked": 0,
            "total_found":   0,
            "started_at":    datetime.now().isoformat(),
            "last_updated":  datetime.now().isoformat(),
        }

    def save_progress(self, index, total_checked, total_found):
        self.progress["last_index"]    = index
        self.progress["total_checked"] = total_checked
        self.progress["total_found"]   = total_found
        self.progress["last_updated"]  = datetime.now().isoformat()
        with open(self.progress_file, "w") as f:
            json.dump(self.progress, f, indent=4)

    def _load_checked(self):
        if os.path.exists(self.checked_file):
            try:
                with open(self.checked_file, "r") as f:
                    return set(line.strip() for line in f if line.strip())
            except Exception:
                pass
        return set()

    def mark_checked(self, username):
        self.checked.add(username)
        with open(self.checked_file, "a") as f:
            f.write(username + "\n")

    def is_checked(self, username):
        return username in self.checked

    def _load_available(self):
        """Charge les usernames déjà trouvés pour éviter les doublons dans le fichier."""
        if not os.path.exists(self.available_file):
            return set()
        result = set()
        with open(self.available_file, "r") as f:
            for line in f:
                parts = line.strip().split("] ", 1)
                if len(parts) == 2:
                    result.add(parts[1])
        return result

    def save_available(self, username):
        if username in self.available_set:
            return
        self.available_set.add(username)
        with open(self.available_file, "a") as f:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            f.write(f"[{now}] {username}\n")

    def _load_sent(self):
        """Charge les usernames déjà notifiés par webhook (persiste entre redémarrages)."""
        if not os.path.exists(self.sent_file):
            return set()
        with open(self.sent_file, "r") as f:
            return set(line.strip() for line in f if line.strip())

    def mark_sent(self, username):
        self.sent.add(username)
        with open(self.sent_file, "a") as f:
            f.write(username + "\n")

    def is_sent(self, username):
        return username in self.sent

    def reset(self):
        for path in [self.progress_file, self.checked_file, self.sent_file]:
            if os.path.exists(path):
                os.remove(path)
        self.progress = self._load_progress()
        self.checked  = set()
        self.sent     = set()

    def show_resume_info(self):
        if self.progress["last_index"] > 0:
            print(f"""
{Colors.YELLOW}{Colors.BOLD}
╔══════════════════════════════════════════════════╗
║         ⏩ REPRISE DÉTECTÉE - MODE {self.mode.upper():<14} ║
╠══════════════════════════════════════════════════╣
║  Dernier index   : {self.progress["last_index"]:<28} ║
║  Déjà vérifiés  : {self.progress["total_checked"]:<28} ║
║  Déjà trouvés   : {self.progress["total_found"]:<28} ║
║  Démarré le     : {self.progress["started_at"][:19]:<28} ║
║  Dernière MAJ   : {self.progress["last_updated"][:19]:<28} ║
╚══════════════════════════════════════════════════╝
{Colors.END}""")
            return True
        return False

    def show_files_info(self):
        print(f"""
{Colors.CYAN}📁 Fichiers pour le mode [{self.mode}] :
   ├── {self.progress_file}
   ├── {self.checked_file}
   ├── {self.sent_file}
   └── {self.available_file}
{Colors.END}""")


# ================= VALIDATION =================
def is_valid_username(username):
    if len(username) < 2 or len(username) > 32:
        return False
    allowed = set(string.ascii_lowercase + string.digits + "_.")
    if not all(c in allowed for c in username):
        return False
    if ".." in username:
        return False
    return True


# ================= GENERATOR =================
def generate_usernames(mode):
    """Générateur — produit les usernames un par un sans tout charger en RAM."""
    letters   = string.ascii_lowercase
    digits    = string.digits
    all_chars = letters + digits + "_."

    if mode == "2":
        for combo in itertools.product(all_chars, repeat=2):
            username = "".join(combo)
            if is_valid_username(username):
                yield username

    elif mode == "3":
        for combo in itertools.product(all_chars, repeat=3):
            username = "".join(combo)
            if is_valid_username(username):
                yield username

    elif mode == "4a":
        for combo in itertools.product(digits, repeat=4):
            yield "".join(combo)

    elif mode == "4b":
        for combo in itertools.product(letters, repeat=4):
            yield "".join(combo)

    elif mode == "4c":
        seen    = set()
        special = ["i", "l"]
        for combo in itertools.product(digits, repeat=3):
            base = "".join(combo)
            for sp in special:
                for pos in range(4):
                    username = base[:pos] + sp + base[pos:]
                    if username not in seen:
                        seen.add(username)
                        yield username

    elif mode == "4d":
        for combo in itertools.product(digits, repeat=3):
            base = "".join(combo)
            yield "_" + base
            yield base + "_"

    elif mode == "4e":
        for combo in itertools.product(letters, repeat=3):
            base = "".join(combo)
            yield "_" + base
            yield base + "_"

    elif mode == "4f":
        for combo in itertools.product(digits, repeat=3):
            base = "".join(combo)
            yield "." + base
            yield base + "."

    elif mode == "4g":
        for combo in itertools.product(letters, repeat=3):
            base = "".join(combo)
            yield "." + base
            yield base + "."

    elif mode == "5a":
        for combo in itertools.product(letters, repeat=5):
            yield "".join(combo)

    elif mode == "5b":
        for combo in itertools.product(digits, repeat=5):
            yield "".join(combo)

    else:
        print(f"{Colors.RED}[ERROR] Mode inconnu : {mode}{Colors.END}")
        sys.exit(1)


def count_usernames(mode):
    """Retourne le total sans générer la liste complète en mémoire."""
    if mode in KNOWN_COUNTS:
        return KNOWN_COUNTS[mode]
    return sum(1 for _ in generate_usernames(mode))


# ================= STATS =================
class Stats:
    def __init__(self, total, already_done=0, already_found=0):
        self.total         = total
        self.checked       = already_done
        self.available     = already_found
        self.errors        = 0
        self.session_check = 0
        self.start         = datetime.now()

    def progress(self):
        pct     = (self.checked / self.total * 100) if self.total > 0 else 0
        elapsed = max((datetime.now() - self.start).total_seconds(), 1)
        speed   = self.session_check / elapsed
        remaining = self.total - self.checked
        eta_sec   = int(remaining / speed) if speed > 0 else 0
        eta_str   = f"{eta_sec // 3600}h {(eta_sec % 3600) // 60}m {eta_sec % 60}s"

        return (
            f"{Colors.BOLD}{Colors.CYAN}"
            f"[{self.checked:,}/{self.total:,}] "
            f"{pct:.2f}% | "
            f"✅ {self.available:,} dispo | "
            f"❌ {self.errors:,} erreurs | "
            f"⚡ {speed:.1f}/s | "
            f"⏳ ETA: {eta_str}"
            f"{Colors.END}"
        )


# ================= WEBHOOK =================
def send_webhook(username, mode, mode_label, webhooks):
    webhook_url = webhooks.get(mode)
    if not webhook_url:
        print(f"{Colors.YELLOW}[WEBHOOK] ⚠️ Pas de webhook configuré pour le mode {mode}{Colors.END}")
        return

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    payload = {
        "embeds": [{
            "title": "🚨 USERNAME DISPONIBLE !",
            "description": (
                f"```\n{username}\n```\n"
                f"**Type :** `{mode_label}`\n"
                f"**Date :** `{now}`\n"
                f"**Longueur :** `{len(username)} caractères`\n\n"
                f"⚡ **DÉPÊCHE-TOI AVANT QU'IL SOIT PRIS !**"
            ),
            "color": 0x00FF00,
            "footer": {"text": f"Discord Username Checker v4.0 | Mode {mode}"},
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "content": "@everyone",
    }

    for attempt in range(3):
        try:
            r = requests.post(webhook_url, json=payload, timeout=10)
            if r.status_code in (200, 204):
                print(f"{Colors.PURPLE}[WEBHOOK] ✅ Envoyé pour → {username} (mode {mode}){Colors.END}")
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
                print(f"{Colors.YELLOW}[WEBHOOK] ⚠️ Code {r.status_code}, retry {attempt + 1}/3{Colors.END}")
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"{Colors.RED}[WEBHOOK ERROR] {e}, retry {attempt + 1}/3{Colors.END}")
            time.sleep(2 ** attempt)

    print(f"{Colors.RED}[WEBHOOK] ❌ Échec après 3 tentatives pour → {username}{Colors.END}")


# ================= CHECK WITH PROXY =================
def check_username(username, proxy_manager):
    url     = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
    payload = {"username": username}

    for attempt in range(3):
        proxy      = proxy_manager.get_proxy()
        proxy_dict = proxy["dict"] if proxy else None

        try:
            r = requests.post(url, json=payload, headers=HEADERS, proxies=proxy_dict, timeout=8)

            if r.status_code == 200:
                proxy_manager.mark_success(proxy)
                data = r.json()
                # Type check strict : "taken" doit être un bool pour éviter
                # les faux positifs si l'API retourne null ou un entier
                if isinstance(data, dict) and isinstance(data.get("taken"), bool):
                    return not data["taken"]
                return None

            if r.status_code == 429:
                retry_after = 1.0
                try:
                    retry_after = float(r.json().get("retry_after", 1.0))
                except Exception:
                    pass
                print(
                    f"{Colors.YELLOW}[RATE LIMIT] Proxy {proxy['raw'][:25] if proxy else 'no proxy'}... "
                    f"sleep {retry_after:.1f}s → prochain proxy...{Colors.END}"
                )
                proxy_manager.mark_fail(proxy)
                time.sleep(retry_after)
                continue

            proxy_manager.mark_fail(proxy)
            continue

        except requests.exceptions.ProxyError:
            proxy_manager.mark_fail(proxy)
            continue
        except requests.exceptions.ConnectTimeout:
            proxy_manager.mark_fail(proxy)
            continue
        except requests.exceptions.ConnectionError:
            proxy_manager.mark_fail(proxy)
            continue
        except Exception as e:
            print(f"{Colors.RED}[ERROR] {e}{Colors.END}")
            proxy_manager.mark_fail(proxy)
            continue

    return None


# ================= MENU =================
def show_menu():
    print(f"""
{Colors.CYAN}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════════╗
║         DISCORD USERNAME CHECKER v4.0                         ║
║         With Auto-Resume & Multi-Webhook & Proxy              ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  {Colors.GREEN}[2]{Colors.CYAN}   → 2 characters (all)      ex: ab, a_, .9, _0           ║
║  {Colors.GREEN}[3]{Colors.CYAN}   → 3 characters (all)      ex: abc, a_b, .9z            ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  {Colors.YELLOW}4 CHARACTERS OPTIONS :{Colors.CYAN}                                       ║
║                                                               ║
║  {Colors.GREEN}[4a]{Colors.CYAN}  → 4 chiffres              ex: 0000 → 9999              ║
║  {Colors.GREEN}[4b]{Colors.CYAN}  → 4 lettres               ex: aaaa → zzzz              ║
║  {Colors.GREEN}[4c]{Colors.CYAN}  → 3 chiffres + i/l        ex: 12i3, l456               ║
║  {Colors.GREEN}[4d]{Colors.CYAN}  → 3 chiffres + _          ex: _123, 456_               ║
║  {Colors.GREEN}[4e]{Colors.CYAN}  → 3 lettres + _           ex: _abc, xyz_               ║
║  {Colors.GREEN}[4f]{Colors.CYAN}  → 3 chiffres + .          ex: .123, 456.               ║
║  {Colors.GREEN}[4g]{Colors.CYAN}  → 3 lettres + .           ex: .abc, xyz.               ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  {Colors.YELLOW}5 CHARACTERS OPTIONS :{Colors.CYAN}                                       ║
║                                                               ║
║  {Colors.GREEN}[5a]{Colors.CYAN}  → 5 lettres               ex: aaaaa → zzzzz            ║
║  {Colors.GREEN}[5b]{Colors.CYAN}  → 5 chiffres              ex: 00000 → 99999            ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
{Colors.END}""")


# ================= PREVIEW =================
def show_preview(total, preview_items, mode_label, already_done):
    remaining = total - already_done

    print(f"\n{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════════{Colors.END}")
    print(f"{Colors.GREEN}Mode          : {mode_label}{Colors.END}")
    print(f"{Colors.YELLOW}Total         : {total:,} usernames{Colors.END}")
    print(f"{Colors.YELLOW}Déjà vérifiés : {already_done:,} usernames{Colors.END}")
    print(f"{Colors.GREEN}Restants      : {remaining:,} usernames{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════════{Colors.END}")

    if preview_items:
        print(f"\n{Colors.PURPLE}Aperçu (10 prochains à checker) :{Colors.END}")
        for i, u in enumerate(preview_items):
            print(f"  {i + 1}. {u}")

    estimated_sec = remaining * 0.5
    hours         = int(estimated_sec // 3600)
    minutes       = int((estimated_sec % 3600) // 60)
    print(f"\n{Colors.YELLOW}⏱️  Temps estimé : ~{hours}h {minutes}m (avec proxies){Colors.END}\n")


# ================= MAIN =================
def run():
    show_menu()

    mode = input(f"{Colors.BOLD}Choisis un mode : {Colors.END}").strip().lower()

    mode_labels = {
        "2":  "2 characters (a-z, 0-9, _, .)",
        "3":  "3 characters (a-z, 0-9, _, .)",
        "4a": "4 chiffres (0000-9999)",
        "4b": "4 lettres (aaaa-zzzz)",
        "4c": "3 chiffres + i/l",
        "4d": "3 chiffres + _ (début/fin)",
        "4e": "3 lettres + _ (début/fin)",
        "4f": "3 chiffres + . (début/fin)",
        "4g": "3 lettres + . (début/fin)",
        "5a": "5 lettres",
        "5b": "5 chiffres",
    }

    if mode not in mode_labels:
        print(f"{Colors.RED}❌ Mode invalide.{Colors.END}")
        sys.exit(1)

    # ── WEBHOOKS ─────────────────────────────────────────
    webhooks = load_webhooks()

    # ── PROXY ────────────────────────────────────────────
    print(f"\n{Colors.CYAN}⏳ Chargement des proxies...{Colors.END}")
    proxy_manager = ProxyManager(PROXY_FILE)
    proxy_manager.show_status()

    # ── LOGGER ───────────────────────────────────────────
    logger = Logger(mode)
    logger.show_files_info()

    has_resume    = logger.show_resume_info()
    already_done  = logger.progress["last_index"]
    already_found = logger.progress["total_found"]

    if has_resume:
        choice = input(
            f"{Colors.BOLD}Reprendre depuis l'index {already_done:,} ? (o = reprendre | n = recommencer) : {Colors.END}"
        ).strip().lower()

        if choice in ["n", "non", "no"]:
            logger.reset()
            already_done  = 0
            already_found = 0
            print(f"{Colors.YELLOW}🔄 Scan recommencé depuis le début.{Colors.END}")
        else:
            print(f"{Colors.GREEN}⏩ Reprise depuis l'index {already_done:,}.{Colors.END}")

    # ── COMPTAGE & PREVIEW ───────────────────────────────
    print(f"\n{Colors.CYAN}⏳ Comptage des usernames...{Colors.END}")
    total = count_usernames(mode)

    # Génère seulement les 10 items du preview sans charger tout en RAM
    preview_items = list(itertools.islice(
        itertools.islice(generate_usernames(mode), already_done, None),
        10
    ))
    show_preview(total, preview_items, mode_labels[mode], already_done)

    confirm = input(f"{Colors.BOLD}Lancer le scan ? (o/n) : {Colors.END}").strip().lower()
    if confirm not in ["o", "oui", "y", "yes"]:
        print(f"{Colors.YELLOW}❌ Scan annulé.{Colors.END}")
        sys.exit(0)

    # ── SCAN ─────────────────────────────────────────────
    stats = Stats(total, already_done, already_found)

    print(f"\n{Colors.GREEN}{Colors.BOLD}🚀 SCAN DÉMARRÉ AVEC {proxy_manager.total_loaded} PROXIES !{Colors.END}\n")

    # Reprend depuis already_done sans itérer inutilement toute la liste
    scan_gen = itertools.islice(generate_usernames(mode), already_done, None)

    for index, username in enumerate(scan_gen, start=already_done):
        if logger.is_checked(username):
            continue

        available = check_username(username, proxy_manager)
        now       = datetime.now().strftime("%H:%M:%S")

        stats.checked       += 1
        stats.session_check += 1

        if available is True:
            # Double-check pour éliminer les faux positifs (proxy qui ment, race condition)
            time.sleep(1)
            available = check_username(username, proxy_manager)

        if available is True:
            stats.available += 1
            print(f"{Colors.GREEN}{Colors.BOLD}[{now}] ✅ DISPONIBLE → {username}{Colors.END}")
            logger.save_available(username)

            if not logger.is_sent(username):
                send_webhook(username, mode, mode_labels[mode], webhooks)
                logger.mark_sent(username)
                time.sleep(WEBHOOK_COOLDOWN)

        elif available is False:
            print(f"{Colors.RED}[{now}] ❌ PRIS       → {username}{Colors.END}")

        else:
            stats.errors += 1
            print(f"{Colors.YELLOW}[{now}] ⚠️  ERREUR    → {username}{Colors.END}")

        logger.mark_checked(username)
        logger.save_progress(index + 1, stats.checked, stats.available)

        if stats.session_check % 25 == 0:
            print(f"\n{stats.progress()}")
            proxy_manager.show_status()
            print()

        time.sleep(CHECK_INTERVAL_SEC)

    print(f"""
{Colors.PURPLE}{Colors.BOLD}
╔════════════════════════════════════════════╗
║           ✅ SCAN TERMINÉ ✅               ║
╠════════════════════════════════════════════╣
║  Total vérifié   : {stats.checked:<20,} ║
║  Disponibles     : {stats.available:<20,} ║
║  Erreurs         : {stats.errors:<20,} ║
╚════════════════════════════════════════════╝
{Colors.END}""")

    if stats.available > 0:
        print(f"{Colors.GREEN}🎉 Résultats sauvegardés dans : {logger.available_file}{Colors.END}")


# ================= START =================
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⏹️  Scan interrompu — progression sauvegardée automatiquement.{Colors.END}")
        sys.exit(0)
