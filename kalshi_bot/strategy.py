"""Signal-driven strategy (prices in dollars, as returned by the Kalshi API).

A Signal returns your estimated P(YES) for a market. We buy YES when
fair - yes_ask - fee >= min_edge, or NO when (1-fair) - no_ask - fee >= min_edge,
sizing with fractional Kelly.
"""
from dataclasses import dataclass
from typing import Protocol


class Signal(Protocol):
    def fair_probability(self, market: dict) -> float | None:
        """P(YES) in [0,1], or None to abstain."""


@dataclass
class Order:
    ticker: str
    side: str          # "yes" | "no"
    count: int
    price: float       # dollars paid per contract on `side`
    edge: float        # net of fees


def taker_fee(price: float) -> float:
    """Approximate Kalshi taker fee per contract: 0.07 * P * (1-P)."""
    return 0.07 * price * (1 - price)


def kelly_contracts(p: float, price: float, bankroll_usd: float, fraction: float) -> int:
    """Binary contract paying $1 bought at `price`. f* = (p - price) / (1 - price)."""
    if price <= 0 or price >= 1 or p <= price:
        return 0
    return int(bankroll_usd * (p - price) / (1 - price) * fraction // price)


def asks(market: dict) -> tuple[float | None, float | None]:
    def f(k):
        v = market.get(k)
        return float(v) if v not in (None, "") else None
    ya, na = f("yes_ask_dollars"), f("no_ask_dollars")
    # an ask of 1.00 (or 0.00) means nothing is offered at a tradable price
    return (ya if ya and 0.01 <= ya <= 0.99 else None, na if na and 0.01 <= na <= 0.99 else None)


MIN_PRICE, MAX_PRICE = 0.05, 0.95   # no penny lottery tickets / near-certainties
MAX_GAP = 0.20                      # |fair - market mid| beyond this => likely OUR error, abstain


def decide(market: dict, signal: Signal, bankroll_usd: float,
           min_edge: float, kelly_fraction: float) -> Order | None:
    fair = signal.fair_probability(market)
    if fair is None:
        return None
    ya, na = asks(market)
    if ya is not None and na is not None:
        mid = (ya + (1 - na)) / 2
    else:
        mid = ya if ya is not None else (1 - na if na is not None else None)
    if mid is not None and abs(fair - mid) > MAX_GAP:
        return None
    ya = ya if ya is not None and MIN_PRICE <= ya <= MAX_PRICE else None
    na = na if na is not None and MIN_PRICE <= na <= MAX_PRICE else None
    cands = []
    if ya:
        cands.append(("yes", ya, fair - ya - taker_fee(ya), fair))
    if na:
        cands.append(("no", na, (1 - fair) - na - taker_fee(na), 1 - fair))
    cands = [c for c in cands if c[2] >= min_edge]
    if not cands:
        return None
    side, ask, edge, p_win = max(cands, key=lambda c: c[2])
    n = kelly_contracts(p_win, ask + taker_fee(ask), bankroll_usd, kelly_fraction)
    return Order(market["ticker"], side, n, ask, edge) if n > 0 else None
