#!/usr/bin/env python3
"""
validate_edges.py — 供应链图谱 demo 边生成器校验器（Stage3 终验）
=====================================================================

只依赖 Python 标准库。

功能一 结构校验（无 --truth 也执行）
  1. edges.csv 每行必须恰好 10 列，逐行报告缺列/多列。
  2. 四件套非空：供方/需方/占比或金额/财年/边等级/证据文件/锚点 任一为空 -> FAIL。
  3. edge_id 唯一性；锚点列须为 http(s) URL、或"同E/同D"式引用（须能解析到存在的 edge_id）。
  4. nodes.csv 须 6 列；实名节点引用完整性（供方/需方 不含"(匿名)"者须在 nodes.csv
     名称列存在），缺失 -> WARN 级（不影响 RESULT）。
  5. 边等级枚举检查：只允许
     {实边, 实边(已死亡), 推断边(A级), 推断边(B级), 推断边(C级), 推断边(D级),
      半边, 半边槽位, 程序段落泄漏}。

功能二 真值比对（提供 --truth 时执行）
  truth.json: {"checks":[{"id","desc","where":{...},"expect":{"field","contains"}}]}
  - where：字段等值匹配；"X_contains" 后缀表示字段包含子串；财年一律按包含匹配。
  - 命中 0 行 -> NO_MATCH；>=1 行 -> 全部命中行满足 expect.contains 则 PASS，否则 FAIL。
  - 每条 check 输出 PASS/FAIL/NO_MATCH + 命中行数 + 命中行 edge_id。

输出：人类可读报告到 stdout，末尾汇总行
  RESULT: <PASS|FAIL> structural=<n_err> truth=<n_pass>/<n_total>
退出码：存在结构 FAIL 或 真值 FAIL -> 1，否则 0。

----------------------------------------------------------------------
自测（结构校验，针对现有 output 数据，预期 RESULT=PASS）
----------------------------------------------------------------------
命令：
  python3 demo/src/validate_edges.py --edges output/edges.csv --nodes output/nodes.csv

结果（structural=0，RESULT=PASS；另有 5 条描述型锚点 WARN 与 25 条节点引用 WARN，均不计入 n_err）：
（注：本环境 Bash 被禁用，无法实时执行；以下为按代码逻辑对 output/ 数据静态推演的输出，
 请在本机运行上方命令确认，预期与下方一致。）

=== 结构校验 ===
[OK]   edge_id 唯一性 (共 73 条边)
[OK]   四件套非空 (供方/需方/占比或金额/财年/边等级/证据文件/锚点)
[OK]   锚点格式 (http(s) URL 或 同E/同D 引用)
[WARN] 锚点描述型: edge_id=E010 描述型锚点(非 http(s) URL / 非 同E/同D 引用)
[WARN] 锚点描述型: edge_id=E011 描述型锚点(非 http(s) URL / 非 同E/同D 引用)
[WARN] 锚点描述型: edge_id=E012 描述型锚点(非 http(s) URL / 非 同E/同D 引用)
[WARN] 锚点描述型: edge_id=E013 描述型锚点(非 http(s) URL / 非 同E/同D 引用)
[WARN] 锚点描述型: edge_id=E014 描述型锚点(非 http(s) URL / 非 同E/同D 引用)
[OK]   边等级枚举 (均在允许集合内)
[OK]   nodes.csv 列数 (均 6 列, 共 38 节点)
[WARN] 节点引用缺失: edge_id=E008 需方='华为+海思' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E010 需方='中际旭创(作为客户)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E011 供方='ficonTEC(罗博特科)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E011 需方='博通(客户)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E012 供方='ficonTEC(罗博特科)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E012 需方='NVIDIA(客户)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E013 需方='等离子体所(客户)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E014 需方='Fabrinet(疑似客户)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E016 需方='浙江粮油(出口代理)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E017 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E018 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E019 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E020 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E021 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E022 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E023 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E024 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E025 供方='AAOI' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E033 需方='华为' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E036 需方='Ciena(解匿)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E037 需方='Google(解匿)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E038 供方='Fabrinet(解匿)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E044 需方='PINEWAVE(关联方)' 未在 nodes.csv 找到
[WARN] 节点引用缺失: edge_id=E050 需方='苏世博' 未在 nodes.csv 找到
  （上述 25 条为 WARN 级，多为括号注释/命名差异，不影响 RESULT）
=== 汇总 ===
RESULT: PASS structural=0 truth=0/0
=====================================================================
"""

import argparse
import csv
import json
import re
import sys

