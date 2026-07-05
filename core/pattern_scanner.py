from .pivot_detector import PivotPoint
from .pattern_rules import HARMONIC_RULES, in_range
from .prz_engine import calculate_prz
from dataclasses import dataclass

@dataclass
class HarmonicPattern:
    symbol: str
    timeframe: str
    pattern_name: str
    direction: str  

    x: PivotPoint
    a: PivotPoint
    b: PivotPoint
    c: PivotPoint
    d: PivotPoint | None

    prz_low: float
    prz_high: float
    prz_center: float

    confidence: float
    status: str 

def scan_patterns(pivots: list[PivotPoint], tolerance: float = 0.10) -> list[HarmonicPattern]:
    found_patterns = []
    
    for i in range(len(pivots) - 4):
        p1, p2, p3, p4, p5 = pivots[i:i+5]
        
        if p1.type == "high" and p2.type == "low" and p3.type == "high" and p4.type == "low" and p5.type == "high":
            direction = "bearish"
        elif p1.type == "low" and p2.type == "high" and p3.type == "low" and p4.type == "high" and p5.type == "low":
            direction = "bullish"
        else:
            continue
            
        x, a, b, c, d = p1.price, p2.price, p3.price, p4.price, p5.price
        
        xa = abs(a - x)
        ab = abs(b - a)
        bc = abs(c - b)
        cd = abs(d - c)
        ad = abs(a - d)
        xc = abs(c - x)
        
        if xa == 0 or ab == 0 or bc == 0 or xc == 0: continue
            
        ab_xa = ab / xa
        bc_ab = bc / ab
        cd_bc = cd / bc
        ad_xa = ad / xa
        bc_xa = bc / xa
        xc_xa = xc / xa
        cd_xc = cd / xc
        
        for name, rules in HARMONIC_RULES.items():
            is_valid = True
            
            # ONLY validate the historical X-A-B-C formation. 
            # We do NOT validate D here, because D is dynamically ticking towards the PRZ.
            if "AB_XA" in rules and not in_range(ab_xa, rules["AB_XA"][0], rules["AB_XA"][1], tolerance, "AB_XA"): is_valid = False
            if "BC_AB" in rules and not in_range(bc_ab, rules["BC_AB"][0], rules["BC_AB"][1], tolerance, "BC_AB"): is_valid = False
            if "XC_XA" in rules and not in_range(xc_xa, rules["XC_XA"][0], rules["XC_XA"][1], tolerance, "XC_XA"): is_valid = False
            if "BC_XA" in rules and not in_range(bc_xa, rules["BC_XA"][0], rules["BC_XA"][1], tolerance, "BC_XA"): is_valid = False
                
            if is_valid:
                prz = calculate_prz(x, a, b, c, name, direction)
                if not prz.get('is_valid_prz', True):
                    continue # PRZ levels are too scattered to form a valid zone
                
                confidence = 100.0 - (tolerance * 100)
                
                pattern = HarmonicPattern(
                    symbol="UNKNOWN", timeframe="UNKNOWN", pattern_name=f"{direction.capitalize()} {name}",
                    direction=direction, x=p1, a=p2, b=p3, c=p4, d=p5,
                    prz_low=prz['prz_low'], prz_high=prz['prz_high'], prz_center=prz['center'],
                    confidence=confidence, status="potential"
                )
                found_patterns.append(pattern)
                
    return found_patterns
