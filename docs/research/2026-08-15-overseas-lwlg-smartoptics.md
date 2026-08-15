# 海外候选一手证据审计：Lightwave Logic × Smartoptics（2026-08-15）

## 0. 文档边界与纪律

- 本研究文档只承载证据审计，不改 canonical（tree.yaml / knowledge.yaml / points.csv /
  edges.csv 等）；同批 calls 实现仅按本文结论更新独立情报层，且不执行 Git 提交。
- 审计仅依据第一方（A 级）正式材料与官网披露：SEC 10-Q/10-K、Oslo Børs 正式季度报告
  （Cision 承载的交易所公告）与官网新闻/事件页。所有结论为 **first-party asserted**，
  无独立来源验证，不得据此推断供货或替代关系（SPEC §2 非目标）。
- 零结果双通道（纪律 9）：两期不同正式披露互为通道，另加官网新闻/事件页 90 天复核；
  官网博客、播客与第三方媒体文章只作为第一方披露入口，不自动成为事实或事件。
- 本文件输出审计结论与晋级建议（quarterly / watch / 维持 discovery）；对应 calls 层
  实现及其边界记录在 §4。

## 1. 审计对象身份（源自 company_candidates.csv）

| candidate_id | entity | suggested_role | suggested_tier | capability_scope | inclusion_reason | verification_status |
|---|---|---|---|---|---|---|
| CAND_LWLG | Lightwave Logic | upstream_enabler | quarterly(P3) | M3/C4 | 电光聚合物调制器提供新材料路线 | source_verified |
| CAND_SMARTOPTICS | Smartoptics | system_vendor | quarterly(P3) | MOD1/MOD2 | OSFP 与开放光传输提供欧洲长尾样本 | source_verified |

两家的共同点：都是上市主体、最近四个正式期间均有可直接取得的一手材料、且整个经营内容
与光通信直接相关（LWLG 全部业务是电光聚合物调制材料；SMOP 全部业务是开放光传输与
光收发系统）。审计目标是确认四期材料可逐槽登记、信号分级与晋级建议。

---

## 2. Lightwave Logic（CAND_LWLG）

### 2.1 正式期材料清单（最近四个正式期间，全部 A 级 SEC 法定文件）

| 期间 | 材料 | 发布日期 | period_end | 信源等级/类型 | URL |
|---|---|---|---|---|---|
| 2026Q2 | 10-Q | 2026-08-14 | 2026-06-30 | A / regulatory_filing | https://www.sec.gov/Archives/edgar/data/1325964/000107997326001097/lwlg_10q-063026.htm |
| 2026Q1 | 10-Q | 2026-05-15 | 2026-03-31 | A / regulatory_filing | https://www.sec.gov/Archives/edgar/data/1325964/000155335026000087/lwlg_10q-033126.htm |
| 2025FY | 10-K | 2026-03-20 | 2025-12-31 | A / regulatory_filing | https://www.sec.gov/Archives/edgar/data/1325964/000107997326000348/lwlg_10k-123125.htm |
| 2025Q3 | 10-Q | 2025-11-14 | 2025-09-30 | A / regulatory_filing | https://www.sec.gov/Archives/edgar/data/1325964/000107997325001745/lwlg_10q-093025.htm |

### 2.2 逐期审计发现

- 业务口径：LWLG 是**专门从事电光（EO）聚合物调制材料与 IP 的公司**（Perkinamine®），
  目标是集成进硅光（SiPh）/PIC 平台，为高速光调制器提供材料；不制造光模块、分立器件
  或完整模块，商业模式为材料销售 + IP 许可 + PDK 使能 + 版税（10-Q/10-K 一致表述）。
  该业务与光通信直接相关（direct_optical），不是集团宽口径下的间接信号。
- **2026Q2（2026-08-14 10-Q）**：三/六个月净销售额 $32,751 / $61,918（同比 $25,605 /
  $48,522），全部来自 2023 年 5 月签署的首个商业许可+材料供应协议（单一瑞士客户，
  占收入 10% 以上）；与客户签订 NRE 联合开发 MOA（2026 年 1 月执行，公司自 2025 年
  起已开始相关工作，共同开发硅光 EO 聚合物调制器芯片）：Phase 1 对价 $130,000 已在
  交付后确认，Phase 2 $200,000 待客户验收分期支付，2026 上半年收到 $100,000 分期款
  计入合同负债；公司明确客户产品规模商业生产收入最早要到 2027 年。
- **2026Q1（2026-05-15 10-Q）**：季度净销售额 $29,167（同比 $22,917），100% 来自瑞士；
  同一 JDA/MOA 口径（2026 年 1 月执行）；客户项目处于商业化框架下的开发阶段。
- **2025FY（2026-03-20 10-K）**：全年经营口径与前述一致；公司称资金足以支撑经营
  至少到 2027 年 12 月；管理层明确客户产品规模商业生产收入最早要到 2027 年。
- **2025Q3（2025-11-14 10-Q）**：九个月许可协议收入 $77,688（同比 $58,938）；
  PDK 开发（为潜在及现有客户提供 Process Development Kits）写入商业化策略。
