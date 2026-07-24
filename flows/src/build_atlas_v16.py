#!/usr/bin/env python3
"""build_atlas_v16.py — 光模块产业图谱 v1.6 · 三合一前端

在 v1.5 关系图（四硬约束不变）上合并两个新视图，一次产出：
- 视图① 关系图：236 边 / 169 节点，原四硬约束不变
  （自包含零外链 / 边等级视觉可区分+图例 / 节点点击溯源锚点 / 页脚徽章
  "236边/169节点/判例2A+2B"）。
- 视图② 节点层上下游分层：flows/out/supply-chain-nodes-v0.md（169 节点，
  48 有锚 / 121 待锚），全视图标注「宽准入 · 不承重」。
- 视图③ 工序/内容：flows/out/content-layer-sample-lieqi.md（猎奇 34 条）
  + flows/out/content-pilot-yuanjie.md（源杰 39 条），全视图标注
  「未准入 · 不作关系边证据 · issuer_self 永不承重」。

输入均为既有彩排产出文件；本脚本只做事前端的装配与断言，不改任何台账。
输出自包含、无外部资源依赖的 output/光模块产业图谱-v1.6.html。
"""

import csv
import json
import os
import re
from collections import Counter


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODES_PATH = os.path.join(ROOT, "output", "nodes.csv")
EDGES_PATH = os.path.join(ROOT, "output", "edges.csv")
LAYER_MD = os.path.join(ROOT, "flows", "out", "supply-chain-nodes-v0.md")
LIEQI_MD = os.path.join(ROOT, "flows", "out", "content-layer-sample-lieqi.md")
YUANJIE_MD = os.path.join(ROOT, "flows", "out", "content-pilot-yuanjie.md")
OUT_PATH = os.path.join(ROOT, "output", "光模块产业图谱-v1.6.html")

LAYER_ORDER = ("L1", "L2", "L3", "L4", "L5", "L6", "L7")
LAYER_LABEL = {
    "L1": "上游材料",
    "L2": "光/电芯片 + DSP芯片",
    "L3": "封装/代工 + 贸易/委托加工",
    "L4": "光器件",
    "L5": "模块/光电子商",
    "L6": "代工(EMS) / 线缆 / 系统 / 终端",
    "L7": "算力终端 / 云",
}
DSP_BLINDSPOT = {"Marvell", "博通(Broadcom)"}


# ---------------------------------------------------------------- 视图① 数据

def layer_for_type(node_type):
    """按「类型」字段归层；顺序用于消解复合类型，不使用节点名称映射。"""
    t = (node_type or "").strip()

    if any(k in t for k in ("算力终端", "云巨头")):
        return "L7"
    if any(k in t for k in (
        "芯片", "DSP", "半导体", "半导体IDM", "驱动控制", "功率器件封测"
    )):
        return "L2"
    if any(k in t for k in (
        "代工(EMS)", "线缆/系统/终端", "系统设备商", "网络设备OEM",
        "CATV设备商", "CATV分销商", "消费电子终端", "汽车电机厂"
    )):
        return "L6"
    if "光器件" in t or "模块/器件" in t:
        return "L4"
    if any(k in t for k in (
        "模块/光电子商", "光模块厂", "光模块/宽带", "供应链主体", "旭创关联方"
    )):
        return "L5"
    if any(k in t for k in (
        "封装/代工", "贸易", "代理", "物流", "设备商", "设备经销",
        "设备/科研", "科研院所", "仪器", "自动化", "焊接"
    )):
        return "L3"
    if any(k in t for k in (
        "上游材料", "材料/设备供应商", "加工件供应商", "锻件厂"
    )):
        return "L1"
    raise ValueError(f"未覆盖的节点类型: {t!r}")


def grade_class(grade):
    if grade.startswith("实边(已死"):
        return "dead"
    if grade.startswith("实边"):
        return "lit"
    if grade.startswith("推断边"):
        return "infer"
    if grade.startswith("程序段落"):
        return "leak"
    return "shadow"


def country_key(country):
    c = country or ""
    if c.startswith("中国") or (
        "中国" in c and all(x not in c for x in ("日本", "德国", "新加坡"))
    ):
        return "cn"
    if "美国" in c:
        return "us"
    if "日本" in c or "台湾" in c:
        return "jt"
    if c == "待核":
        return "veil"
    return "other"


def norm(name):
    """边端点名称归一；匿名端点保留原文并在渲染时生成幽灵槽位。"""
    if not name:
        return name
    n = name.strip()
    alias = {
        "AAOI": "Applied Optoelectronics(AAOI)",
        "华为+海思": "华为(含海思)",
        "华为": "华为(含海思)",
        "博通": "博通(Broadcom)",
        "博通(客户)": "博通(Broadcom)",
        "Broadcom": "博通(Broadcom)",
        "NVIDIA(客户)": "NVIDIA",
        "索尔思": "索尔思(Source Photonics)",
        "Fabrinet(解匿)": "Fabrinet",
        "Fabrinet(疑似客户)": "Fabrinet",
        "Ciena(解匿)": "Ciena",
        "Google(解匿)": "Google",
        "中际旭创(作为客户)": "中际旭创",
        "罗博特科": "罗博特科/ficonTEC",
        "ficonTEC(罗博特科)": "罗博特科/ficonTEC",
        "PINEWAVE(关联方)": "PINEWAVE",
        "等离子体所(客户)": "等离子体所",
        "浙江粮油(出口代理)": "浙江粮油",
        "索恩格": "索恩格(SEG Automotive)",
        "苏世博": "索恩格(SEG Automotive)",
        "Corning(解匿)": "Corning Incorporated",
    }
    return alias.get(n, n)


def load_csv():
    with open(NODES_PATH, encoding="utf-8-sig", newline="") as f:
        nodes = list(csv.DictReader(f))
    with open(EDGES_PATH, encoding="utf-8-sig", newline="") as f:
        edges = list(csv.DictReader(f))
    return nodes, edges


def build_graph():
    nodes, edges = load_csv()
    node_map = {}
    for row in nodes:
        name = row["名称"].strip()
        node_map[name] = {
            "id": name,
            "type": row["类型"].strip(),
            "country": row["国别"].strip(),
            "code": row.get("代码", "").strip(),
            "note": row.get("备注", "").strip(),
            "layer": layer_for_type(row["类型"]),
            "ck": country_key(row["国别"]),
            "deg": 0,
            "blindspot": name in DSP_BLINDSPOT,
        }

    edge_payload = []
    ghosts = {}

    def endpoint(name):
        if name in node_map:
            return name
        gid = "◈ " + name
        if gid not in ghosts:
            ghosts[gid] = {
                "id": gid,
                "type": "匿名槽位",
                "country": "",
                "code": "",
                "note": "边端点未在 nodes.csv 单列；不计入 169 节点。",
                "layer": None,
                "ck": "veil",
                "deg": 0,
                "ghost": True,
                "blindspot": False,
                "_neighbor_layers": [],
            }
        return gid

    for row in edges:
        supplier = endpoint(norm(row["供方"]))
        demander = endpoint(norm(row["需方"]))
        edge_payload.append({
            "id": row["edge_id"],
            "s": supplier,
            "d": demander,
            "cls": grade_class(row["边等级"]),
            "grade": row["边等级"],
            "amt": row["占比或金额"],
            "fy": row["财年"],
            "src": row["证据文件"],
            "anchor": row["锚点"],
            "vs": row["验证状态"],
            "note": row["备注"],
        })
        for endpoint_id in (supplier, demander):
            if endpoint_id in node_map:
                node_map[endpoint_id]["deg"] += 1
            else:
                ghosts[endpoint_id]["deg"] += 1

        if supplier in ghosts and demander in node_map:
            ghosts[supplier]["_neighbor_layers"].append(node_map[demander]["layer"])
        if demander in ghosts and supplier in node_map:
            ghosts[demander]["_neighbor_layers"].append(node_map[supplier]["layer"])

    for ghost in ghosts.values():
        layers = ghost.pop("_neighbor_layers")
        ghost["layer"] = Counter(layers).most_common(1)[0][0] if layers else "L5"

    render_nodes = list(node_map.values()) + list(ghosts.values())
    layer_counts = Counter(n["layer"] for n in node_map.values())
    grade_counts = Counter(e["cls"] for e in edge_payload)
    return {
        "nodes": render_nodes,
        "edges": edge_payload,
        "layerOrder": LAYER_ORDER,
        "layerLabel": LAYER_LABEL,
        "layerCounts": dict(layer_counts),
        "canonicalNodeCount": len(nodes),
        "edgeCount": len(edges),
        "ghostCount": len(ghosts),
        "gradeCounts": dict(grade_counts),
        "badge": f"{len(edges)}边/{len(nodes)}节点/判例2A+2B",
    }


# ---------------------------------------------------------------- 视图② 数据

