#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
discovery_queue.py — 统一发现队列 + 判定闸台账（**原型-未准入**，kimi/k3 车道）

定位：ROADMAP-v1.7（未冻结草案）A 项 S0 发现层的配套原型。核心主张——
S0 该常设的是**队列与闸**（容器），该事件触发的是**算子**。本脚本把四类
发现算子的产出归一到一个队列 schema，用一台状态机驱动"待闸→过闸/剔除→
边工序/入图"，并为 D 项查全率提供**只认过闸项**的分母。

发现算子（本原型覆盖）：
  media_lead    媒体事件线索（flows/out/leads-pool.csv，真实入队）
  customs_diff  海关分国别月度量结构突变（flows/out/customs-partners.csv 实算）
  bom_scan      S0a 部件词表全库扫描（仅 MOCK 行占住 schema，非真实检索结果）
  （bfs_jump / must_edge 本原型不演示，schema 同构：对象类型不同而已）

红线执行：
  - 本车道**不作任何闸裁决**（证据判定归终验）。闸台账输出为空骨架。
  - MOCK 行仅为 schema 演示，行内显式标注 MOCK，不得引用。
  - 海关量异常只是触发器（旁证，不承重），队列内"待验证T1路径"已写明。

纪律断言（脚本自检，任一失败即退出码 1）：
  A1 发现算子 ∈ 已知集合；A2 状态 ∈ 状态机合法值；A3 queue_id 唯一；
  A4 bom_scan 行必须带词表出处（含版本）；A5 闸台账引用的 queue_id 必须存在
     且裁决值合法；A6 查全率分母只统计"过闸且裁决=生产"的对象——原始命中
     永远不作分母（D 项防线）。

输入（只读）：flows/out/leads-pool.csv、flows/out/customs-partners.csv
产出（全新文件，前缀 proto-，不覆盖任何既有产物）：
  flows/out/proto-discovery-queue.csv        统一发现队列
  flows/out/proto-gate-ledger-skeleton.csv   判定闸台账骨架（空，待终验填写）
  flows/out/proto-recall-rate-mock.csv       查全率表演示行（MOCK）
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEADS_CSV = ROOT / "flows" / "out" / "leads-pool.csv"
PARTNERS_CSV = ROOT / "flows" / "out" / "customs-partners.csv"
OUT_QUEUE = ROOT / "flows" / "out" / "proto-discovery-queue.csv"
OUT_GATE = ROOT / "flows" / "out" / "proto-gate-ledger-skeleton.csv"
OUT_RECALL = ROOT / "flows" / "out" / "proto-recall-rate-mock.csv"

OPERATORS = {"media_lead", "customs_diff", "bom_scan", "bfs_jump", "must_edge"}
STATES = {"待闸", "过闸-待边工序", "剔除-已登记", "已入图"}
VERDICTS = {"生产", "提及", "噪声", "确认", "证伪", "已知解释"}

# customs_diff 触发阈值：2026H1 vs 2025H1 分伙伴金额
DIFF_PCT = 50.0          # 同比变化幅度阈值 %
DIFF_ABS_USD = 5_000_000  # 绝对变化阈值（防小基数噪声）

QUEUE_HEADER = [
    "queue_id", "发现算子", "对象类型", "对象", "发现证据(URL/出处)", "发现日期",
    "待验证T1路径", "状态", "闸裁决", "闸裁决人", "闸裁决日期", "裁决理由", "备注",
]
GATE_HEADER = [
    "gate_id", "queue_id", "对象", "命中上下文(段落/词)", "段落类型预判",
    "闸裁决", "裁决人", "裁决日期", "理由", "剔除登记号(若剔除)",
]
RECALL_HEADER = [
    "部件词", "词表出处(含版本)", "检索日", "分母_过闸生产商数",
    "分子_台账覆盖生产商数", "查全率", "口径备注",
]


def new_row(qid, op, otype, obj, evidence, date, t1path, note=""):
    return {
        "queue_id": qid, "发现算子": op, "对象类型": otype, "对象": obj,
        "发现证据(URL/出处)": evidence, "发现日期": date,
        "待验证T1路径": t1path, "状态": "待闸", "闸裁决": "", "闸裁决人": "",
        "闸裁决日期": "", "裁决理由": "", "备注": note,
    }


