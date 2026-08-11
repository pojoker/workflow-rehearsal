#!/usr/bin/env python3
"""scan.py — 扫描+不变量①-⑪。用法: python3 scan.py [--check]
--check: 只跑不变量(<10s)。扫描分母=corpus/annual(_frozen登记);legacy-input=证据库不参与扫描。"""
import sys,os,csv,re,glob,time,subprocess

ROOT=os.path.dirname(os.path.abspath(__file__))
ERR=[]
def fail(k,msg): ERR.append(f"[{k}] {msg}")

def rows(f):
    p=os.path.join(ROOT,f)
    return list(csv.DictReader(open(p,encoding='utf-8-sig'))) if os.path.exists(p) else []

def observation_names():
    """Read the small observation-list contract without requiring PyYAML."""
    text=open(os.path.join(ROOT,'tree.yaml'),encoding='utf-8').read()
    match=re.search(r'^observation_list:.*?^tree:',text,flags=re.M|re.S)
    if not match: return set()
    return set(re.findall(r'\{名称:\s*([^,}]+)',match.group(0)))

E_状态={'生产中','在建','传闻','宇宙外观察'}
E_标签={'A股','美股','港股','台股','日股','欧股','新三板','未上市私企','未上市国企','未上市(母上市)','未解析'}
E_数值类型={'占比','金额'}
E_单位={'元','万元','亿元','美元','万美元','百万美元','亿美元','欧元','万欧元'}
E_边等级={'实边','半边','推断A','推断B','推断C'}
E_来源={'扫描','线索','人工'}
E_处置={'已入点','已入边候选','驳回-碰撞','驳回-非本格','驳回-证据不足','待判'}
U2Y={'元':1,'万元':1e4,'亿元':1e8,'美元':7,'万美元':7e4,'百万美元':7e6,'亿美元':7e8,'欧元':8,'万欧元':8e4}

def staleness():
    fs=glob.glob(os.path.join(ROOT,'corpus/annual/**/*.pdf'),recursive=True)
    if not fs: print('[饥饿] corpus/annual 无语料'); return
    n=(time.time()-max(os.path.getmtime(f) for f in fs))/86400
    frozen={r['代码'] for r in rows('corpus/_frozen.csv')}
    # 有目录≠有语料: 须真含pdf才算覆盖(否则空目录静默冒充已覆盖,实测曾把31家缺口谎报成3家)
    have={os.path.basename(d) for d in glob.glob(os.path.join(ROOT,'corpus/annual/*'))
          if os.path.isdir(d) and glob.glob(d+'/**/*.pdf',recursive=True)}
    miss=sorted(frozen-have)
    print(f"[语料] 最新文件距今{n:.0f}天; 宇宙内缺席年报 {len(miss)} 家"+(f"(样例:{','.join(miss[:5])})" if miss else ''))
    if n>120: print("[黄灯] 语料距今>120天,该投喂了(README年报季提示)")