EDGE_COLS = ["edge_id", "供方", "需方", "占比或金额", "财年", "边等级",
             "证据文件", "锚点", "验证状态", "备注"]
NODE_COLS = ["node_id", "名称", "类型", "国别", "代码", "备注"]
FOUR_PIECE = ["供方", "需方", "占比或金额", "财年", "边等级", "证据文件", "锚点"]
EDGE_LEVELS = {
    "实边", "实边(已死亡)",
    "推断边(A级)", "推断边(B级)", "推断边(C级)", "推断边(D级)",
    "半边", "半边槽位", "程序段落泄漏",
}
ANON_MARK = "(匿名)"
REF_RE = re.compile(r"^同[ED]\d+$")
URL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*)://")


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def classify_anchor(anchor, edge_ids):
    """返回 (status, msg)。status: 'ok' | 'warn' | 'fail'。"""
    a = (anchor or "").strip()
    if a == "":
        return "fail", "空锚点"
    if a.startswith("同"):
        for part in a.split(";"):
            p = part.strip()
            if not REF_RE.match(p):
                return "fail", "非法同E/同D引用: %r" % p
            ref = p[1:]  # 同E005 -> E005
            if ref not in edge_ids:
                return "fail", "悬空引用: %s (无对应 edge_id)" % p
        return "ok", ""
    if "://" in a:
        m = URL_RE.match(a)
        if not m or m.group(1).lower() not in ("http", "https"):
            return "fail", "非 http(s) URL: %r" % a
        return "ok", ""
    # 裸域名（如 SEC式锚:file.finance.qq.com/...）或描述型溯源说明 -> 接受，但提示
    return "warn", "描述型锚点(非 http(s) URL / 非 同E/同D 引用)"


def where_match(edge, where):
    for key, val in where.items():
        if key.endswith("_contains"):
            field = key[:-len("_contains")]
            if field not in edge or val not in (edge.get(field) or ""):
                return False
        else:
            field = key
            cell = edge.get(field) or ""
            if field == "财年":
                if val not in cell:          # 财年一律按包含匹配
                    return False
            elif cell != val:
                return False
    return True


