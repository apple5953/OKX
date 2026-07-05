import pandas as pd
import numpy as np

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_divergence(df: pd.DataFrame, current_idx: int, lookback: int = 20, direction: str = "bullish") -> bool:
    if 'rsi' not in df.columns:
        df['rsi'] = calculate_rsi(df)
        
    if current_idx < lookback:
        return False
        
    recent_data = df.iloc[current_idx-lookback:current_idx+1]
    
    if direction == "bullish":
        price_low_idx = recent_data['low'].idxmin()
        if price_low_idx == current_idx:
            past_data = recent_data.iloc[:-1]
            if not past_data.empty:
                prev_low_idx = past_data['low'].idxmin()
                if df['rsi'].iloc[current_idx] > df['rsi'].iloc[prev_low_idx]:
                    return True
    else:
        price_high_idx = recent_data['high'].idxmax()
        if price_high_idx == current_idx:
            past_data = recent_data.iloc[:-1]
            if not past_data.empty:
                prev_high_idx = past_data['high'].idxmax()
                if df['rsi'].iloc[current_idx] < df['rsi'].iloc[prev_high_idx]:
                    return True
                    
    return False