def parse_layer_md():
    """解析 supply-chain-nodes-v0.md：分层组 + 节点行 + 分层方法。"""
    lines = open(LAYER_MD, encoding="utf-8").read().splitlines()
    groups, methods = [], []
    cur = None
    in_method = False
    for ln in lines:
        m = re.match(r"^## (L\d+|V|X)\s+(.+)$", ln)
        if m:
            key = m.group(1)
            kind = "main" if re.fullmatch(r"L[1-8]", key) else ("v" if key == "V" else "x")
            cur = {"key": key, "title": m.group(2).strip(), "kind": kind, "nodes": []}
            groups.append(cur)
            in_method = False
            continue
        if ln.startswith("## "):
            in_method = ln.startswith("## 分层方法")
            cur = None
            continue
        if in_method and re.match(r"^\d+\.\s", ln):
            methods.append(re.sub(r"\*\*", "", ln).strip())
            continue
        if cur is not None and ln.startswith("| N"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) != 4:
                raise ValueError(f"节点行单元格数异常: {ln[:60]}")
            m2 = re.match(r"^(N\d+)\s+(.+)$", cells[0])
            if not m2:
                raise ValueError(f"节点行首格异常: {cells[0]!r}")
            status = cells[3]
            anchored = status.startswith("有锚")
            stance = ""
            sm = re.search(r"stance=(.+)$", status)
            if sm:
                stance = sm.group(1).strip()
            cur["nodes"].append({
                "nid": m2.group(1),
                "name": m2.group(2).strip(),
                "doing": cells[1],
                "anchor": "" if cells[2] == "—" else cells[2],
                "anchored": anchored,
                "stance": stance,
            })
    anchored_n = sum(1 for g in groups for n in g["nodes"] if n["anchored"])
    total = sum(len(g["nodes"]) for g in groups)
    return {
        "meta": {
            "total": total,
            "anchored": anchored_n,
            "pending": total - anchored_n,
            "seq": "材料→光芯片→DSP→封装→器件→模块→代工EMS→终端；设备/仪器为纵轴",
            "source": "flows/out/supply-chain-nodes-v0.md · 节点层宽准入 v0 · 生成日 2026-07-24",
        },
        "methods": methods,
        "groups": groups,
    }


# ---------------------------------------------------------------- 视图③ 数据

BULLET_PAIR = re.compile(r"\*\*([^*]+)\*\*：")


def parse_bullet(line):
    """把 '- **k**：v ｜ **k2**：v2' 解析为有序 (k, v) 列表。"""
    parts = re.split(r"(?=\*\*[^*]+\*\*：)", line.lstrip("- ").strip())
    out = []
    for p in parts:
        m = re.match(r"\*\*([^*]+)\*\*：(.*)$", p.strip())
        if m:
            val = m.group(2).strip().rstrip("｜").strip().rstrip()
            out.append((m.group(1).strip(), val))
    return out


QUOTE_KEY = re.compile(r"引语|锚点")


def parse_content_md(path, cid_prefix):
    """解析内容层 markdown 为条目列表 + 诚实边界 + 统一锚点。"""
    lines = open(path, encoding="utf-8").read().splitlines()
    entries, boundaries = [], []
    cur = None
    section = "head"
    anchor_url = ""
    for ln in lines:
        if ln.startswith("## 诚实边界"):
            section = "boundary"
            cur = None
            continue
        if ln.startswith("## 报告") or ln.startswith("## 汇总"):
            section = "report"
            cur = None
            continue
        m = re.match(r"^## ([①②③④⑤])", ln)
        if m:
            section = "entries"
            cur = None
            continue
        if ln.startswith("## "):
            cur = None
            continue
        if section == "head" and "统一锚点" in ln:
            um = re.search(r"https?://\S+", ln)
            if um:
                anchor_url = um.group(0).rstrip("。)）")
        if section == "entries":
            em = re.match(r"^### ((?:" + cid_prefix + r")\d+)\s*$", ln)
            if em:
                cur = {"cid": em.group(1), "pairs": []}
                entries.append(cur)
                continue
            if cur is not None and ln.startswith("- **"):
                cur["pairs"].extend(parse_bullet(ln))
            continue
        if section == "boundary":
            if re.match(r"^\d+\.\s", ln):
                boundaries.append(re.sub(r"\*\*", "", ln).strip())
            elif boundaries and ln.strip() and not ln.startswith("---"):
                boundaries[-1] += re.sub(r"\*\*", "", ln).strip()
    return entries, boundaries, anchor_url


def shape_entry(raw, schema):
    """把无序 (k, v) 对整理成前端渲染结构。"""
    pairs = raw["pairs"]
    get = lambda k: next((v for kk, v in pairs if kk == k), "")
    type_label = get("事实类型") or get("类型")
    tm = re.match(r"^([①②③④⑤])", type_label)
    tnum = tm.group(1) if tm else "?"
    content = get("内容")
    if not content:
        raise ValueError(f"{raw['cid']} 缺内容")
    stance_raw = get("stance") or ""
    stance_cls = ""
    if stance_raw:
        stance_cls = stance_raw.split("（")[0].strip()
    if schema == "lieqi" and tnum == "⑤":
        stance_cls = "issuer_self"
        stance_raw = "发行人竞争陈述（红线：不得转写为客观事实）"
    tense = get("时态")
    quotes, meta, notes = [], [], []
    for k, v in pairs:
        if k in ("事实类型", "类型", "内容", "stance", "时态"):
            continue
        if QUOTE_KEY.search(k):
            quotes.append([k, v])
        elif k in ("章节位置", "source_chain", "验证态", "关联", "立场标注"):
            meta.append([k, v])
        else:
            notes.append([k, v])
    return {
        "cid": raw["cid"],
        "tnum": tnum,
        "typeLabel": type_label,
        "content": content,
        "stanceCls": stance_cls,
        "stanceText": stance_raw,
        "tense": tense,
        "quotes": quotes,
        "meta": meta,
        "notes": notes,
    }


def build_content():
    lieqi_raw, lieqi_bd, lieqi_anchor = parse_content_md(LIEQI_MD, "C")
    yj_raw, yj_bd, yj_anchor = parse_content_md(YUANJIE_MD, "YJ")
    lieqi = [shape_entry(r, "lieqi") for r in lieqi_raw]
    yuanjie = [shape_entry(r, "yuanjie") for r in yj_raw]

    def tcounts(entries):
        c = Counter(e["tnum"] for e in entries)
        return {k: c.get(k, 0) for k in ("①", "②", "③", "④", "⑤")}

    yj_stance = Counter(e["stanceCls"] for e in yuanjie)
    payload = {
        "lieqi": {
            "title": "猎奇智能 · 招股说明书（申报稿）第五节「业务与技术」",
            "status": "内容层样品 · 未准入",
            "schema": "五类：①工序步骤 ②技术参数 ③产品代际 ④设备-工序映射 ⑤发行人竞争陈述",
            "corpus": "flows/input/lieqi_prospectus.txt（行约 8237–10520 精读）· 抽取日 2026-07-24",
            "anchor": lieqi_anchor,
            "discipline": "只记原文逐字存在的内容；类型⑤不得转写为客观事实；「命中引语」为原文完整一句。",
            "total": len(lieqi),
            "tcounts": tcounts(lieqi),
            "tlabels": {"①": "工序步骤", "②": "技术参数", "③": "产品代际", "④": "设备-工序映射", "⑤": "发行人竞争陈述"},
            "entries": lieqi,
            "boundaries": lieqi_bd,
        },
        "yuanjie": {
            "title": "源杰科技（688498）· 2023年年度报告 第三节「管理层讨论与分析」",
            "status": "内容台账有界试点 v1.7b · 未准入",
            "schema": "冻结 schema v1：①工序步骤 ②技术参数 ③产品构成 ④代际事件 ⑤设备-工序能力；stance 横切",
            "corpus": "688498_2023年报.txt（行 497–1300 精读）· 抽取日 2026-07-24 · 约3.5小时等效",
            "anchor": yj_anchor,
            "discipline": "39/39 条引语级机械验证命中；双闸自查无一条可读作关系边证据；去重扣减 3 条（YJ25/YJ26/YJ32 与猎奇样品知识域重叠），净新增 36 条。",
            "total": len(yuanjie),
            "tcounts": tcounts(yuanjie),
            "tlabels": {"①": "工序步骤", "②": "技术参数", "③": "产品构成", "④": "代际事件", "⑤": "设备-工序能力"},
            "stanceCounts": {k: yj_stance.get(k, 0) for k in ("neutral", "industry", "issuer_self")},
            "entries": yuanjie,
            "boundaries": yj_bd,
        },
        "mapLanes": [
            {
                "title": "光模块封测主流程",
                "sub": "猎奇智能招股书视角 · 依据 C01 / C06",
                "steps": [
                    {"name": "贴片", "cids": ["C21", "C22"]},
                    {"name": "引线键合", "cids": [], "gap": "发行人产品不覆盖本环（C01 及样品诚实边界 3）"},
                    {"name": "光学耦合", "cids": ["C23"]},
                    {"name": "老化测试", "cids": ["C24", "C25", "C26"]},
                ],
                "notes": ["C27", "C28"],
            },
            {
                "title": "光芯片 IDM 制造流程",
                "sub": "源杰科技年报视角 · 依据 YJ01 / YJ02",
                "steps": [
                    {"name": "芯片设计", "cids": []},
                    {"name": "晶圆制造", "cids": ["YJ05", "YJ06"]},
                    {"name": "芯片加工", "cids": ["YJ04"]},
                    {"name": "测试", "cids": ["YJ38"]},
                ],
                "subflow": {"ref": "YJ02", "steps": ["MOCVD 外延生长", "光栅工艺", "光波导制作", "金属化工艺", "端面镀膜", "自动化芯片测试", "芯片高频测试", "可靠性测试验证"]},
                "notes": ["YJ33", "YJ34", "YJ35", "YJ36", "YJ37", "YJ07"],
            },
        ],
    }
    return payload


