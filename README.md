# 光模块供应链图谱（点先行 v2）

一个账本，两个产品。数据只有一份（points.csv / edges.csv / triage.csv / corpus/_frozen.csv），md/html 都是渲染。

**产品① 全景图**（`out/全景.md` / `.html`，由 `render.py` 生成）
一棵光模块 BOM 树：39 个格子挂着做这件事的公司，每家带披露引语+锚+判定等级；格子间有流向骨架+已证边计数；空格是诚实结论不是缺陷。回答"这个环节有谁、谁供谁"。

**产品② 参与识别**（`out/参与识别.md` / `.csv` / `.html`，由 `participation.py` 生成）
公司级名单：宇宙内每家公司恰好一行，结论四态——已确认参与 / 待确认 / 尚未发现已过闸证据 / 未覆盖；"尚未发现"不等于否。回答"这家公司参与吗"。详细设计见 `refs/参与识别-MVP.md`。

## 日常怎么用（全流程）
1. 新年报/招股书 PDF 扔进 corpus/annual/<代码>/，在 corpus/_frozen.csv 记一行（带出处）
2. `python3 scan.py` —— 关键词召回待办清单（`ANY` 词只召回"是否参与"，不预判格子；自动跳过已处置项）
3. 判定闸会话：逐条判 入点/驳回/待判，写 points.csv 和 triage.csv，**会话末必跑 `python3 scan.py --check`**
4. `python3 render.py` 重建全景图；`python3 participation.py` 重建参与识别名单（`--check` 校验分母、证据闭合与幂等）
5. 你只看 git diff 点头/摇头；commit 信息带"产出: +N点 +M边 驳回K"

年报季提示：A股年报4月末集中披露；美股10-K财年后60-90天。
边界：语料宇宙见 corpus/_frozen.csv（每文件一行带出处）；archive/ 为旧结构冷冻区（默认禁读）。
