# 境外公司路径②取证（远程会话，待本地判定闸）

检索日期：2026-07-25。规则：仅采公司自述（10-K/8-K 原句英文照录），锚全部 sec.gov 原文页。研报/媒体转述一律未采。
本文件只是取证结果，不动 points.csv/edges.csv；入点/立边由本地判定闸决定。

---

## 1. Lumentum (LITE) —— 最高优先级

- CIK 1633978。FY2025 10-K（财年止 2025-06-28，2025-08-19 提交）。
- **10-K 锚**：https://www.sec.gov/Archives/edgar/data/1633978/000162828025040830/lite-20250628.htm

### 建议点（按 cell）

| cell_id | 建议状态 | 自述原句（10-K 原文照录） |
|---|---|---|
| C1 激光器芯片 | 生产中 | "We are making significant investments in next generation optical components for cloud data center and AI/ML applications, including higher speed and higher optical power laser chips for use in high-speed datacom transceivers and data interconnection solutions." 另："…which enhanced our product portfolio by adding Oclaro's indium phosphide laser and photonic integrated circuit technologies, as well as its coherent component and module capabilities."（InP 激光器+PIC 内制能力来源） |
| C2 VCSEL | 生产中 | "We also manufacture key components used in optical transceivers and data interconnect solutions, including high-speed laser transmitters, photonic integrated circuits, and photodiodes, high-power laser light sources, as well as VCSELs and VCSEL arrays for short-reach data transmission." |
| C3 探测器芯片 | 生产中 | 同上句（"…and photodiodes…"），与 C2 共句，判定闸自裁是否单句双点 |
| C6 可调谐/相干光组件 | 生产中 | "In data center interconnects, Lumentum offers both its own coherent pluggable transceivers and the underlying ultra-narrow linewidth laser and coherent components used by transceiver customers." 另："Our tunable transceivers and transmitter modules and high-speed coherent components are essential to DWDM systems…" |
| MOD1 数通直检模块 | 生产中 | "Lumentum is a leading provider of high-speed optical transceivers and optical components that underpin today's AI and cloud computing applications." |
| MOD2 相干模块 | 生产中 | C6 第一句同源（"its own coherent pluggable transceivers"） |

产线佐证（免锚常识层备注）："We use a combination of our own wafer fabrication facilities, or wafer fabs, assembly and test facilities, as well as third-party contract manufacturers to produce our products."（自有 fab，日本相模原 fab 2024-07 购入土地厂房 $42.2M）

### NVIDIA 战略投资边（8-K，Item 3.02）

- **8-K 锚**：https://www.sec.gov/Archives/edgar/data/1633978/000119312526085412/d41019d8k.htm （2026-03-02，Item 3.02/5.03/7.01/9.01）
- 原句："…completed the issuance and sale of 2,876,415 shares of the Company's Series A Convertible Preferred Stock…to NVIDIA Corporation…pursuant to a Securities Purchase Agreement between the parties…dated as of March 2, 2026." + "The shares of Series A Preferred Stock were sold at a price of $695.31 per share for an aggregate purchase price of $2,000,000,000 in cash (the 'Transaction')."
- 附带合作主张（8-K 正文转述其新闻稿）："…announcing, among other things, the private placement pursuant to the Purchase Agreement and a strategic partnership to develop state of the art optics technology…"
- 边候选：NVIDIA→Lumentum 股权/战投边，数值 20 亿，单位 美元，财年 2026-03-02 单笔，锚 sec.gov 8-K 原文。私募（Section 4(a)(2)），可转优先股。

---

## 2. Coherent (COHR) —— 最高优先级

- CIK 820318。FY2025 10-K（财年止 2025-06-30，2025-08-15 提交，文件前缀仍为 iivi）。
- **10-K 锚**：https://www.sec.gov/Archives/edgar/data/820318/000082031825000014/iivi-20250630.htm

### 建议点（按 cell）

