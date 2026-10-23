from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import requests
import numpy as np

from automatic_ai import generate_pending
from binance_client import RequestBudget, BinanceClient, RatePause, BinanceAccessError
from market_data import active_usdt_contracts, valid_symbol, demo_market
from model_evolution import select_model
from monitor_settings import save_settings, save_credentials, load_credentials
from notifications import dispatch, DeliveryError, send_message
from scanner import MarketScanner
from signal_store import connect, get_state, record_signal, set_state
from learning_lab import save_record, model_path


TOKEN = "123456789:" + "a" * 35


def fixture_signal(**changes):
    now = time.time()
    payload = {"symbol": "TESTUSDT", "interval": "1h", "candle_time": "2026-10-23T10:59:59.999+00:00",
        "side": "LONG", "mode": "live", "expires_at": now + 3600,
        "entry": 100.0, "mark_price": 100.1, "stop": 98.0, "targets": [103, 104, 106],
        "score": 5, "model_probability": .7, "model_id": "fixture", "factors": [], "news": []}
    return {**payload, **changes}


def enable_telegram(root):
    save_credentials({"telegram_token": TOKEN, "telegram_chat": "123456789"}, root)
    save_settings({"notifications_enabled": True, "channel": "telegram"}, root)


class DiscoveryTests(unittest.TestCase):
    def test_discovers_all_trading_usdt_perpetuals(self):
        rows = [{"symbol": s, "status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDT", "marginAsset": "USDT"}
                for s in ["BTCUSDT", "SUSDT", "1000PEPEUSDT", "币安人生USDT"]]
        rows += [{**rows[0], "symbol": "OLDUSDT", "status": "SETTLING"},
                 {**rows[0], "symbol": "EXPIRYUSDT", "contractType": "CURRENT_QUARTER"},
                 {**rows[0], "symbol": "OTHERUSDT", "marginAsset": "USDC"}]
        self.assertEqual(set(active_usdt_contracts({"symbols": rows})), {"BTCUSDT", "SUSDT", "1000PEPEUSDT", "币安人生USDT"})

    def test_symbol_paths_are_safe_without_excluding_unicode_listings(self):
        self.assertTrue(valid_symbol("币安人生USDT"))
        self.assertTrue(valid_symbol("SUSDT"))
        for symbol in ("../../BTCUSDT", "BTC/USDT", "BTCUSDT\n", "USDT"):
            self.assertFalse(valid_symbol(symbol))

    def test_budget_and_backoff(self):
        clock = [0.0]
        budget = RequestBudget(4, clock=lambda: clock[0], gap=0)
        budget.acquire(2); budget.acquire(2)
        with self.assertRaises(RatePause): budget.acquire(1)
        clock[0] = 61
        budget.acquire(2)
        budget.pause(90)
        with self.assertRaises(RatePause): budget.acquire(1)
        clock[0] = 152
        budget.acquire(1)

    def test_binance_429_does_not_retry_immediately(self):
        response = Mock(status_code=429, headers={"Retry-After": "120"})
        get = Mock(return_value=response)
        client = BinanceClient(RequestBudget(gap=0), get)
        with self.assertRaises(RatePause): client.json("/fapi/v1/exchangeInfo")
        with self.assertRaises(RatePause): client.json("/fapi/v1/exchangeInfo")
        self.assertEqual(get.call_count, 1)

    def test_region_restriction_is_reported_clearly(self):
        response = Mock(status_code=451)
        client = BinanceClient(RequestBudget(gap=0), Mock(return_value=response))
        with self.assertRaises(BinanceAccessError) as error:
            client.json('/fapi/v1/exchangeInfo')
        self.assertIn('451',str(error.exception))
        self.assertIn('所在地區',str(error.exception))


