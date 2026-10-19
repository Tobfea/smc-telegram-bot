import sys
import yfinance as yf
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# List of major assets for the heatmap
HEATMAP_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"]

def get_market_data(symbol):
    """Fetches Daily and 1-Hour data from Yahoo Finance."""
    yf_symbol = f"{symbol.upper()}=X" if not symbol.endswith("=X") else symbol.upper()
    try:
        df_d1 = yf.download(yf_symbol, period="3mo", interval="1d", progress=False)
        df_h1 = yf.download(yf_symbol, period="10d", interval="1h", progress=False)
        
        if isinstance(df_d1.columns, pd.MultiIndex):
            df_d1.columns = df_d1.columns.get_level_values(0)
        if isinstance(df_h1.columns, pd.MultiIndex):
            df_h1.columns = df_h1.columns.get_level_values(0)
            
        return df_d1, df_h1
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None, None

def analyze_smc(symbol):
    df_d1, df_h1 = get_market_data(symbol)
    if df_d1 is None or df_d1.empty or df_h1 is None or df_h1.empty:
        return None, None, None, None, None, None

    # Macro & Structure Bias
    d1_close = float(df_d1['Close'].iloc[-1])
    d1_sma = float(df_d1['Close'].rolling(50).mean().iloc[-1])
    d1_bias = "🟢 Bullish" if d1_close > d1_sma else "🔴 Bearish"
    
    h1_close = float(df_h1['Close'].iloc[-1])
    h1_sma = float(df_h1['Close'].rolling(20).mean().iloc[-1])
    h1_bias = "🟢 Bullish" if h1_close > h1_sma else "🔴 Bearish"
    
    # 1. FVG Detection (Daily)
    fvg_status = "None Detected"
    for i in range(len(df_d1) - 2, 2, -1):
        low_i = float(df_d1['Low'].iloc[i])
        high_i_min2 = float(df_d1['High'].iloc[i - 2])
        high_i = float(df_d1['High'].iloc[i])
        low_i_min2 = float(df_d1['Low'].iloc[i - 2])
        
        if low_i > high_i_min2:
            fvg_status = f"Bullish FVG ({round(high_i_min2, 4)} - {round(low_i, 4)})"
            break
        elif high_i < low_i_min2:
            fvg_status = f"Bearish FVG ({round(high_i, 4)} - {round(low_i_min2, 4)})"
            break

    # 2. Order Block (OB) Detection (H1)
    ob_status = "None Detected"
    for i in range(len(df_h1) - 2, 5, -1):
        o_curr = float(df_h1['Open'].iloc[i])
        c_curr = float(df_h1['Close'].iloc[i])
        o_prev = float(df_h1['Open'].iloc[i-1])
        c_prev = float(df_h1['Close'].iloc[i-1])
        
        # Bullish OB: Last down candle before strong green expansion
        if c_curr > o_curr and (c_curr - o_curr) > (float(df_h1['Close'].diff().abs().mean()) * 1.5):
            if c_prev < o_prev: # previous was bearish
                ob_status = f"Demand Zone / OB ({round(o_prev, 4)} - {round(c_prev, 4)})"
                break
        # Bearish OB: Last up candle before strong red drop
        elif c_curr < o_curr and (o_curr - c_curr) > (float(df_h1['Close'].diff().abs().mean()) * 1.5):
            if c_prev > o_prev: # previous was bullish
                ob_status = f"Supply Zone / OB ({round(c_prev, 4)} - {round(o_prev, 4)})"
                break

    # 3. Liquidity Pooling (EQH / EQL on H1)
    recent_highs = df_h1['High'].tail(24)
    recent_lows = df_h1['Low'].tail(24)
    liquidity_status = "No Clear Pool"
    
    # Check if recent highs cluster closely (Equal Highs - Buy Side Liquidity)
    max_high = recent_highs.max()
    min_low = recent_lows.min()
    
    high_count = sum(1 for h in recent_highs if abs(h - max_high) / max_high < 0.0008)
    low_count = sum(1 for l in recent_lows if abs(l - min_low) / min_low < 0.0008)
    
    if high_count >= 2:
        liquidity_status = f"Buy-Side Liquidity (EQH near {round(max_high, 4)})"
    elif low_count >= 2:
        liquidity_status = f"Sell-Side Liquidity (EQL near {round(min_low, 4)})"

    return d1_bias, h1_bias, fvg_status, ob_status, liquidity_status, round(d1_close, 5)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **Welcome to the Apex SMC Engine!**\n\n"
        "Institutional-grade market structure, FVG, Order Block, and Liquidity analysis bot.\n\n"
        "📌 **Commands:**\n"
        "• `/smc EURUSD` - Full top-down SMC report\n"
        "• `/heatmap` - Multi-pair market bias scan\n"
        "• `/help` - Usage guide"
    )
    await update.message.reply_markdown(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **SMC Bot Guide**\n\n"
        "• `/smc <PAIR>`: Analyzes D1 Macro bias, H1 structure, Fair Value Gaps, Order Blocks, and Liquidity pools.\n"
        "• `/heatmap`: Scans major pairs (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, XAUUSD) instantly."
    )
    await update.message.reply_markdown(help_text)

async def smc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper() if context.args else "EURUSD"
    await update.message.reply_text(f"🔍 Running institutional scan for {symbol}...")
    
    d1_bias, h1_bias, fvg, ob, liq, price = analyze_smc(symbol)
    if not d1_bias:
        await update.message.reply_text(f"❌ Could not fetch data for `{symbol}`. Try standard symbols like `EURUSD`, `GBPUSD`, `XAUUSD`.")
        return

    report = (
        f"🏛️ **APEX SMC REPORT: {symbol}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🗓️ **Daily Bias:** {d1_bias}\n"
        f"⏳ **H1 Structure:** {h1_bias}\n"
        f"📦 **Fair Value Gap:** {fvg}\n"
        f"🧱 **Order Block:** {ob}\n"
        f"🌊 **Liquidity Pool:** {liq}\n"
        f"📍 **Current Price:** `{price}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Tip: Align your intraday entries with the Daily expansion direction.*"
    )
    
    await update.message.reply_markdown(report)

async def heatmap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🗺️ Scanning major asset liquidity & bias matrix...")
    
    matrix_output = "🗺️ **MARKET STRUCTURE HEATMAP**\n━━━━━━━━━━━━━━━━━━━\n"
    
    for pair in HEATMAP_PAIRS:
        d1, h1, _, _, _, price = analyze_smc(pair)
        if d1:
            # Shorten icons for clean table alignment
            d_icon = "🟢" if "Bullish" in d1 else "🔴"
            h_icon = "🟢" if "Bullish" in h1 else "🔴"
            matrix_output += f"• **{pair}** ({price})\n  D1: {d_icon} | H1: {h_icon}\n"
        else:
            matrix_output += f"• **{pair}**: ❌ Data error\n"
            
    matrix_output += "━━━━━━━━━━━━━━━━━━━\n💡 *Green = Bullish | Red = Bearish*"
    await update.message.reply_markdown(matrix_output)

if __name__ == "__main__":
    TOKEN = "8861936572:AAGubadUWVGpX6BjCMbQAeh2NQHlCp6nmIU"  # <-- Replace with your BotFather token
    
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("smc", smc_command))
        app.add_handler(CommandHandler("heatmap", heatmap_command))
        
        print("🤖 Apex SMC Engine is online with advanced analytics...")
        app.run_polling()
    except Exception as e:
        print(f"CRITICAL STARTUP ERROR: {e}")