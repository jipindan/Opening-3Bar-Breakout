# Opening 3-Bar Trend Breakout

An intraday momentum breakout strategy for Chinese commodity futures, backtested on 5-minute bars with dynamic position sizing and daily trend filtering.

---

## Strategy Logic

At the open of each trading session (day session 09:00 + night session 21:00 where applicable), observe the closing prices of the first 3 five-minute bars:

- **Long signal**: close1 < close2 < close3 (consecutive uptick)
- **Short signal**: close1 > close2 > close3 (consecutive downtick)
- **No trade**: mixed direction

Entry at bar 3 close (+ 1 tick slippage), stop loss 1 tick beyond bar 3's extreme, take profit at 2.5× the stop distance. All positions are closed intraday — no overnight holds.

---

## Instruments

| Symbol | Exchange | Multiplier | Tick | Why |
|--------|----------|------------|------|-----|
| LC Lithium Carbonate | GFEX | 1t / lot | ¥20 | Strong trend characteristics, new energy sector |
| PS Polysilicon | GFEX | 3t / lot | ¥5 | Industrial, lower correlation with LC |

Data: tqsdk (TianQin Quant), free account, 5-min continuous main contract

---

## Position Sizing

**1% risk rule**: lots = ⌊(equity × 1%) ÷ stop-loss amount per lot⌋. Skip if less than 1 lot.

Hard cap: total margin used ≤ 50% of equity at all times.

---

## Key Decisions

### 1. Daily Trend Filter — biggest single improvement

**Problem**: The strategy is regime-dependent. It profits in trending markets and bleeds in choppy ones. In April–May 2026 all instruments entered a choppy phase simultaneously, causing a 20k drawdown from the peak.

**Solution**: Only take signals aligned with the daily moving average direction. Long only when prior-day close > N-day MA; short only when below.

| Config | Return | Max DD | Trades |
|--------|--------|--------|--------|
| No filter (baseline) | +21.2% | 14.4% | 344 |
| Daily MA N=10 | +8.9% | 9.2% | 168 |
| **Daily MA N=40 (adopted)** | **+21.8%** | **9.8%** | 145 |
| Daily MA N=20 | +12.0% | 7.2% | 158 |
| Intraday MA (5-min) | Negative | — | — |

**Why N=40**: N=10/20/40 all reduce drawdown consistently (no curve-fitting). N=40 preserves the original return while halving the drawdown. Intraday MA is discarded — a fast MA whipsaws in choppy markets and filters out good signals too.

---

### 2. Instrument Selection

**Rule**: validate positive fixed-1-lot expected value before including any instrument.

| Symbol | Fixed-1-lot return | Win rate | Decision |
|--------|--------------------|----------|----------|
| PS Polysilicon | +13.2% | 41.9% | ✅ Keep |
| LC Lithium Carbonate | +7.9% | 41.4% | ✅ Keep |
| AG Silver | +1.3% | 35.4% | ⏸ Pause (only 4 months of data) |
| RB / M / MA / I | All negative | 28–38% | ❌ Dropped |

RB/M/MA/I were dropped: negative edge in the test period, and their small per-lot stop sizes caused dynamic sizing to open 7–20 lots per trade, amplifying losses to −51.8% account return.

---

### 3. Risk-Reward Ratio

Win rate of ~40% requires a favorable RR to stay profitable. Tested 1:1 through 1:4:

| RR Ratio | Win rate | Stop-hit rate | Return | Max DD |
|----------|----------|---------------|--------|--------|
| 1:1.0 | 50% | — | ~0% | 6.3% | Commission erases profit |
| 1:2.0 | 43% | 55% | +24.1% | 8.0% | |
| **1:2.5 (adopted)** | **39%** | **60%** | **+23.5%** | **5.0%** | |
| 1:3.0 | 37% | — | +22.5% | 5.7% | |
| 1:4.0 | 37% | — | +42.0% | 4.4% | Overlaps with swing logic, small-sample dependent |

**Why 1:2.5**: nearly identical return to 1:2 but max drawdown drops from 8% to 5%. 1:4 looks attractive but a target 4× away is a multi-hour move — at that point you are competing with swing trading, not intraday momentum.

---

## Backtest Results

**Config**: LC + PS · Daily MA N=40 · RR=2.5 · 1% risk per trade · ¥100,000 initial capital

**Period**: 2025-07-30 to 2026-05-29 (~10 months)

| Metric | Value |
|--------|-------|
| Account return | **+23.5%** |
| Final equity | **¥123,531** |
| Max drawdown | **5.0%** |
| Trades taken | 141 |
| Win rate | 39% |
| Worst single trade | −¥1,265 |

**Benchmark comparison (same period)**:

| Benchmark | Return | Max DD |
|-----------|--------|--------|
| CSI Commodity Futures Index | +16.7% | −12.8% |
| **This strategy** | **+23.5%** | **−5.0%** |
| CSI 300 | +17.8% | −7.8% |

---

## Getting Started

```bash
pip install -r requirements.txt

# Required for first-time data download (cached locally after that)
export TQ_USER=your_username
export TQ_PWD=your_password

python main.py
```

Output: per-symbol backtest → account simulation → trend filter comparison → robustness sweep → charts

---

## Project Structure

```
├── config.py              # All parameters (symbols, RR ratio, risk %, etc.)
├── data/fetcher.py        # tqsdk data download and local caching
├── strategy/
│   ├── three_bar.py       # Signal logic (pure functions)
│   └── trend.py           # Daily trend filter
├── backtest/
│   ├── engine.py          # Backtest loop
│   ├── account.py         # Account simulation with dynamic sizing
│   └── compare.py         # Multi-config comparison
├── report/
│   ├── stats.py           # Performance metrics
│   └── plot.py            # Charts
├── main.py                # Entry point
├── NOTES.md               # Strategy knowledge base
└── output/                # Backtest artifacts (charts, trade logs)
```

---

## Known Limitations

- ~10 months of data — statistical confidence is limited
- LC listed 2022, PS listed 2023 — no longer history exists
- Continuous contract roll gaps cause minor distortion
- 5-min OHLC only; within-bar fill assumes stop-first (conservative)
- Strategy is regime-dependent: performs well in trending markets, underperforms in choppy conditions
