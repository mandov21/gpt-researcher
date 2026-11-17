"""Main loop. Usage:  python -m kalshi_bot.bot --series KXHIGHNY --once

Live trading requires KALSHI_ENV=live, KALSHI_DRY_RUN=0 AND --confirm-live.
"""
import argparse
import logging
import time
import uuid

from .client import KalshiClient
from .config import Config
from .risk import RiskManager
from .signals import FixedSignal
from .strategy import decide

log = logging.getLogger("kalshi_bot")


def run_once(client: KalshiClient, cfg: Config, risk: RiskManager, signal, markets: list[dict]) -> None:
    bankroll = client.get_balance_cents() / 100 if client._key else 100.0
    for m in markets:
        if m.get("status") not in ("open", "active"):
            continue
        ob = client.get_orderbook(m["ticker"])
        o = decide(m, ob, signal, bankroll, cfg.min_edge, cfg.kelly_fraction)
        if not o:
            continue
        n, why = risk.check(o.ticker, o.side, o.count, o.price_cents)
        if n == 0:
            log.info("skip %s: %s", o.ticker, why)
            continue
        log.info("%s %s x%d @%dc edge=%.3f%s", "WOULD BUY" if cfg.dry_run else "BUY",
                 o.ticker, n, o.price_cents, o.edge, o.side.upper())
        if cfg.dry_run:
            continue
        client.place_limit_order(o.ticker, o.side, n, o.price_cents,
                                 client_order_id=str(uuid.uuid4()))
        risk.record_fill(o.ticker, o.side, n, o.price_cents)  # conservative: assume filled


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True, help="series ticker to scan")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--confirm-live", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    cfg = Config.from_env()
    if cfg.env == "live" and not cfg.dry_run and not args.confirm_live:
        raise SystemExit("Refusing live trading without --confirm-live")
    log.info("env=%s dry_run=%s", cfg.env, cfg.dry_run)

    client = KalshiClient(cfg)
    risk = RiskManager(cfg)
    signal = FixedSignal({})  # TODO: replace with a real signal
    while True:
        markets = client.list_markets(series_ticker=args.series, status="open")
        run_once(client, cfg, risk, signal, markets)
        if args.once or risk.halted:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