class OutboxTests(unittest.TestCase):
    def test_duplicate_signal_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            db = connect(root)
            signal = fixture_signal()
            event = record_signal(db, signal, 0)
            self.assertIsNotNone(event)
            db.close(); db = connect(root)
            self.assertIsNone(record_signal(db, signal, 0))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            db.close()

    def test_demo_and_expired_data_never_enter_push_outbox(self):
        with tempfile.TemporaryDirectory() as root:
            db = connect(root)
            self.assertIsNone(record_signal(db, fixture_signal(mode="demo")))
            self.assertIsNone(record_signal(db, fixture_signal(expires_at=time.time() - 1)))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            db.close()

    def test_cooldown_is_per_symbol_and_direction(self):
        with tempfile.TemporaryDirectory() as root:
            db = connect(root)
            now = time.time()
            self.assertIsNotNone(record_signal(db, fixture_signal(), 60, now))
            self.assertIsNone(record_signal(db, fixture_signal(candle_time="next"), 60, now + 1))
            self.assertIsNotNone(record_signal(db, fixture_signal(side="SHORT"), 60, now + 1))
            db.close()

    def test_successful_notification_is_sent_only_once(self):
        with tempfile.TemporaryDirectory() as root:
            enable_telegram(root)
            db = connect(root)
            record_signal(db, fixture_signal())
            sender = Mock(return_value="1")
            self.assertEqual(dispatch(db, root, sender=sender)["sent"], 1)
            db.close(); db = connect(root)
            self.assertEqual(dispatch(db, root, sender=sender)["sent"], 0)
            self.assertEqual(sender.call_count, 1)
            stored = db.execute("SELECT payload FROM events").fetchone()[0]
            self.assertNotIn(TOKEN, stored)
            db.close()

    def test_timeout_is_unknown_and_never_automatically_resent(self):
        with tempfile.TemporaryDirectory() as root:
            enable_telegram(root)
            db = connect(root)
            record_signal(db, fixture_signal())
            sender = Mock(side_effect=DeliveryError("network_result_unknown", ambiguous=True))
            dispatch(db, root, sender=sender); dispatch(db, root, sender=sender)
            self.assertEqual(sender.call_count, 1)
            self.assertEqual(db.execute("SELECT status FROM deliveries").fetchone()[0], "unknown")
            db.close()

    def test_confirmed_429_uses_retry_after(self):
        with tempfile.TemporaryDirectory() as root:
            enable_telegram(root)
            db = connect(root)
            record_signal(db, fixture_signal())
            sender = Mock(side_effect=[DeliveryError("telegram_rate_limit", retry_after=60), "ok"])
            now = time.time()
            dispatch(db, root, now, sender)
            dispatch(db, root, now + 30, sender)
            self.assertEqual(sender.call_count, 1)
            dispatch(db, root, now + 61, sender)
            self.assertEqual(sender.call_count, 2)
            self.assertEqual(db.execute("SELECT status FROM deliveries").fetchone()[0], "sent")
            db.close()

    def test_transport_exceptions_never_leak_bot_url(self):
        post = Mock(side_effect=requests.Timeout("secret URL " + TOKEN))
        with self.assertRaises(DeliveryError) as context:
            send_message("test", {"telegram_token": TOKEN, "telegram_chat": "1234"}, transport=post)
        self.assertNotIn(TOKEN, str(context.exception))
        self.assertTrue(context.exception.ambiguous)

    def test_concurrent_database_startup(self):
        with tempfile.TemporaryDirectory() as root:
            def write(index):
                db = connect(root); set_state(db, str(index), {"index": index}); db.close()
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write, range(24)))
            db = connect(root)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scan_state").fetchone()[0], 24)
            db.close()


class FakeExchange:
    def __init__(self, count=12):
        self.symbols = [f"T{i}USDT" for i in range(count)]
        self.calls = []
        self.budget = RequestBudget(limit=10000, gap=0)

    def json(self, path, params=None, weight=1):
        self.calls.append((path, params))
        if path.endswith("exchangeInfo"):
            return {"symbols": [{"symbol": s, "status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDT", "marginAsset": "USDT"} for s in self.symbols]}
        if path.endswith("premiumIndex"):
            return [{"symbol": s, "time": int(time.time() * 1000), "markPrice": 100, "lastFundingRate": .0001} for s in self.symbols]
        if path.endswith("24hr"):
            return [{"symbol": s, "quoteVolume": 1e9} for s in self.symbols]
        if path.endswith("klines"):
            frame = demo_market(params["symbol"], params["interval"], params["limit"])["candles"]
            return [[int(r.time.timestamp()*1000), r.open, r.high, r.low, r.close, r.volume,
                     int(r.close_time.timestamp()*1000), r.quote_volume, 1, 0, r.taker_buy_quote] for r in frame.itertuples()]
        raise AssertionError(path)


