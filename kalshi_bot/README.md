# kalshi_bot

Signal-driven Kalshi trader. Defaults: **demo environment, dry-run**.

1. Create API keys at demo.kalshi.co (account settings → API), save the private key PEM.
2. `pip install -r kalshi_bot/requirements.txt`
3. `export KALSHI_ENV=demo KALSHI_API_KEY_ID=... KALSHI_PRIVATE_KEY_PATH=/path/key.pem`
4. `python -m kalshi_bot.bot --series <SERIES_TICKER> --once`  (logs "WOULD BUY"; set `KALSHI_DRY_RUN=0` to place demo orders)
5. Implement a `Signal` in `signals.py` (returns P(YES) per market).

Live: `KALSHI_ENV=live KALSHI_DRY_RUN=0` plus `--confirm-live`. Risk limits live in `config.py`
and are enforced in `risk.py`. Tests: `pytest kalshi_bot`.

Not yet implemented: fill tracking (fills are assumed), WebSocket feed, backtesting, PnL settlement.
