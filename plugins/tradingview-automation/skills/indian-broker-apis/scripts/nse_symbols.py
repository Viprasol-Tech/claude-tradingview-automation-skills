#!/usr/bin/env python3
"""NSE derivatives helpers: expiry dates and broker-instrument resolution.

Part of claude-tradingview-automation-skills by Viprasol Tech Private Limited.

TradingView sends continuous symbols (NSE:NIFTY1!) or option tickers
(NSE:NIFTY261229C26000); brokers need an exact contract. Do not build broker
symbol strings by hand: resolve them from the broker's daily instrument dump.

  python nse_symbols.py expiry --month 2026-12 --holidays nse_holidays.txt
  python nse_symbols.py resolve instruments.csv --name NIFTY --type FUT --front --today 2026-11-24
  python nse_symbols.py resolve instruments.csv --tv NSE:NIFTY261229C26000
  python nse_symbols.py --self-test

Expiry rule used (NSE, from September 2025): index and stock derivatives expire
on Tuesday; the monthly contract on the month's last Tuesday; a holiday moves
expiry to the previous trading day. Holidays are NOT built in: pass NSE's
holiday list for the year (one YYYY-MM-DD per line). Check NSE circulars for
changes. The resolver reads a Kite-style instruments CSV (columns name,
tradingsymbol, instrument_type, expiry, strike, lot_size, exchange); other
brokers' dumps work if you rename columns with --col.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date, timedelta
from decimal import Decimal

TUESDAY = 1


def load_holidays(path: str | None) -> set[date]:
    if not path:
        return set()
    out = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0].strip()
            if line:
                out.add(date.fromisoformat(line))
    return out


def _roll_back(d: date, holidays: set[date]) -> date:
    while d.weekday() >= 5 or d in holidays:
        d -= timedelta(days=1)
    return d


def monthly_expiry(year: int, month: int, holidays: set[date], weekday: int = TUESDAY) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return _roll_back(d, holidays)


def weekly_expiries(year: int, month: int, holidays: set[date], weekday: int = TUESDAY) -> list[date]:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    out = []
    while d.month == month:
        e = _roll_back(d, holidays)
        if e.month == month:   # a roll-back into the previous month belongs to that month's list
            out.append(e)
        d += timedelta(days=7)
    if month < 12:
        nxt = date(year, month + 1, 1)
    else:
        nxt = date(year + 1, 1, 1)
    while nxt.weekday() != weekday:
        nxt += timedelta(days=1)
    e = _roll_back(nxt, holidays)
    if e.month == month and e not in out:   # next month's first expiry rolled back into this month
        out.append(e)
    return out


TV_OPTION = re.compile(r"^(?:NSE:)?([A-Z&-]+?)(\d{2})(\d{2})(\d{2})([CP])(\d+(?:\.\d+)?)$")


def parse_tv_option(sym: str) -> dict:
    m = TV_OPTION.match(sym.strip().upper())
    if not m:
        raise ValueError(f"not a TradingView NSE option ticker: {sym!r} (expected NAME+YYMMDD+C/P+STRIKE)")
    name, yy, mm, dd, cp, strike = m.groups()
    return {"name": name, "expiry": date(2000 + int(yy), int(mm), int(dd)),
            "type": "CE" if cp == "C" else "PE", "strike": Decimal(strike)}


def resolve(rows: list[dict], name: str, typ: str, expiry: date | None = None, strike: Decimal | None = None,
            front: bool = False, today: date | None = None, exchange: str = "NFO", roll_days: int = 0) -> dict:
    cands = []
    for r in rows:
        if r.get("exchange", exchange) != exchange or r["name"].upper() != name.upper() or r["instrument_type"] != typ:
            continue
        try:
            exp = date.fromisoformat(r["expiry"][:10])
        except ValueError:
            continue
        try:
            row_strike = Decimal(r.get("strike") or "0")
        except ArithmeticError:
            continue
        if strike is not None and row_strike != strike:
            continue
        cands.append((exp, r))
    if expiry is not None:
        cands = [c for c in cands if c[0] == expiry]
    elif front:
        cutoff = (today or date.today()) + timedelta(days=roll_days)
        live = [c for c in cands if c[0] >= cutoff]
        nearest = min((c[0] for c in live), default=None)
        cands = [c for c in live if c[0] == nearest]   # still ambiguous if several strikes share it
    if len(cands) != 1:
        raise LookupError(f"{len(cands)} contracts match {name} {typ} expiry={expiry} strike={strike}; "
                          "refusing to guess (refresh the instrument dump?)")
    return cands[0][1]


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text)
    except ArithmeticError:
        raise argparse.ArgumentTypeError(f"invalid number: {text!r}") from None


def load_rows(path: str, renames: list[str]) -> list[dict]:
    mapping = dict(x.split("=", 1) for x in renames)  # ours=theirs
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if mapping:
        rows = [{**r, **{ours: r.get(theirs, "") for ours, theirs in mapping.items()}} for r in rows]
    return rows


def _self_test() -> None:
    h = {date(2026, 12, 29)}
    assert monthly_expiry(2026, 12, set()) == date(2026, 12, 29)
    assert monthly_expiry(2026, 12, h) == date(2026, 12, 28)           # holiday -> previous trading day
    assert monthly_expiry(2026, 11, set()) == date(2026, 11, 24)
    assert monthly_expiry(2027, 6, {date(2027, 6, 29), date(2027, 6, 28)}) == date(2027, 6, 25)  # skips weekend too
    assert weekly_expiries(2026, 12, set()) == [date(2026, 12, d) for d in (1, 8, 15, 22, 29)]
    o = parse_tv_option("NSE:NIFTY261229C26000")
    assert o == {"name": "NIFTY", "expiry": date(2026, 12, 29), "type": "CE", "strike": Decimal("26000")}
    try:
        parse_tv_option("NSE:NIFTY1!")
    except ValueError:
        pass
    else:
        raise AssertionError("continuous symbol parsed as option")
    rows = [
        {"exchange": "NFO", "name": "NIFTY", "tradingsymbol": "NIFTY26NOVFUT", "instrument_type": "FUT", "expiry": "2026-11-24", "strike": "0", "lot_size": "65"},
        {"exchange": "NFO", "name": "NIFTY", "tradingsymbol": "NIFTY26DECFUT", "instrument_type": "FUT", "expiry": "2026-12-29", "strike": "0", "lot_size": "65"},
        {"exchange": "NFO", "name": "NIFTY", "tradingsymbol": "NIFTY26DEC26000CE", "instrument_type": "CE", "expiry": "2026-12-29", "strike": "26000.0", "lot_size": "65"},
    ]
    assert resolve(rows, "NIFTY", "FUT", front=True, today=date(2026, 11, 24))["tradingsymbol"] == "NIFTY26NOVFUT"
    assert resolve(rows, "NIFTY", "FUT", front=True, today=date(2026, 11, 25))["tradingsymbol"] == "NIFTY26DECFUT"
    assert resolve(rows, "NIFTY", "FUT", front=True, today=date(2026, 11, 23), roll_days=2)["tradingsymbol"] == "NIFTY26DECFUT"
    two = rows + [{**rows[2], "tradingsymbol": "NIFTY26DEC26100CE", "strike": "26100"}]
    try:
        resolve(two, "NIFTY", "CE", front=True, today=date(2026, 11, 25))
    except LookupError:
        pass
    else:
        raise AssertionError("--front picked one of several strikes")
    assert weekly_expiries(2026, 9, {date(2026, 9, 1)})[0] == date(2026, 9, 8)        # 1 Sep rolls into August
    assert weekly_expiries(2026, 8, {date(2026, 9, 1)})[-1] == date(2026, 8, 31)      # ...and is listed there
    assert resolve(rows, "NIFTY", "CE", expiry=o["expiry"], strike=o["strike"])["tradingsymbol"] == "NIFTY26DEC26000CE"
    try:
        resolve(rows, "NIFTY", "FUT")
    except LookupError:
        pass
    else:
        raise AssertionError("ambiguous match accepted")
    print("nse_symbols self-test passed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NSE expiries and instrument resolution")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("expiry", help="Weekly and monthly expiry dates for a month")
    e.add_argument("--month", required=True, help="YYYY-MM")
    e.add_argument("--holidays", help="File of NSE trading holidays, one YYYY-MM-DD per line")
    r = sub.add_parser("resolve", help="Find the exact contract in a broker instrument CSV")
    r.add_argument("csv")
    r.add_argument("--tv", help="TradingView option ticker, e.g. NSE:NIFTY261229C26000")
    r.add_argument("--name")
    r.add_argument("--type", choices=["FUT", "CE", "PE"])
    r.add_argument("--expiry", type=date.fromisoformat)
    r.add_argument("--strike", type=_decimal)
    r.add_argument("--front", action="store_true", help="Nearest expiry on or after --today")
    r.add_argument("--today", type=date.fromisoformat)
    r.add_argument("--roll-days", type=int, default=0, help="With --front, skip contracts expiring within N days")
    r.add_argument("--exchange", default="NFO")
    r.add_argument("--col", action="append", default=[], metavar="OURS=THEIRS", help="Rename a column")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    try:
        if a.cmd == "expiry":
            y, m = map(int, a.month.split("-"))
            hol = load_holidays(a.holidays)
            if not hol:
                print("warning: no holiday file given; dates are not holiday-adjusted", file=sys.stderr)
            print("monthly ", monthly_expiry(y, m, hol))
            print("weekly  ", " ".join(str(d) for d in weekly_expiries(y, m, hol)))
            return 0
        if a.cmd == "resolve":
            rows = load_rows(a.csv, a.col)
            if a.tv:
                o = parse_tv_option(a.tv)
                row = resolve(rows, o["name"], o["type"], o["expiry"], o["strike"], exchange=a.exchange)
            else:
                if not (a.name and a.type):
                    print("error: give --tv, or --name and --type", file=sys.stderr)
                    return 2
                row = resolve(rows, a.name, a.type, a.expiry, a.strike, a.front, a.today, a.exchange, a.roll_days)
            for k in ("tradingsymbol", "instrument_token", "expiry", "strike", "lot_size", "tick_size"):
                if k in row:
                    print(f"{k:16}{row[k]}")
            return 0
    except (ValueError, LookupError, OSError, ArithmeticError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