class ScannerTests(unittest.TestCase):
    def test_demo_entrypoint_never_starts_push_or_paid_ai_workers(self):
        from scanner import main
        with patch('sys.argv',['scanner.py','--demo','--once']), patch('scanner.connect'), patch('scanner.research_db'), patch('scanner.MarketScanner') as service, patch('scanner.threading.Thread') as thread:
            service.return_value.cycle.return_value={"mode":"demo"}
            main()
            thread.assert_not_called()

    def test_qualified_model_and_real_rule_pipeline_create_one_alert(self):
        with tempfile.TemporaryDirectory() as root:
            market = demo_market("SUSDT", "1h")
            frame = market["candles"]
            close = np.exp(np.linspace(np.log(20), np.log(100), len(frame)))
            frame["close"] = close
            frame["open"] = np.r_[close[0] * .995, close[:-1]]
            frame["high"] = frame.close * 1.0005
            frame["low"] = frame.open * .9995
            market.update(mode="live", mark_price=100.0, funding=0.0)
            trained_until = frame.iloc[-8].close_time
            record = {"id": "pipeline-fixture", "research_pass": True, "demo": False,
                "trained_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                "last_candle": str(trained_until), "threshold": .6, "horizon": 6, "cost": .0014,
                "model": {"mean": [0.0]*9, "scale": [1.0]*9, "weights": [0.0]*9, "bias": 3.0}}
            save_record(model_path(Path(root)/'models','SUSDT','1h',False),record)
            db = connect(root)
            scanner = MarketScanner(root)
            from monitor_settings import load_settings
            row, _, _ = scanner.evaluate(db, market, {"quoteVolume":1e9}, load_settings(root))
            self.assertEqual(row["side"], "LONG", row)
            scanner.evaluate(db, market, {"quoteVolume":1e9}, load_settings(root))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0],1)
            enable_telegram(root)
            sender = Mock(return_value="accepted")
            self.assertEqual(dispatch(db,root,sender=sender)["sent"],1)
            self.assertIn("SUSDT",sender.call_args.args[0])
            self.assertIn("不是勝率",sender.call_args.args[0])
            # Current price has run away: the next evaluation must return WAIT.
            market["mark_price"] = 120.0
            row, _, _ = scanner.evaluate(db, market, {"quoteVolume":1e9}, load_settings(root))
            self.assertEqual(row["side"],"WAIT")
            self.assertFalse(row["gates"]["標記價格新鮮且未過度偏離"])
            db.close()

    def test_universe_has_no_top_six_or_top_hundred_cap(self):
        with tempfile.TemporaryDirectory() as root:
            db = connect(root)
            scanner = MarketScanner(root, FakeExchange(700))
            self.assertEqual(len(scanner.universe(db)), 700)
            db.close()

    def test_all_symbols_are_scanned_and_closed_candle_cache_is_reused(self):
        with tempfile.TemporaryDirectory() as root:
            client = FakeExchange(12)
            save_settings({"training_per_cycle": 1}, root)
            scanner = MarketScanner(root, client)
            first = scanner.cycle()
            self.assertEqual(first["analyzed"], 12, first)
            first_requests = sum(p.endswith("klines") and a["limit"] == 300 for p, a in client.calls)
            second = scanner.cycle()
            second_requests = sum(p.endswith("klines") and a["limit"] == 300 for p, a in client.calls)
            self.assertEqual(first_requests, 12)
            self.assertEqual(second_requests, first_requests)
            self.assertEqual(second["analyzed"], 12)
            db = connect(root)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0], 12)
            db.close()

    def test_demo_scan_cannot_publish_live_events(self):
        with tempfile.TemporaryDirectory() as root:
            result = MarketScanner(root, demo=True).cycle()
            self.assertEqual(result["analyzed"], 6)
            db = connect(root)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            db.close()

    def test_global_connection_failure_has_visible_status(self):
        with tempfile.TemporaryDirectory() as root:
            client = Mock()
            client.json.side_effect = requests.ConnectionError()
            status = MarketScanner(root, client).cycle()
            self.assertEqual(status["status"], "連線失敗")
            db = connect(root)
            self.assertEqual(get_state(db, "status")["universe"], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            db.close()


class AutomaticAITests(unittest.TestCase):
    def test_automatic_ai_is_opt_in_and_quota_limited(self):
        with tempfile.TemporaryDirectory() as root:
            db = connect(root)
            record_signal(db, fixture_signal())
            summary = Mock(return_value="研究摘要")
            self.assertEqual(generate_pending(db, root, summary), "disabled")
            summary.assert_not_called()
            save_credentials({"ai_api_key": "unit-test-not-a-real-key"}, root)
            save_settings({"auto_ai_enabled": True, "ai_daily_limit": 1}, root)
            from collector import connect as sources_db
            sources = sources_db(root)
            sources.execute('INSERT INTO news VALUES (?,?,?,?,?)',('https://example.com/news','ETF research','Fixture','2026-10-23','2026-10-23'))
            sources.commit(); sources.close()
            self.assertEqual(generate_pending(db, root, summary), "complete")
            original = json.loads(db.execute('SELECT payload FROM events ORDER BY created_at LIMIT 1').fetchone()[0])
            self.assertEqual(original['ai_sources'][0]['title'],'ETF research')
            self.assertNotIn('unit-test-not-a-real-key',json.dumps(original))
            record_signal(db, fixture_signal(symbol="OTHERUSDT"))
            self.assertEqual(generate_pending(db, root, summary), "daily_limit")
            self.assertEqual(summary.call_count, 1)
            db.close()

    def test_failed_candidate_cannot_replace_passing_incumbent(self):
        incumbent = {"research_pass": True, "id": "old"}
        candidate = {"research_pass": False, "id": "new"}
        selected, audit = select_model(incumbent, candidate, None)
        self.assertEqual(selected["id"], "old")
        self.assertFalse(audit["promoted"])


if __name__ == "__main__":
    unittest.main()
