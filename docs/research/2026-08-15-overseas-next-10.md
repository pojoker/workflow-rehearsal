# 海外候选一手证据审计：Hamamatsu × Microchip + 下一批 8 家（2026-08-15）

## 0. 文档边界与纪律

- 本文件只写 `docs/research/2026-08-15-overseas-next-10.md`；不改 canonical（tree.yaml /
  knowledge.yaml / points.csv / edges.csv 等）、不动 `calls/*.csv`、不执行 Git。
- 审计仅依据第一方（A 级）正式材料与官网披露：财报公告、业绩简报、SEC 附件与官网产品/新闻页。
  所有结论为 **first-party asserted**，无独立来源验证，不得据此推断供货或替代关系
  （SPEC §2 非目标：不把第一方陈述升级为公司能力点、供货边或产业结构事实）。
- 零结果双通道（纪律 9）：两期不同正式披露互为通道，另加官网产品/新闻页 90 天复核；
  本文件不把"未单列/未提及"当作行业负面证据，只作候选晋级判定输入。
- 本文件只输出审计结论与晋级建议（watch / quarterly / 维持 discovery），
  实际改写 `company_candidates.csv` / `watch_entities.csv` 由 calls 层操作者另行动作。

## 1. 审计对象身份（源自 company_candidates.csv）

| candidate_id | entity | suggested_role | suggested_tier | capability_scope | inclusion_reason | verification_status |
|---|---|---|---|---|---|---|
| CAND_HAMAMATSU | Hamamatsu Photonics | upstream_enabler | quarterly(P3) | C3 | InGaAs 探测器可能补足接收器件 | source_verified |
| CAND_MCHP | Microchip | upstream_enabler | quarterly(P3) | C5 | 高速 Ethernet PHY 可能提供电侧信号 | source_verified |

本批共 10 家 source_verified 候选，本文完成其中 2 家审计，其余 8 家列为下一批（§4）。

---

## 2. Hamamatsu Photonics（CAND_HAMAMATSU）

### 2.1 正式期材料清单

| 期间 | 材料 | 发布日期 | period_end | 信源等级/类型 | URL |
|---|---|---|---|---|---|
| FY2026 H1/Q2 | 半年报/业绩公告（IR 新闻） | 2026-05-14 | 2026-03-31 | A / regulatory_filing | https://www.hamamatsu.com/jp/en/news/investor-relations/2026/20260514000000.html |
| FY2026 Q1 | Q1 业绩简报（results briefing） | 2026-02-11 | 2025-12-31 | A / earnings_presentation | https://www.hamamatsu.com/content/dam/hamamatsu-photonics/sites/documents/01_HQ/ir/financial-information/results-briefing/h_ir_260211_se_en.pdf |

### 2.2 逐期审计发现

- **FY2026 H1/Q2（2026-05-14，period_end 2026-03-31）**：
  材料仅出现"工业业务受生成式 AI 投资支持"类表述（industrial business supported by
  generative AI investment）；**光通信未单列**——无独立光通信分部/销售口径、无接收器件
  相关经营信号。
- **FY2026 Q1 简报（2026-02-11）**：
  全文复核**无光通信经营信号**（无光通信销售额、无探测器/接收器件订单、无相关客户或节点表述）。
- 两期均为"正式材料存在但无光通信单列口径"；按 MELCO 先例（两期 no_relevant_signal →
  WATCH_MELCO），属候选不满足 quarterly 层经营信号门槛，而非行业负面证据。

### 2.3 官网产品页与 90 天事件复核（第二通道）

- 近 90 天官网产品页事件仅见 UV 光电二极管、THz 等**非本研究事件**，无光通信接收器件
  采用/量产类公告。
- 官网产品页（https://www.hamamatsu.com/jp/en/our-company/business-domain/solid-state-division/products.html）
  证明 **InGaAs photodiode 可用于 optical communication**——这是**能力证据（capability）**，
  不是近期采用/量产事件（stage evidence），不构成研究事件。

### 2.4 证据等级与判定

