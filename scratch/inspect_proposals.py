with open(r'C:\Users\DILEEP BHARGAV\.gemini\antigravity-ide\brain\9dbcfa54-8031-4a4b-a2be-928ec62dec55\.system_generated\tasks\task-1362.log', 'r') as f:
    lines = [l.strip() for l in f if 'TradeProposal Generated' in l]

print(f"Total TradeProposal Generated: {len(lines)}")
for l in lines[-30:]:
    print(l)
