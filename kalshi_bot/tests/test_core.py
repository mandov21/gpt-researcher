import base64
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi_bot.config import Config
from kalshi_bot.risk import RiskManager
from kalshi_bot.strategy import decide, kelly_contracts, taker_fee


class Fixed:
    def __init__(self, p): self.p = p
    def fair_probability(self, m): return self.p


MKT = {"ticker": "T", "yes_ask_dollars": "0.4500", "no_ask_dollars": "0.5600"}


def test_buys_yes_with_edge():
    o = decide(MKT, Fixed(0.62), 10, 0.07, 0.25)
    assert o and o.side == "yes" and o.price == 0.45 and o.count > 0 and o.edge > 0.07


def test_buys_no_with_edge():
    o = decide(MKT, Fixed(0.30), 10, 0.07, 0.25)
    assert o and o.side == "no"


def test_edge_must_beat_fees():
    assert decide(MKT, Fixed(0.50), 10, 0.07, 0.25) is None


def test_untradable_ask_ignored():
    m = {"ticker": "T", "yes_ask_dollars": "1.0000", "no_ask_dollars": "1.0000"}
    assert decide(m, Fixed(0.99), 10, 0.07, 0.25) is None


def test_abstain():
    class N:
        def fair_probability(self, m): return None
    assert decide(MKT, N(), 10, 0.07, 0.25) is None


def test_kelly_zero_when_no_edge():
    assert kelly_contracts(0.4, 0.5, 100, 0.25) == 0


def test_fee_shape():
    assert abs(taker_fee(0.5) - 0.0175) < 1e-9


def test_risk_caps_and_halt():
    cfg = Config(max_contracts_per_order=5, max_position_per_market=7, max_exposure_usd=10, max_daily_loss_usd=5)
    r = RiskManager(cfg)
    assert r.check("T", "yes", 100, 0.5)[0] == 5
    r.record_fill("T", "yes", 5, 0.5)
    assert r.check("T", "yes", 100, 0.5)[0] == 2
    r.record_pnl(-5)
    assert r.check("T", "yes", 1, 0.5)[0] == 0 and r.halted


def test_signature_roundtrip(tmp_path):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from kalshi_bot.client import KalshiClient
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    p = tmp_path / "k.pem"
    p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    c = KalshiClient(Config(api_key_id="id", private_key_path=str(p)))
    sig = base64.b64decode(c._sign("123", "GET", "/trade-api/v2/portfolio/balance"))
    key.public_key().verify(sig, b"123GET/trade-api/v2/portfolio/balance",
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())


def test_order_body_v2(tmp_path):
    from kalshi_bot.client import KalshiClient
    sent = {}
    c = KalshiClient(Config())
    c._request = lambda method, ep, **kw: sent.update(m=method, ep=ep, body=kw["json"]) or {}
    c.place_order("T", "no", 3, 0.56)
    assert sent["ep"] == "/portfolio/events/orders"
    b = sent["body"]
    assert b["side"] == "ask" and b["price"] == "0.4400" and b["count"] == "3.00"   # buy NO @.56 == sell YES @.44
    c.place_order("T", "yes", 2, 0.30)
    assert sent["body"]["side"] == "bid" and sent["body"]["price"] == "0.3000"


def test_huge_disagreement_abstains():
    m = {"ticker": "T", "yes_ask_dollars": "0.0200", "no_ask_dollars": "0.9900"}
    assert decide(m, Fixed(0.40), 10, 0.07, 0.25) is None      # model says 40%, market 2%: distrust model


def test_penny_prices_skipped():
    m = {"ticker": "T", "yes_ask_dollars": "0.0300", "no_ask_dollars": "0.9800"}
    assert decide(m, Fixed(0.25), 10, 0.07, 0.25) is None
