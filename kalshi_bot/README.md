# kalshi_bot

Signal-driven Kalshi trader. Defaults: **demo environment, dry-run**.

1. Create API keys at demo.kalshi.co (account settings → API), save the private key PEM.
2. `pip install -r kalshi_bot/requirements.txt`
3. `export KALSHI_ENV=demo KALSHI_API_KEY_ID=... KALSHI_PRIVATE_KEY_PATH=/path/key.pem`
4. `python -m kalshi_bot.bot --series <SERIES_TICKER> --once`  (logs "WOULD BUY"; set `KALSHI_DRY_RUN=0` to place demo orders)
5. Signal: `weather.py` (NWS forecast -> bin probabilities for KXHIGHNY). It logs forecasts to `forecast_log.csv` for calibration.

Live: `KALSHI_ENV=live KALSHI_DRY_RUN=0` plus `--confirm-live`. Risk limits live in `config.py`
and are enforced in `risk.py`. Tests: `pytest kalshi_bot`.

Guardrails: skips prices <5c or >95c, abstains when the model differs from the market by >20 points (usually model error), abstains on same-day markets after 4pm local.
Calibrate `sigma`/`bias` in `WeatherSignal` from settled days before trusting any edge.

Daily dry-run: `kalshi_bot/daily.sh` (writes CSVs + calibration_latest.txt into `kalshi_bot/data/`; never places orders).

Not yet implemented: fill tracking (fills are assumed), WebSocket feed, backtesting, PnL settlement.
