# 玄枢·严谨四柱（Xuanshu Four Pillars Skill）

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-engineering--regression--tested-orange.svg)](docs/VALIDATION.md)

一个面向 ChatGPT/Codex Agent Skills 规范的可审计四柱八字 Skill。它先用确定性脚本处理冻结历法事件表、冻结历史时区依赖、近似地方视太阳时、子时流派和大运，再让模型只在固定规则注册表范围内做明确标注的传统解释。

> 当前版本：`0.1.0`<br>
> 计算状态：`DEVELOPMENT_VALIDATED_NOT_INDEPENDENTLY_CERTIFIED`<br>
> 人生预测状态：`NOT_EMPIRICALLY_VALIDATED`

English summary: an auditable Four Pillars agent skill that separates frozen civil-time normalization, versioned calendrical mapping, explicit traditional providers, registry-constrained interpretation, and low-risk reflection.

## 为什么不是另一个“提示词算八字”

普通四柱 Skill 常让语言模型自己推日柱、猜节气、忽略历史时区，再用用户反馈反向调整解释。本项目把这些风险分成代码强制的计算校验与 Agent 必须遵循的行为契约：

- **Agent 契约**：不允许模型凭记忆排四柱；必须运行离线计算脚本。
- **代码强制**：要求 `tzdata==2026.3` / IANA `2026c`，支持 DST gap/fold，记录 TZif SHA-256；历法事件表和时区依赖缺少、哈希或版本不符时即停止。
- 年、月柱按同一绝对瞬间与冻结节气边界比较；近似地方视太阳时只影响日、时基准，并明确无独立误差界。
- 23:00 的两套版本化子时政策并行计算，分别公开日柱换日与时干锚定语义。
- 时间未知或处在区间时返回输入候选集合；区间扫描额外加入历史时区跳变点。近似视太阳时的 ±guard 反事实检查另标为 `sensitivity_bracket`，不混作有效输入候选或概率分布。
- 起运 provider 公式版本化；时间不确定时禁止输出一个伪精确的交运时刻。
- 输出分成 L1A 时间、L1B 版本化历法、L1C 传统映射、L2 注册规则解释、L3 低风险反思。
- **Agent 契约**：传统解释注册表当前为小范围实验功能；未登记规则必须省略，不能临时编造 `rule_id`。
- **Agent 契约**：禁止用“你说准了”作为模型验证或即时调参依据。

v0.1.0 尚未完成真实模型端到端遵循性评测。确定性脚本可以强制计算输入、候选集合和 manifest 身份；自然语言解释与高风险边界仍依赖 Skill 指令，不能被描述为已经由代码完全强制。

## 快速开始

运行时要求：Python 3.11+、Node.js 20+、`tzdata==2026.3`。冻结历法数据的再生成环境另需 Python 3.12+，见 [tools/README.md](tools/README.md)。

```bash
python -m pip install -r requirements.txt
python skills/analyze-four-pillars-rigorously/scripts/self_test.py
python skills/analyze-four-pillars-rigorously/scripts/four_pillars_engine.py \
  --input examples/basic-gregorian.json --pretty
```

本地 Codex 可把 `skills/analyze-four-pillars-rigorously` 复制到 `$HOME/.agents/skills/`，或作为仓库级 Skill 放到 `.agents/skills/`。ChatGPT/Codex 的当前 Skill 结构说明见 [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills)。

## 输入示例

```json
{
  "birth": {
    "calendar": "gregorian",
    "date": "1988-02-15",
    "time": "23:30:00",
    "timezone": "Asia/Shanghai"
  },
  "rules": {
    "time_basis": "civil_clock",
    "day_boundary": "both"
  }
}
```

详见 [输入契约](skills/analyze-four-pillars-rigorously/references/input-contract.md) 和 `examples/`。

## 引擎输出契约与 Agent 行为边界

引擎的结构化 JSON 会提供下列计算字段；按照 Skill 生成的自然语言报告应据此呈现，但当前尚无端到端模型遵循性认证：

1. 输入、UTC、历史偏移、fold、经度与时间修正；
2. 稳定四柱和条件候选；
3. 距离节气、子时或时辰边界的秒数，以及区间是否跨界；
4. 精确出生时间下的 provider 专属象征性交运时刻，或明确的阻断状态；
5. 仅来自固定注册表、带 `rule_id + premises + source revision` 的传统解释；
6. 有效输入候选与未认证敏感性带的分表；
7. 未知项、冲突流派和当前认证限制。

普通版和专业版可以使用不同语言，但底层计算事实必须完全相同。

## 准确性声明

本项目不宣称“算命准确 100 倍”。只有在 [FourPillarsBench-v1](skills/analyze-four-pillars-rigorously/references/evaluation-contract.md) 的冻结基准上，关键错误率比参考配置降低至少 100 倍，且置信区间门禁仍通过时，才允许做限定于该指标的比较声明。

离线回归与仓库发布门禁（实际通过数以当前 CI 记录为准）覆盖：

- 四柱 golden case；
- 农历转公历 golden case、跨时区农历闭环、农历重复时刻 fold 及闰月严格类型；
- 早子/晚子流派；
- DST 重复时间、不存在时间和历史 20 分钟短回拨；
- 同一 UTC 时刻跨时区的年月柱、同经度近似视太阳时不变性；
- 经度每增加 1°，平太阳时修正增加 4 分钟；
- 日柱逐日递进并在 60 日后复现；
- 区间网格取整、跨时辰提醒和不确定时间起运阻断；
- 时区路径穿越、未知规则、冲突字段和非法类型拒绝；
- 结果重复运行一致、冻结历法数据及规则/provider/provenance manifest 完整性与报告身份绑定；
- 示例可执行性、版本一致性、本地链接、生成物排除、来源哈希以及 CI Action 完整提交哈希。

