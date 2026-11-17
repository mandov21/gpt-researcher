"""Main loop. Usage:  python -m kalshi_bot.bot --series KXHIGHNY --once

Default is dry-run on the demo env. Live trading requires KALSHI_ENV=live,
KALSHI_DRY_RUN=0 AND --confirm-live.
"""
import argparse
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
import time
import uuid

from .client import KalshiClient
from .config import Config
from .risk import RiskManager
from .strategy import decide
from .weather import WeatherSignal

log = logging.getLogger("kalshi_bot")
PAPER = Path("paper_trades.csv")


def log_paper(o, n: int, fair: float) -> None:
    new = not PAPER.exists()
    with PAPER.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts_utc", "ticker", "side", "count", "price", "fair", "net_edge"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), o.ticker, o.side, n,
                    o.price, round(fair, 4), round(o.edge, 4)])


def run_once(client: KalshiClient, cfg: Config, risk: RiskManager, signal, markets: list[dict],
             bankroll: float) -> None:
    for m in markets:
        if m.get("status") not in ("open", "active"):
            continue
        try:
            o = decide(m, signal, bankroll, cfg.min_edge, cfg.kelly_fraction)
        except Exception as e:  # data source hiccup: skip, never trade blind
            log.warning("signal error on %s: %s", m["ticker"], e)
            continue
        if not o:
            continue
        n, why = risk.check(o.ticker, o.side, o.count, o.price)
        if n == 0:
            log.info("skip %s: %s", o.ticker, why)
            continue
        log.info("%s %s %s x%d @ $%.2f net_edge=%.3f", "WOULD BUY" if cfg.dry_run else "BUY",
                 o.ticker, o.side.upper(), n, o.price, o.edge)
        if cfg.dry_run:
            log_paper(o, n, signal.fair_probability(m))
            continue
        resp = client.place_order(o.ticker, o.side, n, o.price, client_order_id=str(uuid.uuid4()))
        filled = int(float(resp.get("fill_count", 0)))
        if filled:
            risk.record_fill(o.ticker, o.side, filled, float(resp.get("average_fill_price") or o.price))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="KXHIGHNY")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=600)
    ap.add_argument("--confirm-live", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    cfg = Config.from_env()
    if cfg.env == "live" and not cfg.dry_run and not args.confirm_live:
        raise SystemExit("Refusing live trading without --confirm-live")
    log.info("env=%s dry_run=%s", cfg.env, cfg.dry_run)

    client = KalshiClient(cfg)
    risk = RiskManager(cfg)
    signal = WeatherSignal()
    while True:
        bankroll = client.get_balance_usd() if client._key else float(cfg.max_exposure_usd)
        markets = client.list_markets(series_ticker=args.series, status="open")
        run_once(client, cfg, risk, signal, markets, min(bankroll, cfg.max_exposure_usd))
        if args.once or risk.halted:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
