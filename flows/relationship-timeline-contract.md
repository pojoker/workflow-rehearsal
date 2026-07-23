# 关系级时间聚合数据契约（R3，Claude 定稿，2026-07-23）

依 codex O2（roadmap-review-codex.md）：先契约后实现，防止关系视图制造伪连续性。

## 1. 关系键

- **不用显示名 groupby**。建别名映射表（实现内置 dict）：`Fabrinet(解匿)→Fabrinet`、
  `Ciena(解匿)→Ciena`、`Google(解匿)→Google`、`中际旭创(作为客户)→中际旭创`、
  `华为+海思→华为(含海思)`、`华为→华为(含海思)`、`博通(客户)→博通(Broadcom)`、
  `Broadcom→博通(Broadcom)`、`NVIDIA(客户)→NVIDIA`、`ficonTEC(罗博特科)→罗博特科/ficonTEC`、
  `PINEWAVE(关联方)→PINEWAVE`、`浙江粮油(出口代理)→浙江粮油`、
  `索尔思(Source Photonics)→索尔思(Source Photonics)`、`苏世博→索恩格(SEG Automotive)`、
  `罗博特科→罗博特科/ficonTEC`（v1.1 补，2026-07-24：R3 实现如实报告裸名 E076 未归一，
  经核 E076 与 E011/E012 为同一主体，补此规则）
- 匿名端点（含"匿名"字样）**不聚合**——每个匿名槽位保持独立行，不与实名关系合并。
- 关系键 =（规范化供方, 规范化需方），方向敏感（A→B 与 B→A 是两条关系）。

## 2. 期间键

- FY 与自然年**不混同**：year 字段区分 `2023`（自然年）与 `FY2023`（财年）两种
  period_type；同一关系两种口径并存时不去重、不比较大小，各自成序列。
- `2025Q1` 等季度期照原样保留，period_type=quarter。

## 3. 同年多边冲突

- 同一关系键+同一期间出现多个事件（如 E010 与 E045 都载猎奇→旭创 2024）：
  金额/占比一致则合并为一行并列出全部来源边ID；不一致则保留多行并标
  `conflict=true`（不擅自择一）。

## 4. 关系级状态裁决

- first_observed/last_observed 在**关系级**重算（跨边）。
- 同期间某边 observed、另一边 censored：关系级取 **observed 优先**（有观测即非截尾）。
- confirmed_ended 仅当该关系全部边均达 confirmed_ended（现实上仍只有
  NeoPhotonics→华为）。
- confirmed_started 需文件明示起始年（联讯"2018年起合作"型），标注来源。

## 5. 证据链保留

- 每个聚合事件行必须带 `source_edge_ids`（分号分隔）——禁止为连续性丢证据链。

## 输出

flows/out/relationship-timeline.csv：
`relation_id,供方,需方,period,period_type,pct_or_amt,observe_type,source_edge_ids,conflict`
自测：打印关系数/事件数/conflict 计数；抽验 猎奇→中际旭创（应跨 E010+E045 连成
2023-2025 序列）与 Fabrinet→Lumentum（E005+E068 与 E038 的 FY 序列）。
