"""common.py — shared plumbing for prop-lab. stdlib only.

Data lives in ./data as append-only CSVs (text = git-friendly, pandas-friendly).
"""
import csv, json, os, sys, time, urllib.request, urllib.parse, urllib.error, datetime as dt

BASE = "https://api.prop-line.com/v1"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
os.makedirs(DATA, exist_ok=True); os.makedirs(DOCS, exist_ok=True)

# ---------------------------------------------------------------- config
SPORTS = ["football_nfl"]                      # add "basketball_nba", "baseball_mlb" later
BOOKS_TRACKED = {"hardrock", "underdog", "draftkings", "fanduel", "pinnacle", "bovada", "kalshi", "fanatics"}
BETTABLE = {"hardrock"}                        # the only legal book in FL
SNAPSHOT_HOURS_BEFORE = 24 * 6                 # start snapshotting events within 6 days

# Gates for a "candidate" single (from the first Chiefs–Colts reading)
GATE = dict(
    fair_min=0.30, fair_max=0.70,              # no deep alts — devig error lives there
    min_books=3,                               # line must be quoted by >=3 books
    min_ev_pct=3.0,                            # edge must beat estimation noise
    trusted_anchors={"pinnacle", "bovada"},    # exchange anchors need extra books
    kalshi_min_books=4,
)
SGP_BOOKS = ["fanduel", "draftkings"]
SGP_PROBES_PER_EVENT = 3                       # H4 sampling; keep API calls modest

# ---------------------------------------------------------------- time
def utcnow():
    return dt.datetime.now(dt.timezone.utc)

def iso(t=None):
    return (t or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(s):
    return dt.datetime.strptime(s.replace("+00:00", "Z"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)

# ---------------------------------------------------------------- api
class Api:
    def __init__(self, key=None):
        self.key = key or os.environ.get("ODDS_API_KEY")
        if not self.key:
            sys.exit("ODDS_API_KEY not set")
        self.calls = 0; self.remaining = None

    def _req(self, method, path, params=None, body=None, retries=3):
        url = BASE + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"X-API-Key": self.key, "Content-Type": "application/json",
                                              "User-Agent": "prop-lab/1.0"})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self.calls += 1
                    self.remaining = r.headers.get("X-Daily-Remaining")
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(int(e.headers.get("Retry-After", "5"))); continue
                if e.code in (404, 422, 503):
                    return {"_error": e.code, "_body": e.read().decode()[:500]}
                if attempt == retries - 1: raise
                time.sleep(2 ** attempt)
            except (urllib.error.URLError, TimeoutError):
                if attempt == retries - 1: raise
                time.sleep(2 ** attempt)

    def get(self, path, **params):  return self._req("GET", path, params)
    def post(self, path, body, **params): return self._req("POST", path, params, body)

# ---------------------------------------------------------------- csv store
def csv_path(name): return os.path.join(DATA, f"{name}.csv")

def append_rows(name, rows, fields):
    if not rows: return 0
    p = csv_path(name); new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new: w.writeheader()
        for r in rows: w.writerow(r)
    return len(rows)

def read_rows(name):
    p = csv_path(name)
    if not os.path.exists(p): return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

def state_get(key, default=None):
    p = os.path.join(DATA, "state.json")
    if not os.path.exists(p): return default
    return json.load(open(p)).get(key, default)

def state_set(key, value):
    p = os.path.join(DATA, "state.json")
    s = json.load(open(p)) if os.path.exists(p) else {}
    s[key] = value
    json.dump(s, open(p, "w"), indent=1, sort_keys=True)

# ---------------------------------------------------------------- telegram
def telegram(text):
    tok = os.environ.get("TELEGRAM_TOKEN"); chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        print("[telegram disabled]\n" + text); return False
    body = json.dumps({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read(); return True
    except Exception as e:
        print("telegram failed:", e); return False

# ---------------------------------------------------------------- math
def am_to_p(a):
    a = int(a); return 100 / (a + 100) if a > 0 else -a / (-a + 100)

def am_to_dec(a):
    a = int(a); return 1 + (a / 100 if a > 0 else 100 / -a)
