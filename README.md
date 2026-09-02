# 光模块产业结构与公司能力地图（点先行 v2）

canonical 一个账本，四个读者产品 + 一层知识。前三个产品共用 tree.yaml / knowledge.yaml / points.csv / edges.csv / triage.csv / corpus/_frozen.csv；第四产品是只读引用 canonical 的独立情报层。md/html 都是渲染。

架构 = 本体层 + 事实与解释层 + 关系层 + 产品投影（三层一投影）：

| 层 | 文件 | 回答什么 | 举证要求 |
|---|---|---|---|
| 本体（骨架） | `tree.yaml` | 产业由哪些环节构成 | **纯骨架免锚**：只留 ID/名称/父子/粗粒度路线/流向/状态；机制性内容一律进 knowledge，格上只挂 `knowledge_ids` 引用；争议格标 `status: provisional` + `decision_ref` |
| 事实与解释 | `knowledge.yaml`（为什么）/ `points.csv`（谁在做）/ `macro_evidence.csv`（宏观数字A–D分级） | 这环节干嘛的、谁在做、数字可不可信 | 每条证据带**类型化锚**，不变量⑧⑨机器核验：`url` 须为链接 / `local_file` 须存在+页码章节 / `ledger_ref` 须指向真实点边 / `search_protocol` 负证据须记关键词+范围+日期+命中数——填"已核验"过不了闸 |
| 关系（观察） | `edges.csv` | 谁给谁供货（不参与结构判定） | 四件套 |
| 产品投影 | `route_bom.csv` | 具体路线（800G DR8/1.6T/400ZR）由什么组成 | IEEE/OIF 标准锚；每行须 `cell_ids` 映射回树或声明 `architecture_only`/`gap` 并说明——树不向产品代际扩张，投影层负责细粒度 |

编号约定：知识 `KN###`、宏观结论 `MC###`、路线BOM行 `RB###`；历史点/边保持 `P###`/`E###` 不迁移（向后兼容）。
依赖声明：Python 3 + **PyYAML**（render/scan 均用，正式锁定）+ `pdftotext`（poppler）。

本产品画的不是"谁给谁供货"，而是"产品如何被做出来，以及谁具备做各环节的能力"：结构骨架（tree.yaml）先于公司独立定义，公司按证据挂到结构节点上。北方华创挂在"MOCVD设备"、源杰挂在"激光器芯片"，**不因此声称北方华创向源杰供货**。供货关系只作为独立观察层存在（edges.csv 四件套），不参与结构完整性判定；空格不会因为没找到公司而从图中消失。

**产品① 结构×能力地图**（`out/全景.md` / `.html`，由 `render.py` 生成）
一棵光模块 BOM 树：39 个格子挂着做这件事的公司，每家带披露引语+锚+判定等级+生产状态；空格显式渲染为研究缺口，是诚实结论不是缺陷。流向骨架（常识层免锚）+已证边计数作为观察层叠加。回答"产业由哪些环节组成、不同路线异同、每个环节有谁在做、证据是什么"；不回答"A 是不是 B 的供应商"。

**产品② 参与识别**（`out/参与识别.md` / `.csv` / `.html`，由 `participation.py` 生成）
公司级名单：宇宙内每家公司恰好一行，结论四态——已确认参与 / 待确认 / 尚未发现已过闸证据 / 未覆盖；"尚未发现"不等于否。回答"这家公司参与吗"。详细设计见 `refs/参与识别-MVP.md`。

**产品③ 公司能力明细**（`capability_details.csv` / `output/pdf/光模块产业链公司能力明细.pdf` / WorkBuddy HTML，由 `build_detailed_capability_report.py` 生成）
以“公司 × 细分节点”为最小单元，把 `points.csv` 的已过闸证据标准化为具体产品、材料与技术、工艺能力、规格与应用、当前阶段和产业角色。PDF 与 HTML 使用同一份 `capability_details.csv`，未获披露支撑的字段显示“披露未细分”，不推断供货关系。

HTML 保持单一读者页面：`route_bom.csv` 提供 800G DR8 / 1.6T DR8 / 400ZR 的正交轴与 BOM；`macro_evidence.csv` 管理首页量化结论的 A-D 证据等级；`edges.csv` 中少量已验证实边叠加到公司能力卡。后台可以扩 schema 和校验器，但不另造读者页面。

**产品④ 海外电话会与官网技术情报**（`calls/*.csv` → `calls/out/`，由 `/Users/jowang/miniconda3/bin/python3 -m calls all` 生成）

独立管理海外同业/下游电话会、公司官网署名技术博客、技术演示、动态卡点、承诺兑现和国内能力潜在匹配。管理层商业陈述、分析师问题与公司技术作者陈述机械隔离；只生成候选验证链，不回写 canonical。`calls/out/panorama-intelligence.csv` 可选投影到 WorkBuddy HTML 的“海外电话会与官网技术情报”章节，缺失时安全跳过。

**知识库**（`knowledge.yaml` → `out/知识库.md` / `.html`，由 `render.py` 生成）
项目的"为什么"层。每条知识用不懂行的人能看懂的大白话写：一句话结论 + 说细点 + 怎么用它判断，
后面跟逐条证据（谁说的、原话、出处、锚）。没有证据的常识不进这里——不变量⑧会拦。
主格的知识摘要直接渲进全景图对应环节旁边，其余关联格只给一行指针。
例：K001 讲清共晶固晶机为什么光模块用的和显示屏用的差一个数量级（±1~3µm vs ±50µm），
并据此给出设备类公司的准入判断法；K002 讲清气密封装不是技术高低而是电信/数通两条路线的分野。