- 证据状态：`company_claim_only`（能力页面为第一方产品主张）；正式经营信号：无。
- **结论：维持 discovery（退回 `source_verified`，不升 watch）**。依据：两期不同正式披露均无
  光通信经营信号（已核零结果，tier review 保留），第二通道（90 天产品/新闻页复核）确认无
  光通信采用事件；且升级闸门要求 watch 公司"持续产生高价值事件"——Hamamatsu 近 90 天无
  相关状态变化事件，不满足 watch 晋级条件，故退回发现队列、清空 promoted_entity_id、
  删除 WATCH_HAMAMATSU。

---

## 3. Microchip Technology（CAND_MCHP）

### 3.1 正式期材料清单

| 期间 | 材料 | 发布日期 | period_end | 信源等级/类型 | URL |
|---|---|---|---|---|---|
| FQ1 FY2027 | 季度业绩公告（press release） | 2026-08-06 | 2026-06-30 | A / earnings_release | https://ir.microchip.com/news-events/press-releases/detail/1409/microchip-technology-announces-financial-results-for-first-quarter-of-fiscal-year-2027 |
| FY2026 Q4/FY | 8-K Exhibit 99.1（正式业绩附件） | 2026-05-07 | 2026-03-31 | A / regulatory_filing | https://ir.microchip.com/sec-filings/all-sec-filings/content/0000827054-26-000012/exhibit991q4fy26.htm |

### 3.2 逐期审计发现

- **FQ1 FY2027（2026-08-06，period_end 2026-06-30）**：
  PCIe Gen6 connectivity **design wins 由 6 增至 12**（第一方宣称的电侧连接设计赢单）。
  属电连接/信号完整性口径，**不是光模块采用事件**。
- **FY2026 Q4/FY（2026-05-07，period_end 2026-03-31）**：
  出现 data center / AI engagement 与 Gen6 retimer 表述，同为**电侧（retimer/PHY 类）
  连接信号**，未出现光模块/光收发器采用表述。
- 两期均无光侧（光模块/光引擎/收发器）采用证据；信号强度为 adjacent_segment
  （电连接相邻），非 direct_optical。

### 3.3 官网事件复核（第二通道，近 90 天）

- 2026-06-02 **PCIe6/CXL3.1 retimer** 发布为近 90 天最高价值相关事件
  （入口 https://www.microchip.com/en-us/about/news-releases）。
- 该事件属**相邻电连接/信号完整性**（PCIe/CXL retimer、Ethernet PHY 家族），
  **不建立光模块阶段**，不构成光模块价值链事件。

### 3.4 证据等级与判定

- 证据状态：`company_claim_only`（design wins、retimer 发布均为第一方宣称，无独立验证）；
  光模块采用信号：无。
- **结论：晋级 watch（事件监控层），不升 quarterly**。依据：两期不同正式披露
  （FY2027Q1 业绩公告、FY2026Q4 8-K 附件）均为 `adjacent_segment` 电侧相邻信号——形式上
  通过 quarterly 的最低材料门槛（两个不同正式披露期且非均为 `no_relevant_signal`），但实质
  只有电侧邻接（Gen6 retimer / PCIe Gen6 design wins）、无直接光学采用，因此只升
  watch、不升 quarterly。
- 边界：PCIe/CXL retimer 与 Ethernet PHY 是电侧信号，不得推断为光模块供货或替代；
  design wins 数量为第一方声称，无独立验证；不得以电侧景气推断光侧景气。
- 待核（watch 期间）：Microchip 在光模块价值链的具体角色（电侧 PHY/DSP vs 光侧器件）
  需后续正式材料或独立来源；光侧采用事件出现后才重新评估 quarterly 晋级。

---

## 4. 下一批待研究 8 家

本批 10 家 source_verified 候选剔除上述 2 家后，剩余 8 家进入下一批正式期一手证据审计：

