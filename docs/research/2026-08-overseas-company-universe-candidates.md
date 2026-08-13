# 海外公司扩展候选池（2026-08）

> 截止：2026-08-13。用途：为 `calls` 海外公司新闻与季度材料层提供高召回候选，不直接改变 canonical 产业链。纳入依据只使用公司官网、公司 IR、SEC/交易所/监管披露；本清单是“值得跟踪”的证据，不等于产品已量产、已获客户采用或已形成收入。

## 结论先行

- 当前 14 家应继续作为季度深度覆盖基线；新增公司不能一律强制补四季度。
- 扩展价值最大的空白不是再加一批整机客户，而是补齐 **InP/SOI 材料—光子/模拟芯片—封装/EMS—耦合与测试设备—连接器**。这些节点能把海外技术路线与现有 `cell_id`、国内产业链能力真正交叉验证。
- 本文给出 **64 家新增候选**：首批 10 家、次批 20 家、长尾 34 家。首批均为上市公司且具有连续正式披露入口；私企、子公司、云客户和机构只进入 watch/discovery，不制造四季度空槽。
- 已在 `watch_entities.csv` 的 IQE、DustPhotonics 不计入这 64 家，也不重复推荐。

## 当前基线：14 家（不得重复新增）

| 公司 | ticker | 当前角色 |
|---|---:|---|
| Coherent | COHR | 激光器、器件、模块、材料 |
| Lumentum | LITE | 激光器、模块、CPO/光源 |
| Applied Optoelectronics | AAOI | 数据中心光模块 |
| Fabrinet | FN | 光通信制造服务 |
| NVIDIA | NVDA | AI 计算与网络平台 |
| Arista Networks | ANET | 数据中心交换系统 |
| Cisco | CSCO | 交换、路由、光互联 |
| Meta Platforms | META | 超大规模客户/开放硬件 |
| Broadcom | AVGO | 交换芯片、DSP、CPO |
| Marvell | MRVL | 光 DSP、互联芯片 |
| Nokia | NOK | 光传输与网络系统 |
| Ciena | CIEN | 相干传输与 DCI |
| MACOM | MTSI | 激光/模拟前端/光器件 |
| Credo | CRDO | 高速 SerDes/DSP/互联 |

既有 watch entity：IQE（InP 外延）与 DustPhotonics（硅光/CPO）只保留事件监控，不重复计数。

## 分层规则

- **quarterly universe**：上市主体；官方季度/半年度材料可连续获得；材料中有较高概率出现光互联产品、产能、良率、客户验证或订单信号。
- **watch entity**：私企、集团子公司、云客户、并购标的或只在重大事件时产生高价值信号；不要求四季度齐全。
- **discovery queue**：技术相关但公司业务过宽、光学收入不可分拆、官网主张尚缺商业验证，先做发现性检索。
- `总部/制造` 只记录已由官网/IR直接支持的内容；“未核”表示不凭常识补写。

## 第一批：10 家（建议先落 quarterly universe）

