import math
from datetime import date

from kalshi_bot.weather import parse_event_date, prob_yes

def mk(st, lo=None, hi=None): return {"strike_type": st, "floor_strike": lo, "cap_strike": hi}


def test_parse_date():
    assert parse_event_date("KXHIGHNY-26NOV17") == date(2026, 11, 17)


def test_bins_sum_to_one():
    mu, s = 57.3, 2.5
    bins = [mk("less", None, 55)] + [mk("between", a, a + 1) for a in range(55, 63, 2)] + [mk("greater", 62)]
    # 54-or-below, 55-56, 57-58, 59-60, 61-62, 63-or-above
    assert abs(sum(prob_yes(b, mu, s) for b in bins) - 1) < 1e-9


def test_peak_bin_is_forecast_bin():
    ps = {a: prob_yes(mk("between", a, a + 1), 57.5, 2.0) for a in (53, 55, 57, 59, 61)}
    assert max(ps, key=ps.get) == 57


def test_observed_floor_zeroes_lower_bins():
    assert prob_yes(mk("between", 55, 56), 58, 1.5, floor_obs=58) == 0.0
    assert prob_yes(mk("less", None, 55), 58, 1.5, floor_obs=58) == 0.0
    assert abs(prob_yes(mk("greater", 62), 58, 1.5, floor_obs=58)
               + prob_yes(mk("between", 59, 62), 58, 1.5, floor_obs=58)
               + prob_yes(mk("between", 58, 58), 58, 1.5, floor_obs=58) - 1) < 1e-9
