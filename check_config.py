import requests, json
r = requests.get('http://127.0.0.1:8765/api/network-bridge/llm-configs')
data = r.json()
configs = data.get('configs', [])
print(f'LLM配置数: {len(configs)}')
for c in configs[:5]:
    print(f'  name={c.get("name")} model={c.get("model")} protocol={c.get("protocol")}')
if not configs:
    print('(空)')
