#!/usr/bin/env python3
"""Reference receiver for TradingView webhook alerts: verify, de-duplicate, queue.

Part of claude-tradingview-automation-skills by Viprasol Tech Private Limited.

TradingView cannot sign webhooks or send custom headers, so this receiver:
  * accepts requests only from TradingView's published source IPs (configurable),
  * requires a shared secret inside the JSON body (constant-time compare),
  * validates the payload (no NaN/Infinity, finite positive qty/price),
  * requires a fresh "timenow" timestamp and rejects duplicates,
  * answers immediately and appends accepted signals to a JSON-lines queue.
It never places orders: a separate worker reads the queue and talks to the
broker (see the signal-to-order skill). Standard library only.

Expected alert message (see tv-alert-design):
  {"secret":"...","symbol":"{{exchange}}:{{ticker}}","action":"buy","timenow":"{{timenow}}", ...}

  TV_SECRET=change-me-to-32-random-chars python tv_webhook_server.py serve --port 8080
  python tv_webhook_server.py serve --trust-proxy 127.0.0.1     # behind nginx/Caddy on the same host
  python tv_webhook_server.py --self-test

Run it behind HTTPS (a reverse proxy on port 443); TradingView only calls ports
80 and 443.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# TradingView webhook source IPs (check TradingView's help centre for changes).
TRADINGVIEW_IPS = frozenset({"52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7"})
REQUIRED = ("secret", "symbol", "action", "timenow")
ACTIONS = {"buy", "sell", "long", "short", "exit", "close", "flat"}
NUMERIC = ("qty", "price", "size")
MAX_BODY = 16 * 1024
MIN_SECRET = 16


class Reject(Exception):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code


def _no_constants(name: str):
    raise Reject(400, f"{name} is not valid JSON (a Pine value was na; use nz())")


def parse_time(ts: object) -> float:
    """ISO 8601 as sent by {{timenow}} (also +0000 offsets; naive = UTC) or epoch s/ms."""
    if isinstance(ts, bool) or not isinstance(ts, (str, int, float)):
        raise ValueError("timenow must be a string or number")
    s = str(ts).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        t = float(s)
        return t / 1000 if t > 1e12 else t
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s.replace("Z", "+00:00"))
    d = datetime.fromisoformat(s)
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


class Gate:
    """Pure validation logic (no network), so it can be unit-tested."""

    def __init__(self, secret: str, allowed_ips: frozenset[str] | None, max_age_seconds: int = 120) -> None:
        if not secret or len(secret) < MIN_SECRET:
            raise ValueError(f"set a secret of at least {MIN_SECRET} characters (TV_SECRET)")
        if max_age_seconds <= 0:
            raise ValueError("max age must be positive")
        self.secret = secret.encode()
        self.allowed_ips = allowed_ips
        self.max_age = max_age_seconds
        self.dedupe_seconds = 2 * max_age_seconds + 60   # longer than any alert can stay fresh
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def ip_allowed(self, ip: str) -> bool:
        return self.allowed_ips is None or ip in self.allowed_ips

    def check(self, ip: str, body: bytes, now: float | None = None) -> tuple[int, str, dict | None]:
        try:
            return 200, *self._check(ip, body, time.time() if now is None else now)
        except Reject as r:
            return r.code, str(r), None

    def _check(self, ip: str, body: bytes, now: float) -> tuple[str, dict | None]:
        if not self.ip_allowed(ip):
            raise Reject(403, "source IP not allowed")
        if len(body) > MAX_BODY:
            raise Reject(413, "payload too large")
        try:
            data = json.loads(body.decode("utf-8"), parse_constant=_no_constants)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Reject(400, "body is not JSON (check the alert message template)") from None
        if not isinstance(data, dict):
            raise Reject(400, "JSON must be an object")
        provided = data.get("secret")
        if not isinstance(provided, str) or not hmac.compare_digest(provided.encode(), self.secret):
            raise Reject(401, "bad secret")
        missing = [k for k in REQUIRED if data.get(k) in (None, "")]
        if missing:
            raise Reject(400, f"missing fields: {', '.join(missing)}")
        if not isinstance(data["symbol"], str) or not isinstance(data["action"], str):
            raise Reject(400, "symbol and action must be strings")
        if data["action"].lower() not in ACTIONS:
            raise Reject(400, f"unknown action {data['action']!r}")
        for k in NUMERIC:
            if k in data:
                try:
                    v = Decimal(str(data[k]))
                except InvalidOperation:
                    raise Reject(400, f"{k} is not a number") from None
                if isinstance(data[k], bool) or not v.is_finite() or v < 0:
                    raise Reject(400, f"{k} must be a finite, non-negative number")
        try:
            age = now - parse_time(data["timenow"])
        except (ValueError, OverflowError):
            raise Reject(400, "unreadable timenow (send \"{{timenow}}\")") from None
        if age > self.max_age:
            raise Reject(409, f"stale alert ({age:.0f}s old)")
        if age < -60:
            raise Reject(400, "timenow is in the future (clock or time-zone error)")
        if "id" in data and not isinstance(data["id"], str):
            raise Reject(400, "id must be a string")
        clean = {k: v for k, v in data.items() if k != "secret"}
        key = hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()
        with self._lock:
            self._seen = {k: t for k, t in self._seen.items() if now - t < self.dedupe_seconds}
            if key in self._seen:
                return "duplicate ignored", None
            self._seen[key] = now
        return "accepted", {**clean, "_received": now, "_dedupe_key": key}


def make_handler(gate: Gate, queue_path: str, proxies: frozenset[str]):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "tv-webhook"
        timeout = 5  # seconds per socket operation; slow or stalled clients are dropped

        def log_message(self, fmt, *args):  # never log bodies (they contain the secret)
            sys.stderr.write("%s - %s\n" % (self.client_address[0], fmt % args))

        def _ip(self) -> str:
            peer = self.client_address[0]
            xff = self.headers.get("X-Forwarded-For")
            if peer in proxies and xff:
                return xff.split(",")[-1].strip()   # the address your proxy saw
            return peer

        def _reply(self, code: int, msg: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(msg.encode())

        def do_POST(self):  # noqa: N802
            ip = self._ip()
            if not gate.ip_allowed(ip):          # before reading anything
                return self._reply(403, "source IP not allowed")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._reply(411, "Content-Length required")
            if length < 0:
                return self._reply(400, "bad Content-Length")
            if length > MAX_BODY:
                return self._reply(413, "payload too large")
            body = self.rfile.read(length)
            code, msg, signal = gate.check(ip, body)
            if signal is not None:
                with lock, open(queue_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(signal) + "\n")
            self._reply(code, msg)

        def do_GET(self):  # noqa: N802
            self._reply(200, "ok")

    return Handler


def _self_test() -> None:
    secret = "s3cret-s3cret-s3cret"
    g = Gate(secret, TRADINGVIEW_IPS, max_age_seconds=120)
    ip = "52.89.214.238"
    now = 1795511700.0 + 30  # 30 s after 2026-11-24T09:15:00Z

    def body(**kw) -> bytes:
        base = {"secret": secret, "symbol": "NSE:RELIANCE", "action": "buy", "timenow": "2026-11-24T09:15:00Z"}
        return json.dumps({**base, **kw}).encode()

    code, msg, sig = g.check(ip, body(qty=10, id="a1"), now)
    assert code == 200 and msg == "accepted" and "secret" not in sig, (code, msg)
    assert g.check(ip, body(qty=10, id="a1"), now + 5)[1] == "duplicate ignored"
    assert g.check(ip, body(qty=10, id="a1", action="sell"), now)[1] == "accepted"   # same id, other action
    assert g.check("1.2.3.4", body(), now)[0] == 403
    assert g.check(ip, body(secret="wrong-wrong-wrong-x"), now)[0] == 401
    assert g.check(ip, body(secret=None), now)[0] == 401
    assert g.check(ip, b"BUY RELIANCE", now)[0] == 400
    assert g.check(ip, b"[1,2]", now)[0] == 400
    assert g.check(ip, body(timenow="2026-11-24T09:00:00Z"), now)[0] == 409
    assert g.check(ip, body(timenow="2026-11-24T10:15:00Z"), now)[0] == 400
    assert g.check(ip, body(timenow="yesterday"), now)[0] == 400
    assert g.check(ip, body(timenow=None), now)[0] == 400                          # time is required
    assert g.check(ip, body(action="moon"), now)[0] == 400
    assert g.check(ip, body(id=[1]), now)[0] == 400
    assert g.check(ip, body(qty="abc"), now)[0] == 400
    assert g.check(ip, body(qty=-1), now)[0] == 400
    assert g.check(ip, body().replace(b'"buy"', b'"buy","qty":NaN'), now)[0] == 400
    assert g.check(ip, body(qty="NaN"), now)[0] == 400
    assert g.check(ip, body().replace(b'"2026-11-24T09:15:00Z"', b"NaN"), now)[0] == 400
    assert g.check(ip, b"x" * (MAX_BODY + 1), now)[0] == 413
    assert g.check(ip, body(timenow="2026-11-24T09:15:00+0000", id="b"), now)[0] == 200   # Pine "Z" format
    assert g.check(ip, body(timenow=1795511700000, id="c"), now)[0] == 200                # epoch ms
    assert g.dedupe_seconds > g.max_age
    assert Gate(secret, None).check("10.0.0.1", body(symbol="BTCUSDT", action="long"), now)[0] == 200
    for bad in ("short", ""):
        try:
            Gate(bad, None)
        except ValueError:
            continue
        raise AssertionError("weak secret accepted")
    print("tv_webhook_server self-test passed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Receive TradingView webhook alerts safely")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1", help="Bind address (put a TLS reverse proxy in front)")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--queue", default="signals.jsonl")
    s.add_argument("--any-ip", action="store_true", help="Disable the TradingView IP allow-list (testing only)")
    s.add_argument("--trust-proxy", action="append", default=[], metavar="PROXY_IP",
                   help="Honour X-Forwarded-For only from this proxy address (repeatable)")
    s.add_argument("--max-age", type=int, default=120, help="Reject alerts whose timenow is older (s)")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if a.cmd != "serve":
        ap.print_help()
        return 2
    try:
        gate = Gate(os.environ.get("TV_SECRET", ""), None if a.any_ip else TRADINGVIEW_IPS, max_age_seconds=a.max_age)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(gate, a.queue, frozenset(a.trust_proxy)))
    print(f"listening on {a.host}:{a.port}, queue -> {a.queue}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
