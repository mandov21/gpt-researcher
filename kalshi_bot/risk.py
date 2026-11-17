"""Hard risk limits. Every order must pass through RiskManager.check()."""
from dataclasses import dataclass, field

from .config import Config


@dataclass
class RiskManager:
    cfg: Config
    positions: dict[str, int] = field(default_factory=dict)   # ticker -> net contracts (+yes / -no)
    exposure_usd: float = 0.0
    realized_pnl_usd: float = 0.0
    halted: bool = False

    def record_fill(self, ticker: str, side: str, count: int, price: float) -> None:
        self.positions[ticker] = self.positions.get(ticker, 0) + (count if side == "yes" else -count)
        self.exposure_usd += count * price

    def record_pnl(self, delta_usd: float) -> None:
        self.realized_pnl_usd += delta_usd
        if self.realized_pnl_usd <= -self.cfg.max_daily_loss_usd:
            self.halted = True

    def check(self, ticker: str, side: str, count: int, price: float) -> tuple[int, str]:
        """Return (allowed_count, reason). allowed_count may be reduced; 0 means reject."""
        if self.halted:
            return 0, "halted: daily loss limit hit"
        c = min(count, self.cfg.max_contracts_per_order)
        signed = 1 if side == "yes" else -1
        cur = self.positions.get(ticker, 0)
        room = self.cfg.max_position_per_market - max(0, signed * cur)
        c = min(c, room)
        cost = price
        budget = self.cfg.max_exposure_usd - self.exposure_usd
        c = min(c, int(budget // cost)) if cost > 0 else 0
        if c <= 0:
            return 0, "position/exposure limit"
        return c, "ok"