**研究问题树（主研究入口）**（`research_questions.yaml` → `out/研究问题树.md`，由 `render.py` 生成）
从“什么是光模块？”开始，按理解依赖逐层生长出一份稳定 ID 的研究导航，明确区分两套知识：
**物理知识体系**（系统功能→组件→接口→制造→设备）与**技术路线体系**（需求/约束→瓶颈→正交轴→路线画像→能力→公司能力群）。
两套体系之间不是第三棵树，而是一组 **Why 关联**（需求/瓶颈→工程选择→物理变化→公司能力），写入 `knowledge.yaml` 顶层 `why_links:`。
研究答案仍是可追加到 `knowledge.yaml` 的 KN 条目（物理/路线）；问题树只保存导航与回填合同，不保存事实答案。
路线能力群严格区分**候选能力群**（能力匹配，不是路线采用/供货证据）与**确认服务群**（须有路线级直接证据）。

> 研究问题树是主研究入口；`out/问题队列.md` 是后台**维护问题队列**（QA–QE 维护欠账），二者不是一回事，也不互相替代。

```bash
# 重建研究问题树（与全景图/知识库/问题队列一同生成）
/Users/jowang/miniconda3/bin/python3 render.py
# 校验输出未被手改（含 研究问题树.md）
/Users/jowang/miniconda3/bin/python3 render.py --verify
# 不变量①-⑭（含研究问题树 v2 校验）
/Users/jowang/miniconda3/bin/python3 scan.py --check
```
注意：所有 Python 命令统一用 Miniconda 解释器 `/Users/jowang/miniconda3/bin/python3`（自带 PyYAML），
不要用系统 `python3`，否则可能报 yaml 模块缺失。

## 日常怎么用（全流程）
1. 新年报/招股书 PDF 扔进 corpus/annual/<代码>/，在 corpus/_frozen.csv 记一行（带出处）
2. `/Users/jowang/miniconda3/bin/python3 scan.py` —— 关键词召回待办清单（`ANY` 词只召回"是否参与"，不预判格子；自动跳过已处置项）
3. 判定闸会话：逐条判 入点/驳回/待判，写 points.csv 和 triage.csv，**会话末必跑 `/Users/jowang/miniconda3/bin/python3 scan.py --check`**
4. 判定中若搞清了"这环节为什么难/怎么判够格"，写进 `knowledge.yaml`（须带证据引语+出处+锚）
5. `/Users/jowang/miniconda3/bin/python3 render.py` 重建全景图与知识库；`/Users/jowang/miniconda3/bin/python3 participation.py` 重建参与识别名单（`--check` 校验分母、证据闭合与幂等）
6. `/Users/jowang/miniconda3/bin/python3 build_detailed_capability_report.py` 重建公司能力明细 CSV、PDF 与合并版 HTML
7. 你只看 git diff 点头/摇头；commit 信息带"产出: +N点 +M边 空格A/B 驳回K"（空格数取 `render.py` 页脚，纪律第8条）

年报季提示：A股年报4月末集中披露；美股10-K财年后60-90天。
边界：语料宇宙见 corpus/_frozen.csv（每文件一行带出处）；archive/ 为旧结构冷冻区（默认禁读）。

## 国内日更镜像

`domestic_daily` 是 `corpus/_daily_update.py` 的隔离实现：它读取本仓库账本、`corpus/_frozen.csv`、`triage.csv`、`points.csv`、`_restart_watchlist.csv`、年报、IR 和 QA 作为只读输入，但绝不写入 `corpus/`、`tmp/daily/` 或 canonical 文件。输出根目录由调用方传入：

```bash
python3 -m domestic_daily run --source-root . --state-root /path/to/domestic-daily-state --date 2026-09-02
```

运行状态、投关表文本、QA 全量并集快照、日报和队列差分均写入 `state_root`。关注公司仍是“triage 待判 ∪ points 生产中/在建 ∪ 日更 watchlist”；投关表查询仍覆盖 `relation/category_dyhd_szdy` 与全文“投资者关系”，宇宙外只产生光通信补录候选；公告仍按原 `ANN_PAT` 过滤；QA 从 `2023-01-01` 请求并按 `index_id` 与既有源/镜像快照并集，只增不减。重启段是内容/标题机械匹配，不构成判定，QA 增量须人工过内容。月度重筛逐家公司执行，只报告差分、不改 `_frozen.csv`，401/token 失败记录后降级。

实现通过 state-root 锁、临时 staging 目录和原子替换保证重复运行幂等；网络由 `RequestsClient` 提供，互动问答直接在临时隔离根中复用原 `_fetch_qa.py` 的深交所、上证 e 互动、全景网兜底与熔断逻辑，测试使用 `FixtureClient`，不依赖公网。手工调度可在未来使用同一 CLI，例如 `30 18 * * * cd /repo && python3 -m domestic_daily run --source-root . --state-root /var/lib/domestic-daily --date $(date +\%F)`；本项目不会安装或启动 scheduler。离线测试：`python3 -m unittest discover -s tests -p 'test_domestic_daily.py'`。源基线扫描仍须单独运行 `python3 scan.py --check`；缺失 gitignored 年报文本时，其召回结果仅代表当前基线，不能视为完整语料覆盖。
