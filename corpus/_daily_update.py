#!/usr/bin/env python3
"""日更脚本(纯脚本零token,纪律2): 投关表/互动易/公告流三增量 + scan召回差分 + 一页日报。
用法: python3 corpus/_daily_update.py   (产出 tmp/daily/YYYY-MM-DD.md + tmp/daily/queue-latest.txt)
"""
import csv, datetime, glob, json, os, re, subprocess, sys, time
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
spec = importlib.util.spec_from_file_location('_fetch', 'corpus/_fetch.py')
fetch = importlib.util.module_from_spec(spec); sys.modules['_fetch'] = fetch; spec.loader.exec_module(fetch)
spec2 = importlib.util.spec_from_file_location('_fetch_ir', 'corpus/_fetch_ir.py')
fir = importlib.util.module_from_spec(spec2); sys.modules['_fetch_ir'] = fir; spec2.loader.exec_module(fir)
spec3 = importlib.util.spec_from_file_location('_fetch_qa', 'corpus/_fetch_qa.py')
fqa = importlib.util.module_from_spec(spec3); sys.modules['_fetch_qa'] = spec3.loader and fqa
sys.modules['_fetch_qa'] = fqa; spec3.loader.exec_module(fqa)

TODAY = datetime.date.today().isoformat()
DAY3 = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
DAY14 = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
KW = re.compile(r'光模块|光通信|光器件|光引擎|光芯片|CPO|硅光|800G|1\.6T|相干|LPO|TOSA|ROSA|BOSA|FAU|MPO|AWG|DFB|EML|VCSEL|隔离器|插芯|耦合|固晶|贴片|键合|外延|MOCVD|磷化铟|InP', re.I)

