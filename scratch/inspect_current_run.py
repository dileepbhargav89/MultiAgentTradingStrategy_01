with open(r'C:\Users\DILEEP BHARGAV\.gemini\antigravity-ide\brain\9dbcfa54-8031-4a4b-a2be-928ec62dec55\.system_generated\tasks\task-1425.log', 'r') as f:
    lines = f.readlines()

wf = [l.strip() for l in lines if '[Walk-Forward]' in l]
print(f"Walk-forward checkpoints: {len(wf)}")
for l in wf:
    print(" ", l)

trades_closed = [l.strip() for l in lines if 'STOP LOSS triggered' in l or 'TP1 FILLED' in l or 'TP2 (2.5R RUNNER) FILLED' in l]
print(f"\nTotal trade events: {len(trades_closed)}")
tp1_cnt = sum(1 for l in trades_closed if 'TP1 FILLED' in l)
tp2_cnt = sum(1 for l in trades_closed if 'TP2' in l)
sl_cnt = sum(1 for l in trades_closed if 'STOP LOSS' in l)
print(f"TP1 hits: {tp1_cnt} | TP2 runner hits: {tp2_cnt} | SL hits: {sl_cnt}")