| cell_id | 建议状态 | 自述原句（10-K 原文照录） |
|---|---|---|
| C1 激光器芯片 | 生产中 | "We have in-house laser design and manufacturing capability for GaAs-based VCSELs, InP-based DMLs, EMLs, and CW lasers." |
| C2 VCSEL | 生产中 | "Coherent has multiple 6-inch GaAs VCSEL fabs in the U.S." 另："Today, Coherent is one of the very few vertically integrated 6-inch VCSEL manufacturers with a proven track record in high-volume manufacturing of high-reliability, large multi-emitter VCSEL arrays…" |
| C3 探测器芯片 | 生产中 | "We manufacture GaAs VCSELs and VCSEL arrays, InP edge-emitting lasers and photo diodes, as well as specialty glass wafers for the consumer electronics market." |
| C4 硅光PIC | 生产中 | "Our portfolio also includes silicon photonics and a broad array of CPO-enabling technologies."（产品组合句，弱于制造句，判定闸自裁等级） |
| MOD1 数通直检模块 | 生产中 | 产品列原文："Datacom transceivers and components for datacom transceivers 800G/1.6T transceivers, CPO, VCSELs, EMLs, silicon photonics, ICs, isolators, and thermoelectric coolers; 400G/lane components supporting 3.2T and 6.4T." |
| MOD2 相干模块 | 生产中 | "Coherent transceivers Drive further integration to reduce size and power consumption; increase bandwidth to enable 100G/200G/400G/800G coherent transceivers." |

公司总述（树层备注可用）："Coherent…is a vertically integrated manufacturing company that develops, manufactures, and markets lasers, transceivers, and other optical and optoelectronic devices, modules, and systems, as well as engineered materials…"

### NVIDIA 战略投资边（8-K，Item 3.02）

- **8-K 锚**：https://www.sec.gov/Archives/edgar/data/820318/000119312526084366/d42735d8k.htm （2026-03-02，Item 3.02/7.01/9.01）
- 原句："…entered into a Securities Purchase Agreement…with NVIDIA Corporation…and Coherent completed the issuance and sale of 7,788,161 shares of the Company's common stock, no par value…at a price of $256.31 per share for an aggregate purchase price of $2,000,000,000 in cash…"
- 附带合作主张（8-K 正文）："…a collaboration between Coherent and NVIDIA under which NVIDIA has access to five additional Coherent product families related to co-packaged optics, enabling next-generation AI infrastructure…"
- 边候选：NVIDIA→Coherent 股权/战投边，数值 20 亿，单位 美元，2026-03-02 单笔，普通股私募，锚 sec.gov 8-K 原文。

---

## 3. Applied Optoelectronics (AAOI) —— 补强（triage 已挂 MOD1 待判）

- CIK 1158114。FY2025 10-K（2026-02-26 提交）。
- **10-K 锚**：https://www.sec.gov/Archives/edgar/data/1158114/000143774926005875/aaoi20251231_10k.htm

| cell_id | 建议状态 | 自述原句 |
|---|---|---|
| MOD1 数通直检模块 | 生产中 | "…we supply optical transceivers that plug into switches and servers within the data center…" + "Our products are used to interconnect network elements within data centers generally, and our 800G products in particular are used to interconnect AI compute infrastructure." |
| C1 激光器芯片 | 生产中 | "We manufacture the majority of the laser chips and optical components that are used in our products." + "All of our laser chips are manufactured in our facility in Sugar Land, Texas."（MBE/MOCVD 自产） |
| D12 光引擎/COB | 生产中(弱) | "The majority of the data center optical transceivers that we sell utilize our own lasers and subassemblies (we refer to the transceivers subassemblies as 'light engines')…"（light engine 自用为主，是否入格判定闸自裁） |

总述："AOI is a leading, vertically integrated provider of fiber-optic networking products, primarily for four networking end-markets: internet data center, cable television ('CATV'), telecommunications ('telecom'), and fiber-to-the-home ('FTTH')."

---

## 4. MACOM (MTSI) —— 新点候选

- CIK 1493594。FY2025 10-K（财年止 2025-10-03，2025-11-14 提交）。
- **10-K 锚**：https://www.sec.gov/Archives/edgar/data/1493594/000149359425000054/mtsi-20251003.htm