v0.1 的公开公历输入范围为 1901-01-01 至 2033-12-31。农历标签年份包络为 1900–2033，但两端都只是部分年份：最早可接受名义标签是 1900 年十一月十一（非闰），最晚是 2033 年闰十一月初十；标签还必须唯一转换到公开公历范围内。1900–2034 日历帧和延伸至 2035-02-28 的事件仅用于端点上下文，不扩大公开输入范围。

仓库提供项目自有的 `tools/generate_calendar_data.py`；它在构建期用 Skyfield 1.54 与 JPL DE440s 生成事件，并结合 USNO `deltat.data`、`deltat.preds` 和 NASA 多项式处理时间尺度。JPL/USNO 输入由复现者按锁定 URL 和哈希在本地下载，不提交仓库，也不进入运行时。数据不保存 TT JD，而把 `TT − 冻结 Delta T` 记录为明确命名的 `unix_ms_ut1_proxy`，即以 Unix 毫秒编码的 UT1-as-UTC 比较代理；它不是未经限定的精确历史 UTC。

冻结数据采用 `xuanshu-calendar-data-v0.2`：节气行 `row[3]` 保存 Delta T 来源代码；农历月行 `row[8]` 保存来源代码、`row[9]` 保存 `uncertainty_flags`；农历不确定事件 `row[6]` 保存来源代码。生成器对新月与中气各自 guard 的候选北京日期做笛卡尔积检查；只要可能改变中气归月或闰月序列就拒绝冻结，要求先编码完整替代月序。

最终冻结数据的本地 HKO 日期级 oracle 复扫状态为 `PASS_WITH_DISCLOSED_DIVERGENCES`：覆盖 48,578 个公历日和 3,192 个节气，保留 90 个农历逐日差异（恰为 3 段连续 30 日）和 6 个节气北京日期差异，未发现其他差异。仓库不复制或分发 HKO 表格、行文本或完整数据集；冻结数据只保存这 9 条独立比较得到的非表达性差异事实（两侧日期、代码和来源 locator），以便运行时审计。HKO 不是历法数据的生成输入。

不确定性分三层记录，不能混称一个“误差”：用户 `boundary_guard_seconds` 是输入边界敏感性带；数据集每个事件的 `model_guard_seconds` 是 Delta T/时间尺度模型复核带；HKO authority divergence 是回溯天文模型与历书出版表的日期/约定差异。1973 年前事件采用保守 600 秒模型复核带；USNO 实测段约 2 秒；预测段为公开误差向上取整再加 2 秒；2033.75 后的内部 padding 使用连续情景且至少 10 秒，只是情景，不是官方预测或置信区间。现代事件距北京午夜 600 秒以内可以触发 review，但不能据此宣称其实际误差为 600 秒或一律判错。

若一个 Jie 的事件 model guard 可改变年/月柱，Node v0.2 会返回 `birth_before_term` 与 `birth_after_term` 两个 `calendar_model_variant`，并在 `solar_term_boundary_uncertainty` 中保留来源与 guard；两个受 guard 的 Jie 同时适用时以 `CALENDAR_BOUNDARY_UNRESOLVED` 失败关闭。农历边界不枚举完整替代月序：公历输入返回名义固定 UTC+8 农历值和 `boundary_uncertainty`，若 `unresolved_result_change_without_enumerated_variant=true` 则不得将该农历标签当作唯一前提；农历反向输入遇到适用的 model guard 或 HKO authority divergence 则失败关闭。

尚未完成的独立认证门禁包括使用独立于生成源的高精度星历进行差分、完整事件边界区间求解器和大规模传统规则库。因此版本仍是 development validated，而不是 independently certified；回归测试通过也不等于人生预测得到验证。构建复现流程见 [tools/README.md](tools/README.md)。

## 隐私与安全

- 默认不收集姓名、曾用名、详细住址、在世状态或历史事件。
- 不要在 Issue、PR、日志或测试 fixture 中提交真实出生资料。
- 不输出死亡、灾难、严重疾病、犯罪、出轨、生育或不可避免的不幸断言。
- 不用四柱解读代替医疗、法律、投资、婚姻、就业或生育决策。
- 传统解释属于文化与反思材料，不是经科学验证的因果预测。

详见 [SECURITY.md](SECURITY.md)。

## 仓库结构

```text
xuanshu-four-pillars-skill/
├── skills/analyze-four-pillars-rigorously/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── scripts/
│   ├── references/
│   └── assets/
├── examples/
├── tests/
├── docs/
└── .github/workflows/ci.yml
```

## 来源与许可证

本项目仅借鉴公开同类 Skill 的抽象目录思路，不复制其排盘规则和命理摘要。运行时历法与传统映射代码为项目实现，并读取冻结的 `calendar-1901-2033.json`。该数据在构建期由 Skyfield 1.54、JPL DE440s、USNO Delta T 记录/预测和 NASA Delta T 多项式生成；JPL 内核、Skyfield 和 HKO 表格/行文本均不随仓库分发。冻结数据只保留 9 条独立比较所得的 HKO 差异事实，不把 HKO 作为生成输入。

四个大运起运 provider 是项目代码对 `tyme4ts 1.5.2` MIT 实现所公开公式的独立重写；不再捆绑或运行 `tyme4ts` 二进制，但保留其许可证副本和明确归属。完整来源、哈希与分发边界见 [NOTICE](NOTICE) 和 [provenance-manifest.json](skills/analyze-four-pillars-rigorously/references/provenance-manifest.json)。

项目原创部分采用 [MIT License](LICENSE)。
