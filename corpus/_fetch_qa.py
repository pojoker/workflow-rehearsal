#!/usr/bin/env python3
"""从深交所互动易抓取公司问答 → corpus/qa/<代码>/qa.jsonl
用法: python3 corpus/_fetch_qa.py 代码1 代码2 ... [--since 2023-01-01]
- 互动易/董秘回答=准披露渠道,可作点锚(计划文档已批准);只有"回答"是证据,提问不是。
- 空回答("以公告为准"式)落地时打 empty 标记,扫描跳过。
- 单线程限速(纪律5);链路: queryKeyboardInfo→secid; searchResult(infoTypes=11)分页。
- 沪市(sns.sseinfo.com)未接入,调用沪市代码时如实报错。
jsonl 行: {code,secid,question,answer,answer_date,ask_date,index_id,empty,fetch_date,source}
"""
import sys,os,json,time,re,datetime
import requests

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
   'Referer':'https://irm.cninfo.com.cn/'}
EMPTY_PAT=re.compile(r'^(尊敬的投资者[，,]?)?(您好[！!。]?)?(感谢您?的?(关注|提问)[和与及]?(支持)?[！!。，,]?)*(请|敬请)?(您)?(关注|参考|以)公司?(定期报告|公告|披露)(为准)?[。！!]?(谢谢[！!。]?)?$')

def secid_of(code):
    r=requests.post('https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo',
                    data={'keyWord':code},headers=H,timeout=15)
    for d in (r.json().get('data') or []):
        if d.get('stockCode')==code: return d.get('secid'),d.get('shortName')
    return None,None


def fetch_sse(code,since):
    """上证e互动: company.do?stockcode= 取uid; userfeeds.do(typeCode=company,type=11)分页HTML解析"""
    r=requests.get('https://sns.sseinfo.com/company.do',params={'stockcode':code},
                   headers={'User-Agent':H['User-Agent'],'Referer':'https://sns.sseinfo.com/'},timeout=15)
    m=re.search(r'uid=(\d+)',r.text)
    nm=re.search(r'companyName[^>]*>\s*([^<(（\s]+)',r.text) or re.search(r'<title>\s*([^<(（]+)',r.text)
    if not m: print(f'[{code}] e互动uid未找到'); return None
    uid=m.group(1); name=(nm.group(1).strip() if nm else code)
    items=[];page=1
    while True:
        rr=requests.get('https://sns.sseinfo.com/ajax/userfeeds.do',
            params={'typeCode':'company','type':11,'pageSize':20,'uid':uid,'page':page},
            headers={'User-Agent':H['User-Agent'],'Referer':'https://sns.sseinfo.com/'},timeout=20)
        chunk=re.split(r'id="item-\d+"',rr.text)[1:]
        if not chunk: break
        items+=chunk; page+=1; time.sleep(2)
        if page>40: break
    out=[];today=datetime.date.today().isoformat()
    DATE=re.compile(r'(\d{4})年(\d{2})月(\d{2})日')
    for it in items:
        plain=re.sub(r'(§ *)+','§',re.sub(r'\s+',' ',re.sub(r'<[^>]+>','§',it)))
        dates=DATE.findall(plain)
        qm=re.search(r':[^§]*\('+code+r'\)§([^§]+)§',plain)
        am=re.search(r'◆§◆§([^§]{2,10})§([^§]{2,})§\|§收藏',plain)
        q=(qm.group(1).strip() if qm else '')
        a=(am.group(2).strip() if am else '')
        if am and name in ('上证e互动',code): name=am.group(1).strip()
        ad='-'.join(dates[1]) if len(dates)>1 else ''
        qd='-'.join(dates[0]) if dates else ''
        if ad and ad<since: continue
        out.append({'code':code,'secid':f'sse_uid{uid}','question':q,'answer':a,
            'answer_date':ad,'ask_date':qd,'index_id':'',
            'empty':bool(not a or EMPTY_PAT.match(re.sub(r'\s','',a)) or (len(a)<75 and ('披露为准' in a or '公告为准' in a))),
            'fetch_date':today,'source':'sns.sseinfo.com userfeeds.do(type=11)'})
    d=os.path.join(ROOT,'corpus','qa',code); os.makedirs(d,exist_ok=True)
    fp=os.path.join(d,'qa.jsonl')
    with open(fp,'w',encoding='utf-8') as f:
        for o in out: f.write(json.dumps(o,ensure_ascii=False)+'\n')
    print(f'[{code} {name}] {len(out)}条(空回答{sum(1 for o in out if o["empty"])}) → {fp}')
    return len(out)

def fetch(code,since):
    if code.startswith('6'):
        return fetch_sse(code,since)
    if not (code.startswith('0') or code.startswith('3')):
        print(f'[{code}] 北交所无互动平台,跳过(如实记缺口)'); return None
    secid,name=secid_of(code)
    if not secid:
        print(f'[{code}] secid未找到'); return None
    rows=[];page=1
    while True:
        r=requests.get('https://irm.cninfo.com.cn/newircs/search/searchResult',params={
            'stockCodes':f'{secid}_{code}','keywords':'','infoTypes':'11',
            'startDate':f'{since} 00:00:00',
            'endDate':datetime.date.today().strftime('%Y-%m-%d')+' 23:59:59',
            'pageNum':page,'pageSize':30,'onlyAttentionCompany':2},headers=H,timeout=20)
        d=r.json().get('data') or {}
        res=d.get('results') or []
        rows+=res
        if page>=int(d.get('totalPage') or 0) or not res: break
        page+=1; time.sleep(2)
    out=[]
    today=datetime.date.today().isoformat()
    for a in rows:
        ans=(a.get('attachedContent') or '').strip()
        def toi(x):
            try: return int(x)
            except: return 0
        ts=toi(a.get('attachedPubDate')) or toi(a.get('updateDate'))
        out.append({'code':code,'secid':secid,
            'question':(a.get('mainContent') or '').strip(),
            'answer':ans,
            'answer_date':datetime.date.fromtimestamp(ts/1000).isoformat() if ts else '',
            'ask_date':datetime.date.fromtimestamp(toi(a.get('pubDate'))/1000).isoformat() if toi(a.get('pubDate')) else '',
            'index_id':str(a.get('indexId') or ''),
            'empty':bool(not ans or EMPTY_PAT.match(re.sub(r'\s','',ans))),
            'fetch_date':today,
            'source':'irm.cninfo.com.cn searchResult(infoTypes=11)'})
    d=os.path.join(ROOT,'corpus','qa',code); os.makedirs(d,exist_ok=True)
    fp=os.path.join(d,'qa.jsonl')
    with open(fp,'w',encoding='utf-8') as f:
        for o in out: f.write(json.dumps(o,ensure_ascii=False)+'\n')
    n_empty=sum(1 for o in out if o['empty'])
    print(f'[{code} {name}] {len(out)}条(空回答{n_empty}) → {fp}')
    return len(out)

if __name__=='__main__':
    args=[a for a in sys.argv[1:] if not a.startswith('--')]
    since='2023-01-01'
    if '--since' in sys.argv: since=sys.argv[sys.argv.index('--since')+1]
    for c in args:
        try: fetch(c,since)
        except Exception as e: print(f'[{c}] 失败: {str(e)[:80]}')
        time.sleep(2.5)
