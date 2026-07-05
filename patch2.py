
import re
import codecs
content = codecs.open('d:/okx/harmonic_agent/server.py', 'r', 'utf-8').read()
pattern = re.compile(r'(\s+if not block_reason:\s+)(# PROFITABILITY CHECK \(Live Fire Calibration\))')
replacement = r'''\1# --- USER REQUESTED REVERSAL (INVERSE TRADING) ---
                            # Inverse the strategy direction and swap TP/SL
                            p.direction = \'bearish\' if p.direction == \'bullish\' else \'bullish\'
                            orig_sl = plan[\'sl\']
                            plan[\'sl\'] = plan[\'tp1\']
                            plan[\'tp1\'] = orig_sl
                            plan[\'risk_reward\'] = round(1.0 / plan[\'risk_reward\'], 2) if plan[\'risk_reward\'] > 0 else 0
                            p.pattern_name = f\'Inverted {p.pattern_name}\'
                            
                            \2'''
if pattern.search(content):
    content = pattern.sub(replacement, content)
    codecs.open('d:/okx/harmonic_agent/server.py', 'w', 'utf-8').write(content)
    print('Patched successfully!')
else:
    print('Target not found.')

