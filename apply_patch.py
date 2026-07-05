import codecs

with codecs.open('d:/okx/harmonic_agent/server.py', 'r', 'utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, l in enumerate(lines):
    if 'cl_ord_id = f"H{strategy_name}{uuid.uuid4().hex[:8]}"' in l:
        indent = l[:len(l) - len(l.lstrip())]
        new_lines.append(indent + "actual_leverage = lev\n")
        new_lines.append(indent + "break\n")
        new_lines.append(indent[:-4] + "except Exception:\n")
        new_lines.append(indent + "continue\n")
        new_lines.append("\n")
        new_lines.append(indent[:-4] + "# Dynamic Position Sizing (Fixed 60U Base * ML Confidence)\n")
        new_lines.append(indent[:-4] + "base_margin = 60\n")
        new_lines.append(indent[:-4] + "margin_usdt = base_margin * max(0.2, confidence)\n")
        new_lines.append(indent[:-4] + "target_notional = margin_usdt * actual_leverage\n")
        new_lines.append(indent[:-4] + "current_price = df.iloc[-1]['close']\n")
        new_lines.append(indent[:-4] + "contract_size = okx.markets[symbol]['contractSize']\n")
        new_lines.append(indent[:-4] + "raw_size = target_notional / (current_price * float(contract_size))\n")
        new_lines.append(indent[:-4] + "size = max(1, int(raw_size))\n")
        new_lines.append("\n")
        new_lines.append(indent[:-4] + "# --- STRICT INVERSE LOGIC (USER'S Wick-Hunting Edge) ---\n")
        new_lines.append(indent[:-4] + "side = 'sell' if side == 'buy' else 'buy'\n")
        new_lines.append(indent[:-4] + "orig_sl_dist = abs(current_price - plan['sl'])\n")
        new_lines.append(indent[:-4] + "orig_tp_dist = abs(plan['tp1'] - current_price)\n")
        new_lines.append("\n")
        new_lines.append(indent[:-4] + "if side == 'buy':\n")
        new_lines.append(indent + "plan['sl'] = current_price - orig_tp_dist\n")
        new_lines.append(indent + "plan['tp1'] = current_price + orig_sl_dist\n")
        new_lines.append(indent[:-4] + "else:\n")
        new_lines.append(indent + "plan['sl'] = current_price + orig_tp_dist\n")
        new_lines.append(indent + "plan['tp1'] = current_price - orig_sl_dist\n")
        new_lines.append("\n")
        new_lines.append(indent[:-4] + "signal_obj['sl'] = plan['sl']\n")
        new_lines.append(indent[:-4] + "signal_obj['tp1'] = plan['tp1']\n")
        new_lines.append(indent[:-4] + "signal_obj['original_tp_dist'] = abs(plan['tp1'] - current_price)\n")
        new_lines.append(indent[:-4] + "signal_obj['direction'] = 'long' if side == 'buy' else 'short'\n")
        new_lines.append(indent[:-4] + "signal_obj['pattern'] = 'WickHunter Inverted ' + signal_obj['pattern']\n")
        new_lines.append(indent[:-4] + "# ------------------------------------------------\n")
        new_lines.append(l)
    else:
        new_lines.append(l)

content = "".join(new_lines)
# Fix 1: active_min_profit
content = content.replace('active_min_profit = 0.0008', 'active_min_profit = 0.003')
content = content.replace('<0.08%', '<0.3%')

# Fix 2: trailing stop
content = content.replace('if highest_progress >= 0.3 and highest_progress < 0.6:', 'if highest_progress >= 0.6 and highest_progress < 0.8:')
content = content.replace('elif highest_progress >= 0.6:', 'elif highest_progress >= 0.8:')
content = content.replace('locked_progress = highest_progress - 0.3', 'locked_progress = highest_progress - 0.4')

with codecs.open('d:/okx/harmonic_agent/server.py', 'w', 'utf-8') as f:
    f.write(content)
print('Fixed file perfectly!')
