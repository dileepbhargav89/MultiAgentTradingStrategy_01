with open(r'C:\Users\DILEEP BHARGAV\.gemini\antigravity-ide\brain\9dbcfa54-8031-4a4b-a2be-928ec62dec55\.system_generated\tasks\task-1362.log', 'r') as f:
    lines = f.readlines()

sl_lines = [l.strip() for l in lines if 'STOP LOSS triggered' in l]
print(f"Total STOP LOSS lines: {len(sl_lines)}")
for l in sl_lines[-20:]:
    print(l)