def invariants():
    pts,egs,trg=rows('points.csv'),rows('edges.csv'),rows('triage.csv')
    # ①分母: annual/<code> 必在_frozen
    frozen={r['代码'] for r in rows('corpus/_frozen.csv')}
    if not frozen: fail('①','corpus/_frozen.csv 缺失或为空')
    for d in glob.glob(os.path.join(ROOT,'corpus/annual/*')):
        c=os.path.basename(d)
        if os.path.isdir(d) and c not in frozen: fail('①',f'语料目录无分母行: {c}')
    # ②端点闭合
    pid={p['point_id'] for p in pts}|{'ANON','EXT'}
    for e in egs:
        for col in ('供方point_id','需方point_id'):
            if e.get(col,'') and e[col] not in pid: fail('②',f"{e.get('edge_id')} {col}={e[col]} 悬空")
    # ③自指(零豁免): 上市且非宇宙外观察 ⇒ 公司须∈_frozen名称或代码; 宇宙外观察须在tree观察名单
    obs=observation_names()
    fro_names={r['名称'] for r in rows('corpus/_frozen.csv')}
    for p in pts:
        if p['状态']=='宇宙外观察':
            if p['公司'] not in obs: fail('③',f"{p['公司']} 宇宙外观察但不在tree观察名单")
        elif p['上市标签'] in ('A股',):
            if p['公司'] not in fro_names and not any(p['公司'] in n or n in p['公司'] for n in fro_names):
                fail('③',f"{p['公司']} A股生产点不在_frozen分母(零豁免,须先入corpus)")
    # ④单位量级
    for e in egs:
        t=e.get('数值类型','')
        if t=='金额':
            if e.get('单位','') not in E_单位: fail('④',f"{e.get('edge_id')} 金额行单位非法:[{e.get('单位')}]")
            else:
                try:
                    v=float(str(e['数值']).replace(',',''))*U2Y[e['单位']]
                    if not (1e3<=v<=5e11): fail('④',f"{e.get('edge_id')} 金额换算{v:.0f}元越界(疑单位错)")
                except: fail('④',f"{e.get('edge_id')} 数值不可解析")
        elif t=='占比':
            try:
                v=float(str(e['数值']))
                if not (0<v<=100): fail('④',f"{e.get('edge_id')} 占比{v}越界")
            except: fail('④',f"{e.get('edge_id')} 占比不可解析")
    # ⑤枚举
    for p in pts:
        if p['状态'] not in E_状态: fail('⑤',f"points {p.get('point_id')} 状态非法:{p['状态']}")
        if p['上市标签'] not in E_标签: fail('⑤',f"points {p.get('point_id')} 上市标签非法:{p['上市标签']}")
    for e in egs:
        if e.get('数值类型') and e['数值类型'] not in E_数值类型: fail('⑤',f"{e.get('edge_id')} 数值类型非法")
        if e.get('边等级') and e['边等级'] not in E_边等级: fail('⑤',f"{e.get('edge_id')} 边等级非法:{e['边等级']}")
    for t in trg:
        if t['来源'] not in E_来源: fail('⑤',f"triage {t.get('hit_id')} 来源非法")
        if t['处置'] not in E_处置: fail('⑤',f"triage {t.get('hit_id')} 处置非法")
    for i,l in enumerate(open(os.path.join(ROOT,'words.txt'),encoding='utf-8')) if os.path.exists(os.path.join(ROOT,'words.txt')) else []:
        if l.strip() and not l.startswith('#') and l.count('|')!=3: fail('⑤',f"words.txt 第{i+1}行竖线数≠3")
    # ⑥白名单
    # 须与 .githooks/pre-commit 的 WL 逐字一致(两处重复定义,改一处必改另一处——今日已三次因漏改卡闸)
    # '.git': worktree 下 .git 是文件不是目录,不列入则误报越位(远程代理绕闸根因)
    WL={'README.md','CLAUDE.md','tree.yaml','knowledge.yaml','points.csv','edges.csv','triage.csv','words.txt',
        'scan.py','render.py','participation.py','make_participation_pdf.py',
        'build_detailed_capability_report.py','capability_details.csv',
        'route_bom.csv','macro_evidence.csv','shipments.csv',
        'RESTART-v2.md','CONTEXT.md','.gitignore','.git','.DS_Store'}
    for f in os.listdir(ROOT):
        if os.path.isfile(os.path.join(ROOT,f)) and f not in WL: fail('⑥',f'根目录白名单外文件: {f}')
    refs=os.listdir(os.path.join(ROOT,'refs')) if os.path.isdir(os.path.join(ROOT,'refs')) else []
    if len(refs)>8: fail('⑥',f'refs/文件数{len(refs)}>8(2026-08-04由6放宽,纪律4)')
    for m in glob.glob(os.path.join(ROOT,'**/*.md'),recursive=True):
        rel=os.path.relpath(m,ROOT)
        if not rel.startswith(('archive/','refs/','out/','corpus/','calls/','docs/')) and rel not in ('README.md','CLAUDE.md','RESTART-v2.md','CONTEXT.md'):
            fail('⑥',f'越位md: {rel}')
    # ⑦triage一致性
    pnames={p['公司'] for p in pts}
    for t in trg:
        if t['处置']=='已入点' and t['公司'] not in pnames: fail('⑦',f"triage {t['hit_id']} 已入点但points无此公司")
    # ⑧知识库: 无证据的"常识"不许入库;锚按型核验("已核验"三个字过不了闸)
    kp=os.path.join(ROOT,'knowledge.yaml')
    treetext=open(os.path.join(ROOT,'tree.yaml'),encoding='utf-8').read()
    cells=set(re.findall(r'cell_id:\s*([A-Za-z0-9]+)',treetext))
    eids={e['edge_id'] for e in egs}
    pids={p['point_id'] for p in pts}
    kn_ids=set()
    if os.path.exists(kp):
        try:
            import yaml; kb=yaml.safe_load(open(kp,encoding='utf-8')).get('knowledge',[]) or []
        except Exception as e:
            kb=[]; fail('⑧',f'knowledge.yaml 不可解析: {e}')
        for k in kb:
            i=k.get('id','?')
            if not re.fullmatch(r'KN\d{3}',str(i)): fail('⑧',f'知识id须为KN###: {i}')
            if i in kn_ids: fail('⑧',f'知识id重复: {i}')
            kn_ids.add(i)
            for f_ in ('标题','一句话'):
                if not (k.get(f_) or '').strip(): fail('⑧',f'{i} 缺{f_}')
            ev=k.get('证据') or []
            if not ev: fail('⑧',f'{i} 无证据(无证据的常识不入知识库)')
            for j,e in enumerate(ev):
                for f_ in ('谁','出处','锚型','锚'):
                    if not str(e.get(f_,'') or '').strip(): fail('⑧',f'{i} 证据[{j}] 缺{f_}'); break
                else:
                    t,a=e['锚型'],e['锚']
                    if t=='url':
                        if not str(a).startswith(('http://','https://')): fail('⑧',f'{i} 证据[{j}] url锚非链接: {str(a)[:40]}')
                    elif t=='local_file':
                        if '#' not in str(a): fail('⑧',f'{i} 证据[{j}] local_file锚缺#定位: {str(a)[:60]}')
                        elif not os.path.exists(os.path.join(ROOT,str(a).split('#')[0])): fail('⑧',f'{i} 证据[{j}] 文件不存在: {str(a).split("#")[0]}')
                    elif t=='ledger_ref':
                        if str(a) not in pids|eids: fail('⑧',f'{i} 证据[{j}] ledger_ref {a} 不在points/edges')
                    elif t=='search_protocol':
                        if not isinstance(a,dict) or not all(x in a for x in ('关键词','语料范围','检索日期','命中数')):
                            fail('⑧',f'{i} 证据[{j}] search_protocol须含 关键词/语料范围/检索日期/命中数')
                    elif t=='web_snapshot':
                        if not isinstance(a,dict) or not all(x in a for x in ('原URL','存档路径','抓取日期')):
                            fail('⑧',f'{i} 证据[{j}] web_snapshot须含 原URL/存档路径/抓取日期')
                        else:
                            if not str(a['原URL']).startswith(('http://','https://')): fail('⑧',f'{i} 证据[{j}] web_snapshot原URL非法')
                            if not os.path.exists(os.path.join(ROOT,str(a['存档路径']))): fail('⑧',f'{i} 证据[{j}] web_snapshot存档不存在: {a["存档路径"]}')
                    else: fail('⑧',f'{i} 证据[{j}] 锚型非法: {t}')
            for c in (k.get('格') or []):
                if c not in cells: fail('⑧',f'{i} 格 {c} 不在tree.yaml')
    # tree引用闭合: knowledge_ids/decision_ref 必须指向真实知识条目
    for ref in re.findall(r'knowledge_ids:\s*\[([^\]]*)\]',treetext):
        for x in [y.strip() for y in ref.split(',') if y.strip()]:
            if x not in kn_ids: fail('⑧',f'tree knowledge_ids {x} 不在knowledge.yaml')
    for x in re.findall(r'decision_ref:\s*(\S+?)[,}]',treetext):
        if x not in kn_ids: fail('⑧',f'tree decision_ref {x} 不在knowledge.yaml')
    # ⑨路线投影与宏观结论: route_bom每行必须映射或说明;宏观须MC###+A-D级
    rb=rows('route_bom.csv')
    rbid=set()
    for r in rb:
        i=r.get('route_item_id','?')
        if not re.fullmatch(r'RB\d{3}',i): fail('⑨',f'route_bom id须为RB###: {i}')
        if i in rbid: fail('⑨',f'route_bom id重复: {i}')
        rbid.add(i)
        st=r.get('mapping_status','')
        if st not in ('mapped','architecture_only','gap'): fail('⑨',f'{i} mapping_status非法: {st}')
        cs=[c.strip() for c in (r.get('cell_ids') or '').split(',') if c.strip()]
        for c in cs:
            if c not in cells: fail('⑨',f'{i} cell_id {c} 不在tree.yaml')
        if st=='mapped' and not cs: fail('⑨',f'{i} mapped但cell_ids为空')
        if st in ('architecture_only','gap') and not (r.get('mapping_note') or '').strip(): fail('⑨',f'{i} {st}须给mapping_note说明为何不映射')
    for r in rows('macro_evidence.csv'):
        if not re.fullmatch(r'MC\d{3}',r.get('claim_id','?')): fail('⑨',f"macro claim_id须为MC###: {r.get('claim_id')}")
        if r.get('证据等级') not in ('A','B','C','D'): fail('⑨',f"macro {r.get('claim_id')} 证据等级非法")
    # ⑪出货量推断层: shipments.csv 行级校验(ADR-0001)
    if os.path.exists(os.path.join(ROOT,'shipments.csv')):
        for r in rows('shipments.csv'):
            if not re.fullmatch(r'SE\d{3}',r.get('row_id','?')): fail('⑪',f"shipments row_id须为SE###: {r.get('row_id')}")
            lv = r.get('证据等级','')
            if lv not in ('B','C','D'): fail('⑪',f"{r.get('row_id')} 证据等级{lv}非法(推断层封顶C,B仅直接披露,禁A)")
            if str(r.get('情景标记','')).startswith('scenario') and lv!='D': fail('⑪',f"{r.get('row_id')} 情景行必须为D级")
            if r.get('单位','') not in ('只','颗','件','支','片','只/个','支/套','片/个','台','台/套','千克','千只','KK','万只','万颗','万个','万件','万支','万片','万平方米','万美元'): fail('⑪',f"{r.get('row_id')} 单位非法: {r.get('单位')}")
    # ⑩互动易qa车道: jsonl格式合法+必备键;点锚引用的qa快照必须存在且真含引语
    for qf in glob.glob(os.path.join(ROOT,'corpus/qa/*/qa.jsonl')):
        try:
            import json as _j
            for i,l in enumerate(open(qf,encoding='utf-8')):
                o=_j.loads(l)
                for k in ('code','question','answer','answer_date','index_id','empty','fetch_date'):
                    if k not in o: fail('⑩',f'{os.path.basename(os.path.dirname(qf))} qa.jsonl 第{i+1}行缺{k}'); break
        except Exception as e: fail('⑩',f'{qf} 不可解析: {e}')
    for p in pts:
        m=re.search(r'corpus/qa/(\d+)/qa\.jsonl',p.get('锚点URL','') or '')
        if m:
            qf=os.path.join(ROOT,f'corpus/qa/{m.group(1)}/qa.jsonl')
            if not os.path.exists(qf): fail('⑩',f"{p['point_id']} 引用qa快照不存在: {m.group(1)}"); continue
            quote=re.sub(r'\s+','',(p.get('命中引语') or '').strip('"').split('(互动易')[0].strip('"'))
            blob=re.sub(r'\s+','',open(qf,encoding='utf-8').read())
            if quote and quote not in blob: fail('⑩',f"{p['point_id']} 引语未在qa快照命中")



