"""Configuration. Defaults are deliberately conservative: demo env, dry-run."""
import os
from dataclasses import dataclass

URLS = {
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
    "live": "https://api.elections.kalshi.com/trade-api/v2",
}


@dataclass(frozen=True)
class Config:
    env: str = "demo"                 # "demo" | "live"
    api_key_id: str = ""
    private_key_path: str = ""
    dry_run: bool = True              # log intended orders, don't send
    # --- risk limits (all hard caps, enforced in risk.py) ---
    max_contracts_per_order: int = 10
    max_position_per_market: int = 25     # contracts, either side
    max_exposure_usd: float = 50.0        # total $ at risk across open positions+orders
    max_daily_loss_usd: float = 20.0      # halt trading once breached
    min_edge: float = 0.05                # required (fair - price) in probability units
    kelly_fraction: float = 0.25          # fractional Kelly sizing

    @property
    def base_url(self) -> str:
        return URLS[self.env]

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ.get("KALSHI_ENV", "demo")
        if env not in URLS:
            raise ValueError(f"KALSHI_ENV must be one of {list(URLS)}")
        return cls(
            env=env,
            api_key_id=os.environ.get("KALSHI_API_KEY_ID", ""),
            private_key_path=os.environ.get("KALSHI_PRIVATE_KEY_PATH", ""),
            dry_run=os.environ.get("KALSHI_DRY_RUN", "1") != "0",
        )
