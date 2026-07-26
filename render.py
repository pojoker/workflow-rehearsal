#!/usr/bin/env python3
"""render.py — tree.yaml+csv→out/全景.md+.html 幂等确定性渲染。--verify: 重渲比对防手改。"""
import os,csv,sys,yaml,filecmp,tempfile,shutil
ROOT=os.path.dirname(os.path.abspath(__file__))
def rows(f):
    p=os.path.join(ROOT,f)
    return list(csv.DictReader(open(p,encoding='utf-8-sig'))) if os.path.exists(p) else []
def build(outdir):
    tr=yaml.safe_load(open(os.path.join(ROOT,'tree.yaml'),encoding='utf-8'))
    pts,egs=rows('points.csv'),rows('edges.csv')
    bycell={}
    for p in pts: bycell.setdefault(p['cell_id'],[]).append(p)
    L=['# 光模块产业结构与公司能力地图（点先行 v2）','',
       '> 本页由 render.py 生成，勿手改（--verify 会拒绝）。',
       '> 回答三问：①产业由哪些环节构成 ②不同技术路线异同 ③每格谁在做、证据是什么。',
       '> 不回答"A是不是B的供应商"——公司按证据挂结构节点，不因同格而声称供货关系。','']
    # 先收元数据(名称+路线),供路线投影与流向复用
    meta={}
    def collect(n):
        if isinstance(n,list):
            for x in n: collect(x)
        elif isinstance(n,dict):
            if 'cell_id' in n: meta[n['cell_id']]=(n['名称'].strip(),(n.get('路线') or '未标').strip())
            for c in n.get('children',[]): collect(c)
    collect(tr['tree'])
    # 路线对比:39格按路线标签投影(纯渲染,零数据变更——标签本就在tree上)
    routes={}
    for cid,(_,rt) in meta.items(): routes.setdefault(rt,[]).append(cid)
    order=(['共用'] if '共用' in routes else [])+sorted(k for k in routes if k!='共用')
    L+=['## 技术路线对比（tree.yaml 路线标签投影）','',
        '共用骨干=三条路线都要经过的环节；独有格=该路线区别于其他路线之处。','',
        '| 路线 | 格数 | 有公司 | 空格 |','|---|---|---|---|']
    for r in order:
        cs=sorted(routes[r]); e=[c for c in cs if not bycell.get(c)]
        L.append(f"| {r} | {len(cs)} | {len(cs)-len(e)} | {','.join(e) if e else '—'} |")
    L.append('')
    for r in order:
        cs=sorted(routes[r])
        L.append(f"**{r}**（{len(cs)}格）："+'；'.join(f"{c} {meta[c][0]}({len(bycell.get(c,[]))}家)" for c in cs))
        L.append('')
    empty=[]
    def walk(n,dep):
        if isinstance(n,list):
            for x in n: walk(x,dep)
        elif isinstance(n,dict):
            if 'cell_id' in n:
                cs=bycell.get(n['cell_id'],[])
                L.append(f"{'#'*min(dep+1,6)} {n['cell_id']} {n['名称']}  ·路线:{n.get('路线','')}  ·{len(cs)}家")
                if cs:
                    L.append('| 公司 | 状态 | 上市 | 引语 | 锚 |'); L.append('|---|---|---|---|---|')
                    for p in sorted(cs,key=lambda x:x['公司']):
                        L.append(f"| {p['公司']} | {p['状态']} | {p['上市标签']} | {p['命中引语'][:60]} | [锚]({p['锚点URL']}) |")
                else:
                    empty.append(n['cell_id']); L.append('（空格——未有公司过闸）')
                L.append('')
            else:
                L.append(f"{'#'*min(dep,6)} {n.get('名称',n.get('id',''))}"); L.append('')
                for c in n.get('children',[]): walk(c,dep+1)
    walk(tr['tree'],2)
    # BOM流向:骨架(常识层)+已证边计数(edges.csv经point_id→cell聚合)
    names={c:m[0] for c,m in meta.items()}
    pid2cell={p['point_id']:p['cell_id'] for p in pts}
    cnt={}
    for e in egs:
        sc,dc=pid2cell.get(e.get('供方point_id','')),pid2cell.get(e.get('需方point_id',''))
        if sc and dc and sc!=dc: cnt[(sc,dc)]=cnt.get((sc,dc),0)+1
    L+=['---','## BOM流向（骨架=常识层免锚；括号=已证公司级边数，来自edges.csv）','']
    skel=set()
    for f in tr.get('flows',[]):
        s=f['from']
        for d in f['to']:
            skel.add((s,d))
            c=cnt.get((s,d),0)
            L.append(f"- {s} {names.get(s,'')} → {d} {names.get(d,'')}"+(f"  **(已证{c}边)**" if c else ''))
    extra=sorted((k,v) for k,v in cnt.items() if k not in skel)
    if extra:
        L+=['','骨架外已证流向（现实先于常识，待并入骨架或复核归格）：']
        for (s,d),c in extra: L.append(f"- {s} {names.get(s,'')} → {d} {names.get(d,'')} ({c}边)")
    L.append('')
    dates=[p['检索日期'] for p in pts if p.get('检索日期')]
    cov=f"{len(pts)}点/{len(egs)}边"
    L+=['---',f"页脚：宇宙={tr['universe']['count']}家(冻结{tr['universe']['frozen_date']}) | 数据截至={max(dates) if dates else '—'} | 覆盖={cov} | 空叶格={len(empty)}个: {','.join(empty) if empty else '无'}"]
    os.makedirs(outdir,exist_ok=True)
    md='\n'.join(L)+'\n'
    open(os.path.join(outdir,'全景.md'),'w',encoding='utf-8').write(md)
    html='<!DOCTYPE html><meta charset="utf-8"><title>光模块供应链全景v2</title><body style="font-family:sans-serif;max-width:960px;margin:2em auto"><pre style="white-space:pre-wrap">'+md.replace('&','&amp;').replace('<','&lt;')+'</pre></body>'
    open(os.path.join(outdir,'全景.html'),'w',encoding='utf-8').write(html)
if __name__=='__main__':
    if '--verify' in sys.argv:
        tmp=tempfile.mkdtemp(); build(tmp)
        ok=all(filecmp.cmp(os.path.join(tmp,f),os.path.join(ROOT,'out',f),shallow=False) for f in ('全景.md','全景.html') if os.path.exists(os.path.join(ROOT,'out',f)))
        shutil.rmtree(tmp)
        if not ok: print('\033[31m[--verify] out/ 与重渲不一致(疑手改)\033[0m'); sys.exit(1)
        print('--verify: 一致')
    else:
        build(os.path.join(ROOT,'out')); print('out/ 已重建')