# ---------------------------------------------------------------- HTML 模板

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>光模块产业图谱 v1.6 · 三合一</title>
<style>
:root{
  --void:#080B14;--panel:#0F1420;--panel2:#161D2B;--grid:#1B2333;
  --ink:#EAEEF6;--mute:#727D97;--faint:#3A4358;
  --lit:#4FE0C4;--infer:#FFB347;--shadow:#4A5470;--dead:#E05A6A;--leak:#48D7E8;
  --cn:#F0655C;--us:#5B9DF0;--jt:#FFCF5E;--other:#8792AB;--veil:#5A6480;
  --mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
  --disp:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--void);color:var(--ink);font-family:var(--disp);
  -webkit-font-smoothing:antialiased}
body{background-image:linear-gradient(var(--grid) 1px,transparent 1px),
  linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:44px 44px}
body::before{content:"";position:fixed;inset:0;pointer-events:none;
  background:radial-gradient(100% 65% at 50% -10%,rgba(79,224,196,.07),transparent 62%),
  radial-gradient(80% 60% at 100% 100%,rgba(91,157,240,.05),transparent 55%)}
.wrap{position:relative;max-width:1500px;margin:auto;padding:46px 26px 76px}
.eyebrow{display:flex;align-items:center;gap:12px;margin-bottom:17px;color:var(--lit);
  font-family:var(--mono);font-size:12px;letter-spacing:.3em;text-transform:uppercase}
.eyebrow::before{content:"";width:26px;height:1px;background:var(--lit);box-shadow:0 0 8px var(--lit)}
h1{max-width:17ch;margin:0 0 18px;font-size:clamp(34px,5vw,60px);line-height:1.04;
  letter-spacing:-.025em;font-weight:650}
h1 span{color:var(--lit);text-shadow:0 0 24px rgba(79,224,196,.45)}
.thesis{max-width:76ch;margin:0 0 30px;color:var(--mute);font-size:clamp(15px,1.6vw,18px);
  line-height:1.68}.thesis b{color:var(--ink);font-weight:550}
.stats{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));margin-bottom:28px;
  border:1px solid var(--faint);border-radius:14px;overflow:hidden;
  background:linear-gradient(180deg,rgba(22,29,43,.72),rgba(15,20,32,.72))}
.stat{padding:16px 18px;border-right:1px solid var(--faint)}.stat:last-child{border:0}
.stat .n{font-family:var(--mono);font-size:27px;font-weight:650}.stat .k{margin-top:4px;
  color:var(--mute);font-size:11px;letter-spacing:.04em}
.legend{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:16px}
.chip{display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border:1px solid var(--faint);
  border-radius:999px;background:rgba(15,20,32,.72);color:var(--mute);font-family:var(--mono);
  font-size:11px;cursor:pointer;user-select:none;transition:.18s}
.chip:hover{color:var(--ink);border-color:var(--mute)}.chip.off{opacity:.3}
.chip.on{color:var(--lit);border-color:var(--lit)}
.chip .sw{width:21px;border-top:2px solid}.chip[data-c=lit] .sw{border-color:var(--lit);
  box-shadow:0 0 7px var(--lit)}.chip[data-c=infer] .sw{border-color:var(--infer);
  border-top-style:dashed}.chip[data-c=shadow] .sw{border-color:var(--shadow);
  border-top-style:dashed}.chip[data-c=dead] .sw{border-color:var(--dead);
  border-top-style:dotted}.chip[data-c=leak] .sw{border-color:var(--leak);
  border-top-style:dashed}
.stage{position:relative;overflow:auto;border:1px solid var(--faint);border-radius:18px;
  background:linear-gradient(180deg,rgba(11,15,24,.86),rgba(8,11,20,.95));
  box-shadow:0 28px 80px rgba(0,0,0,.22)}
svg{display:block;width:100%;min-width:1180px;height:auto}
.band-label{font-family:var(--mono);font-size:12px;letter-spacing:.12em;fill:var(--mute)}
.band-count{font-family:var(--mono);font-size:10px;fill:var(--faint)}
.edge{fill:none;cursor:pointer;transition:opacity .18s,stroke-width .18s}
.edge.lit{stroke:var(--lit);stroke-width:1.35;opacity:.56}
.edge.infer{stroke:var(--infer);stroke-width:1.45;stroke-dasharray:8 5;opacity:.75}
.edge.shadow{stroke:var(--shadow);stroke-width:1;stroke-dasharray:2 6;opacity:.42}
.edge.dead{stroke:var(--dead);stroke-width:1.4;stroke-dasharray:1 7;opacity:.78}
.edge.leak{stroke:var(--leak);stroke-width:1.45;stroke-dasharray:6 4;opacity:.82}
.edge.hot{opacity:1;stroke-width:2.8}.edge.dim{opacity:.035}
.flow{fill:none;stroke:var(--lit);stroke-width:2;stroke-linecap:round;pointer-events:none;
  filter:drop-shadow(0 0 4px var(--lit));opacity:.78}
.node{cursor:pointer;transition:opacity .18s}.node .halo{fill:none;stroke-width:1.2}
.node .core{transition:r .18s}.node .name{font-size:10.5px;fill:var(--ink);
  paint-order:stroke;stroke:var(--void);stroke-width:3px;stroke-linejoin:round}
.node.ghost .name{fill:var(--veil);font-style:italic}.node.dim{opacity:.09}
.node.hot .name{fill:#fff;font-weight:700}.node.blind .halo{stroke:var(--infer)!important;
  stroke-width:1.7;stroke-dasharray:5 4}.blind-label{font-family:var(--mono);font-size:8px;
  fill:var(--infer);paint-order:stroke;stroke:var(--void);stroke-width:3px;letter-spacing:.05em}
