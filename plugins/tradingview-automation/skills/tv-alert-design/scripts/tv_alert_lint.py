#!/usr/bin/env python3
"""Lint a TradingView alert message before it reaches your webhook.

Part of claude-tradingview-automation-skills by Viprasol Tech Private Limited.

TradingView replaces {{placeholders}} as plain text, then POSTs the result. A
template that looks like JSON can still render as invalid JSON: an unquoted
{{ticker}}, a plot value that renders as NaN, a trailing comma. This script
renders the template with realistic sample values and reports every problem.

  python tv_alert_lint.py alert.txt
  python tv_alert_lint.py --message '{"secret":"...","symbol":"{{ticker}}","action":"{{strategy.order.action}}"}'
  python tv_alert_lint.py --self-test

Exit code 0 = clean, 1 = errors (the webhook would reject or misread it).
"""

from __future__ import annotations

import argparse
import json
import re
import sys

PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

# Sample values, chosen so a quoting mistake breaks the JSON parse.
STRING_VARS = {
    "ticker": "RELIANCE", "exchange": "NSE", "interval": "15", "time": "2026-11-24T09:15:00Z",
    "timenow": "2026-11-24T09:15:03Z", "syminfo.currency": "INR", "syminfo.basecurrency": "BTC",
    "syminfo.ticker": "RELIANCE", "syminfo.tickerid": "NSE:RELIANCE", "syminfo.root": "RELIANCE",
    "strategy.order.action": "buy", "strategy.order.id": "Long Entry", "strategy.order.comment": "EMA cross",
    "strategy.market_position": "long", "strategy.prev_market_position": "flat",
    "description": "Reliance Industries",
}
NUMERIC_VARS = {
    "open": "2875.5", "high": "2890", "low": "2870.25", "close": "2884.1", "volume": "1532400",
    "strategy.order.contracts": "10", "strategy.order.price": "2884.1",
    "strategy.market_position_size": "10", "strategy.prev_market_position_size": "0",
    "strategy.position_size": "10",
}
RAW_VARS = {"strategy.order.alert_message"}  # whatever text the Pine script passed
MIN_SECRET = 16  # same minimum as tv_webhook_server.py
WEAK = {"change-me", "secret", "password", "your-secret-here"}
PLOT = re.compile(r"^plot(_\d+|\(\s*\"[^\"]+\"\s*\))$")


def classify(name: str) -> str:
    if name in STRING_VARS:
        return "string"
    if name in NUMERIC_VARS or PLOT.match(name):
        return "number"
    if name in RAW_VARS:
        return "raw"
    return "unknown"


def _quoted(template: str, start: int, end: int) -> bool:
    """True if the placeholder sits inside a JSON string literal."""
    in_str = False
    i = 0
    while i < start:
        c = template[i]
        if c == "\\" and in_str:
            i += 2
            continue
        if c == '"':
            in_str = not in_str
        i += 1
    return in_str


def render(template: str, nan_plots: bool = False) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        kind = classify(name)
        if kind == "string":
            return STRING_VARS[name]
        if kind == "number":
            return "NaN" if nan_plots and name.startswith("plot") else NUMERIC_VARS.get(name, "1.5")
        return m.group(0)  # TradingView leaves unknown placeholders as literal text
    return PLACEHOLDER.sub(sub, template)


