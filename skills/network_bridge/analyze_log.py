import re
log_path = r'C:\Users\Landis\Desktop\sigma - 副本\skills\network_bridge\logs\network_bridge_2026-07-19.log'
with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('=== 模拟扩展LLM视角: 14:19:46 委托 ===')
task = '打开携程搜索全季酒店宁波老外滩 7/23入住 7/24退房'
print(f'任务: {task}\n')

step = 0
for line in lines:
    if '14:19:4' not in line and '14:20:' not in line and '14:21:' not in line:
        continue
    if '[CONTENT]' not in line:
        continue
    text = line.split('[CONTENT] [INFO] ')[-1].strip()

    if 'snapshot START' in text:
        step += 1
    elif 'fill START' in text:
        print(f'  [{step}] FILL {text[:120]}')
    elif 'click START' in text:
        print(f'  [{step}] CLICK {text[:120]}')
    elif 'targeted_click START' in text:
        print(f'  [{step}] TARGETED_CLICK {text[:120]}')
    elif 'snapshot DONE' in text:
        url_m = re.search(r"url': '([^']+)", text)
        ref_m = re.search(r"refCount': (\d+)", text)
        sid_m = re.search(r"snapshotId': (\d+)", text)
        url = url_m.group(1)[:90] if url_m else '?'
        ref = ref_m.group(1) if ref_m else '?'
        sid = sid_m.group(1) if sid_m else '?'
        ss = ' [带截图]' if 'hasScreenshot' in text else ''
        print(f'  [{step}] SNAPSHOT #{sid} | {url} | {ref}元素{ss}')
    elif 'click |' in text or 'targeted_click |' in text:
        if "'clicked': True" in text:
            nav = ' [页跳转!]' if "'navigationDetected': True" in text else ''
            print(f'       => 点击成功{nav}')
        else:
            print(f'       => 点击失败')
    elif 'fill |' in text:
        print(f'       => 输入完成')

    if 'beian.miit' in line:
        print(f'\n      !! 导航到了 beian.miit.gov.cn (工信部) !!')
    if '14:21:28' in line and 'PARTIAL' in line:
        print(f'\n结果: 30轮用完, status=partial')