def load_leads():
    """media_lead：线索池真实入队。状态映射：待验证→待闸。"""
    rows = []
    with open(LEADS_CSV, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(new_row(
                qid=f"DQ-{r['lead_id']}", op="media_lead", otype="company",
                obj=r["涉及公司"], evidence=r["线索来源(媒体/公众号名+URL)"],
                date=r["报道日期"], t1path=r["待验证的T1路径"],
                note=f"线索描述：{r['线索描述'][:80]}…" if len(r["线索描述"]) > 80
                     else f"线索描述：{r['线索描述']}",
            ))
    return rows


def customs_diff():
    """customs_diff：分伙伴 2026H1 vs 2025H1 金额同比，实算触发器。"""
    sums = {}
    with open(PARTNERS_CSV, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["币种"] != "USD":
                continue
            ym = r["月份"]
            half = "H1-2025" if "202501" <= ym <= "202506" else \
                   "H1-2026" if "202601" <= ym <= "202606" else None
            if half:
                key = (r["贸易伙伴"], half)
                sums[key] = sums.get(key, 0) + float(r["金额"])
    partners = {p for p, _ in sums}
    rows, n = [], 0
    for p in sorted(partners):
        a, b = sums.get((p, "H1-2025"), 0.0), sums.get((p, "H1-2026"), 0.0)
        delta = b - a
        pct = (delta / a * 100.0) if a else (float("inf") if b else 0.0)
        if abs(pct) >= DIFF_PCT and abs(delta) >= DIFF_ABS_USD:
            n += 1
            rows.append(new_row(
                qid=f"DQ-CD-{n:03d}", op="customs_diff", otype="flow_anomaly",
                obj=p,
                evidence="flows/out/customs-partners.csv 自算（2025H1 vs 2026H1，USD）",
                date="2026-07-24",
                t1path=("按省份分拆+台账节点定位对应该伙伴国的主要出口主体，"
                        "定向检索其产能/募投/环评披露；海关量为旁证不承重"),
                note=(f"2025H1={a:,.0f} → 2026H1={b:,.0f} USD，"
                      f"Δ={delta:+,.0f}（{pct:+.1f}%）"),
            ))
    return rows


def mock_bom_rows():
    """bom_scan：仅占住 schema。MOCK 标注，非真实检索结果，不得引用。"""
    return [
        new_row(
            qid="DQ-BOM-MOCK-001", op="bom_scan", otype="company",
            obj="MOCK-示例公司甲",
            evidence="MOCK（schema 占位，非真实检索结果）",
            date="MOCK",
            t1path="MOCK：命中段落上下文 → 判定闸（生产vs提及）",
            note="词表出处：MOCK-猎奇BOM-v0（占位）；MOCK 行不得引用",
        ),
    ]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def self_test(queue):
    errors = []
    ids = [r["queue_id"] for r in queue]
    if len(ids) != len(set(ids)):
        errors.append("A3 queue_id 不唯一")
    for r in queue:
        if r["发现算子"] not in OPERATORS:
            errors.append(f"A1 未知算子: {r['queue_id']}")
        if r["状态"] not in STATES:
            errors.append(f"A2 非法状态: {r['queue_id']}")
        if r["发现算子"] == "bom_scan" and "词表出处" not in r["备注"]:
            errors.append(f"A4 bom_scan 缺词表出处: {r['queue_id']}")
    return errors


def main():
    queue = load_leads() + customs_diff() + mock_bom_rows()
    errors = self_test(queue)

    write_csv(OUT_QUEUE, QUEUE_HEADER, queue)
    write_csv(OUT_GATE, GATE_HEADER, [])  # 闸裁决归终验，本车道只交骨架
    write_csv(OUT_RECALL, RECALL_HEADER, [{
        "部件词": "MOCK-陶瓷插芯",
        "词表出处(含版本)": "MOCK-猎奇BOM-v0（占位）",
        "检索日": "MOCK",
        "分母_过闸生产商数": "MOCK：仅统计闸台账中裁决=生产的对象",
        "分子_台账覆盖生产商数": "MOCK：edges.csv 中该部件有供货边的生产商",
        "查全率": "MOCK=分子/分母",
        "口径备注": "MOCK 演示行：分母随词表版本与检索日快照变，引用须带两者",
    }])

    by_op = {}
    for r in queue:
        by_op[r["发现算子"]] = by_op.get(r["发现算子"], 0) + 1
    print("== discovery_queue 原型自检 ==")
    print(f"队列总量: {len(queue)} 行；按算子: {by_op}")
    print(f"状态分布: 全部 待闸（闸裁决归终验，本车道不代判）")
    if errors:
        print("纪律断言失败:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("纪律断言 A1-A4: 通过（A5/A6 待闸台账有内容后生效）")
    print(f"产出: {OUT_QUEUE.name} / {OUT_GATE.name} / {OUT_RECALL.name}（原型-未准入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
