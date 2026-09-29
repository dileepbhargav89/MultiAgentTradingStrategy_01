with open(r'C:\Users\DILEEP BHARGAV\.gemini\antigravity-ide\brain\9dbcfa54-8031-4a4b-a2be-928ec62dec55\.system_generated\tasks\task-1362.log', 'r') as f:
    lines = [l.strip() for l in f if 'STOP LOSS triggered' in l or 'TP1 FILLED' in l or 'TAKE PROFIT 2' in l or 'Position Inception' in l]

print(f"Total trade events: {len(lines)}")
for l in lines[-30:]:
    print(l)
