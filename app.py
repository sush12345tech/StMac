import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import ta

# -----------------------------
# Utility function for downloads
# -----------------------------
def download_results(df):
    # --- CSV ---
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Top 10 Results (CSV)",
        data=csv,
        file_name="top10_macd_results.csv",
        mime="text/csv",
    )

    # --- Excel ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Top10 Results")
    st.download_button(
        label="📊 Download Top 10 Results (Excel)",
        data=output.getvalue(),
        file_name="top10_macd_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# -----------------------------
# Streamlit App UI
# -----------------------------
st.title("📈 MACD Parameter Optimizer")

st.markdown("""
Upload historical price data (1500+ days recommended)  
and test MACD parameter combinations to find the most accurate ones
based on your target conditions.
""")

# File upload
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

    # Ensure proper columns
    if not set(["Date", "Close"]).issubset(data.columns):
        st.error("File must contain 'Date' and 'Close' columns.")
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"])
    data = data.sort_values("Date").reset_index(drop=True)

    st.write("### Data Preview", data.head())

    # -----------------------------
    # User Inputs with descriptions
    # -----------------------------
    st.sidebar.header("MACD Parameter Ranges")

    st.sidebar.markdown("**Fast EMA:** Short-term EMA period for MACD calculation. Typically between 2 to 50.")
    fast_min = st.sidebar.number_input("Fast EMA Min", 2, 50, 12, help="Minimum period for the fast EMA")
    fast_max = st.sidebar.number_input("Fast EMA Max", 2, 50, 20, help="Maximum period for the fast EMA")

    st.sidebar.markdown("**Slow EMA:** Long-term EMA period for MACD calculation. Must be greater than Fast EMA, typically 10 to 100.")
    slow_min = st.sidebar.number_input("Slow EMA Min", 10, 100, 26, help="Minimum period for the slow EMA")
    slow_max = st.sidebar.number_input("Slow EMA Max", 10, 100, 40, help="Maximum period for the slow EMA")

    st.sidebar.markdown("**Signal EMA:** EMA period for the MACD signal line. Commonly 2 to 30.")
    signal_min = st.sidebar.number_input("Signal EMA Min", 2, 30, 9, help="Minimum period for the signal EMA")
    signal_max = st.sidebar.number_input("Signal EMA Max", 2, 30, 15, help="Maximum period for the signal EMA")

    st.sidebar.header("Optimization Criteria")

    st.sidebar.markdown("**Target %:** The % price increase from entry you want to test hitting.")
    target_pct = st.sidebar.number_input("Target % (from entry)", 1.0, 100.0, 5.0, help="Target price percentage gain from trade entry")

    st.sidebar.markdown("**Max Trading Days:** Maximum number of trading days to hit the target from entry.")
    max_days = st.sidebar.number_input("Max Trading Days to Hit Target", 1, 100, 10, help="Days allowed to reach target price")

    st.sidebar.markdown("**Minimum Trades:** Minimum number of trades required to validate parameter combination.")
    min_trades = st.sidebar.number_input("Minimum Trades Required", 1, 100, 5, help="Minimum trades to consider a parameter valid")

    st.sidebar.markdown("**Minimum Accuracy:** Minimum accuracy % (target hits / trades) for parameter acceptance.")
    min_accuracy = st.sidebar.number_input("Minimum Accuracy %", 1, 100, 40, help="Minimum accuracy percentage to accept parameters")

    # -----------------------------
    # Run Optimization
    # -----------------------------
    if st.button("🚀 Run Optimization"):
        results = []

        for fast in range(fast_min, fast_max + 1):
            for slow in range(slow_min, slow_max + 1):
                if fast >= slow:  # restriction
                    continue
                for signal in range(signal_min, signal_max + 1):
                    df = data.copy()

                    # Compute MACD
                    macd_line = ta.trend.ema_indicator(df["Close"], window=fast) - ta.trend.ema_indicator(df["Close"], window=slow)
                    signal_line = macd_line.ewm(span=signal).mean()

                    df["MACD"] = macd_line
                    df["Signal"] = signal_line

                    # Entry condition: crossover
                    df["Crossover"] = (df["MACD"].shift(1) < df["Signal"].shift(1)) & (df["MACD"] > df["Signal"])

                    entries = df[df["Crossover"]].index
                    total_trades = len(entries)

                    if total_trades < min_trades:
                        continue

                    hits = 0
                    for entry in entries:
                        entry_price = df.loc[entry, "Close"]
                        target_price = entry_price * (1 + target_pct / 100)

                        # Look ahead for max_days
                        subset = df.loc[entry+1 : entry+max_days]
                        if (subset["Close"] >= target_price).any():
                            hits += 1

                    accuracy = (hits / total_trades) * 100 if total_trades > 0 else 0

                    if accuracy >= min_accuracy:
                        results.append({
                            "FastEMA": fast,
                            "SlowEMA": slow,
                            "SignalEMA": signal,
                            "Trades": total_trades,
                            "Hits": hits,
                            "Accuracy%": round(accuracy, 2)
                        })

        # -----------------------------
        # Show Results
        # -----------------------------
        if results:
            results_df = pd.DataFrame(results)
            results_df = results_df.sort_values("Accuracy%", ascending=False).reset_index(drop=True)

            st.success(f"✅ Found {len(results_df)} valid combinations")
            st.write("### Top 10 Results")
            top10 = results_df.head(10)
            st.dataframe(top10)

            # Download Buttons
            download_results(top10)

        else:
            st.warning("No parameter combinations matched your criteria.")


