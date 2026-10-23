import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import numpy as np
import pandas as pd
import requests

from market_data import demo_market, load_market, validate_candles, load_news, fetch_feed, import_history_csv
from context_data import load_context, parse_context
from analysis_engine import analyze, indicators, position_size
from learning_lab import (feature_frame, train_and_evaluate, simulate, trade_stats,
                          update_paper_journal, save_record, load_record)
from collector import collect_cycle, connect
from ai_research import summarize
from decision_engine import consensus


class MarketTests(unittest.TestCase):
    def test_demo_overlapping_history_is_consistent(self):
        short = demo_market("BTCUSDT", "1h")["candles"]
        long = demo_market("BTCUSDT", "1h", 1500)["candles"]
        pd.testing.assert_frame_equal(short.reset_index(drop=True), long.tail(300).reset_index(drop=True))

    def test_auto_fallback_is_explicit(self):
        with patch("market_data.live_market", side_effect=RuntimeError("blocked")):
            market = load_market("BTCUSDT", "1h")
            self.assertEqual(market["mode"], "demo")
            self.assertIn("live", market["errors"])

    def test_live_only_never_falls_back(self):
        with patch("market_data.live_market", side_effect=RuntimeError("blocked")):
            with self.assertRaises(RuntimeError):
                load_market("BTCUSDT", "1h", "live")

    def test_bad_ohlc_is_rejected(self):
        rows = [[i * 3600000, 10, 9, 8, 11, 1, i * 3600000 + 3599999] for i in range(100)]
        with self.assertRaises(ValueError):
            validate_candles(rows)

    def test_open_candles_are_excluded(self):
        now = pd.Timestamp.now(tz="UTC").floor("1h")
        start = int((now - pd.Timedelta(hours=99)).timestamp() * 1000)
        rows = [[start+i*3600000, 10, 12, 8, 11, 1, start+(i+1)*3600000-1] for i in range(100)]
        frame = validate_candles(rows, now.to_pydatetime())
        self.assertEqual(len(frame), 99)
        self.assertTrue((frame.close_time < now).all())

    def test_stale_and_missing_bars_force_wait(self):
        market = demo_market("BTCUSDT", "1h")
        future = market["fetched_at"] + timedelta(days=2)
        self.assertEqual(analyze(market, future)["side"], "WAIT")
        market["candles"] = market["candles"].drop(index=100)
        self.assertFalse(analyze(market)["valid"])

    def test_no_model_or_demo_never_produces_consensus_entry(self):
        market = demo_market("BTCUSDT", "1h")
        result = analyze(market)
        self.assertEqual(consensus(market, result)["side"], "WAIT")
        market["mode"] = "live"
        result["side"] = "LONG"
        self.assertEqual(consensus(market, result)["side"], "WAIT")

    def test_flat_rsi_and_causal_indicators(self):
        frame = demo_market("ETHUSDT", "1h")["candles"]
        flat = frame.copy()
        flat["close"] = 100.0
        self.assertEqual(indicators(flat).iloc[-1].rsi, 50)
        before = indicators(frame.iloc[:250])
        after = indicators(frame)
        np.testing.assert_allclose(before.ema20, after.ema20.iloc[:250])

    def test_risk_budget_accounts_for_fees(self):
        result = position_size(1000, 1, 100, 95, 3, .05)
        self.assertAlmostEqual(result["quantity"] * (5 + 195 * .0005), 10)
        self.assertEqual(result["budget"], 10)
        with self.assertRaises(ValueError):
            position_size(1000, 1, 100, 100)

    def test_news_failures_do_not_create_headlines(self):
        with patch("market_data.fetch_feed", side_effect=requests.ConnectionError()):
            articles, errors = load_news()
        self.assertEqual(articles, [])
        self.assertEqual(len(errors), 3)

    def test_feed_filters_unsafe_links(self):
        response = Mock(content=b'<rss><channel><item><title>Test</title><link>javascript:alert(1)</link></item><item><title>ETF</title><link>https://example.com/news</link></item></channel></rss>')
        with patch("market_data.requests.get", return_value=response):
            articles = fetch_feed("Test", "https://example.com/feed")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "ETF")

    def test_history_csv_validates_prices_and_interval(self):
        frame = demo_market("BTCUSDT", "1h", 1500)["candles"]
        imported = import_history_csv(frame.to_csv(index=False).encode(), "1h")
        np.testing.assert_allclose(imported.close, frame.close)
        frame.loc[0, "close"] = -1
        with self.assertRaises(ValueError):
            import_history_csv(frame.to_csv(index=False).encode(), "1h")

    def test_context_failures_are_distinct_from_zero(self):
        with patch("context_data.get_json", side_effect=requests.ConnectionError()):
            context = load_context()
        self.assertEqual(context["data"], {})
        self.assertEqual(len(context["errors"]), 4)

    def test_stablecoin_supply_change_not_called_inflow(self):
        rows = [{"date": 1700000000 + i * 86400, "totalCirculating": {"peggedUSD": 100 + i}} for i in range(8)]
        context = parse_context("DefiLlama Stablecoins", rows)
        self.assertAlmostEqual(context["change_7_samples_pct"], 7)
        self.assertEqual(context["stablecoin_supply_usd"], 107)
        self.assertNotIn("inflow", context)


class LearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candles = demo_market("BTCUSDT", "1h", 1500)["candles"]
        cls.record = train_and_evaluate(cls.candles, "BTCUSDT", "1h", demo=True)

    def test_purged_time_partitions(self):
        split = self.record["split"]
        self.assertLess(pd.Timestamp(split["train_last_outcome"]), pd.Timestamp(split["validation_first_signal"]))
        self.assertLess(pd.Timestamp(split["validation_last_outcome"]), pd.Timestamp(split["test_first_signal"]))

    def test_test_prices_do_not_choose_model(self):
        altered = self.candles.copy()
        for column in ("open", "high", "low", "close"):
            altered.loc[altered.index[-100:], column] *= 1.3
        other = train_and_evaluate(altered, "BTCUSDT", "1h", demo=True)
        self.assertEqual(self.record["model"], other["model"])
        self.assertEqual(self.record["threshold"], other["threshold"])
        self.assertEqual(self.record["regularization"], other["regularization"])

    def test_demo_cannot_pass_research_gate(self):
        self.assertFalse(self.record["research_pass"])
        self.assertFalse(self.record["checks"]["使用真實行情"])

    def test_features_do_not_use_future(self):
        short = feature_frame(self.candles.iloc[:700])
        long = feature_frame(self.candles)
        pd.testing.assert_frame_equal(short, long.iloc[:len(short)].reset_index(drop=True))

    def test_simulation_next_open_costs_no_overlap(self):
        frame = self.candles.iloc[:30].copy().reset_index(drop=True)
        probabilities = np.ones(30) * .9
        trades = simulate(frame, probabilities, 0, 20, 3, .6, .0014)
        self.assertEqual(trades[0]["entry"], float(frame.iloc[1].open))
        self.assertAlmostEqual(trades[0]["net_return"], frame.iloc[3].close / frame.iloc[1].open - 1 - .0014)
        for previous, following in zip(trades, trades[1:]):
            self.assertGreater(pd.Timestamp(following["entry_time"]), pd.Timestamp(previous["exit_time"]))

    def test_zero_trades_are_not_a_passing_backtest(self):
        stats = trade_stats([])
        self.assertEqual(stats["trades"], 0)
        self.assertIsNone(stats["win_rate"])
        self.assertIsNone(stats["profit_factor"])

    def test_insufficient_history_rejected(self):
        with self.assertRaises(ValueError):
            train_and_evaluate(self.candles.iloc[:300], "BTCUSDT", "1h", demo=True)

    def test_paper_prediction_is_recorded_before_outcome(self):
        record = copy.deepcopy(self.record)
        record["model"]["weights"] = [0.0] * 9
        record["model"]["bias"] = 5.0
        record["last_candle"] = str(self.candles.iloc[299].close_time)
        record["horizon"] = 3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.json"
            first = update_paper_journal(path, record, self.candles.iloc[:301])
            self.assertEqual(first["rows"][0]["status"], "pending")
            self.assertIsNone(first["rows"][0]["entry"])
            second = update_paper_journal(path, record, self.candles.iloc[:302])
            self.assertEqual(second["rows"][0]["entry"], self.candles.iloc[301].open)
            self.assertEqual(second["rows"][0]["status"], "pending")
            last = update_paper_journal(path, record, self.candles.iloc[:304])
            self.assertEqual(last["rows"][0]["status"], "closed")
            self.assertEqual(last["rows"][0]["exit"], self.candles.iloc[303].close)
            self.assertEqual(last["summary"]["trades"], 1)
            self.assertAlmostEqual(last["summary"]["sum_net_returns"], last["rows"][0]["net_return"])
            again = update_paper_journal(path, record, self.candles.iloc[:304])
            self.assertEqual(len(last["rows"]), len(again["rows"]))

    def test_collector_persists_and_does_not_retrain_each_poll(self):
        with tempfile.TemporaryDirectory() as directory:
            a = collect_cycle(demo=True, train=True, root=directory)
            b = collect_cycle(demo=True, train=True, root=directory)
            self.assertEqual(a["model_id"], b["model_id"])
            db = connect(directory)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM training_runs").fetchone()[0], 1)
            db.close()

    def test_live_collector_logs_failure_without_fake_data(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("collector.live_market", side_effect=RuntimeError("blocked")):
                with self.assertRaises(RuntimeError):
                    collect_cycle(root=directory, news=False)
            db = connect(directory)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM heartbeat").fetchone()[0], "error")
            db.close()


class AITests(unittest.TestCase):
    def test_no_key_means_no_external_call(self):
        with patch.dict("os.environ", {}, clear=True), patch("ai_research.requests.post") as request:
            with self.assertRaises(ValueError):
                summarize({}, {}, [], provider="openai")
            request.assert_not_called()

    def test_ai_receives_source_ids_and_demo_status(self):
        market = demo_market("BTCUSDT", "1h")
        result = analyze(market)
        response = Mock(ok=True)
        response.json.return_value = {"choices": [{"message": {"content": "模擬研究 [1]"}}]}
        with patch("ai_research.requests.post", return_value=response) as request:
            text = summarize(market, result, [{"title": "ETF", "source": "Test", "url": "https://example.com", "published": "now"}], api_key="unit-test-placeholder", provider="openai")
            content = request.call_args.kwargs["json"]["messages"][1]["content"]
            payload = json.loads(content)
        self.assertEqual(payload["data_mode"], "demo")
        self.assertEqual(payload["headlines_untrusted_data"][0]["id"], 1)
        self.assertEqual(text, "模擬研究 [1]")
        self.assertNotIn("unit-test-placeholder", content)


if __name__ == "__main__":
    unittest.main()
