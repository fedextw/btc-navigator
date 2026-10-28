# B＋C Stage 4 — Controlled Autonomous Research

Stage 3 engineering acceptance passed locally. This stage extends failed-strategy feedback into repeatable, **explicitly invoked** research steps. It is NOT yet a continuously running unattended agent, and it cannot order or promote live strategies.

## What has been implemented
- `agent_stage_four_research.py`: one bounded step using a content-addressed prior report, newly retrieved closed Binance USD-M candles, independent-validation checks and one real bounded model proposal.
- Rejects overwritten workspaces, tampered prior reports, unsafe provenance, unchanged or overlapping market validation; the model is not contacted when temporal evidence is invalid.
- Saves `step_summary.json`, a new immutable candidate evaluation report, lineage and explicit `no_qualified_candidate` where appropriate; zero live authority.
- Independent unit tests use mocked provider calls and cannot establish real-provider availability or profitability.

## Running a single step (optional, costs API credits)
Provide the hashed JSON report path from the final Stage 3 `resume` folder. In the updated B+C checkout:

```powershell
py -3 agent_stage_four_research.py --prior-report ".local-state\stage3-delivery-final-01\resume\f272b27d23d3b3012482ee7d88c4fd027e0364b35c5bfeeab926d0aa86ee6593.json" --out ".local-state\stage4-step-01" --symbol BTCUSDT --interval 1h --count 1600 --model gpt-4.1-mini
```

If not enough NEW candles have elapsed to make the new validation segment start after the latest prior dataset cutoff, it deliberately refuses before calling the model. This is correct: do not trick the gate by reusing old candles.

## Stage 4 acceptance remains OPEN
1. Unattended operator with bounded frequency and replay-safe persistent checkpoint
2. Scheduling without duplicate evaluation and crash-safe recovery
3. Rotating Binance USDT-margined futures universe with sound data readiness/freshness rules
4. Real paper-forward evidence, performance after costs and slippage, and operational audit

No merge to production. No live orders. No guaranteed positive expectancy.
