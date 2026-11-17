"""Signal-driven strategy.

Plug in a Signal that returns your estimated probability the market resolves YES.
The strategy buys YES when fair - ask >= min_edge, NO when (1-fair) - no_ask >= min_edge,
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
    price_cents: int
    edge: float


def kelly_contracts(p: float, price: float, bankroll_usd: float, fraction: float) -> int:
    """Binary contract paying $1 bought at `price`. f* = (p - price) / (1 - price)."""
    if price <= 0 or price >= 1 or p <= price:
        return 0
    f = (p - price) / (1 - price)
    return int(bankroll_usd * f * fraction // price)


def best_asks(orderbook: dict) -> tuple[int | None, int | None]:
    """Kalshi books list resting *bids* per side: yes=[[price,qty],...], no=[...].
    Ask to buy YES = 100 - best NO bid; ask to buy NO = 100 - best YES bid."""
    yes_bids = orderbook.get("yes") or []
    no_bids = orderbook.get("no") or []
    yes_ask = 100 - max(p for p, _ in no_bids) if no_bids else None
    no_ask = 100 - max(p for p, _ in yes_bids) if yes_bids else None
    return yes_ask, no_ask


def decide(market: dict, orderbook: dict, signal: Signal, bankroll_usd: float,
           min_edge: float, kelly_fraction: float) -> Order | None:
    fair = signal.fair_probability(market)
    if fair is None:
        return None
    yes_ask, no_ask = best_asks(orderbook)
    candidates = []
    if yes_ask:
        candidates.append(("yes", yes_ask, fair - yes_ask / 100))
    if no_ask:
        candidates.append(("no", no_ask, (1 - fair) - no_ask / 100))
    candidates = [c for c in candidates if c[2] >= min_edge and 1 <= c[1] <= 99]
    if not candidates:
        return None
    side, ask, edge = max(candidates, key=lambda c: c[2])
    p_win = fair if side == "yes" else 1 - fair
    n = kelly_contracts(p_win, ask / 100, bankroll_usd, kelly_fraction)
    return Order(market["ticker"], side, n, ask, edge) if n > 0 else None
