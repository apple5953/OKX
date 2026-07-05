def build_trade_plan(direction: str, x_price: float, a_price: float, c_price: float, d_price: float, pattern: str, min_rr: float = 1.5, sl_buffer_pct: float = 0.20) -> dict:
    move_ad = abs(a_price - d_price)
    
    # Calculate SL buffer dynamically based on the current price and the strategy's aggressiveness
    # sl_buffer_pct is passed as a percentage of the price (e.g., 0.02 for 2%)
    sl_buffer = max(d_price * sl_buffer_pct, d_price * 0.002)
    
    if "Gartley" in pattern or ("Bat" in pattern and "Alt" not in pattern) or "Cypher" in pattern:
        use_x_for_sl = True
    else:
        use_x_for_sl = False

    if direction == "bullish":
        tp1 = d_price + move_ad * 0.382
        tp2 = d_price + move_ad * 0.618
        tp3 = c_price
        
        base_price = min(d_price, x_price) if use_x_for_sl else d_price
        sl = base_price - sl_buffer
        # Enforce minimum 1.5% stop loss distance from entry (d_price) to prevent narrow stop outs
        min_sl_dist = d_price * 0.015
        if abs(d_price - sl) < min_sl_dist:
            sl = d_price - min_sl_dist
            
    else:
        tp1 = d_price - move_ad * 0.382
        tp2 = d_price - move_ad * 0.618
        tp3 = c_price
        
        base_price = max(d_price, x_price) if use_x_for_sl else d_price
        sl = base_price + sl_buffer
        # Enforce minimum 1.5% stop loss distance from entry (d_price) to prevent narrow stop outs
        min_sl_dist = d_price * 0.015
        if abs(sl - d_price) < min_sl_dist:
            sl = d_price + min_sl_dist

    must_close_tp1 = False
    if "Shark" in pattern:
        if direction == "bullish":
            tp1 = max(tp1, d_price + move_ad * 0.5)
        else:
            tp1 = min(tp1, d_price - move_ad * 0.5)
        must_close_tp1 = True

    # Note: Theoretical Risk/Reward from D point. Server will recalculate actual RR using Real-Time Entry Price.
    risk = abs(d_price - sl)
    reward = abs(tp1 - d_price)
    rr = reward / risk if risk > 0 else 0

    return {
        "direction": direction,
        "entry": d_price, # Theoretical Entry (D Point)
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk_reward": round(rr, 2), # Theoretical RR
        "must_close_tp1": must_close_tp1
    }
