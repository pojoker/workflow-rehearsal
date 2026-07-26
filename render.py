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
    # 知识库: 为什么层(须带证据引语+出处)。按格索引,渲进对应格 + 独立页
    kb=[]
    kp=os.path.join(ROOT,'knowledge.yaml')
    if os.path.exists(kp): kb=yaml.safe_load(open(kp,encoding='utf-8')).get('knowledge',[]) or []
    kb=sorted(kb,key=lambda k:k['id'])
    kbycell={}
    for k in kb:
        for c in (k.get('格') or []): kbycell.setdefault(c,[]).append(k)
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
                for k in kbycell.get(n['cell_id'],[]):
                    # 主格(格列表首位)出全文,其余格只给指针,避免同一条知识重复刷屏
                    if (k.get('格') or [None])[0]==n['cell_id']:
                        L.append(f"> 📖 **{k['标题']}**（{k['id']}，全文见 out/知识库.md）")
                        for ln in k['一句话'].strip().split('\n'): L.append(f"> {ln}")
                    else:
                        L.append(f"> 📖 参见 {k['id']}　{k['标题']}（主格 {k['格'][0]}，全文见 out/知识库.md）")
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
    L+=['---',f"页脚：宇宙={tr['universe']['count']}家(冻结{tr['universe']['frozen_date']}) | 数据截至={max(dates) if dates else '—'} | 覆盖={cov} | 空叶格={len(empty)}/{len(meta)}: {','.join(empty) if empty else '无'}（纪律第8条 commit 取此数）"]
    os.makedirs(outdir,exist_ok=True)
    md='\n'.join(L)+'\n'
    open(os.path.join(outdir,'全景.md'),'w',encoding='utf-8').write(md)
    html='<!DOCTYPE html><meta charset="utf-8"><title>光模块供应链全景v2</title><body style="font-family:sans-serif;max-width:960px;margin:2em auto"><pre style="white-space:pre-wrap">'+md.replace('&','&amp;').replace('<','&lt;')+'</pre></body>'
    open(os.path.join(outdir,'全景.html'),'w',encoding='utf-8').write(html)
    # 知识库独立页: 每条=大白话结论+细说+判定用法+逐条证据(引语+出处+锚)
    K=['# 光模块产业知识库','',
       '> 本页由 render.py 从 knowledge.yaml 生成，勿手改（--verify 会拒绝）。',
       '> 回答"这个环节到底是干嘛的、为什么难、怎么判断谁够格"。每条都带证据引语与出处；没证据的常识不进本库。','']
    if not kb: K.append('（knowledge.yaml 为空）')
    for k in kb:
        cells='、'.join(k.get('格') or []) or '通用（不限某一格）'
        K+=[f"## {k['id']}　{k['标题']}",'',f"**适用环节**：{cells}　|　**录入**：{k.get('录入日期','—')}",'',
            '### 一句话','',k['一句话'].strip(),'']
        if k.get('说细点'): K+=['### 说细点','',k['说细点'].strip(),'']
        if k.get('怎么用它判断'): K+=['### 怎么用它判断','',k['怎么用它判断'].strip(),'']
        K+=['### 证据','']
        for e in (k.get('证据') or []):
            K.append(f"**{e['谁']}**")
            if e.get('原话'): K.append(f"> {e['原话']}")
            K.append(f"　出处：{e.get('出处','—')}")
            K.append(f"　锚：{e.get('锚','—')}")
            if e.get('说明'): K.append(f"　为什么算证据：{e['说明']}")
            K.append('')
        if k.get('关联点'): K+=[f"**关联点**：{'、'.join(k['关联点'])}",'']
        if k.get('关联判例'): K+=[f"**关联判例**：{k['关联判例']}",'']
        K+=['---','']
    K.append(f"页脚：知识条目 {len(kb)} 条 | 覆盖环节 {len(kbycell)} 个")
    kmd='\n'.join(K)+'\n'
    open(os.path.join(outdir,'知识库.md'),'w',encoding='utf-8').write(kmd)
    khtml='<!DOCTYPE html><meta charset="utf-8"><title>光模块产业知识库</title><body style="font-family:sans-serif;max-width:900px;margin:2em auto;line-height:1.7"><pre style="white-space:pre-wrap">'+kmd.replace('&','&amp;').replace('<','&lt;')+'</pre></body>'
    open(os.path.join(outdir,'知识库.html'),'w',encoding='utf-8').write(khtml)
if __name__=='__main__':
    if '--verify' in sys.argv:
        tmp=tempfile.mkdtemp(); build(tmp)
        ok=all(filecmp.cmp(os.path.join(tmp,f),os.path.join(ROOT,'out',f),shallow=False) for f in ('全景.md','全景.html','知识库.md','知识库.html') if os.path.exists(os.path.join(ROOT,'out',f)))
        shutil.rmtree(tmp)
        if not ok: print('\033[31m[--verify] out/ 与重渲不一致(疑手改)\033[0m'); sys.exit(1)
        print('--verify: 一致')
    else:
        build(os.path.join(ROOT,'out')); print('out/ 已重建')
