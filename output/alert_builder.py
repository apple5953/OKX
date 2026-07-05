import json
from dataclasses import asdict

def build_alert(pattern: any, trade_plan: dict, filters: dict) -> str:
    alert_data = {
        "symbol": pattern.symbol,
        "timeframe": pattern.timeframe,
        "pattern": pattern.pattern_name,
        "direction": trade_plan["direction"],
        "status": pattern.status,
        "entry": trade_plan["entry"],
        "sl": trade_plan["sl"],
        "tp1": trade_plan["tp1"],
        "tp2": trade_plan["tp2"],
        "tp3": trade_plan["tp3"],
        "risk_reward": trade_plan["risk_reward"],
        "confidence": pattern.confidence,
        "prz_low": pattern.prz_low,
        "prz_high": pattern.prz_high,
        "filters": filters
    }
    return json.dumps(alert_data, indent=2)