def lint(template: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    stripped = template.strip()
    if PLACEHOLDER.fullmatch(stripped) and PLACEHOLDER.fullmatch(stripped).group(1) in RAW_VARS:
        warnings.append("the message is only {{strategy.order.alert_message}}: lint the alert_message "
                        "strings in your Pine script instead (pass each one to this tool)")
        return errors, warnings
    for m in PLACEHOLDER.finditer(template):
        name, kind = m.group(1), classify(m.group(1))
        quoted = _quoted(template, m.start(), m.end())
        if kind == "unknown":
            warnings.append(f"{{{{{name}}}}} is not a known placeholder; TradingView will send it literally")
        elif re.fullmatch(r"plot_(\d+)", name) and int(name[5:]) > 19:
            errors.append(f"{{{{{name}}}}}: only plot_0 to plot_19 are available")
        elif kind == "string" and not quoted:
            errors.append(f"{{{{{name}}}}} renders as text but is not inside quotes -> invalid JSON")
        elif kind == "number" and quoted and name.startswith("plot"):
            warnings.append(f"{{{{{name}}}}} arrives as the string \"NaN\" on bars where the plot is na; "
                            "wrap the plot in nz() and check the value is finite on the server")
        elif kind == "number" and quoted:
            warnings.append(f"{{{{{name}}}}} is quoted, so it arrives as a string; parse it as Decimal on the server")
        elif kind == "number" and name.startswith("plot"):
            warnings.append(f"{{{{{name}}}}} renders as NaN on bars where the plot is na, which is invalid JSON; "
                            "wrap the plot in nz() in Pine (quoting does not help)")
        elif kind == "raw" and quoted:
            warnings.append("{{strategy.order.alert_message}} inside quotes breaks if the Pine text contains "
                            "a double quote; keep alert_message free of quotes")
    if "{{" in PLACEHOLDER.sub("", template):
        errors.append("unbalanced {{ ... }} braces")
    rendered = render(template)
    if not stripped.startswith("{"):
        warnings.append("message is not a JSON object; send JSON so the receiver can validate fields")
        return errors, warnings
    try:
        data = json.loads(rendered, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        errors.append(f"rendered message is not valid JSON: {exc.msg} at char {exc.pos}: "
                      f"...{rendered[max(0, exc.pos - 25):exc.pos + 15]!r}...")
        return errors, warnings
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings
    if not isinstance(data, dict):
        errors.append("JSON must be an object, not a list or value")
        return errors, warnings
    for alt, key in (("passphrase", "secret"), ("token", "secret"), ("ticker", "symbol"),
                     ("side", "action"), ("signal", "action"), ("time", "timenow")):
        if alt in data and key not in data:
            errors.append(f"the receiver expects '{key}', not '{alt}'")
    secret = data.get("secret")
    if "secret" not in data:
        errors.append("no secret field: anyone who finds the URL can trade on your account")
    elif not isinstance(secret, str) or len(secret.strip()) < MIN_SECRET or secret.strip().lower() in WEAK:
        errors.append(f"secret must be a random string of at least {MIN_SECRET} characters")
    for key in ("symbol", "action"):
        if key not in data:
            errors.append(f"no {key} field; the receiver rejects the alert")
    if "timenow" not in data:
        errors.append('no "timenow":"{{timenow}}" field; the receiver needs it to reject stale or replayed alerts')
    return errors, warnings


def _reject_constant(name: str):
    raise ValueError(f"rendered message contains {name}, which is not valid JSON")


def _self_test() -> None:
    sec = "x9-long-random-secret"
    good = ('{"secret":"%s","symbol":"{{exchange}}:{{ticker}}","action":"{{strategy.order.action}}",'
            '"qty":{{strategy.order.contracts}},"price":{{close}},"timenow":"{{timenow}}"}') % sec

    def msg(extra: str = "", **kw) -> str:
        base = {"secret": sec, "symbol": "{{ticker}}", "action": "buy", "timenow": "{{timenow}}", **kw}
        return json.dumps(base)[:-1] + extra + "}"

    e, w = lint(good)
    assert not e and not w, (e, w)
    e, _ = lint(msg().replace('"{{ticker}}"', "{{ticker}}"))
    assert any("not inside quotes" in x for x in e), e
    e, _ = lint('{"symbol":"{{ticker}}","action":"buy","timenow":"{{timenow}}"}')
    assert any("no secret" in x for x in e), e
    e, _ = lint(msg(","))
    assert any("not valid JSON" in x for x in e), e
    _, w = lint(msg(',"sl":{{plot_0}}'))
    assert any("nz()" in x for x in w), w
    _, w = lint(msg(',"sl":"{{plot_0}}"'))
    assert any("NaN" in x for x in w), w
    _, w = lint(msg(x="{{tickr}}"))
    assert any("not a known placeholder" in x for x in w), w
    _, w = lint("{{strategy.order.alert_message}}")
    assert any("alert_message" in x for x in w), w
    _, w = lint("BUY {{ticker}} now")
    assert any("not a JSON object" in x for x in w), w
    assert _quoted('{"a":"x\\"{{ticker}}"}', 8, 18)
    for bad in ("", "change-me", "short", "secret"):
        e, _ = lint(msg(secret=bad))
        assert any("at least" in x for x in e), (bad, e)
    e, _ = lint('{"passphrase":"x9-long-random-secret","ticker":"{{ticker}}","side":"buy","timenow":"{{timenow}}"}')
    assert sum("the receiver expects" in x for x in e) == 3, e
    e, _ = lint('{"secret":"%s","symbol":"{{ticker}}","action":"buy"}' % sec)
    assert any("timenow" in x for x in e), e
    e, _ = lint(msg(',"x":NaN'))
    assert any("NaN" in x for x in e), e
    print("tv_alert_lint self-test passed")



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint a TradingView alert message template")
    ap.add_argument("file", nargs="?", help="File containing the alert message")
    ap.add_argument("--message", help="Template text instead of a file")
    ap.add_argument("--show", action="store_true", help="Print the rendered sample message")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if a.message is None and a.file is None:
        ap.print_help()
        return 2
    template = a.message if a.message is not None else open(a.file, encoding="utf-8").read()
    errors, warnings = lint(template)
    if a.show:
        print("rendered:", render(template))
    for x in errors:
        print("ERROR  ", x)
    for x in warnings:
        print("WARNING", x)
    if not errors and not warnings:
        print("OK: renders as valid JSON with a secret, symbol and action")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
