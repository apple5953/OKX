import codecs

with codecs.open('d:/okx/harmonic_agent/server.py', 'r', 'utf-8') as f:
    lines = f.readlines()
    
# Remove the duplicated block
del lines[558:753]

# Apply the intended fixes to the remaining file
content = ''.join(lines)

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