| candidate_id | entity | suggested_role | suggested_tier | capability_scope | inclusion_reason | source_ref（一手入口） | notes |
|---|---|---|---|---|---|---|---|
| CAND_LWLG | Lightwave Logic | upstream_enabler | quarterly(P3) | M3/C4 | 电光聚合物调制器提供新材料路线 | https://www.lightwavelogic.com/ | 商业化和收入风险高 |
| CAND_SMARTOPTICS | Smartoptics | system_vendor | quarterly(P3) | MOD1/MOD2 | OSFP 与开放光传输提供欧洲长尾样本 | https://smartoptics.com/products/optical-transceivers/osfp/ | 规模和 AI 暴露待核 |
| CAND_AMKR | Amkor | upstream_enabler | quarterly(P3) | P1 | 光子与光学封装提供 OSAT 补充 | https://amkor.com/technology/ | 官网证据较泛 |
| CAND_DELTA | Delta Electronics | system_vendor | quarterly(P3) | MOD1/D12 | COBO 与 800G 概念验证提供系统集成样本 | https://landing.deltaww.com/en-US/news/12998 | 旧演示不能证明当前量产 |
| CAND_TEL | TE Connectivity | upstream_enabler | quarterly(P3) | D9 | 数据中心与 CPO 连接提供连接器长尾样本 | https://www.te.com/en/about-te/news-center/te-ofc-2026.html | 光互联收入难分拆 |
| CAND_RBBN | Ribbon Communications | system_vendor | quarterly(P3) | MOD2 | IP optical networking 提供传输长尾样本 | https://ribboncommunications.com/solutions/service-provider-solutions/ip-optical/ribbons-automated-ip-routing-and-optical-networking | AI 光互联信号偏弱 |
| CAND_EKI | Ekinops | system_vendor | quarterly(P3) | MOD2 | 400G 相干系统提供欧洲长尾样本 | https://www.ekinops.com/images/press-releases/24.01.2023-PM400FR05-C2A_PR_ENG.pdf | AI DCI 归因有限 |
| CAND_HPE | HPE | system_vendor | quarterly(P3) | MOD1/MOD2 | Juniper 并入后提供 AI 网络与 1.6T-ready 系统信号 | https://www.hpe.com/us/en/juniper-data-center-interconnect.html | 并购后口径复杂 |

下一批审计要点（沿用本文方法）：每家取最近两个不同正式披露期的 A 级材料逐期复核
（quarterly 晋级须两期非均为 no_relevant_signal），90 天官网事件作第二通道，输出
direct_optical / adjacent_segment / no_relevant_signal 信号分级与 watch/quarterly 建议；
全程 first-party asserted，无独立验证，不推供货/替代。

## 5. 队列推进动作与晋级纪律

- 本文 2 家审计结论（2026-08-15 calls 层执行）：
  - **Microchip → watch**：`CAND_MCHP`→`WATCH_MCHP`（active）。两期正式材料
    （`TR_MCHP_FY2027Q1/FY2026Q4`）均为 adjacent_segment 且 signal_summary 明确
    非光模块采用；形式上过 quarterly 最低材料门槛，但实质仅电侧邻接，故只升 watch。
  - **Hamamatsu → 退回发现队列**：近 90 天无相关状态变化事件，不满足 watch 升级闸门
    （持续产生高价值事件）。`CAND_HAMAMATSU` 保持 `source_verified`、清空
    `promoted_entity_id`、删除 `WATCH_HAMAMATSU`；两期 tier review
    （`TR_HAMAMATSU_FY2026H1/FY2026Q1`，均为 no_relevant_signal）保留为已核零结果。
  - 未创建 universe 四季度槽、未新增 source/claim/event。
- 晋级纪律复核（SPEC §5）：
  - quarterly 层要求两个不同正式披露期且不能两期均为 no_relevant_signal：Microchip
    形式上通过（两期 adjacent_segment），但实质仅电侧邻接、无直接光学采用，故不升
    quarterly；Hamamatsu 两期均为 no_relevant_signal，不满足 quarterly 材料门槛。
  - watch 层要求持续产生高价值事件：Microchip 有近 90 天 PCIe6/CXL3.1 retimer 事件
    支撑 watch 状态；Hamamatsu 近 90 天无相关状态变化事件，退回 discovery。
- 后续动作：下一批 8 家（§4）按其一手入口逐期审计；Microchip 按事件持续监控，出现光侧
  采用/量产事件并经第二 origin 佐证后再评估 quarterly 晋级；Hamamatsu 出现光通信采用
  事件后再重新评估晋级。
- 全局约束重申：本文所有结论为第一方 asserted、无独立验证；不生成供货边、不推断
  替代、不升级能力点；缺失与未知继续显式显示。