| cell_id | 建议状态 | 自述原句 |
|---|---|---|
| C5 电芯片 | 生产中 | "We provide a complete product portfolio of Transimpedance Amplifier (TIAs), Modulator Drivers, Lasers and Photodetectors, to support single-mode, multi-mode and silicon photonics based transceivers and, in some cases, individual component designs are optimized for use together as a chipset." 另（CDR 覆盖）："Our portfolio of opto-electronics products includes clock and data recovery, optical post amplifiers, laser and modulator drivers, transimpedance amplifiers…in 2.5/10/40/100/400 gigabits per second long haul, metro, data center links…" |
| C1/C3（可选） | 生产中(弱) | 同一句中 "Lasers and Photodetectors" 为对外销售的激光器/探测器产品线；速率段覆盖 "100G, 200G, 400G, 800G, 1.6T and higher speeds"。是否单句拆双点判定闸自裁 |

---

## 5. Semtech (SMTC) —— 新点候选

- CIK 88941。FY2026 10-K（财年止 2026-01-25，2026-03-23 提交）。
- **10-K 锚**：https://www.sec.gov/Archives/edgar/data/88941/000008894126000005/smtc-20260125.htm

| cell_id | 建议状态 | 自述原句 |
|---|---|---|
| C5 电芯片 | 生产中 | "Our comprehensive portfolio includes integrated circuits ('ICs') for data centers, enterprise networks, PON, and wireless base station optical transceivers." + "Our high-speed interfaces range from 100Mbps to 1.6Tbps and support key industry standards such as Fibre Channel, InfiniBand, Ethernet, PON and synchronous optical networks."（Signal Integrity 分部 FY2026 营收 $322.6M） |

注：FY2026 10-K 语料内未命中 "Tri-Edge/CDR/TIA/laser driver" 具名句（术语商标句本届年报未出现在正文检索段），以上为其最强产品主张句，如需商标级具名句需另采官网新闻稿，本次未硬凑。
另：2026-03-03 完成收购 HieFo Corporation（约 $34.0M 全现金，10-K 原文），HieFo 为 InP 激光器公司——C1 潜在线索，仅登记不建点。

---

## 6. Fabrinet (FN) —— 已有点 P001 补强

- 已入册 P001/EMS1（sec.gov 锚在 E001）。补英文原句供 P001 引语升级：
- **10-K 锚**：https://www.sec.gov/Archives/edgar/data/1408710/000140871025000039/fn-20250627.htm （FY2025，财年止 2025-06-27）
- 原句："We provide advanced optical packaging and precision optical, electro-mechanical and electronic manufacturing services to original equipment manufacturers ('OEMs') of complex products such as optical communication components, modules and sub-systems, industrial lasers, automotive components, medical devices and sensors."
- 建议：P001 引语字段以此原句替换中文转写，锚 URL 直接落到本 10-K 页。

## 7. Marvell (MRVL) / Broadcom (AVGO) —— 无需补强

- P003 Marvell/C5：已有 sec.gov FY2026 10-K 原文锚（mrvl-20260131.htm），锚质量已达标，不动。
- P020 Broadcom/C5：已有 sec.gov FY2025 10-K 原文锚（avgo-20251102.htm），不动。

---

## 汇总表（一家一行）

| 公司 | 建议 cell | 建议状态 | 锚质量 |
|---|---|---|---|
| Lumentum | C1/C2/C3/C6/MOD1/MOD2 | 生产中 | sec.gov 10-K 原文 + 8-K 原文（NVIDIA 20亿边锚） |
| Coherent | C1/C2/C3/C4/MOD1/MOD2 | 生产中（C4 组合句偏弱） | sec.gov 10-K 原文 + 8-K 原文（NVIDIA 20亿边锚） |
| AAOI | MOD1/C1（D12 弱） | 生产中 | sec.gov 10-K 原文 |
| MACOM | C5（C1/C3 可选） | 生产中 | sec.gov 10-K 原文 |
| Semtech | C5 | 生产中 | sec.gov 10-K 原文（商标具名句未找到自述，未硬凑） |
| Fabrinet | EMS1（P001 补强） | 已入册 | sec.gov 10-K 原文（引语升级候选） |
| Marvell | C5（P003） | 已入册 | sec.gov 原文，达标不动 |
| Broadcom | C5（P020） | 已入册 | sec.gov 原文，达标不动 |
