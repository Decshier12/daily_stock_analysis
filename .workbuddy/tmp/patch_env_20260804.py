import re

p = 'G:/daily_stock_analysis/.env'
s = open(p, encoding='utf-8').read()

rules = [
    (r'(?m)^USE_PROXY=true', 'USE_PROXY=false'),
    (r'(?m)^HTTP_PROXY=http://127\.0\.0\.1:10809', 'HTTP_PROXY='),
    (r'(?m)^HTTPS_PROXY=http://127\.0\.0\.1:10809', 'HTTPS_PROXY='),
    (r'(?m)^AGENT_MODE=true', 'AGENT_MODE=false'),
    (r'(?m)^AGENT_SKILLS=bull_trend,growth_quality,box_oscillation,emotion_cycle,shrink_pullback', 'AGENT_SKILLS='),
    (r'(?m)^MARKET_REVIEW_ENABLED=true', 'MARKET_REVIEW_ENABLED=false'),
    (r'(?m)^DAILY_MARKET_CONTEXT_ENABLED=true', 'DAILY_MARKET_CONTEXT_ENABLED=false'),
    (r'(?m)^BARK_DEVICE_KEY=p6tv2BL4n6GKyvAGYMzqvS', 'BARK_DEVICE_KEY='),
]

for pat, rep in rules:
    s, n = re.subn(pat, rep, s)
    assert n == 1, f'expected exactly 1 match for {pat!r}, got {n}'

open(p, 'w', encoding='utf-8').write(s)
print('PATCH OK; applied', len(rules), 'replacements')
