def calculate_prz(x: float, a: float, b: float, c: float, pattern_name: str, direction: str) -> dict:
    xa_diff = abs(a - x)
    ab_diff = abs(a - b)
    bc_diff = abs(b - c)
    
    levels = []
    
    if pattern_name in ["Gartley", "Bat", "Alt Bat", "Butterfly", "Crab", "Deep Crab"]:
        if pattern_name == "Gartley": ad_ratio = 0.786; bc_ext = 1.272
        elif pattern_name == "Bat": ad_ratio = 0.886; bc_ext = 2.0
        elif pattern_name == "Alt Bat": ad_ratio = 1.13; bc_ext = 2.0
        elif pattern_name == "Butterfly": ad_ratio = 1.272; bc_ext = 1.618
        elif pattern_name in ["Crab", "Deep Crab"]: ad_ratio = 1.618; bc_ext = 2.618
        else: ad_ratio = 1.0; bc_ext = 1.618
        
        if direction == "bullish":
            levels.append(a - xa_diff * ad_ratio)
            levels.append(c - bc_diff * bc_ext)
            levels.append(a - xa_diff) # AB=CD base
        else:
            levels.append(a + xa_diff * ad_ratio)
            levels.append(c + bc_diff * bc_ext)
            levels.append(a + xa_diff) # AB=CD base

    elif pattern_name == "Shark":
        if direction == "bullish":
            levels.append(c - abs(x - c) * 0.886)
        else:
            levels.append(c + abs(x - c) * 0.886)
            
    elif pattern_name == "Cypher":
        if direction == "bullish":
            levels.append(c - abs(x - c) * 0.786)
        else:
            levels.append(c + abs(x - c) * 0.786)

    if not levels:
        levels = [c]
        
    prz_low = min(levels)
    prz_high = max(levels)
    center = sum(levels) / len(levels)
    
    # Validation: A true PRZ must be clustered. 
    # If the distance between highest and lowest projection is > 2.5%, it's too wide.
    prz_spread_pct = (prz_high - prz_low) / center if center > 0 else 0
    is_valid_prz = prz_spread_pct <= 0.025
        
    return {
        "prz_low": prz_low,
        "prz_high": prz_high,
        "center": center,
        "is_valid_prz": is_valid_prz
    }
