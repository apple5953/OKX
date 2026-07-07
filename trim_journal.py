import json, os, datetime

with open('journal_macmini_01.json', encoding='utf-8') as f:
    data = json.load(f)

print(f'Original: {len(data)} records')

# Keep last 3000 (newest = best training data)
kept = data[-3000:]
print(f'Keeping: {len(kept)} records')

# Backup original
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup = f'journal_macmini_01.backup_{ts}.json'
os.rename('journal_macmini_01.json', backup)
print(f'Backup: {backup}')

# Write trimmed
with open('journal_macmini_01.json', 'w', encoding='utf-8') as f:
    json.dump(kept, f, ensure_ascii=False)

new_size = os.path.getsize('journal_macmini_01.json') // 1024
print(f'New size: {new_size} KB')