.cn{fill:var(--cn)}.us{fill:var(--us)}.jt{fill:var(--jt)}
.other{fill:var(--other)}.veil{fill:var(--veil)}
.drawer{position:fixed;z-index:50;top:0;right:0;width:min(430px,92vw);height:100%;
  padding:28px 26px;overflow-y:auto;background:linear-gradient(180deg,#10151F,#0B0F18);
  border-left:1px solid var(--faint);box-shadow:-30px 0 60px rgba(0,0,0,.5);
  transform:translateX(100%);transition:transform .3s cubic-bezier(.4,0,.1,1)}
.drawer.open{transform:none}.drawer h3{margin:0 42px 5px 0;font-size:20px;line-height:1.25}
.close{position:absolute;top:20px;right:20px;width:32px;height:32px;border:1px solid var(--faint);
  border-radius:8px;background:none;color:var(--mute);cursor:pointer}
.gradetag{display:inline-block;margin:8px 0 18px;padding:4px 9px;border-radius:6px;
  font-family:var(--mono);font-size:10px}.gt-lit{background:rgba(79,224,196,.14);color:var(--lit)}
.gt-infer{background:rgba(255,179,71,.14);color:var(--infer)}
.gt-shadow{background:rgba(74,84,112,.22);color:#9aa6c4}
.gt-dead{background:rgba(224,90,106,.16);color:#f08391}
.gt-leak{background:rgba(72,215,232,.14);color:var(--leak)}
.field{padding:12px 0;border-top:1px solid var(--grid)}.lab{margin-bottom:5px;color:var(--mute);
  font-family:var(--mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase}
.val{font-size:13px;line-height:1.55;word-break:break-word}.mono{font-family:var(--mono);
  color:var(--lit)}.field a{color:var(--us);text-decoration:none}.field a:hover{text-decoration:underline}
.edge-row{width:100%;padding:12px 0;border:0;border-top:1px solid var(--grid);
  background:none;color:inherit;text-align:left;cursor:pointer}.edge-row:hover .val{color:#fff}
.hint{margin:15px 0 5px;color:var(--mute);font-family:var(--mono);font-size:10px;
  letter-spacing:.12em}.foot{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;
  margin-top:30px;padding-top:20px;border-top:1px solid var(--grid);color:var(--mute);
  font-size:13px;line-height:1.72}.foot-copy{max-width:88ch}.foot b{color:var(--ink)}
.badge{flex:none;padding:8px 12px;border:1px solid var(--lit);border-radius:999px;color:var(--lit);
  font-family:var(--mono);font-size:11px;box-shadow:0 0 18px rgba(79,224,196,.08)}
/* ---- v1.6 三合一 ---- */
.tabs{display:flex;gap:10px;margin:0 0 26px;flex-wrap:wrap}
.tab{flex:1;min-width:210px;padding:13px 18px;border:1px solid var(--faint);border-radius:12px;
  background:rgba(15,20,32,.72);color:var(--mute);cursor:pointer;text-align:left;
  font-family:var(--disp);font-size:15px;font-weight:600;transition:.18s}
.tab span{display:block;margin-top:3px;font-family:var(--mono);font-size:10px;font-weight:400;
  letter-spacing:.08em;color:var(--faint)}
.tab:hover{border-color:var(--mute);color:var(--ink)}
.tab.active{border-color:var(--lit);color:var(--lit);box-shadow:0 0 22px rgba(79,224,196,.12)}
.tab.active span{color:var(--lit);opacity:.75}
.view{display:none}.view.active{display:block}
.banner{display:flex;gap:12px;align-items:flex-start;margin-bottom:20px;padding:13px 16px;
  border:1px solid var(--infer);border-radius:12px;background:rgba(255,179,71,.06);
  color:var(--infer);font-size:13px;line-height:1.65}
.banner b{color:var(--ink)}
.banner .tag{flex:none;font-family:var(--mono);font-size:10px;letter-spacing:.14em;
  border:1px solid currentColor;border-radius:6px;padding:3px 7px;margin-top:1px}
.banner.cyan{border-color:var(--leak);background:rgba(72,215,232,.05);color:var(--leak)}
.banner.cyan b{color:var(--ink)}
/* ---- 视图② 节点层 ---- */
.lband{margin-bottom:4px}
.lband-head{display:flex;align-items:baseline;gap:12px;padding:12px 4px 10px;
  border-bottom:1px solid var(--grid)}
.lband-head .idx{font-family:var(--mono);color:var(--lit);font-size:12px;letter-spacing:.1em}
.lband-head h3{margin:0;font-size:16px;font-weight:600}
.lband-head .cnt{font-family:var(--mono);font-size:10px;color:var(--mute)}
.lcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(204px,1fr));gap:9px;
  padding:12px 0 8px}
.lcard{padding:10px 12px;border:1px solid var(--faint);border-radius:10px;
  background:rgba(15,20,32,.6);cursor:pointer;transition:.15s}
.lcard:hover{border-color:var(--mute)}
.lcard.pending{border-style:dashed;opacity:.72}
.lcard .nid{font-family:var(--mono);font-size:9px;color:var(--faint);letter-spacing:.08em}
.lcard .nm{font-size:13px;font-weight:600;margin:2px 0 4px;line-height:1.35}
.lcard .doing{font-size:11px;color:var(--mute);line-height:1.5;display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.lcard .st{display:flex;gap:7px;align-items:center;margin-top:7px;font-family:var(--mono);
  font-size:9px;flex-wrap:wrap}
.dot{width:7px;height:7px;border-radius:50%;flex:none}
.dot.ok{background:var(--lit);box-shadow:0 0 6px var(--lit)}
.dot.no{background:var(--veil)}
.ok-t{color:var(--lit)}.no-t{color:var(--veil)}
.stance{color:var(--infer)}
.flow-arrow{text-align:center;color:var(--faint);font-family:var(--mono);font-size:10px;
  letter-spacing:.24em;padding:3px 0}
.vband{border:1px solid rgba(255,207,94,.45);border-radius:12px;padding:2px 14px 12px;
  margin-top:14px;background:rgba(255,207,94,.03)}
.vband .lband-head .idx{color:var(--jt)}
.xzone{margin-top:18px;border-top:1px dashed var(--faint);padding-top:10px}
.xzone>h3{color:var(--mute);font-size:12px;font-family:var(--mono);letter-spacing:.14em;
  font-weight:500;margin:6px 0 2px}
.xzone .lband-head .idx{color:var(--veil)}
.filterbar{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-bottom:18px}
.search{flex:1;min-width:180px;padding:8px 14px;border:1px solid var(--faint);border-radius:999px;
  background:rgba(15,20,32,.72);color:var(--ink);font-family:var(--mono);font-size:11px;outline:none}
.search:focus{border-color:var(--lit)}
.noteblock{margin-top:16px;padding:13px 16px;border:1px dashed var(--faint);border-radius:12px;
  color:var(--mute);font-size:12px;line-height:1.8}
.noteblock h4{margin:0 0 8px;color:var(--ink);font-size:12px;font-family:var(--mono);
  letter-spacing:.1em;font-weight:500}
.noteblock ol{margin:0;padding-left:18px}
.noteblock li{margin-bottom:5px}
/* ---- 视图③ 工序/内容 ---- */
.proc-lane{border:1px solid var(--faint);border-radius:14px;padding:16px 16px 12px;
  margin-bottom:16px;background:rgba(15,20,32,.5)}
.proc-lane-head{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;
  margin-bottom:13px;align-items:baseline}
.proc-lane-head h3{margin:0;font-size:15px;font-weight:600}
.proc-lane-head span{font-family:var(--mono);font-size:10px;color:var(--mute)}
.proc-steps{display:flex;gap:7px;align-items:stretch;flex-wrap:wrap}
.proc-step{flex:1;min-width:150px;border:1px solid var(--grid);border-radius:10px;
  padding:10px;background:rgba(8,11,20,.5)}
.proc-step.gap{opacity:.6;border-style:dashed}
.ps-name{font-size:13px;font-weight:650;margin-bottom:6px}
.ps-arrow{align-self:center;color:var(--faint);font-size:12px}
.ps-note{font-size:10.5px;color:var(--infer);line-height:1.55}
.cidchip{display:block;width:100%;text-align:left;margin:6px 0 0;padding:7px 9px;
  border:1px solid var(--faint);border-radius:8px;background:none;color:var(--mute);
  cursor:pointer;font-size:10.5px;line-height:1.5;font-family:var(--disp);transition:.15s}
.cidchip:hover{border-color:var(--lit);color:var(--ink)}
.cidchip b{font-family:var(--mono);color:var(--lit);font-weight:600;margin-right:5px}
.subflow{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px;align-items:center}
.subflow .sfref{font-family:var(--mono);font-size:9.5px;color:var(--lit)}
.subflow .sf{font-family:var(--mono);font-size:9.5px;color:var(--mute);
  border:1px solid var(--grid);border-radius:6px;padding:4px 8px}
.proc-notes{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;padding-top:10px;
  border-top:1px dashed var(--grid)}
.proc-notes .cidchip{width:auto;margin:0}
.ledger{margin-top:30px}
.ledger-head{border-top:1px solid var(--grid);padding-top:18px;margin-bottom:14px}
.ledger-head h3{margin:0 0 6px;font-size:18px;font-weight:650}
.ledger-head .lmeta{font-family:var(--mono);font-size:10.5px;color:var(--mute);
  line-height:1.9;word-break:break-all}
.ledger-head .lmeta a{color:var(--us);text-decoration:none}
.ledger-head .lmeta a:hover{text-decoration:underline}
.ledger-head .disc{margin-top:8px;font-size:12px;color:var(--infer);line-height:1.65}
.centry{border:1px solid var(--faint);border-radius:12px;margin-bottom:10px;
  background:rgba(15,20,32,.55)}
.centry.flash{animation:flash 1.8s}
@keyframes flash{0%{border-color:var(--lit);box-shadow:0 0 26px rgba(79,224,196,.4)}100%{}}
.centry>summary{display:block;padding:12px 14px;cursor:pointer;list-style:none}
.centry>summary::-webkit-details-marker{display:none}
.centry .crow{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.centry .cid{font-family:var(--mono);font-size:11px;color:var(--lit)}
.centry .openhint{margin-left:auto;font-family:var(--mono);font-size:9px;color:var(--faint)}
.centry[open] .openhint{color:var(--lit)}
.centry h4{margin:8px 0 0;font-size:13.5px;font-weight:550;line-height:1.65;color:var(--ink)}
.tbadge{font-family:var(--mono);font-size:9px;padding:3px 8px;border-radius:6px}
.tb1{background:rgba(79,224,196,.13);color:var(--lit)}
.tb2{background:rgba(91,157,240,.15);color:var(--us)}
.tb3{background:rgba(255,207,94,.13);color:var(--jt)}
.tb4{background:rgba(255,179,71,.13);color:var(--infer)}
.tb5{background:rgba(159,123,234,.16);color:#B79CED}
.sbadge{font-family:var(--mono);font-size:9px;padding:3px 8px;border-radius:6px}
.sb-neutral{background:rgba(135,146,171,.16);color:var(--other)}
.sb-industry{background:rgba(91,157,240,.15);color:var(--us)}
.sb-issuer{background:rgba(224,90,106,.16);color:#F08391;border:1px solid rgba(224,90,106,.45)}
.sb-tense{background:none;color:var(--faint);border:1px solid var(--faint)}
.cbody{padding:2px 14px 13px}
.cbody blockquote{margin:9px 0;padding:9px 12px;border-left:2px solid var(--lit);
  background:rgba(8,11,20,.6);font-size:12px;line-height:1.75;color:#C9D2E4}
.cbody blockquote .qlab{display:block;font-family:var(--mono);font-size:9px;color:var(--mute);
  letter-spacing:.1em;margin-bottom:4px}
.kv{display:flex;gap:10px;font-size:11px;padding:6px 0;border-top:1px solid var(--grid)}
.kv .k{flex:none;width:118px;color:var(--mute);font-family:var(--mono);font-size:9px;
  letter-spacing:.05em;padding-top:2px;word-break:break-all}
.kv .v{color:#C9D2E4;line-height:1.65;word-break:break-word}
.kv.warn .v{color:var(--infer)}
@media(max-width:900px){.stats{grid-template-columns:repeat(3,1fr)}.stat:nth-child(3){border-right:0}
  .stat:nth-child(-n+3){border-bottom:1px solid var(--faint)}.foot{display:block}.badge{display:inline-block;
  margin-top:16px}}@media(max-width:620px){.wrap{padding:30px 14px 58px}.stats{grid-template-columns:repeat(2,1fr)}
  .stat:nth-child(odd){border-right:1px solid var(--faint)}.stat:nth-child(even){border-right:0}
  .stat{border-bottom:1px solid var(--faint)}.stat:nth-last-child(-n+2){border-bottom:0}}
@media(prefers-reduced-motion:reduce){.flow{display:none}.edge,.node{transition:none}}
</style>
</head>
<body>
<main class="wrap">
  <div class="eyebrow">披露证据图谱 · v1.6 · 三合一 · 2026-07</div>
  <h1>光模块产业，<span>被证据分层</span>的结构</h1>
  <p class="thesis">一个文件，三种看法，三套纪律。<b>①关系图</b>回答「我们凭什么看得见这条
    供货关系」——只有它承重；<b>②节点分层</b>回答「谁在哪一层、做什么」——宽准入、
    <b>不承重</b>；<b>③工序/内容</b>回答「设备与工序的能力事实」——未准入样品，
    <b>不作关系边证据</b>。</p>
  <nav class="tabs" role="tablist" aria-label="视图切换">
    <button class="tab active" data-view="graph" role="tab">① 关系图
      <span>证据承重 · 236边 / 169节点 · 四硬约束</span></button>
    <button class="tab" data-view="layers" role="tab">② 节点分层
      <span>宽准入 · 不承重 · 48有锚 / 121待锚</span></button>
    <button class="tab" data-view="content" role="tab">③ 工序 / 内容
      <span>未准入样品 · 猎奇34条 + 源杰39条</span></button>
  </nav>

  <section class="view active" id="view-graph">
    <section class="stats" id="stats" aria-label="数据统计"></section>
    <nav class="legend" id="legend" aria-label="边等级筛选"></nav>
    <section class="stage">
      <svg id="svg" viewBox="0 0 1760 1200" role="img"
        aria-label="光模块产业七层披露证据网络图"></svg>
    </section>
  </section>

  <section class="view" id="view-layers">
    <div class="banner"><span class="tag">宽准入 · 不承重</span><div>
      本视图只回答<b>「谁在哪一层、做什么」</b>。<b>禁止</b>把归层或「做什么」读成供货/采购关系；
      关系承重只在 ①关系图（<code>output/edges.csv</code> / 关系台账，双闸纪律）。准入：单源 T1 锚
      （招股书/年报主营句，或抽取件现成产品列）即可标「做什么」；找不到锚 →
      <b>仅类型归层，待锚</b>，不编造。</div></div>
    <div class="filterbar" id="lfilter">
      <button class="chip on" data-f="all">全部 169</button>
      <button class="chip" data-f="anchored">有锚 48</button>
      <button class="chip" data-f="pending">待锚 121</button>
      <input class="search" id="lsearch" placeholder="检索节点名 / N编号 / 做什么…">
    </div>
    <div id="layers-root"></div>
    <div class="noteblock"><h4>分层方法（源文件原文）</h4><ol id="lmethods"></ol></div>
  </section>

  <section class="view" id="view-content">
    <div class="banner cyan"><span class="tag">未准入 · 不承重</span><div>
      下列 34 + 39 条为<b>内容层样品/试点条目</b>：均<b>未准入</b> <code>output/edges.csv</code> 与关系台账，
      <b>不得作为关系边证据</b>；<b>issuer_self（发行人自述）条目永不承重</b>。工序地图只组织已抽取条目，
      点击条目编号可跳转到台账原文与命中引语。</div></div>
    <div id="proc-root"></div>
    <div class="ledger" id="ledger-lieqi"></div>
    <div class="ledger" id="ledger-yuanjie"></div>
  </section>

  <footer class="foot">
    <div class="foot-copy"><b>诚实边界。</b> ①关系图中，阴影虚线只表示公开披露留下了槽位，
      不能据此点名对手方；DSP 芯片层的 Marvell 与博通使用虚线描边，标为<b>产品映射盲区</b>。
      ②节点分层为宽准入 v0，归层与「做什么」<b>不构成</b>供货/采购关系。③工序/内容为未准入样品，
      issuer_self 条目永不承重。点击 ① 中任意节点查看其全部入边与出边，点击边查看证据文件、
      年份、金额与锚点。</div>
    <div class="badge" id="badge"></div>
  </footer>
</main>
<aside class="drawer" id="drawer" role="dialog" aria-label="证据详情">
  <button class="close" id="dclose" aria-label="关闭">✕</button>
  <div id="dbody"></div>
</aside>
<script id="data" type="application/json">__DATA__</script>
<script id="layerdata" type="application/json">__LAYERS__</script>
<script id="contentdata" type="application/json">__CONTENT__</script>
<script>
/* ================= 视图① 关系图（v1.5 交互语言不变） ================= */
const D=JSON.parse(document.getElementById('data').textContent);
const NS='http://www.w3.org/2000/svg';
const CK={cn:'中国',us:'美国',jt:'日本/台湾',other:'其他',veil:'待核/匿名'};
const CLSNAME={lit:'实边 · 强制披露实名',infer:'推断边 · A/B级判定',
  shadow:'半边槽位 · 对手方不可见',dead:'实边 · 已死亡',
  leak:'程序泄漏 · 侧信道实名'};
const W=1760,PADX=42,TOP=34,ROW_GAP=62;
const svg=document.getElementById('svg'),idmap={},byLayer={};
D.layerOrder.forEach(l=>byLayer[l]=[]);
D.nodes.forEach(n=>{idmap[n.id]=n;byLayer[n.layer].push(n)});
D.layerOrder.forEach(l=>byLayer[l].sort((a,b)=>
  (a.ghost?1:0)-(b.ghost?1:0)||b.deg-a.deg||a.id.localeCompare(b.id,'zh-CN')));

let cursor=TOP;
D.layerOrder.forEach((layer,li)=>{
  const arr=byLayer[layer],rows=arr.length>16?2:1;
  const bandH=rows===2?166:112;
  arr.forEach((n,i)=>{
    const row=rows===2?i%2:0;
    const col=rows===2?Math.floor(i/2):i;
    const inRow=Math.ceil((arr.length-row)/rows);
    const usable=W-PADX*2-180;
    n.x=PADX+170+usable*(col+.5)/Math.max(1,inRow);
    n.y=cursor+(rows===2?(48+row*ROW_GAP):58);
  });
  byLayer[layer]._top=cursor;byLayer[layer]._height=bandH;
  cursor+=bandH;
});
const H=cursor+24;
svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
svg.innerHTML=`<defs><filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
  <feGaussianBlur stdDeviation="1.15" result="b"/><feMerge><feMergeNode in="b"/>
  <feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;

const gBands=document.createElementNS(NS,'g');svg.appendChild(gBands);
D.layerOrder.forEach((layer,li)=>{
  const arr=byLayer[layer],top=arr._top,h=arr._height;
  const rect=document.createElementNS(NS,'rect');
  rect.setAttribute('x','0');rect.setAttribute('y',top);rect.setAttribute('width',W);
  rect.setAttribute('height',h);rect.setAttribute('fill',li%2?'rgba(15,20,32,.34)':'rgba(8,11,20,.18)');
  rect.setAttribute('stroke','var(--grid)');gBands.appendChild(rect);
  const label=document.createElementNS(NS,'text');label.setAttribute('class','band-label');
  label.setAttribute('x',PADX);label.setAttribute('y',top+28);
  label.textContent=`0${li+1}  ${D.layerLabel[layer]}`;gBands.appendChild(label);
  const count=document.createElementNS(NS,'text');count.setAttribute('class','band-count');
  count.setAttribute('x',PADX);count.setAttribute('y',top+47);
  count.textContent=`${D.layerCounts[layer]||0} NODES`;gBands.appendChild(count);
});

function path(a,b){
  if(a.layer===b.layer){
    const lift=Math.max(20,Math.min(55,Math.abs(a.x-b.x)*.18));
    return `M${a.x},${a.y} C${a.x},${a.y-lift} ${b.x},${b.y-lift} ${b.x},${b.y}`;
  }
  const my=(a.y+b.y)/2;
  return `M${a.x},${a.y} C${a.x},${my} ${b.x},${my} ${b.x},${b.y}`;
}
const edgeEls=[],flowEls=[],edgeMap={};
const gEdges=document.createElementNS(NS,'g');svg.appendChild(gEdges);
D.edges.forEach(e=>{
  const a=idmap[e.s],b=idmap[e.d];if(!a||!b)return;edgeMap[e.id]=e;
  const p=document.createElementNS(NS,'path');p.setAttribute('class',`edge ${e.cls}`);
  p.setAttribute('d',path(a,b));p.dataset.cls=e.cls;p._e=e;p._a=a;p._b=b;
  p.addEventListener('click',ev=>{ev.stopPropagation();openEdge(e,a,b)});
  gEdges.appendChild(p);edgeEls.push(p);
  if(e.cls==='lit'&&a.layer!==b.layer){
    const f=document.createElementNS(NS,'path');f.setAttribute('class','flow');
    f.setAttribute('d',path(a,b));f.style.strokeDasharray='3 330';
    f.style.animation=`flow ${3+Math.random()*1.8}s linear infinite`;
    f.style.animationDelay=`${-Math.random()*3}s`;f.dataset.cls='lit';
    gEdges.appendChild(f);flowEls.push(f);
  }
});
const anim=document.createElementNS(NS,'style');
anim.textContent='@keyframes flow{from{stroke-dashoffset:0}to{stroke-dashoffset:-1000}}';
svg.appendChild(anim);

const ABBR={'Applied Optoelectronics(AAOI)':'AAOI','罗博特科/ficonTEC':'罗博特科',
  '索尔思(Source Photonics)':'索尔思','华为(含海思)':'华为',
  '博通(Broadcom)':'博通','Corning Incorporated':'Corning'};
function label(id){
  const raw=id.replace('◈ ','');if(ABBR[raw])return ABBR[raw];
  const clean=raw.replace(/\(.*/,'');
  return clean.length>10?clean.slice(0,9)+'…':clean;
}
const gNodes=document.createElementNS(NS,'g');svg.appendChild(gNodes);
D.nodes.forEach(n=>{
  const g=document.createElementNS(NS,'g');
  g.setAttribute('class',`node ${n.ghost?'ghost ':''}${n.blindspot?'blind ':''}`);
  g.dataset.nid=n.id;
  const title=document.createElementNS(NS,'title');title.textContent=`${n.id.replace('◈ ','')} · ${n.type}`;
  const r=n.ghost?3.5:Math.max(4.8,Math.min(10,4+n.deg*.42));
  const halo=document.createElementNS(NS,'circle');halo.setAttribute('class',`halo ${n.ck}`);
  halo.setAttribute('cx',n.x);halo.setAttribute('cy',n.y);halo.setAttribute('r',r+4);
  halo.setAttribute('stroke',`var(--${n.ck})`);halo.setAttribute('stroke-opacity',n.ghost?'.4':'.88');
  const core=document.createElementNS(NS,'circle');core.setAttribute('class',`core ${n.ck}`);
  core.setAttribute('cx',n.x);core.setAttribute('cy',n.y);core.setAttribute('r',r);
  core.setAttribute('fill-opacity',n.ghost?'.32':'1');if(!n.ghost)core.setAttribute('filter','url(#soft)');
  const text=document.createElementNS(NS,'text');text.setAttribute('class','name');
  text.setAttribute('x',n.x);text.setAttribute('y',n.y+18);text.setAttribute('text-anchor','middle');
  text.textContent=label(n.id);g.append(title,halo,core,text);
  if(n.blindspot){
    const tag=document.createElementNS(NS,'text');tag.setAttribute('class','blind-label');
    tag.setAttribute('x',n.x);tag.setAttribute('y',n.y-14);tag.setAttribute('text-anchor','middle');
    tag.textContent='产品映射盲区';g.appendChild(tag);
  }
  g.addEventListener('click',ev=>{ev.stopPropagation();openNode(n)});
  g.addEventListener('mouseenter',()=>hover(n.id));g.addEventListener('mouseleave',clearHover);
  gNodes.appendChild(g);
});

function neighbors(id){const s=new Set([id]);D.edges.forEach(e=>{
  if(e.s===id)s.add(e.d);if(e.d===id)s.add(e.s)});return s}
function hover(id){const nb=neighbors(id);edgeEls.forEach(p=>{
  const on=p._e.s===id||p._e.d===id;p.classList.toggle('hot',on);p.classList.toggle('dim',!on)});
  document.querySelectorAll('.node').forEach(g=>{
    g.classList.toggle('hot',g.dataset.nid===id);g.classList.toggle('dim',!nb.has(g.dataset.nid))})}
function clearHover(){edgeEls.forEach(p=>p.classList.remove('hot','dim'));
  document.querySelectorAll('.node').forEach(g=>g.classList.remove('hot','dim'))}

const drawer=document.getElementById('drawer'),dbody=document.getElementById('dbody');
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function field(lab,val,mono=false){return val?`<div class="field"><div class="lab">${esc(lab)}</div>
  <div class="val${mono?' mono':''}">${esc(val)}</div></div>`:''}
function openEdge(e,a,b){
  const anchor=/^https?:/.test(e.anchor)?`<div class="field"><div class="lab">锚点 URL</div>
    <div class="val"><a href="${esc(e.anchor)}" target="_blank" rel="noopener">${esc(e.anchor)}</a></div></div>`:
    field('锚点',e.anchor);
  dbody.innerHTML=`<h3>${esc(a.id.replace('◈ ',''))} → ${esc(b.id.replace('◈ ',''))}</h3>
    <span class="gradetag gt-${e.cls}">${esc(e.grade)} · ${CLSNAME[e.cls]}</span>
    ${field('占比 / 金额',e.amt,true)}${field('财年',e.fy,true)}${field('证据文件',e.src)}
    ${anchor}${field('验证状态',e.vs)}${field('备注',e.note)}
    <div class="hint">边 ${esc(e.id)}</div>`;
  drawer.classList.add('open');
}
function openNode(n){
  const outs=D.edges.filter(e=>e.s===n.id),ins=D.edges.filter(e=>e.d===n.id);
  const line=(e,dir)=>`<button class="edge-row" data-eid="${esc(e.id)}"><div class="lab">
    ${dir} ${esc(e.id)} · ${esc(e.grade)}</div><div class="val mono">
    ${esc((dir==='供给'?e.d:e.s).replace('◈ ',''))} · ${esc(e.amt)}</div></button>`;
  dbody.innerHTML=`<h3>${esc(n.id.replace('◈ ',''))}</h3>
    <span class="gradetag gt-${n.ghost?'shadow':'lit'}">${esc(n.type)} · ${CK[n.ck]}</span>
    ${n.blindspot?'<span class="gradetag gt-infer">产品映射盲区</span>':''}
    ${field('所属产业层',D.layerLabel[n.layer])}${field('代码',n.code,true)}${field('备注',n.note)}
    ${outs.length?`<div class="hint">作为供方 · ${outs.length} 条 ↓</div>${outs.map(e=>line(e,'供给')).join('')}`:''}
    ${ins.length?`<div class="hint">作为需方 · ${ins.length} 条 ↓</div>${ins.map(e=>line(e,'获得')).join('')}`:''}`;
  dbody.querySelectorAll('[data-eid]').forEach(el=>el.addEventListener('click',()=>{
    const e=edgeMap[el.dataset.eid];openEdge(e,idmap[e.s],idmap[e.d])}));
  drawer.classList.add('open');
}
document.getElementById('dclose').onclick=()=>drawer.classList.remove('open');
document.addEventListener('keydown',e=>{if(e.key==='Escape')drawer.classList.remove('open')});

const g=D.gradeCounts;
document.getElementById('stats').innerHTML=[
  [D.edgeCount,'条关系边'],[D.canonicalNodeCount,'个数据节点'],[g.lit||0,'实边 · 照亮'],
  [g.shadow||0,'半边 · 阴影'],[g.infer||0,'推断边 · A/B级'],['2A+2B','解匿判例']
].map(([n,k])=>`<div class="stat"><div class="n">${n}</div><div class="k">${k}</div></div>`).join('');
const legend=document.getElementById('legend');
['lit','infer','shadow','dead','leak'].forEach(c=>{
  const el=document.createElement('button');el.className='chip';el.dataset.c=c;
  el.innerHTML=`<span class="sw"></span>${CLSNAME[c]}`;
  el.onclick=()=>{el.classList.toggle('off');const off=el.classList.contains('off');
    edgeEls.forEach(p=>{if(p.dataset.cls===c)p.style.display=off?'none':''});
    flowEls.forEach(f=>{if(f.dataset.cls===c)f.style.display=off?'none':''})};
  legend.appendChild(el);
});
const countries=document.createElement('div');countries.className='chip';countries.style.cursor='default';
countries.innerHTML=Object.entries(CK).map(([k,v])=>`<span style="display:inline-flex;align-items:center;
  gap:4px"><span style="width:7px;height:7px;border-radius:50%;background:var(--${k})"></span>${v}</span>`).join(' · ');
legend.appendChild(countries);
document.getElementById('badge').textContent=D.badge;

/* ================= 视图切换 ================= */
function switchView(v){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===v));
  document.querySelectorAll('.view').forEach(s=>s.classList.toggle('active',s.id==='view-'+v));
  history.replaceState(null,'','#'+v);
  drawer.classList.remove('open');
}
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>switchView(t.dataset.view)));
if(['graph','layers','content'].includes(location.hash.slice(1)))switchView(location.hash.slice(1));

/* ================= 视图② 节点分层 ================= */
const L=JSON.parse(document.getElementById('layerdata').textContent);
function lcard(n){
  return `<div class="lcard ${n.anchored?'':'pending'}" data-anchored="${n.anchored?1:0}"
    data-text="${esc(n.nid+' '+n.name+' '+n.doing).toLowerCase()}">
    <div class="nid">${esc(n.nid)}</div><div class="nm">${esc(n.name)}</div>
    <div class="doing">${esc(n.doing)}</div>
    <div class="st"><span class="dot ${n.anchored?'ok':'no'}"></span>
      <span class="${n.anchored?'ok-t':'no-t'}">${n.anchored?'有锚':'待锚'}</span>
      ${n.stance?`<span class="stance">${esc(n.stance)}</span>`:''}</div></div>`;
}
(function renderLayers(){
  const root=document.getElementById('layers-root');let html='';let mi=0;
  L.groups.forEach(gr=>{
    if(gr.kind==='main'){
      mi++;
      if(mi>1)html+=`<div class="flow-arrow">▼ 下游</div>`;
      const an=gr.nodes.filter(n=>n.anchored).length;
      html+=`<div class="lband"><div class="lband-head"><span class="idx">L${mi}</span>
        <h3>${esc(gr.title)}</h3><span class="cnt">${gr.nodes.length} 节点 · 有锚 ${an} / 待锚 ${gr.nodes.length-an}</span></div>
        <div class="lcards">${gr.nodes.map(lcard).join('')}</div></div>`;
    }
  });
  const vg=L.groups.find(g=>g.kind==='v');
  if(vg){
    const an=vg.nodes.filter(n=>n.anchored).length;
    html+=`<div class="vband"><div class="lband"><div class="lband-head"><span class="idx">V</span>
      <h3>${esc(vg.title)}</h3><span class="cnt">${vg.nodes.length} 节点 · 有锚 ${an} / 待锚 ${vg.nodes.length-an}</span></div>
      <div class="lcards">${vg.nodes.map(lcard).join('')}</div></div></div>`;
  }
  const xgs=L.groups.filter(g=>g.kind==='x');
  if(xgs.length){
    html+=`<div class="xzone"><h3>X · 非 BOM 主链 / 边界外 / 匿名槽位（同样不承重）</h3>`;
    xgs.forEach(gr=>{
      const an=gr.nodes.filter(n=>n.anchored).length;
      html+=`<div class="lband"><div class="lband-head"><span class="idx">X</span>
        <h3>${esc(gr.title)}</h3><span class="cnt">${gr.nodes.length} 节点 · 有锚 ${an} / 待锚 ${gr.nodes.length-an}</span></div>
        <div class="lcards">${gr.nodes.map(lcard).join('')}</div></div>`;
    });
    html+='</div>';
  }
  root.innerHTML=html;
  document.getElementById('lmethods').innerHTML=L.methods.map(m=>`<li>${esc(m)}</li>`).join('');
  root.querySelectorAll('.lcard').forEach(el=>{
    el.addEventListener('click',()=>{
      const nid=el.querySelector('.nid').textContent;
      let found=null,gt='';
      L.groups.forEach(gr=>gr.nodes.forEach(n=>{if(n.nid===nid){found=n;gt=gr.title}}));
      if(!found)return;
      dbody.innerHTML=`<h3>${esc(found.name)}</h3>
        <span class="gradetag ${found.anchored?'gt-lit':'gt-shadow'}">${found.anchored?'有锚':'仅类型归层 · 待锚'}</span>
        ${found.stance?`<span class="gradetag gt-infer">stance=${esc(found.stance)}</span>`:''}
        ${field('节点编号',found.nid,true)}${field('归层',gt)}
        ${field('做什么',found.doing)}${field('锚（原文照录）',found.anchor||'—')}
        <div class="hint">节点层宽准入 · 不承重：归层与「做什么」不得读作供货/采购关系</div>`;
      drawer.classList.add('open');
    });
  });
  let lf='all';
  function applyL(){
    const q=document.getElementById('lsearch').value.trim().toLowerCase();
    document.querySelectorAll('#layers-root .lcard').forEach(el=>{
      const okF=lf==='all'||(lf==='anchored'&&el.dataset.anchored==='1')||(lf==='pending'&&el.dataset.anchored==='0');
      const okQ=!q||el.dataset.text.includes(q);
      el.style.display=okF&&okQ?'':'none';
    });
  }
  document.querySelectorAll('#lfilter .chip').forEach(c=>c.addEventListener('click',()=>{
    lf=c.dataset.f;
    document.querySelectorAll('#lfilter .chip').forEach(x=>x.classList.toggle('on',x===c));
    applyL();
  }));
  document.getElementById('lsearch').addEventListener('input',applyL);
})();

/* ================= 视图③ 工序/内容 ================= */
const C=JSON.parse(document.getElementById('contentdata').textContent);
const EIDX={};
['lieqi','yuanjie'].forEach(k=>C[k].entries.forEach(e=>EIDX[e.cid]={e,ledger:k}));
const TBC={ '①':'tb1','②':'tb2','③':'tb3','④':'tb4','⑤':'tb5' };
function shortLabel(e){
  const first=e.content.split(/[；;。]/)[0];
  return first.length>32?first.slice(0,31)+'…':first;
}
(function renderProc(){
  const root=document.getElementById('proc-root');let html='';
  C.mapLanes.forEach(lane=>{
    html+=`<div class="proc-lane"><div class="proc-lane-head"><h3>${esc(lane.title)}</h3>
      <span>${esc(lane.sub)}</span></div><div class="proc-steps">`;
    lane.steps.forEach((st,i)=>{
      if(i>0)html+=`<div class="ps-arrow">→</div>`;
      html+=`<div class="proc-step ${st.gap?'gap':''}"><div class="ps-name">${esc(st.name)}</div>`;
      if(st.gap)html+=`<div class="ps-note">${esc(st.gap)}</div>`;
      st.cids.forEach(cid=>{const rec=EIDX[cid];if(rec)
        html+=`<button class="cidchip" data-cid="${cid}"><b>${cid}</b>${esc(shortLabel(rec.e))}</button>`});
      html+='</div>';
    });
    html+='</div>';
    if(lane.subflow){
      html+=`<div class="subflow"><span class="sfref">${lane.subflow.ref} 自主生产线工序 →</span>
        ${lane.subflow.steps.map(s=>`<span class="sf">${esc(s)}</span>`).join('')}</div>`;
    }
    if(lane.notes&&lane.notes.length){
      html+=`<div class="proc-notes">${lane.notes.map(cid=>{
        const rec=EIDX[cid];return rec?`<button class="cidchip" data-cid="${cid}"><b>${cid}</b>${esc(shortLabel(rec.e))}</button>`:''}).join('')}</div>`;
    }
    html+='</div>';
  });
  root.innerHTML=html;
  root.querySelectorAll('[data-cid]').forEach(el=>el.addEventListener('click',()=>jumpTo(el.dataset.cid)));
})();
function stanceBadge(e){
  let h='';
  if(e.stanceCls==='issuer_self')h+=`<span class="sbadge sb-issuer">issuer_self · 永不承重</span>`;
  else if(e.stanceCls==='industry')h+=`<span class="sbadge sb-industry">industry</span>`;
  else if(e.stanceCls==='neutral')h+=`<span class="sbadge sb-neutral">neutral</span>`;
  if(e.tense)h+=`<span class="sbadge sb-tense">${esc(e.tense)}</span>`;
  return h;
}
function entryHtml(e){
  const quotes=e.quotes.map(([k,v])=>`<blockquote><span class="qlab">${esc(k)}</span>${esc(v)}</blockquote>`).join('');
  const meta=e.meta.map(([k,v])=>`<div class="kv"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join('');
  const notes=e.notes.map(([k,v])=>`<div class="kv warn"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join('');
  return `<details class="centry" id="entry-${e.cid}" data-tnum="${e.tnum}" data-stance="${esc(e.stanceCls)}"
    data-text="${esc((e.cid+' '+e.content+' '+e.quotes.map(q=>q[1]).join(' ')).toLowerCase())}">
    <summary><div class="crow"><span class="cid">${e.cid}</span>
      <span class="tbadge ${TBC[e.tnum]||''}">${esc(e.typeLabel)}</span>${stanceBadge(e)}
      <span class="openhint">引语与溯源 ▾</span></div>
      <h4>${esc(e.content)}</h4></summary>
    <div class="cbody">${quotes}${meta}${notes}</div></details>`;
}
function renderLedger(key,mountId){
  const ld=C[key],mount=document.getElementById(mountId);
  const tchips=Object.entries(ld.tlabels).map(([t,lab])=>
    `<button class="chip" data-t="${t}">${t}${lab} ${ld.tcounts[t]||0}</button>`).join('');
  const schips=ld.stanceCounts?Object.entries(ld.stanceCounts).map(([s,n])=>
    `<button class="chip" data-s="${s}">${s} ${n}</button>`).join(''):'';
  mount.innerHTML=`<div class="ledger-head"><h3>${esc(ld.title)}</h3>
    <div class="lmeta">${esc(ld.status)} · ${esc(ld.schema)}<br>语料：${esc(ld.corpus)}<br>
    统一锚点：<a href="${esc(ld.anchor)}" target="_blank" rel="noopener">${esc(ld.anchor)}</a></div>
    <div class="disc">${esc(ld.discipline)}</div></div>
    <div class="filterbar"><button class="chip on" data-t="all">全部 ${ld.total}</button>${tchips}${schips}
    <input class="search" placeholder="检索编号 / 内容 / 引语…"></div>
    <div class="elist">${ld.entries.map(entryHtml).join('')}</div>
    <div class="noteblock"><h4>诚实边界（源文件原文）</h4><ol>${ld.boundaries.map(b=>`<li>${esc(b)}</li>`).join('')}</ol></div>`;
  let ft='all',fs='all';
  const q=mount.querySelector('.search');
  function apply(){
    const qq=q.value.trim().toLowerCase();
    mount.querySelectorAll('.centry').forEach(el=>{
      const okT=ft==='all'||el.dataset.tnum===ft;
      const okS=fs==='all'||el.dataset.stance===fs;
      const okQ=!qq||el.dataset.text.includes(qq);
      el.style.display=okT&&okS&&okQ?'':'none';
    });
  }
  mount.querySelectorAll('.filterbar .chip').forEach(c=>c.addEventListener('click',()=>{
    if(c.dataset.s){fs=fs===c.dataset.s?'all':c.dataset.s;
      mount.querySelectorAll('[data-s]').forEach(x=>x.classList.toggle('on',x.dataset.s===fs));}
    else{ft=c.dataset.t;
      mount.querySelectorAll('[data-t]').forEach(x=>x.classList.toggle('on',x.dataset.t===ft));}
    apply();
  }));
  q.addEventListener('input',apply);
  mount._reset=function(){ft='all';fs='all';q.value='';
    mount.querySelectorAll('.filterbar .chip').forEach(x=>x.classList.toggle('on',x.dataset.t==='all'));
    apply();};
}
renderLedger('lieqi','ledger-lieqi');
renderLedger('yuanjie','ledger-yuanjie');
function jumpTo(cid){
  const rec=EIDX[cid];if(!rec)return;
  switchView('content');
  document.getElementById(rec.ledger==='lieqi'?'ledger-lieqi':'ledger-yuanjie')._reset();
  const el=document.getElementById('entry-'+cid);
  el.open=true;
  setTimeout(()=>{el.scrollIntoView({behavior:'smooth',block:'center'});
    el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');},60);
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 装配与断言

def main():
    graph = build_graph()
    layers = parse_layer_md()
    content = build_content()

    def payload(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    html = (HTML
            .replace("__DATA__", payload(graph))
            .replace("__LAYERS__", payload(layers))
            .replace("__CONTENT__", payload(content)))

    # 视图① 四硬约束
    assert graph["edgeCount"] == 236, graph["edgeCount"]
    assert graph["canonicalNodeCount"] == 169, graph["canonicalNodeCount"]
    assert sum(graph["layerCounts"].values()) == 169
    assert graph["gradeCounts"].get("infer") == 4
    assert {"Marvell", "博通(Broadcom)"}.issubset(
        {n["id"] for n in graph["nodes"] if n.get("blindspot")}
    )
    assert "236边/169节点/判例2A+2B" in html
    assert not re.search(
        r'<(?:script|link)[^>]+(?:src|href)\s*=\s*["\']https?://', html, re.I
    ), "HTML 含外部脚本或样式依赖"

    # 视图② 与源文件元数据对账
    assert layers["meta"]["total"] == 169, layers["meta"]
    assert layers["meta"]["anchored"] == 48, layers["meta"]
    assert layers["meta"]["pending"] == 121, layers["meta"]
    assert len(layers["groups"]) == 12
    assert len(layers["methods"]) == 4

    # 视图③ 与源文件汇总对账
    lq, yj = content["lieqi"], content["yuanjie"]
    assert lq["total"] == 34 and lq["tcounts"] == {"①": 6, "②": 8, "③": 6, "④": 8, "⑤": 6}
    assert yj["total"] == 39 and yj["tcounts"] == {"①": 8, "②": 8, "③": 8, "④": 8, "⑤": 7}
    assert yj["stanceCounts"] == {"neutral": 25, "industry": 10, "issuer_self": 4}
    issuer_cids = {e["cid"] for e in yj["entries"] if e["stanceCls"] == "issuer_self"}
    assert issuer_cids == {"YJ16", "YJ24", "YJ32", "YJ39"}, issuer_cids
    overlap = {e["cid"] for e in yj["entries"] if any("重叠" in k for k, _ in e["notes"])}
    assert overlap == {"YJ25", "YJ26", "YJ32"}, overlap
    all_cids = {e["cid"] for e in lq["entries"]} | {e["cid"] for e in yj["entries"]}
    c01 = next(e for e in lq["entries"] if e["cid"] == "C01")
    for kw in ("贴片", "引线键合", "光学耦合", "老化测试", "不含引线键合设备"):
        assert kw in c01["content"], kw
    yj01 = next(e for e in yj["entries"] if e["cid"] == "YJ01")
    for kw in ("芯片设计", "晶圆制造", "芯片加工", "测试"):
        assert kw in yj01["content"], kw
    yj02 = next(e for e in yj["entries"] if e["cid"] == "YJ02")
    for lane in content["mapLanes"]:
        for st in lane["steps"]:
            for cid in st["cids"]:
                assert cid in all_cids, cid
        for cid in lane.get("notes", []):
            assert cid in all_cids, cid
        if "subflow" in lane:
            for kw in lane["subflow"]["steps"]:
                assert kw in yj02["content"], kw

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"wrote {OUT_PATH} {len(html)} bytes")
    print(f"视图①: {graph['edgeCount']}边 / {graph['canonicalNodeCount']}节点 / "
          f"幽灵槽位{graph['ghostCount']} / 等级{dict(graph['gradeCounts'])}")
    print(f"视图②: {layers['meta']['total']}节点 有锚{layers['meta']['anchored']} "
          f"待锚{layers['meta']['pending']} 共{len(layers['groups'])}组")
    print(f"视图③: 猎奇{lq['total']}条 {lq['tcounts']} / 源杰{yj['total']}条 {yj['tcounts']} "
          f"stance{yj['stanceCounts']}")
    print("自测: 236边✓ 169节点✓ 徽章✓ 零外部依赖✓ 节点层48/121✓ 内容34+39✓ "
          "issuer_self红线✓ 工序图cid闭环✓")


if __name__ == "__main__":
    main()
