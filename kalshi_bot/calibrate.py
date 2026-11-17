"""Settle logged data against Kalshi results and fit the weather model.

    python -m kalshi_bot.calibrate [--series KXHIGHNY]

Reads forecast_log.csv + paper_trades.csv (written by the bot), pulls settled
markets from Kalshi's public API, and prints:
  * forecast error stats (actual high - forecast high): bias, sigma, n
  * paper-trading P&L after fees, using the entry prices the bot logged
Needs ~2+ weeks of daily runs before the numbers mean anything.
"""
import argparse
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

from .client import KalshiClient
from .config import Config
from .strategy import taker_fee
from .weather import parse_event_date


def actual_high(markets: list[dict]) -> float | None:
    """Midpoint of the winning bin (exact for 2-degree bins; edge bins give their boundary)."""
    for m in markets:
        if m.get("result") == "yes":
            lo, hi, t = m.get("floor_strike"), m.get("cap_strike"), m["strike_type"]
            if t == "between":
                return (lo + hi) / 2
            return float(hi - 1) if t == "less" else float(lo + 1)
    return None


def settled_by_event(client: KalshiClient, series: str) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for m in client.list_markets(series_ticker=series, status="settled"):
        out[m["event_ticker"]].append(m)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="KXHIGHNY")
    ap.add_argument("--forecasts", default="forecast_log.csv")
    ap.add_argument("--paper", default="paper_trades.csv")
    a = ap.parse_args()
    client = KalshiClient(Config.from_env())
    events = settled_by_event(client, a.series)
    results = {m["ticker"]: m["result"] for ms in events.values() for m in ms}

    # forecast error: use the LAST forecast logged for each target date made the day before (lead ~1 day)
    errs = []
    if Path(a.forecasts).exists():
        last = {}
        for r in csv.DictReader(open(a.forecasts)):
            if r["observed_max_so_far"] in ("", "None"):          # next-day style forecasts only
                last[r["target_date"]] = float(r["forecast_high"])
        for ev, ms in events.items():
            d, ah = str(parse_event_date(ev)), actual_high(ms)
            if d in last and ah is not None:
                errs.append(ah - last[d])
    if len(errs) >= 5:
        print(f"forecast error (actual - forecast): n={len(errs)} bias={st.mean(errs):+.2f}F "
              f"sigma={st.stdev(errs):.2f}F  -> set WeatherSignal(bias=..., sigma_next_day=...)")
        print("note: actual high is the bin midpoint, so sigma is inflated by ~0.6F of binning noise")
    else:
        print(f"forecast error: only {len(errs)} settled days with logs; need >=5 (ideally 14+)")

    # paper P&L
    pnl, n, wins = 0.0, 0, 0
    if Path(a.paper).exists():
        for r in csv.DictReader(open(a.paper)):
            res = results.get(r["ticker"])
            if not res:
                continue
            c, p = int(r["count"]), float(r["price"])
            won = res == r["side"]
            pnl += c * ((1 - p) if won else -p) - c * taker_fee(p)
            n += 1; wins += won
    print(f"paper trades settled: {n}, wins: {wins}, P&L after est. fees: ${pnl:+.2f}")
    print("Go live only if P&L is positive over many trades (100+), not a handful.")


if __name__ == "__main__":
    main()
