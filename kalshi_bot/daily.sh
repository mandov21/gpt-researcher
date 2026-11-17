#!/usr/bin/env bash
# Daily dry-run: log forecasts + paper trades, settle old ones, commit data. Never places orders.
set -euo pipefail
cd "$(dirname "$0")/data"
export PYTHONPATH="$(cd ../.. && pwd)" KALSHI_ENV=live KALSHI_DRY_RUN=1
python3 -m kalshi_bot.bot --series KXHIGHNY --once
python3 -m kalshi_bot.calibrate | tee calibration_latest.txt
