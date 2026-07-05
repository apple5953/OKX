import pandas as pd

def is_reversal_candle(df: pd.DataFrame, index: int, direction: str) -> bool:
    if index < 1:
        return False
        
    # Evaluate the current candle as it enters the PRZ. 
    # For real-time harmonic execution, we want to catch the exact moment the price rejects from the PRZ limits.
        
    curr = df.iloc[index]
    prev = df.iloc[index - 1]
    
    curr_body = abs(curr['close'] - curr['open'])
    prev_body = abs(prev['close'] - prev['open'])
    
    if direction == "bullish":
        # Crypto Engulfing: Current body is larger than previous, closes above previous open, and it's a green candle
        is_engulfing = (prev['close'] <= prev['open'] and 
                        curr['close'] > curr['open'] and 
                        curr['close'] > prev['open'] and 
                        curr_body > prev_body * 1.05)
                        
        lower_wick = min(curr['open'], curr['close']) - curr['low']
        upper_wick = curr['high'] - max(curr['open'], curr['close'])
        # Crypto Pin Bar: Lower wick is at least 1.5x the body, and upper wick is relatively small
        is_pin_bar = lower_wick > curr_body * 1.5 and upper_wick < lower_wick * 0.8
        
        return is_engulfing or is_pin_bar
        
    else:
        # Crypto Engulfing: Current body is larger than previous, closes below previous open, and it's a red candle
        is_engulfing = (prev['close'] >= prev['open'] and 
                        curr['close'] < curr['open'] and 
                        curr['close'] < prev['open'] and 
                        curr_body > prev_body * 1.05)
                        
        lower_wick = min(curr['open'], curr['close']) - curr['low']
        upper_wick = curr['high'] - max(curr['open'], curr['close'])
        # Crypto Pin Bar: Upper wick is at least 1.5x the body, and lower wick is relatively small
        is_pin_bar = upper_wick > curr_body * 1.5 and lower_wick < upper_wick * 0.8
        
        return is_engulfing or is_pin_bar