def scan():
    """全量扫描: words×corpus/annual → 净队列(剔除triage已处置), 空叶格优先(P6), hit_id=公司+cell+文件(P7)"""
    words=[]
    for l in open(os.path.join(ROOT,'words.txt'),encoding='utf-8'):
        if l.strip() and not l.startswith('#'):
            w,cell,ex,ctx=[x.strip() for x in l.split('|')]
            words.append((w,cell,ex,ctx))
    done={t['hit_id'] for t in rows('triage.csv')}
    pts=rows('points.csv'); filled={p['cell_id'] for p in pts}; known_companies={p['公司'] for p in pts}
    frozen={}
    fz_path=os.path.join(ROOT,'corpus/_frozen.csv')
    if os.path.exists(fz_path):
        for r in rows('corpus/_frozen.csv'): frozen[r['代码']]=r['名称']
    q=[]
    def recall_file(txt, co, fname):
        """单个语料文本跑词表,命中入净队列(公司名/代码双轨:annual按_em_文件名,ir按_frozen代码映射)"""
        try: t=re.sub(r'\s+','',open(txt,encoding='utf-8',errors='ignore').read())
        except: return
        for w,cell,ex,ctx in words:
            if cell=='ANY' and co in known_companies: continue
            for mm in list(re.finditer(re.escape(w),t))[:2]:
                seg=t[max(0,mm.start()-40):mm.end()+40]
                if ex and re.search(ex,seg): continue
                if ctx and ctx not in seg: continue
                hid=f'{co}+{cell}+{fname[:40]}'
                if hid in done: continue
                priority=1 if cell=='ANY' else (0 if cell not in filled else 2)
                q.append((priority,hid,co,cell,w,seg))
                break
    for d in sorted(glob.glob(os.path.join(ROOT,'corpus/annual/*/'))):
        for pdf in glob.glob(d+'**/*.pdf',recursive=True):
            txt=pdf+'.txt'
            if not os.path.exists(txt): subprocess.run(['pdftotext','-layout',pdf,txt],capture_output=True)
            m=re.search(r'_([^_]+)_em_',os.path.basename(pdf)); co=m.group(1) if m else os.path.basename(d.rstrip('/'))
            recall_file(txt, co, os.path.basename(pdf))
    # 投关表车道(2026-07-30接入): pdf现抽/docx读fetcher预解的.txt旁车
    for d in sorted(glob.glob(os.path.join(ROOT,'corpus/ir/*/'))):
        code=os.path.basename(d.rstrip('/')); co=frozen.get(code,code)
        for f in sorted(glob.glob(d+'*')):
            if f.endswith('.pdf'):
                txt=f+'.txt'
                if not os.path.exists(txt): subprocess.run(['pdftotext','-layout',f,txt],capture_output=True)
                recall_file(txt, co, os.path.basename(f))
            elif f.endswith('.docx') and os.path.exists(f+'.txt'):
                recall_file(f+'.txt', co, os.path.basename(f))
    q.sort()
    print(f'净队列 {len(q)} 条(空叶格优先排序)')
    labels={0:'空格',1:'参与',2:'  '}
    for pr,hid,co,cell,w,seg in q[:40]: print(f'  [{labels[pr]}] {co} | {cell} | {w} | {seg[:50]}')
    return q

if __name__=='__main__':
    staleness()
    invariants()
    if ERR:
        print('\n'.join('\033[31m'+e+'\033[0m' for e in ERR)); sys.exit(1)
    print('不变量全绿(①-⑪)')
    if '--check' not in sys.argv: scan()