| 公司（上市地） | 总部/主要制造（一手） | 产品/能力与映射 | 纳入理由；主要风险 | 官方来源 |
|---|---|---|---|---|
| AXT（NASDAQ: AXTI） | Fremont；中国三处制造 | InP/GaAs/Ge 衬底；`M1`，T006/T007/T008 | 直接观察 InP 供给、扩产与出口许可；中国制造及许可使地缘因素与经营因素难分离 | [Q1 2026/公司说明](https://investors.axt.com/Investors/news/news-details/2026/AXT-Inc--Announces-First-Quarter-2026-Financial-Results/default.aspx) |
| GlobalFoundries（NASDAQ: GFS） | 未核 | 硅光代工、CPO 平台；`C4/P1`，T013/T015/T017 | 可验证平台从设计到量产的节奏；业务很宽，季度口径未必拆分硅光 | [Silicon Photonics](https://gf.com/technologies/silicon-photonics/) |
| Tower Semiconductor（NASDAQ/TASE: TSEM） | Migdal Haemek, Israel | SiPho/模拟混合信号代工；`C4/C5/P1`，T010/T013/T017 | 官方季度页提供 transcript；风险是客户/应用披露受保密限制 | [季度材料与 transcript](https://ir.towersemi.com/financial-information/quarterly-results/) |
| Semtech（NASDAQ: SMTC） | 未核 | 100/200G 每通道 PMD、TIA/driver、LPO；`C5`，T004/T010/T019 | 高速模拟前端信号密度高；LoRa 等非光业务会稀释口径 | [FiberEdge/DirectEdge](https://www.semtech.com/technology/fiberedge-directedge) |
| MaxLinear（NASDAQ: MXL） | 未核 | 200G TIA、PAM4 DSP；`C5`，T004/T010/T019 | 能补 DSP/TIA 竞争和 LPO 路线；商业份额及客户验证需独立核验 | [Data Center Connectivity](https://www.maxlinear.com/dcc) |
| Jabil（NYSE: JBL） | St. Petersburg；全球 100+ 站点 | 1.6T pluggable、光模块设计制造；`EMS1/MOD1`，T002/T003/T010 | 同时观察制造、供应链和 AI 收入；集团口径很宽，不能把 AI 收入等同光模块收入 | [1.6T transceiver](https://www.jabil.com/news/jabil-launches-1.6t-pluggable-transceiver.html) |
| Veeco（NASDAQ: VECO） | Plainview, New York | InP MOCVD/离子束等设备；`EQ1/EQ2`，T007/T008 | InP 设备订单是产能约束的领先指标；订单可能跨激光、传感等应用 | [InP 设备订单](https://ir.veeco.com/news-and-events/news-details/2026/Veeco-Books-Multi-System-Lumina-and-Spector-Orders-for-Manufacturing-Indium-Phosphide-InP-based-Optical-Components/default.aspx) |
| FormFactor（NASDAQ: FORM） | Livermore, California | 硅光/CPO 晶圆级测试与自动对准；`EQ7`，T015/T017 | 量产测试是当前树中明显缺口；公司主业还包括存储探针卡 | [自动硅光测试](https://www.formfactor.com/product/probe-systems/autonomous-assistants/autonomous-silicon-photonics/) |
| AIXTRON（Xetra: AIXA） | 未核 | InP/GaAs MOCVD；`EQ1`，T007/T008 | 可观察 6 英寸 InP 扩产和设备交期；季度订单不等于数据中心实际装机 | [FY2025 官方发言稿](https://www.aixtron.com/investoren/events/telefonkonferenz/2025/AIXTRON_SE_FY_2025_speech.pdf) |
| ASMPT（HKEX: 0522） | 未核 | 光子芯片贴装、耦合、混合键合/CPO 装配；`EQ3/EQ4/EQ5`，T015/T017 | 覆盖封装自动化关键节点；集团业务宽、样机展示与量产收入需分开 | [OFC 2026 CPO](https://www.asmpt.com/en/news-center/press-releases/asmpt-at-ofc-2026-los-angeles-enabling-scalable-co-packaged-optics-and-photonic-integration/) |

## 第二批：20 家（已完成两期正式材料复核与分层）

本批没有按最初建议机械地全部纳入季度层。两期正式材料复核后，13 家有可重复出现的直接或相邻光学经营信号，已进入 `quarterly universe` 并各补四期正式材料；7 家的集团口径不足以支持季度光学趋势判断，改进入事件监控层。后者仍持续收录官网产品、博客、合作、订单、产能和监管事件，但不制造低质量季度空槽。

- **季度层（13）**：Soitec、Sumitomo Electric、Furukawa Electric、POET、Sivers、Sanmina、Celestica、Mycronic、Oxford Instruments、VIAVI、ADTRAN、Wiwynn、Corning。
- **事件监控层（7）**：Mitsubishi Electric、Fujikura、ASE Technology、SUSS MicroTec、Samco、Keysight、Accton。
- **审计留痕**：20 家共保存 40 条两期 tier review；13 家共新增 52 个正式季度材料槽。分层只影响海外情报采集方式，不写入 canonical 点、边或供应关系。

| 角色 | 公司（属性） | 能力；cell/theme | 建议 | 理由与风险 | 官方来源 |
|---|---|---|---|---|---|
| 材料 | Soitec（Euronext Paris: SOI） | Photonics-SOI；`M1/C4`，T013/T017 | quarterly | SOI 是硅光底座；光子业务口径可能不独立 | [Photonics-SOI](https://www.soitec.com/home/products/product-platforms/photonics-soi) |
| 激光/FAU | Sumitomo Electric（TSE: 5802） | InP、112GBd EML、CW laser、FAU；`M1/C1/D9`，T006/T007/T013 | quarterly | 同时覆盖材料与光耦；集团太宽 | [FlexBeamGuidE](https://sumitomoelectric.com/products/FlexBeamGuidE-SC) |
| 激光/连接 | Furukawa Electric（TSE: 5801） | DFB、Nano-ITLA、MPO/MT、CPO ELS；`C1/C6/D9`，T013/T021 | quarterly | 产品链完整；需区分集团规划和外部订单 | [数据中心方案](https://www.furukawa.co.jp/en/solution/datacenter/index.html) |
| 激光 | Mitsubishi Electric（TSE: 6503） | EML、800G/1.6T/3.2T/CPO；`C1`，T006/T007/T011/T013 | quarterly | 直接观察 EML 产能；集团披露稀释 | [2026 EML 扩产](https://www.mitsubishielectric.com/en/pr/2026/pdf/0529_co5.pdf) |
| 光纤/连接 | Fujikura（TSE: 5803） | 光纤、连接器、数据中心产品；`M4/D9`，T019 | quarterly | 能观察被动互联约束；与高速光模块的收入归因有限 | [IR briefing](https://www.fujikura.co.jp/eng/ir/library/briefing/doc01.pdf) |
| 光引擎 | POET Technologies（NASDAQ: POET / TSXV: PTK） | 晶圆级光互连引擎；`D12/P1`，T010/T015/T017 | quarterly | 小公司信号纯度高；订单、出货和收入兑现风险高 | [Teralight](https://www.poet-technologies.com/products/poet-teralight) |
| 激光 | Sivers Semiconductors（Nasdaq Stockholm: SIVE） | DFB/CW 激光与光子器件；`C1`，T006/T013 | quarterly | 可观察新进入者；规模小、融资和量产风险 | [2025 年报](https://www.sivers-semiconductors.com/wp-content/uploads/2026/05/Sivers_annualreport_2025_2.pdf) |
| EMS | Sanmina（NASDAQ: SANM） | 光子设计、封装和制造；`EMS1/P1`，T002/T003/T015 | quarterly | 补足制造验证；光学收入通常不拆分 | [Optical](https://www.sanmina.com/solutions-contract-manufacturing-design/optical/) |
| EMS/系统 | Celestica（NYSE/TSX: CLS） | 通信系统设计制造；`EMS1/MOD1`，T002/T019 | quarterly | AI 网络制造敞口；官网对光学细分有限 | [Communications](https://www.celestica.com/our-expertise/markets/communications) |
| 封装 | ASE Technology（TWSE: 3711 / NYSE: ASX） | 硅光、FOPOP、光学实验室；`P1/EQ7`，T015/T017 | quarterly | 验证 OSAT 量产能力；技术展示不等于客户量产 | [Silicon Photonics](https://ase.aseglobal.com/silicon-photonics/) |
| 贴装 | Mycronic（Nasdaq Stockholm: MYCR） | 高精度 die bonding；`EQ3/EQ4`，T015 | quarterly | 设备侧验证封装节拍；光子收入未必拆分 | [Die Bonding](https://www.mycronic.com/product-areas/die-bonding/) |
| 键合 | SUSS MicroTec（Xetra: SMHN） | 永久键合；`EQ5`，T015 | quarterly | 覆盖异质集成；缺少光互联独立口径 | [Permanent Bonding](https://www.suss.com/en/products-solutions/bonding-solutions/permanent-bonding?languageChanged=en) |
| 刻蚀 | Oxford Instruments（LSE: OXIG） | InP 激光/探测器等离子工艺；`EQ2`，T007 | quarterly | 可交叉验证 InP 制造卡点；研究/量产场景混合 | [InP 工艺](https://plasma.oxinst.com/media-centre/wp/plasma-solutions-for-inp-lasers-and-photodiodes) |
| 刻蚀 | Samco（TSE: 6387） | InP 设备；`EQ2`，T007/T008 | quarterly | 日本设备补充；数据中心客户证据需核 | [InP equipment](https://www.samco.co.jp/whatsnew/products/2026/03/ExpandingLineupInPEquipment.php) |
| 测试 | Keysight（NYSE: KEYS） | 224G/1.6T 光网络验证；`EQ7`，T010/T019 | quarterly | 标准/测试进度领先于量产；测试新品不等于需求规模 | [1.6T validation](https://www.keysight.com/au/en/about/newsroom/news-releases/2026/0313-pr26-049-keysight-introduces-new-224g-test-solutions-to-enable-1-6t-optical-network-validation.html) |
| 测试 | VIAVI（NASDAQ: VIAV） | 1.6T OSFP 测试；`EQ7`，T010/T019 | quarterly | 可观察验证瓶颈；电信/无线业务稀释 | [ONE-1600ER](https://www.viavisolutions.com/en-us/products/one-1600er-osfp-1600gb-s-test-module) |
| 传输 | ADTRAN（NASDAQ: ADTN） | 800G 传输、可插拔相干光；`MOD2`，T021 | quarterly | 补齐运营商/边缘 DCI；与 AI 内部网络不同 | [800G transport](https://www.adtran.com/de-de/innovation/optical-networking/800g-optical-transport) |
| 交换/光学 | Accton（TWSE: 2345） | 800G LPO、光波长交换；`MOD1`，T014/T017/T019 | quarterly | ODM 端连接国内外供应链；产品展示与外部规模出货需分开 | [Optics](https://www.accton.com/optics/) |
| 服务器/互联 | Wiwynn（TWSE: 6669） | CPO 生态、高速互联；`MOD1`，T017/T019 | quarterly | 观察机柜级集成；客户口径和供应商归因有限 | [High-speed interconnect](https://www.wiwynn.com/technology/high-speed-interconnect) |
| 光纤/连接 | Corning（NYSE: GLW） | AI 数据中心光纤、连接和 CPO；`M4/D9`，T017/T019 | quarterly | 被动互联和布线密度重要；“AI”产品组合可能宽泛 | [GlassWorks AI](https://www.corning.com/optical-communications/worldwide/en/home/solutions/glassworks-ai.html) |

## 长尾：34 家（watch entity / discovery queue）

长尾已按证据用途完成分流：24 家具有可靠第一方入口、但不适合承担季度完整性义务，进入事件监控层；10 家仍留在发现队列，等待至少两期正式材料复核，不用产品页冒充季度经营证据。

- **事件监控（24）**：Freiberger、NTT Innovative Devices、Fujitsu Optical Components、OpenLight、Sicoya、SCINTIL、Xscape、Avicena、Ayar Labs、Lightmatter、Ranovus、Source Photonics、Molex、SENKO、Teramount、ficonTEC、PI、EV Group、EXFO、Alphabet、Microsoft、Amazon、Oracle、AMD。
- **发现队列（10）**：Hamamatsu、Microchip、Lightwave Logic、Smartoptics、Amkor、Delta Electronics、TE Connectivity、Ribbon、Ekinops、HPE。它们不是被否定，只是现阶段不能证明“季度材料里的光学信号密度”足以支持正式覆盖。

| 角色 | 公司（属性；总部/制造未核即不写） | 能力与映射 | 建议；核心风险 | 官方来源 |
|---|---|---|---|---|
| 光电子 | Hamamatsu（TSE: 6965） | InGaAs photodiode；`C3` | discovery；数据中心收入不透明 | [官方技术页](https://www.hamamatsu.com/eu/en/news/featured-products_and_technologies/2024/meeting-optical-communication-demands.html) |
| 材料 | Freiberger Compound Materials（私企） | GaAs/InP wafer；`M1` | watch；无季度义务、产能证据有限 | [Technology](https://freiberger.com/en/technology/) |
| 子公司 | NTT Innovative Devices（NTT 子公司） | 800G/1.2T coherent DSP；`C5/C6` | watch；只跟产品/合作事件 | [DSP](https://www.ntt-innovative-devices.com/en/optical_communications/dsp_products.html) |
| 子公司 | Fujitsu Optical Components（Fujitsu 子公司） | 相干收发器、调制器/接收器；`C6/MOD2` | watch；母公司季度材料难归因 | [Product line](https://www.fujitsu.com/jp/group/foc/imagesgig5/FOC%20Product%20Line-up_20201202.pdf) |
| 芯片 | Microchip（NASDAQ: MCHP） | 高速 Ethernet PHY；`C5` | discovery；光学特异性低 | [META-DX](https://www.microchip.com/en-us/products/high-speed-networking-and-video/ethernet/ethernet-phys/meta-dx-family) |
| 调制材料 | Lightwave Logic（NASDAQ: LWLG） | 电光聚合物调制器；`M3/C4` | discovery；商业化/收入风险高 | [官网](https://www.lightwavelogic.com/) |
| SiPh | OpenLight（私企） | 带集成激光的硅光平台；`C1/C4` | watch；合作/PDK/量产事件，不补四季 | [官网](https://openlightphotonics.com/) |
| SiPh | Sicoya（私企） | SiPh 芯片/收发组件；`C4/D12` | watch；客户与量产透明度低 | [Components](https://sicoya.com/en/silicon-photonic-components/) |
| SiPh | SCINTIL Photonics（私企） | 异质集成硅光；`C1/C4` | watch；融资与量产不确定 | [官网](https://www.scintil-photonics.com/) |
| 光引擎 | Xscape Photonics（私企） | FalconX 多波长光引擎；`D12/C4` | watch；路线新、客户采用待证 | [FalconX](https://www.xscapephotonics.com/falconx) |
| 新型互联 | Avicena（私企） | microLED 光互联；`D12` | watch；非主流路线、量产待证 | [Eval kit](https://avicena.tech/avicena-launches-the-worlds-first-microled-optical-interconnect-eval-kit/) |
| 光 I/O | Ayar Labs（私企） | UCIe optical chiplet、外置光源；`C4/D12` | watch；不补四季，只跟样片/客户/产能 | [UCIe chiplet](https://ayarlabs.com/news/ayar-labs-unveils-worlds-first-ucie-optical-chiplet-for-ai-scale-up-architectures/) |
| 光 I/O | Lightmatter（私企） | Passage NPO/OBO 光引擎；`D12` | watch；路线/商业采用风险 | [Passage](https://lightmatter.co/products/passage) |
| CPO | Ranovus（私企） | Odin CPO；`D12` | watch；合作演示与量产需区分 | [CPO 3.0](https://ranovus.com/wp-content/uploads/2024/03/Ranovus-CPO-3.0-MediaTek-announcement-March-20-2024-Final.pdf) |
| 模块 | Source Photonics（私企） | 800G/1.6T PAM4 module；`MOD1` | watch；无连续财报，跟产品/产能事件 | [1.6T/800G](https://www.sourcephotonics.com/news/source-photonics-announce-the-product-availability-of-its-200g-per-lane-based-1-6t-and-800g-pam4-transceiver-family-products-at-ofc25/) |
| 模块 | Smartoptics（Oslo: SMOP） | OSFP/transponder；`MOD1/MOD2` | discovery；规模小、AI 暴露需核 | [OSFP](https://smartoptics.com/products/optical-transceivers/osfp/) |
| OSAT | Amkor（NASDAQ: AMKR） | 光子/光学封装能力；`P1` | discovery；现有官网证据较泛 | [Technology](https://amkor.com/technology/) |
| 系统/模块 | Delta Electronics（TWSE: 2308） | COBO 12.8T、800G PoC；`MOD1/D12` | discovery；旧演示不能证明当前量产 | [COBO PoC](https://landing.deltaww.com/en-US/news/12998) |
| 连接 | TE Connectivity（NYSE: TEL） | 数据中心/CPO 连接；`D9` | discovery；光互联收入难分拆 | [OFC 2026](https://www.te.com/en/about-te/news-center/te-ofc-2026.html) |
| 连接/OCS | Molex（Koch 私有子公司） | CPO 连接、光路交换；`D9`，T014/T017 | watch；不补四季，只跟新品/并购 | [Optical architecture](https://www.molex.com/en-us/news/molex-accelerates-ai-cluster-deployment-with-one-stop-optical-interconnect-architecture-and-debut-of-high-radix-optical-circuit-switch-platform) |
| 连接 | SENKO（私企） | MPC/高密度连接；`D9` | watch；无季度材料 | [MPC](https://www.senko.com/mpc-series/) |
| 光耦 | Teramount（私企/并购标的） | PhotonicPlug；`D9/P1` | watch；并购状态及量产需复核 | [Molex 收购协议](https://www.molex.com/en-us/news/agreement-to-acquire-teramount-to-accelerate-scalable-co-packaged-optics-adoption) |
| 对准设备 | ficonTEC（私企） | 光子装配/测试自动化；`EQ3/EQ4/EQ7` | watch；无季度义务 | [官网](https://www.ficontec.com/) |
| 对准设备 | PI（私企） | 光子对准；`EQ4` | watch；订单应用不可分 | [Alignment](https://www.pi-usa.us/en/products/photonics-alignment-solutions) |
| 键合设备 | EV Group（私企） | die-to-wafer bonding；`EQ5` | watch；应用横跨多行业 | [D2W white paper](https://www.evgroup.com/fileadmin/media/products/bonding/Die_to_Wafer_bonding_systems/White_Paper_D2W_Bonding.pdf) |
| 测试 | EXFO（私企） | 800G Ethernet lab/manufacturing test；`EQ7` | watch；电信测试与 AI 内部互联需区分 | [FTBx-88800](https://www.exfo.com/en/products/lab-manufacturing-testing/network-protocol-testing/ethernet-testing/ftbx-88800-series/) |
| 传输 | Ribbon Communications（NASDAQ: RBBN） | IP optical networking；`MOD2` | discovery；AI 光互联信号偏弱 | [IP Optical](https://ribboncommunications.com/solutions/service-provider-solutions/ip-optical/ribbons-automated-ip-routing-and-optical-networking) |
| 传输 | Ekinops（Euronext Paris: EKI） | 400G coherent module/system；`MOD2` | discovery；规模及 AI DCI 归因有限 | [400G 官方资料](https://www.ekinops.com/images/press-releases/24.01.2023-PM400FR05-C2A_PR_ENG.pdf) |
| 网络系统 | Hewlett Packard Enterprise（NYSE: HPE；含 Juniper） | 800G DCI/1.6T-ready；`MOD1/MOD2` | discovery；并购后口径与光学归因复杂 | [DCI](https://www.hpe.com/us/en/juniper-data-center-interconnect.html) |
| 云客户 | Alphabet（NASDAQ: GOOGL/GOOG） | 高带宽光网络需求；T019/T020 | watch；客户需求信号，不补四季光学槽 | [官方投资者活动](https://abc.xyz/investor/events/event-details/2025/Thomas-Kurian-CEO-of-Google-Cloud-at-the-Goldman-Sachs-Communacopia--Technology-Conference-on-September-9-2025Thomas-Kurian-CEO-of-Google-Cloud-at-the-Goldman-Sachs-Communacopia--Technology-Conference-on-September-9-2025/default.aspx) |
| 云客户 | Microsoft（NASDAQ: MSFT） | AI 数据中心 capex/容量；T020 | watch；不能把 capex 直接换算成光模块 | [FY26 Q3](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3) |
| 云客户 | Amazon（NASDAQ: AMZN） | AWS AI 基建需求；T020 | watch；光学细节通常缺失 | [Q1 2026](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-First-Quarter-Results/) |
| 云客户 | Oracle（NYSE: ORCL） | OCI 容量/数据中心；T020 | watch；订单与光模块消耗非一一对应 | [FY26 results](https://investor.oracle.com/investor-news/news-details/2026/Oracle-Announces-Record-Q4-and-FY-2026-Results-Driven-by-Cloud-Infrastructure--Cloud-Applications/) |
| 计算平台 | AMD（NASDAQ: AMD） | rack-scale AI platform；T018/T019 | watch；平台发布不证明具体光学 BOM | [Helios](https://ir.amd.com/news-events/press-releases/detail/1261/amd-showcases-helios-rack-scale-platform-built-on-the-open-compute-project-open-rack-for-ai-introduced-by-meta) |

## 不应强制四季度的主体

1. **私企/集团子公司**：Freiberger、OpenLight、Sicoya、SCINTIL、Xscape、Avicena、Ayar Labs、Lightmatter、Ranovus、Source Photonics、Molex、SENKO、Teramount、ficonTEC、PI、EVG、EXFO、NTT Innovative Devices、Fujitsu Optical Components。它们适合按产品发布、融资、合作、量产、并购和客户验证触发抓取。
2. **客户/平台方**：Alphabet、Microsoft、Amazon、Oracle、AMD。只把其中明确指向光网络、速率、拓扑、容量或功耗的材料做事件证据；一般 AI capex 不能自动映射到 `MOD1`。
3. **监管者/标准组织/研究机构**：BIS、欧盟/日本监管者、IEEE 802.3、OIF、OCP、OCI MSA、imec 等应作为 policy/standard/research watch source，不是 company universe。它们没有“公司季度”，也不应产生缺失告警。

## 批次与数量

| 批次 | 数量 | 动作 |
|---|---:|---|
| 第一批 | 10 | 先建立四期正式材料；逐条抽取产品、产能、验证和限制声明 |
| 第二批 | 20 | 已完成两期复核：13 家进入季度层，7 家进入事件监控层 |
| 长尾 | 34 | 已分流：24 家事件监控，10 家保留发现队列；不制造四季度空槽 |
| 合计 | **64** | 不含当前 14 家与既有 IQE、DustPhotonics |

## 第一批 10 家：最近四个可得季度正式材料清单

说明：`official earnings release/webcast` 是允许的 equivalent material；只有官网明确提供 transcript 才标 transcript。下表已逐项改为公司 IR、SEC、交易所披露或公司正式报告的直接 URL。`unavailable` 表示截至本轮核验只找到结果发布预告、未找到已发布的结果/回放/监管文件，预告不能冒充季度材料。

| 公司 | period | period_end | published_date | material_type | 官方/监管 URL | 完整性 |
|---|---|---|---|---|---|---|
| AXT | 2026Q2 | unavailable（预告未披露 period_end） | unavailable | unavailable | [仅有 2026-07-02 的结果发布预告](https://investors.axt.com/Investors/news/news-details/2026/AXT-Inc--Schedules-Second-Quarter-2026-Earnings-Release-for-July-30-2026/default.aspx) | **缺口**：官方季度页仍显示 Q2 material not available；预定 7 月 30 日发布不等于实际发布 |
| AXT | 2026Q1 | 2026-03-31 | 2026-04-30 | earnings release + call/webcast | [直接材料](https://investors.axt.com/Investors/news/news-details/2026/AXT-Inc--Announces-First-Quarter-2026-Financial-Results/default.aspx) | 已核 |
| AXT | 2025Q4 | 2025-12-31 | 2026-02-19 | earnings release + webcast | [直接材料](https://investors.axt.com/Investors/news/news-details/2026/AXT-Inc--Announces-Fourth-Quarter-and-Fiscal-Year-2025-Financial-Results/default.aspx) | 已核 |
| AXT | 2025Q3 | 2025-09-30 | 2025-10-30 | earnings release + webcast | [直接材料](https://investors.axt.com/Investors/news/news-details/2025/AXT-Inc--Announces-Third-Quarter-2025-Financial-Results/default.aspx) | 已核 |
| GlobalFoundries | 2026Q2 | 2026-06-30 | 2026-08-05 | earnings release + webcast/presentation + 6-K | [直接材料](https://investors.gf.com/news-releases/news-release-details/globalfoundries-reports-second-quarter-2026-financial-results) | 已核；同日 6-K 亦已进入 SEC |
| GlobalFoundries | 2026Q1 | 2026-03-31 | 2026-05-05 | earnings release + webcast/presentation + 6-K | [直接材料](https://investors.gf.com/news-releases/news-release-details/globalfoundries-reports-first-quarter-2026-financial-results) | 已核 |
| GlobalFoundries | 2025Q4 | 2025-12-31 | 2026-02-11 | earnings release + webcast/presentation + 20-F | [直接材料](https://investors.gf.com/news-releases/news-release-details/globalfoundries-reports-fourth-quarter-2025-and-fiscal-year-2025) | 已核 |
| GlobalFoundries | 2025Q3 | 2025-09-30 | 2025-11-12 | earnings release + webcast/presentation + 6-K | [直接材料](https://investors.gf.com/news-releases/news-release-details/globalfoundries-reports-third-quarter-2025-financial-results) | 已核 |
| Tower | 2026Q1 | 2026-03-31 | 2026-05-13 | release + webcast + slides + official transcript | [直接材料](https://ir.towersemi.com/news-releases/news-release-details/tower-semiconductor-reports-first-quarter-2026-financial-results/) | 已核 |
| Tower | 2025Q4 | 2025-12-31 | 2026-02-11 | release + webcast + slides + official transcript | [直接材料](https://ir.towersemi.com/news-releases/news-release-details/tower-semiconductor-reports-record-revenue-fourth-quarter-2025) | 已核 |
| Tower | 2025Q3 | 2025-09-30 | 2025-11-10 | release + webcast + slides + official transcript | [直接材料](https://ir.towersemi.com/news-releases/news-release-details/tower-semiconductor-reports-third-quarter-2025-financial-results/) | 已核 |
| Tower | 2025Q2 | 2025-06-30 | 2025-08-04 | release + webcast + slides + official transcript | [直接材料](https://ir.towersemi.com/news-releases/news-release-details/tower-semiconductor-reports-2025-second-quarter-financial) | 已核 |
| Semtech | FY2027Q1 | 2026-04-26 | 2026-05-26 | earnings release + audio webcast/supplement | [直接材料](https://investors.semtech.com/news/semtech-announces-first-quarter-of-fiscal-year-2027-results/0634b869-19f6-4e90-9a0b-110fecf1d2db) | 已核 |
| Semtech | FY2026Q4 | 2026-01-25 | 2026-03-16 | earnings release + audio webcast/supplement | [直接材料](https://investors.semtech.com/news/semtech-announces-fourth-quarter-and-fiscal-year-2026-results/21cc5cf3-f51f-4f27-88d7-4023516e7840) | 已核 |
| Semtech | FY2026Q3 | 2025-10-26 | 2025-11-24 | earnings release + webcast/supplement | [直接材料](https://investors.semtech.com/news/semtech-announces-third-quarter-of-fiscal-year-2026-results/a5b07929-dc1c-49f7-863e-86ffe4ca3353) | 已核 |
| Semtech | FY2026Q2 | 2025-07-27 | 2025-08-25 | earnings release + webcast/supplement | [直接材料](https://investors.semtech.com/news/semtech-announces-second-quarter-of-fiscal-year-2026-results/9b5409e6-9a96-4810-a932-6b86fd42b9c5) | 已核 |
| MaxLinear | 2026Q2 | 2026-06-30 | 2026-07-23 | earnings release + earnings webcast/presentation + 10-Q | [直接材料](https://investors.maxlinear.com/press-releases/detail/617/maxlinear-inc-announces-second-quarter-2026-financial) | 已核 |
| MaxLinear | 2026Q1 | 2026-03-31 | 2026-04-23 | earnings release + earnings webcast/presentation + 10-Q | [直接材料](https://investors.maxlinear.com/press-releases/detail/607/maxlinear-inc-announces-first-quarter-2026-financial) | 已核 |
| MaxLinear | 2025Q4 | 2025-12-31 | 2026-01-29 | earnings release + webcast/presentation + 10-K | [SEC/公司 IR 直接附件](https://investors.maxlinear.com/all-sec-filings/content/0001288469-26-000009/a12312025exhibit991.htm) | 已核 |
| MaxLinear | 2025Q3 | 2025-09-30 | 2025-10-23 | earnings release + earnings webcast | [直接材料](https://investors.maxlinear.com/press-releases/detail/588/maxlinear-inc-announces-third-quarter-2025-financial) | 已核 |
| Jabil | FY2026Q3 | 2026-05-31 | 2026-06-17 | release + presentation + webcast + official transcript | [直接材料](https://investors.jabil.com/news/news-details/2026/Jabil-Posts-Third-Quarter-Results/default.aspx) | 已核 |
| Jabil | FY2026Q2 | 2026-02-28 | 2026-03-18 | release + presentation + webcast + official transcript | [直接材料](https://investors.jabil.com/news/news-details/2026/Jabil-Posts-Second-Quarter-Results/default.aspx) | 已核 |
| Jabil | FY2026Q1 | 2025-11-30 | 2025-12-17 | release + presentation + webcast + official transcript | [直接材料](https://investors.jabil.com/news/news-details/2025/Jabil-Posts-First-Quarter-Results/default.aspx) | 已核 |
| Jabil | FY2025Q4 | 2025-08-31 | 2025-09-25 | release + presentation + webcast + official transcript | [直接材料](https://investors.jabil.com/news/news-details/2025/Jabil-Posts-Fourth-Quarter-and-Fiscal-Year-2025-Results/default.aspx) | 已核 |
| Veeco | 2026Q2 | 2026-06-30 | 2026-08-05 | SEC 10-Q regulatory filing | [SEC 直接文件](https://www.sec.gov/Archives/edgar/data/103145/000110465926091158/veco-20260630x10q.htm) | 已核；官网仍只展示发布预告，因此不伪装成 earnings release/transcript |
| Veeco | 2026Q1 | 2026-03-31 | 2026-05-05 | earnings release + conference call/webcast | [直接材料](https://ir.veeco.com/news-and-events/news-details/2026/Veeco-Reports-First-Quarter-2026-Financial-Results/default.aspx) | 已核 |
| Veeco | 2025Q4 | 2025-12-31 | 2026-02-25 | earnings release + conference call/webcast | [直接材料](https://ir.veeco.com/news-and-events/news-details/2026/Veeco-Reports-Fourth-Quarter-and-Fiscal-Year-2025-Financial-Results/default.aspx) | 已核 |
| Veeco | 2025Q3 | 2025-09-30 | 2025-11-05 | earnings release + conference call/webcast | [直接材料](https://ir.veeco.com/news-and-events/news-details/2025/Veeco-Reports-Third-Quarter-2025-Financial-Results/default.aspx) | 已核 |
| FormFactor | 2026Q2 | 2026-06-27（由 Q1 正式材料确认） | 2026-07-29 | official earnings webcast/event equivalent | [官方财报 webcast 事件页](https://investors.formfactor.com/events/event-details/formfactor-inc-second-quarter-2026-financial-results/) | 已核为 equivalent；未见 earnings release，不得标 transcript |
| FormFactor | 2026Q1 | 2026-03-28 | 2026-04-29 | earnings release + webcast/supporting materials | [直接材料](https://investors.formfactor.com/news-releases/news-release-details/formfactor-inc-reports-2026-first-quarter-results/) | 已核 |
| FormFactor | 2025Q4 | 2025-12-27 | 2026-02-04 | earnings release + webcast/supporting materials | [直接材料](https://investors.formfactor.com/news-releases/news-release-details/formfactor-inc-reports-2025-fourth-quarter-results) | 已核 |
| FormFactor | 2025Q3 | 2025-09-27 | 2025-10-29 | earnings release + webcast/supporting materials | [直接材料](https://investors.formfactor.com/news-releases/news-release-details/formfactor-inc-reports-2025-third-quarter-results) | 已核 |
| AIXTRON | 2026Q2/H1 | 2026-06-30 | 2026-07-30 | official half-year report/call equivalent | [正式报告 PDF](https://www.aixtron.com/investoren/publikationen/2026/englisch/Half-Year%20Group%20Financial%20Report_2026.pdf) | 已核 |
| AIXTRON | 2026Q1 | 2026-03-31 | 2026-04-30 | official quarterly group statement/call equivalent | [正式报告 PDF](https://www.aixtron.com/investoren/publikationen/2026/englisch/3-Months-Report-2026.pdf) | 已核 |
| AIXTRON | FY2025 | 2025-12-31 | 2026-02-26 | annual report + official analyst call | [正式年报 PDF](https://www.aixtron.com/investoren/publikationen/2025/en/Annual%20Report%202025.pdf) | 已核 |
| AIXTRON | 2025Q3/9M | 2025-09-30 | 2025-10-30 | official nine-month statement + analyst call | [正式报告 PDF](https://www.aixtron.com/investoren/publikationen/2025/en/9-Months-Report-2025.pdf) | 已核 |
| ASMPT | 2026Q2/H1 | 2026-06-30 | 2026-07-29 | official results press release | [正式结果 PDF](https://www.asmpt.com/site/assets/files/85463/asmpt_2026_q2_press_release.pdf) | 已核；本轮只确认 press release 直链，不标 transcript |
| ASMPT | 2026Q1 | 2026-03-31 | 2026-04-22 | HKEX/company official results announcement | [正式结果 PDF](https://www.asmpt.com/site/assets/files/85243/e0522_results_announcement_2026_q1.pdf) | 已核 |
| ASMPT | FY2025 | 2025-12-31 | 2026-03-04 | audited annual results announcement | [正式结果 PDF](https://www.asmpt.com/site/assets/files/84503/e0522_results_announcement_2025_q4.pdf) | 已核 |
| ASMPT | 2025Q3/9M | 2025-09-30 | 2025-10-28 | HKEX/company official results announcement | [正式结果 PDF](https://www.asmpt.com/site/assets/files/84017/e0522_results_announcement_2025_q3.pdf) | 已核 |

### 第一批：最近 90 天官网新闻/博客候选（2026-05-15 至 2026-08-13）

| 公司 | 日期 | 事件候选 | 映射/价值 | 官方来源 |
|---|---|---|---|---|
| AXT | 2026-07-29 | 与 Lumentum 签长期供应协议并锁定产能 | `M1`；T006/T007/T008；比未发布的 Q2 结果更直接 | [公司 IR 直接公告](https://investors.axt.com/Investors/news/news-details/2026/AXT-Inc--Announces-Long-Term-Supplier-Agreement-with-Lumentum/default.aspx) |
| GlobalFoundries | 2026-07-29 | 与美国商务部签署 3 亿美元硅光研发拟议资助 LOI | `C4/P1`；T013/T015/T017；LOI 不是最终拨款 | [公司 IR 直接公告](https://investors.gf.com/news-releases/news-release-details/globalfoundries-signs-letter-intent-us-department-commerce-300) |
| Tower | 2026-07-14 | 日本 300mm SiPho/SiGe/先进封装双轨扩产 | `C4/P1`；T013/T015/T017 | [公司 IR 直接公告](https://ir.towersemi.com/news-releases/news-release-details/tower-semiconductor-meti-support-announces-strategic-capacity) |
| Semtech | 2026-05-26 | FY27Q1，抽取 data-center design wins 与 200G/lane 进展 | `C5`；T010/T019 | [官方结果](https://investors.semtech.com/news/semtech-announces-first-quarter-of-fiscal-year-2027-results/0634b869-19f6-4e90-9a0b-110fecf1d2db) |
| MaxLinear | 2026-07-23 | Q2 结果与电话会，重点抽取 optical products / DSP / TIA 的量产和收入陈述 | `C5`；T010/T019；避免使用 4 月 30 日、已超 90 天窗口的 Washington 新闻 | [公司 IR 直接公告](https://investors.maxlinear.com/press-releases/detail/617/maxlinear-inc-announces-second-quarter-2026-financial) |
| Jabil | 2026-06-17 | FY26Q3：AI 基建收入上调，但只采明确光学/制造陈述 | `EMS1/MOD1`；防止把 AI 收入全算光模块 | [官方结果](https://investors.jabil.com/news/news-details/2026/Jabil-Posts-Third-Quarter-Results/default.aspx) |
| Veeco | 2026-06-11 | LUMINA+ MOCVD 获 Ennostar 量产资格 | `EQ1`；T007/T008；官方材料同时说明应用横跨显示、光通信等，不能全归因 AI 光互联 | [公司 IR 直接公告](https://ir.veeco.com/news-and-events/news-details/2026/Ennostar-Qualifies-Veecos-New-LUMINA-MOCVD-System-for-Advanced-Product-Applications/default.aspx) |
| FormFactor | unavailable | 90 天内未找到明确指向 SiPh/CPO 的独立产品/订单新闻 | 7 月 28 日 Keystone Microtech 合作未明确指向光子，不强行纳入；5 月 11 日 Investor Day 已超窗口 4 天 | [公司新闻归档](https://investors.formfactor.com/press-releases) |
| AIXTRON | 2026-07-30 | H1 2026 正式报告，抽取 AsP/InP、datacom laser 和设备订单表述 | `EQ1`；T007/T008；正式报告比泛设备新闻更高价值 | [正式报告 PDF](https://www.aixtron.com/investoren/publikationen/2026/englisch/Half-Year%20Group%20Financial%20Report_2026.pdf) |
| ASMPT | 2026-07-29 | H1/Q2 2026 正式结果，抽取 photonics/CPO 封装与订单信号 | `EQ3/EQ4/EQ5`；T015/T017；财报中的 AI 订单不能自动全部归因光子 | [正式结果 PDF](https://www.asmpt.com/site/assets/files/85463/asmpt_2026_q2_press_release.pdf) |

## 证据限制与落库闸门

- 64 家候选均至少有一个第一方技术/IR入口，但这不代表所有 ticker、总部/制造地、季度发布日期已完成交易所级复核；表中“未核/待核”不得原样进入结构化账本。当前正式季度层共 37 家（原 14 家 + 首批 10 家 + 第二批 13 家）；第二批其余 7 家只进入事件监控。
- 第一批 40 个季度槽中，**39 个达到 period/period_end/published_date/官方直接材料 URL 可用的完整口径，1 个仍不可用**：AXT 2026Q2。截至核验只找到发布预告，未找到结果正文、监管附件或可确认的财报回放直链。GlobalFoundries 与 Veeco 的 Q2 文件已在 8 月 5 日发布，前者有公司 IR 正文与 SEC 6-K，后者可用 SEC 10-Q；FormFactor 2026Q2 只有官方 earnings webcast 事件页，按项目既定的 equivalent-material 口径计完整，但不得标成 earnings release 或 transcript。
- 公司官网的产品页和博客属于公司自述。对“量产、客户采用、订单规模、性能领先”等主张，仍需用财报/监管披露、客户材料或设备/供应链另一端交叉验证。
- 对日本/欧洲公司，半年报、九个月报告、年度报告可能是最稳定的正式材料；应标 `equivalent_material`，不能伪造成美式季度电话会 transcript。
- watch/discovery 的存在是为了提高信息召回，不降低 canonical 的证据门槛，也不自动生成行业结论。当前 64 家新增候选已经全部完成分层：23 家进入季度层、31 家进入事件监控层、10 家保留在发现队列。
