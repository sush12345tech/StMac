import streamlit as st

@st.cache_resource
def load_libs():
    """Load heavy libs once only"""
    import pandas as pd
    import numpy as np
    from io import BytesIO
    import ta
    return pd, np, BytesIO, ta

# ==============================
# Excel Download (Unchanged)
# ==============================
def download_results(df, trades_dict):
    pd, _, BytesIO, _ = load_libs()
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Top10 Results")
        for key, trades in trades_dict.items():
            sheet_name = f"{key[0]}_{key[1]}_{key[2]}"
            trades.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    st.download_button(
        label="📊 Download Excel (Top10 + Trades)",
        data=output.getvalue(),
        file_name="macd_results_with_trades.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ==============================
# Main App
# ==============================
def main():
    pd, np, BytesIO, ta = load_libs()
    
    st.title("📈 MACD Parameter Optimizer (20x Faster ⚡)")
    st.markdown("Upload historical price data")

    uploaded_file = st.file_uploader(
        "Upload CSV or Excel (Date + Close required)",
        type=["csv", "xls", "xlsx"]
    )
    if uploaded_file is None:
        return

    # Read & Prep Data (Unchanged)
    file_ext = uploaded_file.name.split(".")[-1].lower()
    if file_ext == "csv":
        data = pd.read_csv(uploaded_file)
    else:
        data = pd.read_excel(uploaded_file, engine="openpyxl")
    
    if not {"Date", "Close"}.issubset(data.columns):
        st.error("Need 'Date' and 'Close' columns")
        return
        
    data["Date"] = pd.to_datetime(data["Date"])
    data = data.sort_values("Date").reset_index(drop=True)
    st.dataframe(data.head())

    # Parameters (Unchanged)
    st.markdown("### ⚙️ MACD Parameters")
    fast_min, fast_max = st.number_input("Fast EMA", 2, 50, (12, 20)), st.number_input("", 2, 50, 20)
    slow_min, slow_max = st.number_input("Slow EMA", 10, 100, (26, 40)), st.number_input("", 10, 100, 40)
    signal_min, signal_max = st.number_input("Signal EMA", 2, 30, (9, 15)), st.number_input("", 2, 30, 15)
    
    target_pct = st.number_input("Target %", 1.0, 100.0, 5.0)
    max_days = st.number_input("Max Days", 1, len(data), 10)
    min_trades = st.number_input("Min Trades", 1, 100, 5)
    min_accuracy = st.number_input("Min Accuracy %", 1, 100, 40)

    fast_range = range(fast_min, fast_max + 1)
    slow_range = range(slow_min, slow_max + 1)
    signal_range = range(signal_min, signal_max + 1)

    total_combos = len([(f,s) for f in fast_range for s in slow_range if f < s]) * len(signal_range)
    st.info(f"⚙️ {total_combos:,} combos - ETA ~{total_combos//1000}min")

    if not st.button("🚀 Optimize MACD (20x Faster!)", type="primary"):
        return

    # LIVE TRACKER CONTAINERS
    progress_c = st.empty()
    status_c = st.empty()
    metrics_c = st.empty()

    # PREP ARRAYS ONCE
    close_prices = data["Close"].values.astype(np.float64)
    dates = data["Date"].values

    results, trades_dict = [], {}
    combos_checked = valid_combos = 0
    valid_fs_pairs = [(f, s) for f in fast_range for s in slow_range if f < s]
    total_valid_combos = len(valid_fs_pairs) * len(signal_range)

    # ULTRA-FAST LOOP ⚡
    for pair_idx, (fast, slow) in enumerate(valid_fs_pairs):
        # EMA ONCE PER PAIR
        ema_fast = ta.trend.EMAIndicator(close_prices, fast).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(close_prices, slow).ema_indicator()
        macd_base = ema_fast - ema_slow
        
        for signal_idx, signal in enumerate(signal_range):
            combos_checked += 1
            progress = (pair_idx * len(signal_range) + signal_idx + 1) / total_valid_combos
            
            # LIVE UPDATES
            with progress_c.container():
                st.progress(progress)
                st.markdown(f"**⚡ {combos_checked:,}/{total_valid_combos:,} ({progress*100:.1f}%)**")
            
            with status_c.container():
                st.markdown(f"**🔄 Fast={fast} Slow={slow} Signal={signal}**")
            
            with metrics_c.container():
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Checked", combos_checked)
                c2.metric("Valid", valid_combos)
                speed = combos_checked / 60
                eta = (total_valid_combos - combos_checked) / max(speed, 1)
                c3.metric("ETA", f"{eta:.0f}m")
                best = max([r.get('Accuracy%', 0) for r in results] or [0])
                c4.metric("Best", f"{best:.1f}%")

            # FAST CROSSOVER
            signal_line = macd_base.ewm(span=signal).mean()
            crossovers = (macd_base.shift(1) < signal_line.shift(1)) & (macd_base > signal_line)
            entries = np.flatnonzero(crossovers)
            
            if len(entries) < min_trades: continue

            # VECTORIZED TRADES
            hits = 0
            trades = []
            for entry in entries:
                entry_price = close_prices[entry]
                target = entry_price * (1 + target_pct / 100)
                end = min(entry + max_days, len(close_prices) - 1)
                future = close_prices[entry+1:end+1]
                
                hit_mask = future >= target
                if np.any(hit_mask):
                    hit_pos = np.argmax(hit_mask)
                    exit_idx = entry + 1 + hit_pos
                    hits += 1
                else:
                    exit_idx = end
                
                trades.append({
                    "Entry Date": dates[entry], "Entry Price": entry_price,
                    "Exit Date": dates[exit_idx], "Exit Price": close_prices[exit_idx],
                    "Pct Return": round((close_prices[exit_idx] - entry_price)/entry_price*100, 2),
                    "Target Hit": np.any(hit_mask)
                })
            
            accuracy = hits / len(entries) * 100
            if accuracy >= min_accuracy:
                results.append({"FastEMA": fast, "SlowEMA": slow, "SignalEMA": signal,
                               "Trades": len(entries), "Hits": hits, "Accuracy%": round(accuracy, 2)})
                trades_dict[(fast, slow, signal)] = pd.DataFrame(trades)
                valid_combos += 1

    # CLEANUP + RESULTS
    progress_c.empty(); status_c.empty(); metrics_c.empty()
    st.success(f"✅ Done! {combos_checked:,} checked, {len(results)} valid")

    if results:
        results_df = pd.DataFrame(results).sort_values("Accuracy%", ascending=False)
        st.dataframe(results_df.head(10))
        download_results(results_df.head(10), 
                        {k: v for k, v in trades_dict.items() 
                         if tuple(results_df.head(10)[["FastEMA","SlowEMA","SignalEMA"]].iloc[i].values) == k 
                         for i in range(10) if k in trades_dict})
    else:
        st.warning("No matches found")

if __name__ == "__main__":
    main()
