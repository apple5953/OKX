HARMONIC_RULES = {
    "Gartley": {
        "AB_XA": (0.618, 0.618),
        "BC_AB": (0.382, 0.886),
        "CD_BC": (1.272, 1.618),
        "AD_XA": (0.786, 0.786),
    },
    "Bat": {
        "AB_XA": (0.382, 0.500),
        "BC_AB": (0.382, 0.886),
        "CD_BC": (1.618, 2.618),
        "AD_XA": (0.886, 0.886),
    },
    "Alt Bat": {
        "AB_XA": (0.382, 0.382),
        "BC_AB": (0.382, 0.886),
        "CD_BC": (2.0, 3.618),
        "AD_XA": (1.13, 1.13),
    },
    "Butterfly": {
        "AB_XA": (0.786, 0.786),
        "BC_AB": (0.382, 0.886),
        "CD_BC": (1.618, 2.618),
        "AD_XA": (1.27, 1.618),
    },
    "Crab": {
        "AB_XA": (0.382, 0.618),
        "BC_AB": (0.382, 0.886),
        "CD_BC": (2.24, 3.618),
        "AD_XA": (1.618, 1.618),
    },
    "Deep Crab": {
        "AB_XA": (0.886, 0.886),
        "BC_AB": (0.382, 0.886),
        "CD_BC": (2.0, 3.618),
        "AD_XA": (1.618, 1.618),
    },
    "Cypher": {
        "AB_XA": (0.382, 0.618),
        "XC_XA": (1.13, 1.414),
        "CD_XC": (0.786, 0.786),
    },
    "Shark": {
        "AB_XA": (1.13, 1.618),
        "BC_AB": (1.618, 2.24),
        "CD_XC": (0.886, 1.13),
    },
}

def in_range(value: float, min_v: float, max_v: float, tolerance: float = 0.10, rule_type: str = "general") -> bool:
    if rule_type == "AB_XA":
        tol = tolerance * 0.5  # Strict B point
    elif rule_type in ["CD_BC", "AD_XA", "CD_XC"]:
        tol = tolerance * 1.5  # Loose D point
    else:
        tol = tolerance
        
    lower = min_v * (1 - tol)
    upper = max_v * (1 + tol)
    return lower <= value <= upper
