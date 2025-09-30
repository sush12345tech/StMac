import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import ta

def download_results(df, filename):
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=f"📥 Download {filename} (CSV)",
        data=csv,
        file_name=f"{filename}.csv",
        mime="text/csv",
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
    st.download_button(
        label=f"📊 Download {filename} (Excel)",
        data=output.getvalue(),
        file_name=f"{filename}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


st.title("📈 MACD Parameter Optimizer (Flexible Criteria)")

st.markdown("""
Upload historical price data (1500+ days recommended)  
and test MACD parameter combinations to find the most accurate and actionable ones  
based on *your* chosen criteria.  
**Leave any field blank to skip filtering on that criterion.**
""")

uploaded_file = st.file_uploader("Upload CSV or Excel file (must include 'Date' and 'Close')", type=["csv", "xls", "xlsx"])

if uploaded_file is not None:
    file_ext = uploaded_file.name.split(".")[-1].lower()

    if file_ext == "csv":
        data = pd.read_csv(uploaded_file)
    elif file_ext in ["xls", "xlsx"]:
        data = pd.read_excel(uploaded_file, engine="openpyxl")
    else:
        st.error("Unsupported file format")
        st.stop()

    if not set(["Date", "Close"]).issubset(data.columns):
        st.error("File must contain 'Date' and 'Close' columns.")
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"])
    data = data.sort_values("Date").reset_index(drop=True)
    st.write("### Data Preview", data.head())

    st.sidebar.header("MACD Parameter Ranges (leave blank for default)")
    fast_min = st.sidebar.text_input("Fast EMA Min", value="12")
    fast_max = st.sidebar.text_input("Fast EMA Max", value="20")
    slow_min = st.sidebar.text_input("Slow EMA Min", value="26")
    slow_max = st.sidebar.text_input("Slow EMA Max", value="40")
    signal_min = st.sidebar.text_input("Signal EMA Min", value="9")
    signal_max = st.sidebar.text_input("Signal EMA Max", value="15")

    st.sidebar.header("Other Optimization Criteria")
    target_pct = st.sidebar.text_input("Target % (from entry, blank for no target)", value="5")
    max_days = st.sidebar.text_input("Max Trading Days to Hit Target", value="10")
    min_trades = st.sidebar.text_input("Minimum Trades Required", value="5")
    min_accuracy = st.sidebar.text_input("Minimum Accuracy %", value="40")

    # Convert to int/float or None as appropriate
    _safe_int = lambda x, default=None: int(x) if x.strip() != "" else default
    _safe_float = lambda x, default=None: float(x) if x.strip() != "" else default

    fast_min = _safe_int(fast_min, 12)
    fast_max = _safe_int(fast_max, 20)
    slow_min = _safe_int(slow_min, 26)
    slow_max = _safe_int(slow_max, 40)
    signal_min = _safe_int(signal_min, 9)
    signal_max = _safe_int(signal_max, 15)
    target_pct = _safe_float(target_pct)
    max_days = _safe_int(max_days)
    min_trades = _safe_int(min_trades)
    min_accuracy = _safe_float(min_accuracy)

    if st.button("🚀 Run Optimization"):
        results = []
        top10_trades_data = []

        for fast in range(fast_min, fast_max + 1):
            for slow in range(slow_min, slow_max + 1):
                if fast >= slow:
                    continue
                for signal in range(signal_min, signal_max + 1):
                    df = data.copy()
                    macd_line = ta.trend.ema_indicator(df["Close"], window=fast) - ta.trend.ema_indicator(df["Close"], window=slow)
                    signal_line = macd_line.ewm(span=signal).mean()
                    df["MACD"] = macd_line
                    df["Signal"] = signal_line
                    df["Crossover"] = (df["MACD"].shift(1) < df["Signal"].shift(1)) & (df["MACD"] > df["Signal"])

                    entries = df[df["Crossover"]].index
                    total_trades = len(entries)

                    # Skip if minimum trades required and not met
                    if min_trades is not None and total_trades < min_trades:
                        continue

                    trades = []
                    hits = 0
                    for entry in entries:
                        entry_row = df.loc[entry]
                        entry_price = entry_row["Close"]
                        entry_date = entry_row["Date"]

                        # If no target_pct/max_days, then no further analysis
                        exit_price = None
                        exit_date = None
                        holding_days = None
                        target_reached = False

                        if target_pct is not None and max_days is not None:
                            exit_target = entry_price * (1 + target_pct / 100)
                            # Find the first bar where price >= target within max_days after entry
                            subset = df.loc[entry+1 : entry+max_days]
                            reached = subset[subset["Close"] >= exit_target]
                            if not reached.empty:
                                exit_row = reached.iloc[0]
                                exit_price = exit_row["Close"]
                                exit_date = exit_row["Date"]
                                holding_days = (exit_date - entry_date).days
                                hits += 1
                                target_reached = True
                            else:
                                # Walk max_days or until last available
                                if not subset.empty:
                                    exit_row = subset.iloc[-1]
                                    exit_price = exit_row["Close"]
                                    exit_date = exit_row["Date"]
                                    holding_days = (exit_date - entry_date).days
                        else:
                            # If either target/max_days missing, just record NaNs
                            exit_price = np.nan
                            exit_date = pd.NaT
                            holding_days = np.nan

                        trades.append({
                            "Entry Date": entry_date,
                            "Entry Price": entry_price,
                            "Exit Date": exit_date,
                            "Exit Price": exit_price,
                            "Holding Days": holding_days,
                            "Target Reached": target_reached
                        })

                    accuracy = (hits / total_trades) * 100 if total_trades > 0 else 0

                    # Only apply accuracy criterion if given
                    if min_accuracy is not None and accuracy < min_accuracy:
                        continue

                    results.append({
                        "FastEMA": fast,
                        "SlowEMA": slow,
                        "SignalEMA": signal,
                        "Trades": total_trades,
                        "Hits": hits,
                        "Accuracy%": round(accuracy, 2),
                    })
                    top10_trades_data.append((fast, slow, signal, pd.DataFrame(trades)))

        if results:
            results_df = pd.DataFrame(results)
            results_df = results_df.sort_values("Accuracy%", ascending=False).reset_index(drop=True)
            st.success(f"✅ Found {len(results_df)} valid combinations")
            st.write("### Top 10 Results")
            top10 = results_df.head(10)
            st.dataframe(top10)
            download_results(top10, "top10_macd_results")

            st.write("### Trade Details for Top 10 Results")
            # Show expandable/collapsible sections per parameter set
            for idx, row in top10.iterrows():
                fast, slow, signal = row["FastEMA"], row["SlowEMA"], row["SignalEMA"]
                for trade_entry in top10_trades_data:
                    if trade_entry[0] == fast and trade_entry[1] == slow and trade_entry[2] == signal:
                        trades_df = trade_entry[3]
                        with st.expander(f"Fast={fast}, Slow={slow}, Signal={signal} | Accuracy={row['Accuracy%']}%"):
                            st.write(trades_df)
                            download_results(trades_df, f"trades_F{fast}_S{slow}_Sig{signal}")
                        break
        else:
            st.warning("No parameter combinations matched your criteria.")
