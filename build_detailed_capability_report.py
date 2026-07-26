#!/usr/bin/env python3
"""Build a granular company capability ledger, PDF, and merged HTML.

The evidence ledger remains points.csv. This script normalizes confirmed points
into capability_details.csv, then renders both deliverables from that same file.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import participation


ROOT = Path(__file__).resolve().parent
DEFAULT_CSV = ROOT / "capability_details.csv"
DEFAULT_PDF = ROOT / "output" / "pdf" / "光模块产业链公司能力明细.pdf"
DEFAULT_TEMPLATE = Path(
    "/Users/jowang/Workbuddy/2026-07-26-11-49-54/"
    "光模块产业链全景图_产业链优先版.html"
)
DEFAULT_HTML = Path(
    "/Users/jowang/Workbuddy/2026-07-26-11-49-54/"
    "光模块产业链全景图_公司能力细化版.html"
)
FONT_PATH = Path("/System/Library/Fonts/STHeiti Light.ttc")

STAGES = [
    ("材料层", ("M",), "#2C6E8F"),
    ("芯片层", ("C",), "#3D63A8"),
    ("芯片封装", ("P",), "#6750A4"),
    ("光器件层", ("D",), "#8B4D94"),
    ("电路与结构", ("B",), "#A05B36"),
    ("模块层", ("MOD",), "#147A68"),
    ("制造与代工", ("EMS",), "#25745D"),
    ("设备与仪器", ("EQ",), "#6B7280"),
]

PRODUCT_PATTERNS = [
    ("InP衬底", r"\bInP\b|磷化铟衬底"),
    ("GaAs衬底/外延", r"\bGaAs\b|砷化镓"),
    ("SOI/硅光平台", r"\bSOI\b|硅光PIC|硅光芯片|silicon phot"),
    ("EML", r"\bEML\b"),
    ("DFB", r"\bDFB\b"),
    ("CW光源", r"\bCW\b|连续波"),
    ("VCSEL", r"\bVCSEL\b"),
    ("PIN/PD", r"\bPIN\b|\bPD\b|探测器芯片"),
    ("APD", r"\bAPD\b"),
    ("DSP", r"\bDSP\b"),
    ("Driver", r"\bDriver\b|激光驱动"),
    ("TIA", r"\bTIA\b|跨阻放大"),
    ("CDR", r"\bCDR\b|时钟恢复"),
    ("MCU", r"\bMCU\b|主控"),
    ("SerDes/PHY", r"\bSerDes\b|\bPHY\b"),
    ("TOSA", r"\bTOSA\b"),
    ("ROSA", r"\bROSA\b"),
    ("BOSA", r"\bBOSA\b"),
    ("COC/COB光组件", r"\bCOC\b|\bCOB\b|光引擎"),
    ("AWG", r"\bAWG\b|阵列波导光栅"),
    ("WDM滤光片/组件", r"\bWDM\b|\bCWDM\b|\bDWDM\b|\bLWDM\b|滤光片"),
    ("FAU/光纤阵列", r"\bFAU\b|光纤阵列|\bMT-FA\b"),
    ("MPO/MTP连接", r"\bMPO\b|\bMTP\b|MT插芯"),
    ("陶瓷插芯/套管", r"陶瓷插芯|陶瓷套"),
    ("陶瓷管壳/TO管座", r"陶瓷管壳|陶瓷封装管壳|光通信器件外壳|TO管座"),
    ("透镜/微光学", r"透镜|微光学|光学件"),
    ("光模块PCB", r"光模块PCB|高速PCB"),
    ("高速板材/覆铜板", r"高速覆铜板|LowDK|高速板"),
    ("结构件/散热", r"基座|壳体|散热"),
    ("数通光模块", r"数通光模块|高速光模块|光通信收发模块"),
    ("相干模块", r"相干模块|ZR/ZR\+|400ZR"),
    ("接入/电信模块", r"PON|FTTx|电信.*光模块|承载传输"),
    ("AOC", r"有源光缆|\bAOC\b"),
    ("MOCVD/外延设备", r"\bMOCVD\b|\bMBE\b|外延设备"),
    ("光刻/刻蚀设备", r"光刻设备|刻蚀设备|\bICP\b|\bCCP\b"),
    ("耦合/微组装设备", r"耦合设备|微组装|光学耦合"),
    ("测试/老化设备", r"测试设备|测试仪器|老化测试|\bATE\b"),
    ("AOI检测设备", r"\bAOI\b|在线检测"),
]

PROCESS_PATTERNS = [
    ("产品设计", r"研发|设计|自主开发|自研"),
    ("外延生长", r"外延生长|\bMOCVD\b|\bMBE\b"),
    ("晶圆制造/处理", r"晶圆处理|晶圆制造|FAB|流片"),
    ("光刻/刻蚀", r"光刻|刻蚀|光栅"),
    ("薄膜/镀膜", r"薄膜|镀膜|金属化"),
    ("固晶/贴片", r"固晶|贴片|贴装|共晶|COC贴装"),
    ("引线/混合键合", r"金丝键合|引线键合|混合键合|键合"),
    ("光学耦合", r"光学耦合|耦合"),
    ("封装/密封", r"封装|气密|缝焊|激光焊"),
    ("焊接/组装", r"焊接|组装|装配"),
    ("测试/检验", r"测试|检验|分选|眼图|误码"),
    ("老化/可靠性", r"老化|高低温|温循|可靠性"),
    ("委托加工/代工", r"委托加工|代工|OEM|EMS"),
    ("规模制造", r"生产|量产|批量|产业化"),
]

SPEC_PATTERNS = [
    ("1.6T", r"1\.6T"),
    ("800G", r"800G"),
    ("400G", r"400G"),
    ("200G", r"200G"),
    ("100G", r"100G"),
    ("50G", r"50G"),
    ("25G", r"25G"),
    ("10G", r"10G"),
    ("AI/智算数据中心", r"人工智能|AI|智算|云计算|数据中心|算力"),
    ("5G/移动承载", r"\b5G\b|\b4G\b|前传|中回传|承载"),
    ("PON/FTTx接入", r"PON|FTTx|OLT|ONU|固网接入"),
    ("相干/DCI/骨干", r"相干|ZR\+?|DCI|骨干|城域|WSS|OXC"),
]

EVIDENCE_RANK = {
    "判定闸-生产中": 5,
    "node_wide_gate": 5,
    "edge_backed": 4,
    "cross_reference": 3,
    "context_only": 2,
}

FIELDNAMES = [
    "公司代码",
    "公司",
    "市场",
    "行业分类",
    "主环节",
    "cell_id",
    "细分节点",
    "技术路线",
    "具体产品",
    "材料与技术",
    "工艺能力",
    "规格与应用",
    "当前阶段",
    "产业角色",
    "证据等级",
    "证据日期",
    "来源锚点",
    "原始披露摘要",
]


def clean(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().strip('"')
    return value


def extract_url(value: str) -> str:
    match = re.search(r"https?://[^\s\]）)>,，；;`]+", value or "")
    return match.group(0).rstrip(".,") if match else ""


def tree_metadata() -> dict[str, dict[str, str]]:
    text = (ROOT / "tree.yaml").read_text(encoding="utf-8")
    result: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r"\{cell_id:\s*([^,\s]+),\s*名称:\s*(.*?),\s*路线:\s*([^,}]+)"
        r"(?:,\s*工艺备注:\s*(.*?))?\}"
    )
    for match in pattern.finditer(text):
        cell_id, name, route, process_note = match.groups()
        result[cell_id] = {
            "name": clean(name),
            "route": clean(route),
            "process_note": clean(process_note or ""),
        }
    return result


def stage_for(cell_id: str) -> str:
    for stage, prefixes, _ in reversed(STAGES):
        if any(cell_id.startswith(prefix) for prefix in prefixes):
            return stage
    return "其他"


def unique_matches(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    found = []
    for label, pattern in patterns:
        if re.search(pattern, text, flags=re.I) and label not in found:
            found.append(label)
    return found


def stage_detail(text: str, point_status: str) -> str:
    checks = [
        ("规模量产/批量交付", r"规模量产|大批量|批量供货|批量出货|批量销售|批量产销"),
        ("量产/产业化", r"已实现量产|实现量产|量产线|产业化|成熟应用|生产中"),
        ("小批量/试产", r"小批量|试产"),
        ("送样/验证/导入", r"送样|验证|导入"),
        (
            "生产经营中",
            r"研发[、与及/]*生产|研发[、与及/]*制造|研发.*销售|生产.*销售|"
            r"提供.*光模块|主营业务|业务.*涵盖.*销售|营业收入",
        ),
        ("研发/建设中", r"在研|研发|开发中|在建|持续进行中"),
    ]
    for label, pattern in checks:
        if re.search(pattern, text, flags=re.I):
            return label
    return point_status or "披露未细分"


def role_for(cell_id: str, text: str) -> str:
    if re.search(r"委托加工|OEM|EMS|代工", text, flags=re.I):
        return "专业代工/制造服务"
    if cell_id.startswith("MOD"):
        return "光模块设计与制造"
    if cell_id.startswith("EMS"):
        return "模块代工与系统制造"
    if cell_id.startswith("EQ"):
        return "生产设备/检测工具"
    if cell_id.startswith("M"):
        return "材料或晶圆工艺参与者"
    if cell_id.startswith("C"):
        if re.search(r"外部代工|流片采用外部", text):
            return "芯片设计与产品定义（外部流片）"
        if re.search(r"外延|晶圆|FAB|全流程", text, flags=re.I):
            return "芯片IDM/制造平台"
        return "芯片设计或制造"
    if cell_id.startswith("P"):
        return "芯片封装与筛选"
    if cell_id.startswith("D"):
        return "光器件/光组件制造"
    if cell_id.startswith("B"):
        return "电路板或结构材料制造"
    return "产业链参与者"


def material_technology(text: str, node_name: str) -> str:
    tokens = unique_matches(
        text,
        [
            ("InP", r"\bInP\b|磷化铟"),
            ("GaAs", r"\bGaAs\b|砷化镓"),
            ("Si/SOI", r"\bSOI\b|硅光|硅基"),
            ("SiN", r"\bSiN\b"),
            ("PLC", r"\bPLC\b"),
            ("TFLN/铌酸锂", r"铌酸锂|\bTFLN\b"),
            ("陶瓷", r"陶瓷"),
            ("石英", r"石英"),
            ("高频高速覆铜板", r"覆铜板|LowDK|高速板"),
            ("金属有机源/特气", r"MO源|三甲基|磷烷|砷烷|磷化氢|砷化氢"),
        ],
    )
    if tokens:
        return "、".join(tokens)
    if any(word in node_name for word in ("材料", "衬底", "外延", "陶瓷", "板材")):
        return node_name
    return "披露未细分"


def granular_rows() -> list[dict[str, str]]:
    meta = tree_metadata()
    universe = participation.unique_universe()
    universe_names = {row["名称"] for row in universe}
    universe_by_name = {row["名称"]: row for row in universe}
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for point in participation.read_rows("points.csv"):
        if point["状态"] != "生产中":
            continue
        company = participation.resolve_company(point["公司"], universe_names)
        if company:
            grouped[(company, point["cell_id"])].append(point)

    result = []
    for (company, cell_id), points in grouped.items():
        company_meta = universe_by_name[company]
        node = meta.get(cell_id, {"name": cell_id, "route": "未标", "process_note": ""})
        quotes = []
        for point in points:
            quote = clean(point.get("命中引语", ""))
            if quote and quote not in quotes:
                quotes.append(quote)
        quote_text = "；".join(quotes)
        combined = f"{node['name']} {node['process_note']} {quote_text}"
        evidence_and_process = f"{node['process_note']} {quote_text}"
        products = unique_matches(combined, PRODUCT_PATTERNS)
        processes = unique_matches(evidence_and_process, PROCESS_PATTERNS)
        specs = unique_matches(quote_text, SPEC_PATTERNS)
        if not products:
            products = [node["name"]]
        if not processes and node["process_note"]:
            processes = [node["process_note"]]
        best_point = max(
            points,
            key=lambda point: EVIDENCE_RANK.get(point.get("判定等级", ""), 1),
        )
        anchors = [extract_url(point.get("锚点URL", "")) for point in points]
        anchor = next((value for value in anchors if value), clean(best_point.get("锚点URL", "")))
        dates = [point.get("检索日期", "") for point in points if point.get("检索日期")]
        result.append(
            {
                "公司代码": company_meta["代码"],
                "公司": company,
                "市场": company_meta["市场"],
                "行业分类": company_meta["行业分类"],
                "主环节": stage_for(cell_id),
                "cell_id": cell_id,
                "细分节点": node["name"],
                "技术路线": node["route"],
                "具体产品": "、".join(products),
                "材料与技术": material_technology(combined, node["name"]),
                "工艺能力": "、".join(processes) if processes else "披露未细分",
                "规格与应用": "、".join(specs) if specs else "披露未细分",
                "当前阶段": stage_detail(quote_text, best_point.get("状态", "")),
                "产业角色": role_for(cell_id, combined),
                "证据等级": best_point.get("判定等级", "已过闸"),
                "证据日期": max(dates) if dates else "",
                "来源锚点": anchor,
                "原始披露摘要": quote_text,
            }
        )

    stage_index = {stage: index for index, (stage, _, _) in enumerate(STAGES)}
    return sorted(
        result,
        key=lambda row: (
            row["公司代码"],
            stage_index.get(row["主环节"], 99),
            row["cell_id"],
        ),
    )


def write_capability_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def register_font() -> None:
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"中文字体不存在: {FONT_PATH}")
    pdfmetrics.registerFont(TTFont("CN", str(FONT_PATH)))


def pdf_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCN",
            parent=base["Title"],
            fontName="CN",
            fontSize=24,
            leading=33,
            textColor=colors.HexColor("#102A43"),
            spaceAfter=7 * mm,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCN",
            fontName="CN",
            fontSize=9.5,
            leading=15,
            textColor=colors.HexColor("#526777"),
        ),
        "company": ParagraphStyle(
            "CompanyCN",
            fontName="CN",
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#102A43"),
        ),
        "meta": ParagraphStyle(
            "MetaCN",
            fontName="CN",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#6B7885"),
        ),
        "label": ParagraphStyle(
            "LabelCN",
            fontName="CN",
            fontSize=7.4,
            leading=10,
            textColor=colors.HexColor("#5B6670"),
        ),
        "body": ParagraphStyle(
            "BodyCN",
            fontName="CN",
            fontSize=8,
            leading=11.4,
            textColor=colors.HexColor("#273746"),
        ),
        "quote": ParagraphStyle(
            "QuoteCN",
            fontName="CN",
            fontSize=7.2,
            leading=10.2,
            textColor=colors.HexColor("#667481"),
        ),
        "center": ParagraphStyle(
            "CenterCN",
            fontName="CN",
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#25445A"),
        ),
    }


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def paragraph(value: str, style) -> Paragraph:
    normalized = (value or "").replace("<br/>", "\n")
    return Paragraph(esc(normalized).replace("\n", "<br/>"), style)


def page_decor(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(colors.HexColor("#102A43"))
    canvas.rect(0, height - 12 * mm, width, 12 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("CN", 8)
    canvas.drawString(18 * mm, height - 7.8 * mm, "光模块产业链公司能力明细")
    canvas.setFillColor(colors.HexColor("#7A8792"))
    canvas.setFont("CN", 7)
    canvas.drawRightString(width - 18 * mm, 9 * mm, str(doc.page))
    canvas.restoreState()


def build_pdf(path: Path, rows: list[dict[str, str]]) -> None:
    register_font()
    styles = pdf_styles()
    companies: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        companies[row["公司"]].append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        title="光模块产业链公司能力明细",
        author="光模块产业结构与公司能力地图",
    )
    story = [
        Spacer(1, 21 * mm),
        Paragraph("光模块产业链<br/>公司能力明细", styles["title"]),
        Paragraph(
            "以“公司 × 细分节点”为最小单元，逐项呈现具体产品、材料与技术、工艺、规格与应用、当前阶段、产业角色和披露证据。",
            styles["subtitle"],
        ),
        Spacer(1, 13 * mm),
    ]
    stats = [
        paragraph(f"{len(companies)} 家公司", styles["center"]),
        paragraph(f"{len(rows)} 条能力记录", styles["center"]),
        paragraph(f"{len({row['cell_id'] for row in rows})} 个细分节点", styles["center"]),
    ]
    stat_table = Table([stats], colWidths=[56 * mm] * 3)
    stat_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4F8")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D5E1E8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5E1E8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5 * mm),
            ]
        )
    )
    story += [
        stat_table,
        Spacer(1, 11 * mm),
        Paragraph(
            "阅读口径：只展示已进入“生产中”证据闸的公司；字段未被原始披露支撑时明确写“披露未细分”。本报告不讨论谁向谁供货。",
            styles["subtitle"],
        ),
        PageBreak(),
    ]

    for company in sorted(companies, key=lambda name: (companies[name][0]["公司代码"], name)):
        caps = companies[company]
        first = caps[0]
        company_label = (
            company
            if first["公司代码"] == company
            else f"{company}　{first['公司代码']}"
        )
        story.append(CondPageBreak(60 * mm))
        header = Table(
            [
                [
                    Paragraph(
                        f"<b>{esc(company_label)}</b>",
                        styles["company"],
                    ),
                    Paragraph(
                        f"{esc(first['市场'])}<br/>{esc(first['行业分类'])}<br/>{len(caps)}项已确认能力",
                        styles["meta"],
                    ),
                ]
            ],
            colWidths=[128 * mm, 48 * mm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF1F6")),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#C8D7E2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.8 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8 * mm),
                ]
            )
        )
        story += [header, Spacer(1, 2 * mm)]
        for cap in caps:
            detail_rows = [
                [
                    paragraph("节点", styles["label"]),
                    paragraph(
                        f"{cap['cell_id']} · {cap['细分节点']}｜{cap['技术路线']}",
                        styles["body"],
                    ),
                ],
                [paragraph("具体产品", styles["label"]), paragraph(cap["具体产品"], styles["body"])],
                [
                    paragraph("技术 / 工艺", styles["label"]),
                    paragraph(
                        f"材料与技术：{cap['材料与技术']}<br/>工艺能力：{cap['工艺能力']}",
                        styles["body"],
                    ),
                ],
                [
                    paragraph("规格 / 阶段", styles["label"]),
                    paragraph(
                        f"规格与应用：{cap['规格与应用']}<br/>当前阶段：{cap['当前阶段']}｜角色：{cap['产业角色']}",
                        styles["body"],
                    ),
                ],
                [
                    paragraph("披露证据", styles["label"]),
                    paragraph(cap["原始披露摘要"][:420], styles["quote"]),
                ],
            ]
            cap_table = Table(detail_rows, colWidths=[24 * mm, 152 * mm], splitByRow=1)
            cap_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F7F9")),
                        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#D7E0E7")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E1E7EC")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2.2 * mm),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2.2 * mm),
                        ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
                    ]
                )
            )
            story += [
                cap_table,
                Paragraph(
                    f"证据等级：{esc(cap['证据等级'])}　|　证据日期：{esc(cap['证据日期'] or '—')}　|　"
                    + (
                        f'<link href="{esc(cap["来源锚点"])}" color="#165DFF">查看来源</link>'
                        if cap["来源锚点"].startswith(("http://", "https://"))
                        else esc(cap["来源锚点"] or "来源锚点已登记")
                    ),
                    styles["meta"],
                ),
                Spacer(1, 3 * mm),
            ]
        story.append(Spacer(1, 2 * mm))

    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)


def capability_section(rows: list[dict[str, str]]) -> str:
    companies: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        companies[row["公司"]].append(row)
    cards = []
    for company in sorted(companies, key=lambda name: (companies[name][0]["公司代码"], name)):
        caps = companies[company]
        first = caps[0]
        cap_html = []
        for cap in caps:
            source = esc(cap["来源锚点"] or "来源锚点已登记")
            if cap["来源锚点"].startswith(("http://", "https://")):
                source = (
                    f'<a href="{esc(cap["来源锚点"])}" target="_blank" rel="noreferrer">'
                    "查看原始披露</a>"
                )
            cap_html.append(
                f"""
                <div class="cap-item">
                  <div class="cap-head"><b>{esc(cap['cell_id'])} · {esc(cap['细分节点'])}</b>
                    <span>{esc(cap['技术路线'])}</span></div>
                  <dl>
                    <dt>具体产品</dt><dd>{esc(cap['具体产品'])}</dd>
                    <dt>材料与技术</dt><dd>{esc(cap['材料与技术'])}</dd>
                    <dt>工艺能力</dt><dd>{esc(cap['工艺能力'])}</dd>
                    <dt>规格与应用</dt><dd>{esc(cap['规格与应用'])}</dd>
                    <dt>阶段与角色</dt><dd>{esc(cap['当前阶段'])} · {esc(cap['产业角色'])}</dd>
                    <dt>披露摘要</dt><dd class="quote">{esc(cap['原始披露摘要'])}</dd>
                  </dl>
                  <div class="cap-source">{esc(cap['证据等级'])} · {esc(cap['证据日期'])} · {source}</div>
                </div>
                """
            )
        searchable = " ".join(
            [
                company,
                first["公司代码"],
                first["市场"],
                first["行业分类"],
                *[
                    " ".join(
                        cap[field]
                        for field in (
                            "主环节",
                            "细分节点",
                            "具体产品",
                            "材料与技术",
                            "工艺能力",
                            "规格与应用",
                        )
                    )
                    for cap in caps
                ],
            ]
        )
        cards.append(
            f"""
            <article class="company-cap" data-layer="{esc(caps[0]['主环节'])}"
              data-search="{esc(searchable.lower())}">
              <div class="company-cap-title">
                <div><b>{esc(company)}</b><span>{esc(first['公司代码'])}</span></div>
                <small>{esc(first['市场'])} · {esc(first['行业分类'])} · {len(caps)}项能力</small>
              </div>
              {''.join(cap_html)}
            </article>
            """
        )
    layers = "".join(
        f'<option value="{esc(stage)}">{esc(stage)}</option>'
        for stage, _, _ in STAGES
        if any(row["主环节"] == stage for row in rows)
    )
    return f"""
    <div class="sec" id="s8">
      <h2><span class="tag">能力卡</span>公司 × 细分节点能力明细</h2>
      <div class="desc">同一公司跨环节能力合并展示。每项记录包含产品、技术、工艺、规格、阶段、角色与证据；未被披露支持的字段明确标记为“披露未细分”。</div>
      <div class="cap-summary">
        <div><b>{len(companies)}</b><span>已确认公司</span></div>
        <div><b>{len(rows)}</b><span>能力记录</span></div>
        <div><b>{len({row['cell_id'] for row in rows})}</b><span>覆盖细分节点</span></div>
      </div>
      <div class="cap-tools">
        <input id="capSearch" type="search" placeholder="搜索公司、产品、工艺、规格或节点">
        <select id="capLayer"><option value="">全部环节</option>{layers}</select>
        <span id="capCount">{len(companies)} 家公司</span>
      </div>
      <div class="company-cap-grid" id="companyCaps">{''.join(cards)}</div>
    </div>
    """


CAPABILITY_CSS = """
  .cap-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}
  .cap-summary div{background:#eef4f8;border:1px solid #d5e1e8;border-radius:12px;padding:12px;text-align:center}
  .cap-summary b{display:block;font-size:20px;color:var(--accent)}
  .cap-summary span{font-size:11px;color:var(--muted)}
  .cap-tools{position:sticky;top:8px;z-index:5;display:grid;grid-template-columns:1fr 220px auto;gap:10px;align-items:center;background:#fff;padding:10px;border:1px solid var(--line);border-radius:12px;margin:12px 0}
  .cap-tools input,.cap-tools select{width:100%;border:1px solid #cbd5e1;border-radius:8px;padding:9px 11px;background:#fff;color:var(--ink)}
  .cap-tools span{font-size:12px;color:var(--muted);white-space:nowrap}
  .company-cap-grid{display:grid;grid-template-columns:1fr;gap:14px}
  .company-cap{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff}
  .company-cap-title{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:13px 15px;background:#eaf1f6;border-bottom:1px solid #d5e1e8}
  .company-cap-title b{font-size:16px;color:var(--accent)}
  .company-cap-title span{font-size:11px;margin-left:8px;color:var(--muted)}
  .company-cap-title small{color:var(--muted)}
  .cap-item{padding:13px 15px;border-bottom:1px dashed var(--line)}
  .cap-item:last-child{border-bottom:0}
  .cap-head{display:flex;justify-content:space-between;gap:12px;font-size:13px;margin-bottom:8px}
  .cap-head span{font-size:11px;color:#475569;background:#f1f5f9;padding:2px 8px;border-radius:10px}
  .cap-item dl{display:grid;grid-template-columns:94px 1fr;margin:0;font-size:12px}
  .cap-item dt{color:var(--muted);padding:5px 8px;background:#f8fafc;border-bottom:1px solid #eef2f7}
  .cap-item dd{margin:0;padding:5px 8px;border-bottom:1px solid #eef2f7}
  .cap-item dd.quote{color:#64748b}
  .cap-source{font-size:10.5px;color:#94a3b8;margin-top:8px}
  .cap-source a{color:#2563eb;text-decoration:none}
  @media(max-width:900px){.cap-tools{grid-template-columns:1fr}.cap-summary{grid-template-columns:1fr}.company-cap-title{align-items:flex-start;flex-direction:column}.cap-item dl{grid-template-columns:1fr}.cap-item dt{font-weight:600}}
"""

CAPABILITY_JS = """
<script>
(() => {
  const search = document.getElementById('capSearch');
  const layer = document.getElementById('capLayer');
  const count = document.getElementById('capCount');
  const cards = Array.from(document.querySelectorAll('.company-cap'));
  const apply = () => {
    const q = search.value.trim().toLowerCase();
    const selected = layer.value;
    let visible = 0;
    cards.forEach(card => {
      const ok = (!q || card.dataset.search.includes(q)) &&
        (!selected || card.dataset.layer === selected);
      card.style.display = ok ? '' : 'none';
      if (ok) visible += 1;
    });
    count.textContent = `${visible} 家公司`;
  };
  search.addEventListener('input', apply);
  layer.addEventListener('change', apply);
})();
</script>
"""


def build_html(template_path: Path, output_path: Path, rows: list[dict[str, str]]) -> None:
    source = template_path.read_text(encoding="utf-8")
    source = source.replace(
        "<title>光模块行业产业链全景图 · 产业链优先版</title>",
        "<title>光模块行业产业链全景图 · 公司能力细化版</title>",
    )
    source = source.replace(
        "<h1>光模块行业产业链全景图 · 产业链优先版</h1>",
        "<h1>光模块行业产业链全景图 · 公司能力细化版</h1>",
    )
    source = source.replace(
        '<a href="#s7">⑦ 企业图谱</a>',
        '<a href="#s7">⑦ 企业图谱</a>\n    <a href="#s8">⑧ 公司能力卡</a>',
    )
    source = source.replace("</style>", CAPABILITY_CSS + "\n</style>")
    source = source.replace("  <footer>", capability_section(rows) + "\n  <footer>", 1)
    source = source.replace("</body>", CAPABILITY_JS + "\n</body>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--pdf-output", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--html-template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()

    rows = granular_rows()
    write_capability_csv(args.csv_output, rows)
    build_pdf(args.pdf_output, rows)
    build_html(args.html_template, args.html_output, rows)
    print(
        f"companies={len({row['公司'] for row in rows})} "
        f"capabilities={len(rows)} nodes={len({row['cell_id'] for row in rows})}"
    )
    print(args.csv_output)
    print(args.pdf_output)
    print(args.html_output)


if __name__ == "__main__":
    main()
