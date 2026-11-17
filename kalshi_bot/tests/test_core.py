import base64
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi_bot.config import Config
from kalshi_bot.risk import RiskManager
from kalshi_bot.signals import FixedSignal
from kalshi_bot.strategy import best_asks, decide, kelly_contracts

BOOK = {"yes": [[40, 100], [38, 50]], "no": [[55, 100]]}  # yes ask=45, no ask=60


def test_best_asks():
    assert best_asks(BOOK) == (45, 60)


def test_decide_buys_yes_with_edge():
    o = decide({"ticker": "T"}, BOOK, FixedSignal({"T": 0.60}), 100, 0.05, 0.25)
    assert o and o.side == "yes" and o.price_cents == 45 and o.count > 0


def test_decide_no_edge():
    assert decide({"ticker": "T"}, BOOK, FixedSignal({"T": 0.47}), 100, 0.05, 0.25) is None


def test_decide_abstain():
    assert decide({"ticker": "T"}, BOOK, FixedSignal({}), 100, 0.05, 0.25) is None


def test_kelly_zero_when_no_edge():
    assert kelly_contracts(0.4, 0.5, 100, 0.25) == 0


def test_risk_caps_and_halt():
    cfg = Config(max_contracts_per_order=5, max_position_per_market=7, max_exposure_usd=10, max_daily_loss_usd=5)
    r = RiskManager(cfg)
    assert r.check("T", "yes", 100, 50)[0] == 5
    r.record_fill("T", "yes", 5, 50)
    assert r.check("T", "yes", 100, 50)[0] == 2        # position cap 7
    r.record_pnl(-5)
    assert r.check("T", "yes", 1, 50)[0] == 0 and r.halted


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