frozen = {}
with open('corpus/_frozen.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        frozen[r['代码']] = r['名称']

def watched_codes():
    """待判行公司 ∪ 在建点公司 (宇宙内)"""
    codes = set()
    for r in csv.DictReader(open('triage.csv', encoding='utf-8-sig')):
        if r['处置'] == '待判':
            for c, n in frozen.items():
                if n == r['公司']:
                    codes.add(c)
    for r in csv.DictReader(open('points.csv', encoding='utf-8-sig')):
        if r['状态'] == '在建':
            for c, n in frozen.items():
                if n == r['公司']:
                    codes.add(c)
    return sorted(codes)

session = fetch.build_session()
digest = {'ir_new': [], 'qa_new': [], 'ann': [], 'q_delta_new': [], 'q_delta_gone': []}

# ---------- 1) 投关表全局增量(近3天) ----------
seen_titles = set()
hits = []
for tab, cat, titlef in (('relation', 'category_dyhd_szdy', None), ('fulltext', '', '投资者关系')):
    for page in (1, 2, 3):
        payload = {'pageNum': str(page), 'pageSize': '30', 'column': '', 'tabName': tab, 'plate': '',
                   'stock': '', 'searchkey': '', 'secid': '', 'category': cat, 'trade': '',
                   'seDate': f'{DAY3}~{TODAY}', 'sortName': '', 'sortType': '', 'isHLtitle': 'true'}
        try:
            r = session.post(fetch.QUERY_URL, data=payload, timeout=40)
            anns = r.json().get('announcements') or []
        except Exception:
            anns = []
        if not anns:
            break
        for a in anns:
            code = str(a.get('secCode') or '')
            if code not in frozen:
                continue
            title = fetch.clean_html_title(str(a.get('announcementTitle') or ''))
            if titlef and titlef not in title:
                continue
            url = str(a.get('adjunctUrl') or '')
            if not url.lower().endswith('.pdf'):
                continue
            key = code + title
            if key in seen_titles:
                continue
            seen_titles.add(key)
            hits.append((code, fetch.parse_announcement_date(a.get('announcementTime')), title, url))
        time.sleep(1.3)

for code, d, title, url in hits:
    ddir = os.path.join('corpus/ir', code)
    base = fetch.sanitize_filename(f'{code}_{d}_{title}.pdf')
    dst = os.path.join(ddir, base)
    if os.path.exists(dst):
        continue
    os.makedirs(ddir, exist_ok=True)
    try:
        full = fetch.build_pdf_url(url)
        r = session.get(full, headers={'Referer': 'https://www.cninfo.com.cn/'}, timeout=60)
        if not r.content.startswith(b'%PDF'):
            continue
        open(dst, 'wb').write(r.content)
        subprocess.run(['pdftotext', '-layout', dst, dst + '.txt'], capture_output=True)
        digest['ir_new'].append((frozen[code], d, title))
    except Exception:
        pass
    time.sleep(1.3)

# ---------- 2) 互动易增量(关注公司) ----------
# 教训2026-08-08: 曾用14天窗口抓取,fetch()会整体重写qa.jsonl,把窗口外的历史问答(含P195点锚)冲掉,
# 不变量⑩当场拦截。日更必须全量抓取(since=2023-01-01),由fetcher自身限速,文件仍是全量快照。
for c in watched_codes():
    try:
        before = 0
        fp = f'corpus/qa/{c}/qa.jsonl'
        if os.path.exists(fp):
            before = sum(1 for _ in open(fp, encoding='utf-8'))
        n = fqa.fetch(c, '2023-01-01')
        after = sum(1 for _ in open(fp, encoding='utf-8')) if os.path.exists(fp) else 0
        if n and after > before:
            digest['qa_new'].append((frozen[c], after - before))
    except Exception as e:
        print(f'[qa {c}] {str(e)[:60]}')
    time.sleep(1.5)

# ---------- 3) 公告流(关注公司近3天,标题模式) ----------
ANN_PAT = re.compile(r'重大合同|向特定对象|定增|业绩预告|业绩快报|问询|回复|收购|资产重组')
for c in watched_codes():
    payload = {'pageNum': '1', 'pageSize': '15', 'column': '', 'tabName': 'fulltext', 'plate': '',
               'stock': '', 'searchkey': c, 'secid': '', 'category': '', 'trade': '',
               'seDate': f'{DAY3}~{TODAY}', 'sortName': '', 'sortType': '', 'isHLtitle': 'true'}
    try:
        r = session.post(fetch.QUERY_URL, data=payload, timeout=30)
        for a in r.json().get('announcements') or []:
            if str(a.get('secCode') or '') != c:
                continue
            t = fetch.clean_html_title(str(a.get('announcementTitle') or ''))
            if ANN_PAT.search(t):
                digest['ann'].append((frozen[c], fetch.parse_announcement_date(a.get('announcementTime')), t,
                                      'https://static.cninfo.com.cn/' + str(a.get('adjunctUrl') or '').lstrip('/')))
    except Exception:
        pass
    time.sleep(1.3)

# ---------- 4) scan 召回差分 ----------
prev_file = 'tmp/daily/queue-latest.txt'
prev = set()
if os.path.exists(prev_file):
    prev = set(open(prev_file, encoding='utf-8').read().splitlines())
os.makedirs('tmp/daily', exist_ok=True)
os.rename(prev_file, 'tmp/daily/queue-prev.txt') if os.path.exists(prev_file) else None
scan_out = subprocess.run(['python3', 'scan.py'], capture_output=True, text=True).stdout
cur = []
for m in re.finditer(r'\[(?:空格|参与|  )\]\s*(\S+) \| (\S+) \| (.+?) \| (.+)', scan_out):
    cur.append(f'{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}')
with open(prev_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(cur))
new_hits = [x for x in cur if x.split('|')[0] + '|' + x.split('|')[1] not in {p.split('|')[0] + '|' + p.split('|')[1] for p in prev}]
gone = [x for x in prev if x.split('|')[0] + '|' + x.split('|')[1] not in {c.split('|')[0] + '|' + c.split('|')[1] for c in cur}]
digest['q_delta_new'] = new_hits[:15]
digest['q_delta_gone'] = gone[:5]

chk = subprocess.run(['python3', 'scan.py', '--check'], capture_output=True, text=True).stdout
chk_line = [l for l in chk.splitlines() if '全绿' in l or '[' in l]
stale = [l for l in chk.splitlines() if '语料' in l]

# ---------- 5) 写日报 ----------
out = [f'# 日报 {TODAY}', '', '## 语料', *[f'- {l}' for l in stale], '']
out.append(f'## 投关表新增 {len(digest["ir_new"])} 份')
for n, d, t in digest['ir_new'][:20]:
    out.append(f'- {n} | {d} | {t[:60]}')
out.append(f'\n## 互动易增量 {sum(x[1] for x in digest["qa_new"])} 条')
for n, k in digest['qa_new']:
    out.append(f'- {n} +{k}条')
out.append(f'\n## 公告流(关注公司) {len(digest["ann"])} 条')
for n, d, t, u in digest['ann'][:15]:
    out.append(f'- {n} | {d} | [{t[:50]}]({u})')
out.append(f'\n## 召回净队列差分: 新增{len(new_hits)} / 消失{len(gone)}')
for x in digest['q_delta_new']:
    co, cell, w, seg = x.split('|', 3)
    out.append(f'- [{co}|{cell}] {w} | {seg[:60]}')
out.append(f'\n## 校验')
for l in chk_line[:3]:
    out.append(f'- {l}')
evidence_hint = bool(digest['ir_new'] or digest['qa_new'] or digest['ann'] or new_hits)
out.append(f'\n> 判定闸建议: {"有增量,值得开闸复核" if evidence_hint else "无实质增量,今日免开闸"}')
open(f'tmp/daily/{TODAY}.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('\n'.join(out[:8]))
print(f'...\n日报: tmp/daily/{TODAY}.txt')