- 四期材料一致表明：产品阶段为**开发/原型阶段（design win cycle 第 1-3 阶段）**，
  尚无量产、客户验证或批量交付证据；收入极小、单客户依赖，属于商业化风险高的早期
  材料公司，但光学信号直接、连续且可追溯。

### 2.3 官网事件复核（第二通道，近 90 天 = 2026-05-17 至 2026-08-15）

- 2026-03-03 **Silterra/Luceda PDK 新闻稿**（https://www.lightwavelogic.com/press-releases/
  silterra-silicon-photonics-platform-enables-integration-of-lightwave-logic-high-speed-polymer-
  modulators-through-luceda-photonics-pdk ）：EO 聚合物调制器平台进入 Luceda PDK（面向
  Silterra 硅光平台），2026 年初完成首次 tapeout，特性验证预计 2026 年中。**该事件在
  90 天窗口之外**，且为第一方公告（asserted），不构成客户/代工厂独立验证。
- 近 90 天内官网事件页/媒体页仅见播客、网络研讨会与第三方媒体文章（07-30 播客、
  07-23 研讨会、07-22 Gazettabyte 文章、07-09 Luminary 播客、06-16 OIP 会议、05-06
  PIC Magazine 文章）——均为**传播性质**，不构成新的正式业务事件。
- SEC 8-K：2026-04-20 ATM 增售协议修订（融资事件）、2026-05-21 股东大会、2026-07-20
  任命新 CFO——均为公司治理/融资事件，无产品阶段推进。
- 结论：近 90 天无正式披露的产品阶段推进事件；最新正式产品事件是 2026-03-03 PDK 公告。

### 2.4 证据等级与判定

- 四期正式材料（10-Q/10-K）均为 A 级法定披露，光学信号直接且连续：`direct_optical`。
- 证据状态：`company_claim_only`（材料/IP 商业化主张均为第一方，收入极小、无独立客户
  验证或量产证据；PDK/tapeout 为第一方公告）。
- **结论：晋级 quarterly（正式季度覆盖层）**。依据：上市主体（NASDAQ: LWLG）；最近四个
  正式期间（2026Q2/2026Q1/2025FY/2025Q3）均能逐槽登记 A 级 SEC 材料；能持续回答
  “产品阶段（design win cycle/JDA 阶段）与技术路线（EO 聚合物 vs InP/硅光）”问题。
  边界：收入与商业化规模极小、单客户依赖、量产收入最早 2027 年，按 POET/SIVERS 先例
  （小体量商业化观察公司）纳入季度层，但**不得把 PDK/材料主张写成量产或客户采用**；
  博客、播客与媒体文章不自动成为事实。

---

## 3. Smartoptics（CAND_SMARTOPTICS）

### 3.1 正式期材料清单（最近四个正式期间，全部 A 级交易所正式季度报告）

| 期间 | 材料 | 发布日期 | period_end | 信源等级/类型 | URL |
|---|---|---|---|---|---|
| 2026Q2 | Q2 2026 季度报告 | 2026-07-13 | 2026-06-30 | A / regulatory_filing | https://smartoptics.com/cision-post/smartoptics-group-asa-smop-q2-2026-financial-results/ |
| 2026Q1 | Q1 2026 季度报告 | 2026-05-07 | 2026-03-31 | A / regulatory_filing | https://smartoptics.com/cision-post/smartoptics-group-asa-smop-q1-2026-financial-results/ |
| 2025Q4 | Q4 2025 季度及全年报告 | 2026-02-19 | 2025-12-31 | A / regulatory_filing | https://smartoptics.com/cision-post/smartoptics-group-asa-smop-q4-2025-financial-results/ |
| 2025Q3 | Q3 2025 季度报告 | 2025-10-29 | 2025-09-30 | A / regulatory_filing | https://smartoptics.com/cision-post/smartoptics-group-asa-smop-q3-2025-financial-results/ |

（另：2025 年报于 2026-04-10 发布，作为年度正式材料交叉参照；不重复占用季度槽。）

### 3.2 逐期审计发现

- 业务口径：Smartoptics 全部业务是**开放光网络**——open line system、WDM/ROADM、
  光收发器、OSFP 与模块化 transponder/muxponder，服务运营商、云、互联网交换与数据中心
  互联（DCI）。四期报告均为 `direct_optical`。
- **2026Q2（2026-07-13）**：收入 $28.9M（+54.6% YoY），历史新高；毛利率 46.1%；
  EBITDA $4.5M / 15.5%；欧洲收入翻倍至 $10.4M；明确“来自间接超大规模与 AI 数据中心
  业务的贡献增长”；发布新财务愿景（收入潜力 USD 300–400M、2026 年起年均增速 >25%、
  规划期后半段 EBIT 利润率 >16%）；可寻址市场从约 USD 5B（metro）扩至约 USD 11.5B
  （metro + long-haul），行业预测 2029 年约 USD 14B。
