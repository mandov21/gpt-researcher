"""Example signals. Replace with your own edge — this one is a placeholder."""


class FixedSignal:
    """Hard-coded probabilities by ticker; useful for tests and plumbing checks."""
    def __init__(self, probs: dict[str, float]):
        self.probs = probs

    def fair_probability(self, market: dict) -> float | None:
        return self.probs.get(market["ticker"])
