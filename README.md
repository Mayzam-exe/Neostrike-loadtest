<div align="center">

```
███╗   ██╗███████╗ ██████╗ ███████╗████████╗██████╗ ██╗██╗  ██╗███████╗
████╗  ██║██╔════╝██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██║██║ ██╔╝██╔════╝
██╔██╗ ██║█████╗  ██║   ██║███████╗   ██║   ██████╔╝██║█████╔╝ █████╗  
██║╚██╗██║██╔══╝  ██║   ██║╚════██║   ██║   ██╔══██╗██║██╔═██╗ ██╔══╝  
██║ ╚████║███████╗╚██████╔╝███████║   ██║   ██║  ██║██║██║  ██╗███████╗
╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝
```

**A cyberpunk-themed, terminal-native network load testing engine.**  
*Async HTTP flooding · Raw TCP/UDP · Live rich dashboard · Structured logging*

![Python](https://img.shields.io/badge/Python-3.10%2B-cyan?style=flat-square&logo=python&logoColor=white)
![asyncio](https://img.shields.io/badge/asyncio-powered-blueviolet?style=flat-square)
![aiohttp](https://img.shields.io/badge/aiohttp-client-ff69b4?style=flat-square)
![rich](https://img.shields.io/badge/rich-dashboard-00ffff?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

</div>

---

> ⚠️ **AUTHORIZED USE ONLY** — NeoStrike is a **network stress testing tool** intended strictly for use on systems you own or have **explicit written permission** to test. Unauthorized use against third-party systems is illegal and unethical. The author assumes zero liability for misuse.

> 🛡️ **A note on responsible use:** The disclaimer gate and "authorized testing only" framing are front-and-center by design — this kind of tool is only appropriate against infrastructure you own or have written permission to test. Use it to validate your own capacity planning and resilience. Nothing more.

---

## 🗂️ Table of Contents

- [🔍 Overview](#overview)
- [⚡ Features](#features)
- [📦 Requirements](#requirements)
- [🚀 Installation](#installation)
- [🔁 Launch Flow](#launch-flow)
- [⚙️ Engine Architecture](#engine-architecture)
- [🖥️ Live Dashboard](#live-dashboard)
- [🛠️ Configuration Reference](#configuration-reference)
- [📝 Logging](#logging)
- [📁 Project Structure](#project-structure)
- [⚖️ Disclaimer](#disclaimer)

---

## 🔍 Overview

**NeoStrike** is a terminal-native network load testing tool built for authorized stress testing and performance benchmarking. It combines an async HTTP engine, raw socket flood modes, and a cyberpunk `rich`-powered live dashboard into a single interactive CLI experience — no config files, no GUIs, no guesswork.

Designed with production-quality error handling, structured session logging, and a fully interactive configuration wizard, NeoStrike gives you full control over your load test from launch to teardown.

---

## ⚡ Features

- 🎯 **7 test modes** — GET, POST, HEAD, PUT, DELETE, TCP, UDP
- 🔄 **Async HTTP engine** — `asyncio` + `aiohttp` with configurable concurrency and optional token-bucket rate limiting
- 🧵 **Raw socket modes** — TCP/UDP flood via a dedicated thread pool
- 🧙 **Interactive config wizard** — guided setup with early DNS resolution, so bad targets fail *before* the test starts
- 💻 **Live cyberpunk dashboard** — `rich`-powered panels: TELEMETRY, RESPONSES, LIVE FEED, PROGRESS
- ⏱️ **Dual stop conditions** — duration limit *or* request count, whichever hits first
- 🛑 **Graceful shutdown** — `Q` key or `Ctrl+C` exits cleanly
- 📝 **Structured logging** — timestamped `.log` files with per-request outcomes and session summary
- 🔧 **Zero magic numbers** — all tunables are exposed as commented constants at the top of the file

---

## 📦 Requirements

```
aiohttp>=3.9.0
rich>=13.7.0
```

Install via:

```bash
pip install -r requirements.txt
```

> Python 3.10 or higher is required.

---

## 🚀 Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/neostrike.git
cd neostrike

# Install dependencies
pip install -r requirements.txt

# Run
python neostrike.py
```

---

## 🔁 Launch Flow

NeoStrike walks you through a structured setup sequence before anything hits the wire.

### 1 — Disclaimer Gate

A neon-bordered banner appears on launch requiring **explicit confirmation** that you are authorized to test the target. Nothing proceeds until you accept.

```
╔══════════════════════════════════════════════════════╗
║  ⚡  AUTHORIZED USE ONLY  ⚡                         ║
║  Confirm you have permission to test this target.    ║
╚══════════════════════════════════════════════════════╝
```

### 2 — Interactive Config Sequence

| Prompt | Details |
|---|---|
| **Mode** | Select from a formatted table: `GET / POST / HEAD / PUT / DELETE / TCP / UDP` |
| **Target** | Accepts `host`, `host:port`, or full URL — DNS resolved immediately at parse time |
| **Custom Headers** | Optional key-value header injection for HTTP modes |
| **Concurrency** | Number of parallel workers |
| **Duration** | Format: `30s`, `5m`, `1h` |
| **Request Count** | Optional hard cap on total requests sent |

> Bad targets (unresolvable DNS, malformed URLs) fail **at parse time** — not mid-test.

### 3 — Config Review + Final Confirmation

A summary panel displays your full configuration before launch. One final `[Y/N]` prompt before the engine starts.

---

## ⚙️ Engine Architecture

### HTTP Modes (`GET`, `POST`, `HEAD`, `PUT`, `DELETE`)

- Built on **`asyncio` + `aiohttp`**
- Configurable pool of concurrent async workers
- Optional **token-bucket rate limiter** to cap requests per second
- Connection pooling handled by `aiohttp.ClientSession`

### Raw Socket Modes (`TCP`, `UDP`)

- Built on a **thread pool of socket workers**
- Low-level `socket` API for maximum throughput
- Configurable payload size and concurrency

### Stop Conditions

The engine stops on whichever limit is reached first:

- ⏱ Duration limit expires
- 🔢 Request count target is hit
- 🛑 Manual exit via `Q` key or `Ctrl+C`

---

## 🖥️ Live Dashboard

The dashboard is rendered using `rich` and updates in real time throughout the test.

**Theme:** Neon cyan / electric purple / hot pink on deep black.

```
┌─[ NEOSTRIKE v1.0 ]──────────────────────────────────────────────┐
│  ██ TELEMETRY       ██ RESPONSES      ██ LIVE FEED              │
│                                                                  │
│  Target  : https://target.local       200 OK  ████████  91.2%  │
│  Mode    : GET                        4xx     ██        5.1%   │
│  Workers : 50                         5xx     █         3.7%   │
│  Elapsed : 00:01:23                                             │
│                                                                  │
│  ██ PROGRESS ─────────────────────────────── 1,240 / 5,000 req │
│  [████████████░░░░░░░░░░░░░░░░░░░░░] 24.8%   Est. Load: HIGH   │
└──────────────────────────────────────────────────────────────────┘
```

**Panels:**

| Panel | Contents |
|---|---|
| **TELEMETRY** | Target, mode, workers, elapsed time, requests/sec |
| **RESPONSES** | Status code breakdown with animated bar chart |
| **LIVE FEED** | Rolling log of the most recent request outcomes |
| **PROGRESS** | Animated progress bar + estimated-load gauge |

---

## 🛠️ Configuration Reference

All tunables are exposed as **commented constants** at the top of `neostrike.py` — no hunting through the code.

```python
# ── Engine Tunables ─────────────────────────────────────────────
DEFAULT_CONCURRENCY   = 50          # Parallel workers
DEFAULT_TIMEOUT       = 10          # Per-request timeout (seconds)
DEFAULT_DURATION      = 60          # Default test duration (seconds)
RATE_LIMIT_RPS        = None        # Token-bucket cap (None = unlimited)
TCP_UDP_PAYLOAD_SIZE  = 1024        # Bytes per raw socket packet

# ── Logging ─────────────────────────────────────────────────────
LOG_DIR               = "neostrike_logs"
LOG_LEVEL             = "INFO"
```

---

## 📝 Logging

Every session produces a structured log file at:

```
neostrike_logs/neostrike_<timestamp>.log
```

**📋 Log contents:**

- 🗃️ Session metadata (target, mode, config, start time)
- 📡 Per-request outcomes (status, latency, errors)
- 🔴 Error details (timeout, DNS failure, connection refused, client errors)
- 📊 Full session summary (total requests, success rate, duration, avg RPS)

---

## 📁 Project Structure

```
neostrike/
├── neostrike.py          # Main entry point — all logic in one file
├── requirements.txt      # aiohttp, rich
├── neostrike_logs/       # Auto-created on first run
│   └── neostrike_<ts>.log
└── README.md
```

---

## ⚖️ Disclaimer

NeoStrike is built for **authorized network stress testing and performance benchmarking only**.

- ✅ Only test systems you **own** or have **explicit written permission** to test.
- ❌ Do not use this tool against production systems, third-party infrastructure, or any target without prior authorization.
- 🚫 The author is **not responsible** for any damage, legal consequences, or misuse arising from this tool.

🤝 Use responsibly. 🧪 Test ethically.

---

<div align="center">

*Built with `asyncio` · `aiohttp` · `rich` · and too much caffeine.*

</div>