- **2026Q1（2026-05-07）**：收入 $22.9M（+59.6% YoY），历史新高；毛利率 48.2%；
  EBITDA $2.7M / 11.7%（剔除迁址一次性成本 13.7%）；明确“AI 驱动的网络容量扩容与
  数据中心互联”是增长动能，超大规模与云客户加大投入；报告“为保障未来季度收入的
  供应链挑战”（供给约束信号）。
- **2025Q4/全年（2026-02-19）**：Q4 收入 $23.2M（+37.7%）；2025 全年收入 $75.3M
  （+35.6%）；披露“AI 基础设施产生的收入”与大型客户战略进展；毛利率 46.1%（含一次性
  库存调整）。
- **2025Q3（2025-10-29）**：收入 $19.0M（+46.2%）；毛利率 49.5%；EBITDA $2.4M /
  12.6%；“市场日益由 AI 基础设施驱动”；2025 年 8 月已升入 Euronext Oslo Børs 主板。
- 四期材料一致表明：开放光传输与 DCI 需求持续、收入连续创新高、AI/超大规模客户贡献
  上升、供应链紧张是明确供给信号；光学信号直接、连续且可追溯。

### 3.3 官网事件复核（第二通道，近 90 天 = 2026-05-17 至 2026-08-15）

- 2026-06-18 **Netnod 战略合作**（https://smartoptics.com/cision-post/netnod-partners-with-
  smartoptics-to-connect-scandinavian-capitals/ ）：北欧领先互联服务商 Netnod 经多厂商
  评估后选择 Smartoptics 开放光网络方案，自建连接斯德哥尔摩、马尔默、哥德堡、奥斯陆、
  哥本哈根的 DWDM 光环。具名客户/伙伴选择事件，第一方公告（asserted）。
- 2026-07-13 Q2 业绩（监管公告，含新财务愿景）；2026-07-06 业绩发布邀请。
- 90 天窗口内无矛盾或撤回事件；窗口外近期事件（2026-03-26 Pilot Fiber 800G-ready
  ROADM、2026-02-08 Teraco 非洲 DCI）仅作背景。

### 3.4 证据等级与判定

- 四期正式材料（Oslo Børs 季度报告）均为 A 级正式披露，光学信号直接且连续：
  `direct_optical`。
- 证据状态：`company_claim_only`（收入/客户/愿景均为第一方披露；Netnod 合作是具名
  伙伴选择但仍是单方公告；无独立验证的出货或份额）。
- **结论：晋级 quarterly（正式季度覆盖层）**。依据：上市主体（Euronext Oslo Børs: SMOP）；
  最近四个正式期间（2026Q2/2026Q1/2025Q4/2025Q3）均能逐槽登记 A 级正式季度报告；
  能持续回答需求兑现（收入、大型客户、DCI/AI 贡献）与供给卡点（供应链紧张）问题。
  边界：愿景/可寻址市场为前瞻（forward-looking），不得当作已实现收入；Netnod 等
  客户事件为第一方 asserted，不推供货或替代结论。

---

## 4. 队列推进动作与晋级纪律

- 本文 2 家审计结论（2026-08-15 calls 层执行）：
  - **Lightwave Logic → quarterly universe**：`CAND_LWLG`→`LWLG`。两期 tier review
    （`TR_LWLG_2026Q2/2026Q1`，均为 direct_optical）；同批登记四个季度槽
    （2026Q2/2026Q1/2025FY/2025Q3，A 级 SEC 10-Q/10-K）。
  - **Smartoptics → quarterly universe**：`CAND_SMARTOPTICS`→`SMOP`。两期 tier review
    （`TR_SMOP_2026Q2/2026Q1`，均为 direct_optical）；同批登记四个季度槽
    （2026Q2/2026Q1/2025Q4/2025Q3，A 级 Oslo Børs 季度报告）。
  - 两家均不进入 watch（quarterly 已覆盖事件监控价值）；除 8 条季度 source 外未新增
    claim/event；未创建 canonical 点、边或供货关系。
- 晋级纪律复核（SPEC §5 与 README 公司升级闸门）：
  - quarterly 层：上市主体 + 最近四个可得正式期间逐槽登记（同批 4 槽）+ 两个不同正式
    披露期 tier review 且非均为 no_relevant_signal——两家均满足，且信号为
    direct_optical（非 adjacent_segment 电侧/相邻信号）。
  - watch 层无需评估：quarterly 晋级后由四季度材料承担持续监控义务。
  - 博客/媒体纪律：LWLG 近 90 天媒体与播客内容不登记为事件；SilTerra/Luceda PDK
    公告（2026-03-03）为第一方 asserted 产品里程碑，未进入 90 天窗口，不自动升级为
    客户验证或量产。
- 后续动作：LWLG 按季度跟踪 JDA/PDK 推进与 2027 量产窗口兑现；SMOP 按季度跟踪收入/
    DCI/AI 贡献与供应链约束；出现第二 origin 佐证的客户采用或出货事件后再评估事件
    登记与 corroborated 状态。
- 全局约束重申：本文所有结论为第一方 asserted、无独立验证；不生成供货边、不推断
  替代、不升级能力点；缺失与未知继续显式显示。
