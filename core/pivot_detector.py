import pandas as pd
import numpy as np
from dataclasses import dataclass

@dataclass
class PivotPoint:
    index: int
    time: str
    price: float
    type: str  # "high" or "low"

def detect_pivots(df: pd.DataFrame, depth: int = 5) -> list[PivotPoint]:
    pivots = []
    for i in range(depth, len(df) - depth):
        is_high = all(df['high'].iloc[i] >= df['high'].iloc[i-depth:i]) and \
                  all(df['high'].iloc[i] >= df['high'].iloc[i+1:i+depth+1])
        is_low = all(df['low'].iloc[i] <= df['low'].iloc[i-depth:i]) and \
                 all(df['low'].iloc[i] <= df['low'].iloc[i+1:i+depth+1])
        
        if is_high:
            pivots.append(PivotPoint(i, str(df['time'].iloc[i]), df['high'].iloc[i], "high"))
        elif is_low:
            pivots.append(PivotPoint(i, str(df['time'].iloc[i]), df['low'].iloc[i], "low"))
            
    filtered_pivots = []
    for p in pivots:
        if not filtered_pivots:
            filtered_pivots.append(p)
        else:
            last_p = filtered_pivots[-1]
            if last_p.type != p.type:
                filtered_pivots.append(p)
            else:
                if p.type == "high" and p.price > last_p.price:
                    filtered_pivots[-1] = p
                elif p.type == "low" and p.price < last_p.price:
                    filtered_pivots[-1] = p
                    
    return filtered_pivots