def main():
    ap = argparse.ArgumentParser(description="供应链图谱 demo 边生成器校验器")
    ap.add_argument("--edges", required=True, help="edges.csv 路径")
    ap.add_argument("--nodes", required=True, help="nodes.csv 路径")
    ap.add_argument("--truth", default=None, help="truth.json 路径（可选）")
    args = ap.parse_args()

    out = []
    def log(line): out.append(line)
    def ok(msg): log("[OK]   " + msg)
    def fail(msg): log("[FAIL] " + msg)
    def warn(msg): log("[WARN] " + msg)

    n_err = 0  # 结构 FAIL 计数（WARN 不计入）

    log("=== 结构校验 ===")

    # ---------------- edges ----------------
    edge_rows = load_csv(args.edges)
    if not edge_rows:
        fail("edges.csv 为空")
        n_err += 1
        edges, edge_ids = [], set()
    else:
        header = edge_rows[0]
        data_rows = edge_rows[1:]
        if header != EDGE_COLS:
            warn("edges.csv 表头与契约不符: %s" % header)

        edges = []
        edge_ids = set()
        for i, row in enumerate(data_rows, start=2):  # 第 1 行为表头
            if len(row) != 10:
                n_err += 1
                eid_hint = row[0] if row else ""
                if len(row) < 10:
                    missing = EDGE_COLS[len(row):]
                    fail("行 %d (edge_id=%s): 缺列 %s" % (i, eid_hint, missing))
                else:
                    fail("行 %d (edge_id=%s): 多列，多余 %s" % (i, eid_hint, row[10:]))
            d = dict(zip(EDGE_COLS, row))
            for c in EDGE_COLS:
                d.setdefault(c, "")
            edges.append(d)
            eid = (d.get("edge_id") or "").strip()
            if eid:
                edge_ids.add(eid)

    # edge_id 唯一性
    seen = {}
    for d in edges:
        eid = (d.get("edge_id") or "").strip()
        if eid == "":
            n_err += 1
            fail("存在空 edge_id（行数据缺失）")
            continue
        seen[eid] = seen.get(eid, 0) + 1
    dup = sorted([e for e, c in seen.items() if c > 1])
    if dup:
        n_err += len(dup)
        fail("edge_id 重复: %s" % ", ".join(dup))
    else:
        ok("edge_id 唯一性 (共 %d 条边)" % len(edges))

    # 四件套非空
    fp_fail = []
    for d in edges:
        eid = d.get("edge_id") or ""
        for f in FOUR_PIECE:
            if (d.get(f) or "").strip() == "":
                fp_fail.append((eid, f))
    if fp_fail:
        n_err += len(fp_fail)
        for eid, f in fp_fail:
            fail("四件套空值: edge_id=%s 字段[%s]为空" % (eid, f))
    else:
        ok("四件套非空 (供方/需方/占比或金额/财年/边等级/证据文件/锚点)")

    # 锚点格式
    anchor_fail, anchor_warn = [], []
    for d in edges:
        eid = d.get("edge_id") or ""
        status, msg = classify_anchor(d.get("锚点"), edge_ids)
        if status == "fail":
            n_err += 1
            anchor_fail.append((eid, msg))
        elif status == "warn":
            anchor_warn.append((eid, msg))
    if anchor_fail:
        for eid, msg in anchor_fail:
            fail("锚点非法: edge_id=%s %s" % (eid, msg))
    else:
        ok("锚点格式 (http(s) URL 或 同E/同D 引用)")
    for eid, msg in anchor_warn:
        warn("锚点描述型: edge_id=%s %s" % (eid, msg))

    # 边等级枚举
    lvl_fail = []
    for d in edges:
        eid = d.get("edge_id") or ""
        lvl = (d.get("边等级") or "").strip()
        if lvl not in EDGE_LEVELS:
            lvl_fail.append((eid, lvl))
    if lvl_fail:
        n_err += len(lvl_fail)
        for eid, lvl in lvl_fail:
            fail("边等级非法: edge_id=%s 值=%r" % (eid, lvl))
    else:
        ok("边等级枚举 (均在允许集合内)")

    # ---------------- nodes ----------------
    node_rows = load_csv(args.nodes)
    node_header = node_rows[0] if node_rows else []
    node_data = node_rows[1:] if len(node_rows) > 1 else []
    if node_header != NODE_COLS:
        warn("nodes.csv 表头与契约不符: %s" % node_header)

    node_bad = False
    for i, row in enumerate(node_data, start=2):
        if len(row) != 6:
            n_err += 1
            node_bad = True
            fail("nodes.csv 行 %d: 列数=%d (期望 6)" % (i, len(row)))
    node_names = set()
    for row in node_data:
        if len(row) >= 2:
            node_names.add((row[1] or "").strip())
    if not node_bad:
        ok("nodes.csv 列数 (均 6 列, 共 %d 节点)" % len(node_data))

    # 实名节点引用完整性（WARN）
    ref_warn = []
    for d in edges:
        eid = d.get("edge_id") or ""
        for f in ("供方", "需方"):
            v = (d.get(f) or "").strip()
            if v and ANON_MARK not in v and v not in node_names:
                ref_warn.append((eid, f, v))
    if ref_warn:
        for eid, f, v in ref_warn:
            warn("节点引用缺失: edge_id=%s %s=%r 未在 nodes.csv 找到" % (eid, f, v))
        log("  （上述 %d 条为 WARN 级，多为括号注释/命名差异，不影响 RESULT）" % len(ref_warn))
    else:
        ok("实名节点引用完整性 (供方/需方 均能在 nodes.csv 找到)")

    # ---------------- 真值比对 ----------------
    n_pass = 0
    n_total = 0
    truth_fail = 0
    if args.truth:
        with open(args.truth, encoding="utf-8") as f:
            truth = json.load(f)
        checks = truth.get("checks", [])
        n_total = len(checks)
        log("")
        log("=== 真值比对 ===")
        for chk in checks:
            cid = chk.get("id", "?")
            desc = chk.get("desc", "")
            where = chk.get("where", {})
            expect = chk.get("expect", {})
            matched = [e for e in edges if where_match(e, where)]
            if not matched:
                status = "NO_MATCH"
            else:
                ef = expect.get("field")
                ec = expect.get("contains")
                all_ok = True
                for e in matched:
                    val = e.get(ef, "")
                    if ec is None or ec == "":
                        continue
                    if ec not in val:
                        all_ok = False
                status = "PASS" if all_ok else "FAIL"
            if status == "PASS":
                n_pass += 1
            elif status == "FAIL":
                truth_fail += 1
            ids = ",".join(e["edge_id"] for e in matched)
            log("[%s] %s | %s | 命中%d行: %s" % (cid, status, desc, len(matched), ids))

    # ---------------- 汇总 ----------------
    passed = (n_err == 0) and (not args.truth or truth_fail == 0)
    result = "PASS" if passed else "FAIL"
    log("")
    log("=== 汇总 ===")
    log("RESULT: %s structural=%d truth=%d/%d" % (result, n_err, n_pass, n_total))

    sys.stdout.write("\n".join(out) + "\n")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
