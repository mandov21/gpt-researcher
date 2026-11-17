"""Daily-high-temperature signal for Kalshi KXHIGH* markets.

Model: actual high ~ Normal(forecast_high + bias, sigma), rounded to whole °F.
Forecast = max of NWS hourly forecast over the local calendar day. For today's
market we also condition on the running max already observed (T >= observed max).

CAVEAT: Kalshi settles on The Weather Company's reading for the station
(CLINYC = Central Park), not NWS. sigma/bias are priors — calibrate them from
the log written by log_forecast() once you have a few weeks of settled days.
"""
import csv
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

UA = {"User-Agent": "kalshi-weather-bot (personal research)"}

# series -> (NWS gridpoint, observation station, timezone)
STATIONS = {
    "KXHIGHNY": ("OKX/34,45", "KNYC", "America/New_York"),
}
MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def parse_event_date(event_ticker: str) -> date:
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})$", event_ticker)
    return date(2000 + int(m[1]), MONTHS[m[2]], int(m[3]))


def prob_yes(market: dict, mu: float, sigma: float, floor_obs: float | None = None) -> float:
    """P(YES) for a KXHIGH market given high ~ N(mu, sigma), integer-rounded."""
    st = market["strike_type"]
    lo = market.get("floor_strike")
    hi = market.get("cap_strike")
    cdf = lambda x: norm_cdf((x - mu) / sigma)           # P(T_cont <= x)
    # integer reading k  <=>  continuous value in [k-0.5, k+0.5)
    if st == "between":      # inclusive of both integers, e.g. 55-56
        a, b = lo - 0.5, hi + 0.5
    elif st == "less":       # "54 or below" has cap_strike 55 (strictly below)
        a, b = -math.inf, hi - 0.5
    elif st == "greater":    # "63 or above" has floor_strike 62 (strictly above)
        a, b = lo + 0.5, math.inf
    else:
        raise ValueError(f"unsupported strike_type {st}")
    F = lambda x: 0.0 if x == -math.inf else 1.0 if x == math.inf else cdf(x)
    if floor_obs is not None:                              # condition on T >= observed max
        base = F(floor_obs - 0.5)
        denom = 1 - base
        if denom < 1e-9:
            return 1.0 if (a <= floor_obs <= b) else 0.0
        return max(0.0, F(b) - max(F(a), base)) / denom
    return F(b) - F(a)


class WeatherSignal:
    def __init__(self, sigma_next_day: float = 2.5, sigma_same_day: float = 1.8,
                 bias: float = 0.0, log_path: str | Path | None = "forecast_log.csv"):
        self.sigma_next, self.sigma_same, self.bias = sigma_next_day, sigma_same_day, bias
        self.log_path = Path(log_path) if log_path else None
        self._cache: dict[tuple, tuple[float, float | None]] = {}

    # -- data ---------------------------------------------------------------
    def _get(self, url: str) -> dict:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        return r.json()

    def forecast_high(self, series: str, day: date) -> float | None:
        grid, _, tz = STATIONS[series]
        zone = ZoneInfo(tz)
        periods = self._get(f"https://api.weather.gov/gridpoints/{grid}/forecast/hourly")["properties"]["periods"]
        temps = [p["temperature"] for p in periods
                 if datetime.fromisoformat(p["startTime"]).astimezone(zone).date() == day]
        # Partial day coverage (e.g. forecast starts mid-day) is fine for "today":
        # observed max covers the earlier hours.
        return float(max(temps)) if temps else None

    def observed_max(self, series: str, day: date) -> float | None:
        _, station, tz = STATIONS[series]
        zone = ZoneInfo(tz)
        start = datetime.combine(day, datetime.min.time(), zone).astimezone(timezone.utc)
        url = (f"https://api.weather.gov/stations/{station}/observations"
               f"?start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        vals = []
        for f in self._get(url).get("features", []):
            c = f["properties"].get("temperature", {}).get("value")
            if c is not None:
                vals.append(c * 9 / 5 + 32)
        return round(max(vals)) if vals else None

    # -- Signal interface --------------------------------------------------
    def fair_probability(self, market: dict) -> float | None:
        series = market["event_ticker"].split("-")[0]
        if series not in STATIONS:
            return None
        day = parse_event_date(market["event_ticker"])
        tz = ZoneInfo(STATIONS[series][2])
        today = datetime.now(tz).date()
        if day < today:
            return None
        key = (series, day, datetime.now(timezone.utc).strftime("%Y%m%d%H") )  # hourly cache
        if key not in self._cache:
            fh = self.forecast_high(series, day)
            ob = self.observed_max(series, day) if day == today else None
            self._cache[key] = (fh, ob)
            if fh is not None:
                self.log_forecast(series, day, fh, ob)
        fh, ob = self._cache[key]
        if fh is None and ob is None:
            return None
        now = datetime.now(tz)
        if day == today:
            if now.hour >= 16:      # daily high is (almost) set; the market already knows it — abstain
                return None
            hrs_left = max(0.0, 16 - now.hour)
            sigma = max(0.8, min(self.sigma_same, 0.8 + 0.12 * hrs_left))
        else:
            sigma = self.sigma_next
        mu = (max(fh, ob) if fh is not None and ob is not None else (fh if fh is not None else ob)) + self.bias
        return prob_yes(market, mu, sigma, floor_obs=ob)

    def log_forecast(self, series: str, day: date, fh: float, ob: float | None) -> None:
        if not self.log_path:
            return
        new = not self.log_path.exists()
        with self.log_path.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["logged_utc", "series", "target_date", "forecast_high", "observed_max_so_far"])
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), series, day, fh, ob])
