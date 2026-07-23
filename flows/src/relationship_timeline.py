#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关系级时间聚合 (R3) —— 严格按 flows/relationship-timeline-contract.md 实现。

输入:
  - flows/out/edge-timeline.csv   (上轮 per-edge 产出: edge_id,供方,需方,year,pct_or_amt,observe_type)
  - output/edges.csv              (关系级 period_type 来源: edge_id -> 财年)

输出:
  - flows/out/relationship-timeline.csv
    schema: relation_id,供方,需方,period,period_type,pct_or_amt,observe_type,source_edge_ids,conflict

契约要点:
  1. 关系键经内置别名映射归一化(不按显示名 groupby);匿名端点含"匿名"不聚合。
  2. FY 与自然年不混同: period = "FY"+year (财年以 FY 开头时), period_type=fiscal。
  3. 同年同关系多边冲突: 金额/占比一致合并(列全来源边); 不一致保留多行 conflict=true。
  4. first_observed/last_observed/confirmed_ended 在关系级重算(跨边); observed 优先于 censored。
  5. 每个聚合事件行带 source_edge_ids(分号分隔), 不丢证据链。

仅用标准库。
"""

import csv
import os
import re
import sys

# ----------------------------------------------------------------------------
# 0. 路径 (相对脚本位置, 与 cwd 无关)
# ----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))          # .../workflow-rehearsal
EDGE_TIMELINE_CSV = os.path.join(REPO_ROOT, "flows", "out", "edge-timeline.csv")
EDGES_CSV = os.path.join(REPO_ROOT, "output", "edges.csv")
OUT_CSV = os.path.join(REPO_ROOT, "flows", "out", "relationship-timeline.csv")

# ----------------------------------------------------------------------------
# 1. 关系键别名映射表 (契约 §1, 实现内置 dict)
# ----------------------------------------------------------------------------
ALIAS = {
    "Fabrinet(解匿)": "Fabrinet",
    "Ciena(解匿)": "Ciena",
    "Google(解匿)": "Google",
    "中际旭创(作为客户)": "中际旭创",
    "华为+海思": "华为(含海思)",
    "华为": "华为(含海思)",
    "博通(客户)": "博通(Broadcom)",
    "Broadcom": "博通(Broadcom)",
    "NVIDIA(客户)": "NVIDIA",
    "ficonTEC(罗博特科)": "罗博特科/ficonTEC",
    # 契约 v1.1 (2026-07-24) 补: 裸名 E076 与 E011/E012 同一主体
    "罗博特科": "罗博特科/ficonTEC",
    "PINEWAVE(关联方)": "PINEWAVE",
    "浙江粮油(出口代理)": "浙江粮油",
    "索尔思(Source Photonics)": "索尔思(Source Photonics)",
    "苏世博": "索恩格(SEG Automotive)",
}


def normalize(name):
    """应用契约别名映射; 匿名端点原样保留(靠完整键名天然不聚合)。"""
    return ALIAS.get(name, name)


def is_anonymous(name):
    return "匿名" in name


# ----------------------------------------------------------------------------
# 2. 期间键 / period_type 推导 (契约 §2)
# ----------------------------------------------------------------------------
def derive_period(fy_raw, year):
    """返回 (period, period_type)。

    fy_raw : output/edges.csv 的 财年 字段 (用于判定 FY 口径)
    year   : edge-timeline.csv 的 year 字段 (裸年如 '2023', 或 '2025Q1'/'2025-09'/'2023-2025')
    """
    fy_raw = (fy_raw or "").strip()
    if fy_raw.upper().startswith("FY"):
        # FY 口径: 给裸年加 FY 前缀, 与自年显式区分
        y = year.strip()
        period = y if y.upper().startswith("FY") else "FY" + y
        return period, "fiscal"
    # 自然年口径
    y = year.strip()
    if "Q" in y.upper():
        return y, "quarter"
    if re.match(r"^\d{4}-\d{2}$", y):
        return y, "month"
    return y, "year"


# ----------------------------------------------------------------------------
# 3. 期间排序键 (跨口径可比, 仅用于关系内 first/last 判定)
# ----------------------------------------------------------------------------
def sort_key(period, ptype):
    try:
        if ptype == "fiscal":
            y = int(re.match(r"FY(\d{4})", period).group(1)); sub = 0.0
        elif ptype == "quarter":
            m = re.match(r"(\d{4})Q(\d)", period); y = int(m.group(1)); sub = int(m.group(2)) / 4.0
        elif ptype == "month":
            m = re.match(r"(\d{4})-(\d{2})", period); y = int(m.group(1)); sub = int(m.group(2)) / 12.0
        elif ptype == "year":
            if "-" in period:
                y = int(period.split("-")[0]); sub = 0.0
            else:
                y = int(period); sub = 0.0
        else:
            y = 0; sub = 0.0
    except Exception:
        y = 0; sub = 0.0
    return y + sub


# ----------------------------------------------------------------------------
# 4. 关系级 observe_type 裁决 (契约 §4)
# ----------------------------------------------------------------------------
OBSERVED_TYPES = ("observed", "first_observed", "last_observed")


def resolve_observe_type(period, sorted_periods, edge_obs):
    is_first = (period == sorted_periods[0])
    is_last = (period == sorted_periods[-1])
    has_confirmed_ended = any(o == "confirmed_ended" for o in edge_obs)
    has_observation = any(o in OBSERVED_TYPES for o in edge_obs)
    all_censored = all(o == "censored" for o in edge_obs)

    if is_first:
        return "first_observed" if has_observation else "censored"
    if is_last:
        if has_confirmed_ended:
            return "confirmed_ended"
        if has_observation:
            return "last_observed"
        return "censored"
    # 中间期: observed 优先 (契约 §4 同期间 observed 盖过 censored)
    if has_observation:
        return "observed"
    return "censored"


# ----------------------------------------------------------------------------
# 5. 主流程
# ----------------------------------------------------------------------------
def load_fy_map():
    """edge_id -> 财年 (output/edges.csv 第5列)。"""
    fy_map = {}
    with open(EDGES_CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            eid = row["edge_id"].strip()
            if eid and eid not in fy_map:
                fy_map[eid] = row.get("财年", "")
    return fy_map


def load_events(fy_map, warnings):
    """读取 per-edge 时间线, 归一化 + 推导 period, 返回事件列表。"""
    events = []
    missing_fy = []
    with open(EDGE_TIMELINE_CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            eid = row["edge_id"].strip()
            sup_raw = row["供方"].strip()
            con_raw = row["需方"].strip()
            year = row["year"].strip()
            pct = row["pct_or_amt"].strip()
            obs = row["observe_type"].strip()

            sup = normalize(sup_raw)
            con = normalize(con_raw)
            rel_key = (sup, con)

            fy_raw = fy_map.get(eid)
            if fy_raw is None:
                missing_fy.append(eid)
                fy_raw = ""  # 退化为按 year 内容判口径
            period, ptype = derive_period(fy_raw, year)

            events.append({
                "edge_id": eid,
                "rel_key": rel_key,
                "period": period,
                "ptype": ptype,
                "pct": pct,
                "obs": obs,
                "anon": is_anonymous(sup) or is_anonymous(con),
            })
    if missing_fy:
        warnings.append("边 %s 在 output/edges.csv 缺失 财年, 退化为按 year 判口径" % ",".join(sorted(set(missing_fy))))
    return events


def aggregate(events, warnings):
    """关系级聚合。返回 (relationships: list of dict, conflict_total)。"""
    by_rel = {}
    for ev in events:
        by_rel.setdefault(ev["rel_key"], []).append(ev)

    relationships = []
    conflict_total = 0

    for rel_key in sorted(by_rel.keys(), key=lambda k: (k[0], k[1])):
        sup, con = rel_key
        evs = by_rel[rel_key]
        # 关系内按 (period 排序键, period 串) 分组
        period_keys = {}
        for ev in evs:
            pk = (ev["period"], ev["ptype"])
            period_keys.setdefault(pk, []).append(ev)

        # 关系级时间轴用于 first/last 裁决
        sorted_periods = sorted(
            {pk[0] for pk in period_keys},
            key=lambda p: (sort_key(p, _ptype_of(pk)), p)
        )
        # 建立 period串 -> ptype (同一 period 串 ptype 一致)
        ptype_of_period = {pk[0]: pk[1] for pk in period_keys}

        rel_rows = []
        for pk, group in period_keys.items():
            period = pk[0]
            edge_obs = [g["obs"] for g in group]
            rel_obs = resolve_observe_type(period, sorted_periods, edge_obs)

            # 按数值可比键分簇: 同值合并(列全来源边), 异值冲突
            clusters = {}  # value_key -> (canonical_pct, set(edge_ids))
            for g in group:
                vk = value_key(g["pct"])
                if vk not in clusters:
                    clusters[vk] = [g["pct"], set()]
                # 取信息更完整的字面值作展示(含金额者更长)
                if len(g["pct"]) > len(clusters[vk][0]):
                    clusters[vk][0] = g["pct"]
                clusters[vk][1].add(g["edge_id"])
            distinct = list(clusters.keys())
            if len(distinct) == 1:
                vk = distinct[0]
                edge_ids = sorted(clusters[vk][1])
                rel_rows.append({
                    "period": period,
                    "ptype": pk[1],
                    "pct": clusters[vk][0],
                    "obs": rel_obs,
                    "edge_ids": edge_ids,
                    "conflict": False,
                })
                # 字面值不同但数值一致 -> 合并(契约 §3); 透明记录
                lits = sorted({g["pct"] for g in group})
                if len(lits) > 1:
                    warnings.append(
                        "关系 %s→%s 期间 %s 字面值不同但占比一致, 已合并: %s (edges=%s)"
                        % (sup, con, period, " / ".join(lits), ",".join(edge_ids))
                    )
            else:
                # 冲突: 保留多行, 各标 conflict=true
                conflict_total += len(distinct)
                for vk in distinct:
                    edge_ids = sorted(clusters[vk][1])
                    rel_rows.append({
                        "period": period,
                        "ptype": pk[1],
                        "pct": clusters[vk][0],
                        "obs": rel_obs,
                        "edge_ids": edge_ids,
                        "conflict": True,
                    })
                warnings.append(
                    "关系 %s→%s 期间 %s 多边冲突(保留 %d 行): %s"
                    % (sup, con, period, len(distinct),
                       "; ".join("%s[%s]" % (clusters[v][0], ",".join(sorted(clusters[v][1]))) for v in distinct))
                )

        # 关系内按时间排序
        rel_rows.sort(key=lambda r: (sort_key(r["period"], r["ptype"]), r["period"]))
        relationships.append({
            "sup": sup, "con": con, "anon": (is_anonymous(sup) or is_anonymous(con)),
            "rows": rel_rows,
        })
    return relationships, conflict_total


def _ptype_of(pk):
    return pk[1]


def value_key(pct):
    """契约 §3 '金额/占比一致则合并' —— 按数值而非字面值比较。

    提取首个数(占比优先取带 '%' 的数)作为可比键; 同键视为一致, 合并为一行。
    字面值不同但数值相同(如 '9.90%' 与 '9.90%(2730.72万元)')判为一致。
    """
    pct = (pct or "").strip()
    has_pct = "%" in pct
    nums = re.findall(r"\d+\.?\d*", pct)
    fnums = [float(n) for n in nums]
    primary = fnums[0] if fnums else None
    return (has_pct, primary)


def write_output(relationships):
    header = ["relation_id", "供方", "需方", "period", "period_type",
              "pct_or_amt", "observe_type", "source_edge_ids", "conflict"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for i, rel in enumerate(relationships, start=1):
            rid = "R%03d" % i
            for r in rel["rows"]:
                w.writerow([
                    rid, rel["sup"], rel["con"], r["period"], r["ptype"],
                    r["pct"], r["obs"], ";".join(r["edge_ids"]),
                    "true" if r["conflict"] else "false",
                ])


# ----------------------------------------------------------------------------
# 6. 自测
# ----------------------------------------------------------------------------
def self_test(relationships, conflict_total, warnings):
    total_rows = sum(len(rel["rows"]) for rel in relationships)
    print("=" * 64)
    print("R3 关系级时间聚合 — 自测")
    print("=" * 64)
    print("关系数        : %d" % len(relationships))
    print("事件行数      : %d" % total_rows)
    print("conflict 计数 : %d" % conflict_total)

    states = ["first_observed", "observed", "last_observed", "censored", "confirmed_ended"]
    dist = {s: 0 for s in states}
    for rel in relationships:
        for r in rel["rows"]:
            if r["obs"] in dist:
                dist[r["obs"]] += 1
            else:
                dist[r["obs"]] = dist.get(r["obs"], 0) + 1
    print("五态分布      : " + ", ".join("%s=%d" % (s, dist[s]) for s in states))

    # 抽验 1: 猎奇智能 → 中际旭创 (应跨 E010+E045 连成 2023-2025 序列)
    print("-" * 64)
    print("抽验① 猎奇智能 → 中际旭创 (契约指定: E010+E045 连成 2023-2025)")
    _print_relation(relationships, "猎奇智能", "中际旭创")

    # 抽验 2: Fabrinet → Lumentum (E005+E068 与 E038 的 FY 序列, E038 为 FY 口径)
    print("-" * 64)
    print("抽验② Fabrinet → Lumentum (契约指定: E005+E068 与 E038 的 FY 序列)")
    _print_relation(relationships, "Fabrinet", "Lumentum")

    # 解析歧义 warnings
    print("-" * 64)
    print("解析歧义 / warnings (%d):" % len(warnings))
    if warnings:
        for w in warnings:
            print("  - " + w)
    else:
        print("  (无)")
    print("=" * 64)


def _print_relation(relationships, sup, con):
    for rel in relationships:
        if rel["sup"] == sup and rel["con"] == con:
            for r in rel["rows"]:
                print("  %-8s %-8s %-12s %-10s %s  edges=%s"
                      % (r["period"], r["ptype"], r["pct"], r["obs"],
                         "CONFLICT" if r["conflict"] else "", ";".join(r["edge_ids"])))
            return
    print("  (未在关系表中找到)")


def main():
    warnings = []
    fy_map = load_fy_map()
    events = load_events(fy_map, warnings)

    # 契约歧义: 罗博特科 (裸名, E076) 与 罗博特科/ficonTEC (E011/E012) 实为同一主体,
    # 但契约别名表未将裸名 "罗博特科" 归一, 故保持为两条独立关系 —— 如实记录。
    norm_names = {ev["rel_key"][0] for ev in events} | {ev["rel_key"][1] for ev in events}
    if "罗博特科" in norm_names and "罗博特科/ficonTEC" in norm_names:
        warnings.append("歧义: 裸名 '罗博特科'(E076) 与 '罗博特科/ficonTEC'(E011/E012) 域知识为同一主体, "
                        "但契约别名表未含裸名归一规则, 依契约保持为两条独立关系, 未硬凑合并。")

    relationships, conflict_total = aggregate(events, warnings)
    write_output(relationships)
    self_test(relationships, conflict_total, warnings)


if __name__ == "__main__":
    main()
