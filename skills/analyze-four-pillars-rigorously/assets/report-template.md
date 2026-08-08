# 八字排盘报告

> 性质：传统文化分析，不是经科学验证的人生预测。
> 计算状态：{{validation_status}}
> 预测验证状态：{{scientific_prediction_status}}

## A. 输入、时间标准与规则

- 记录时间：
- IANA 时区 / 历史偏移 / fold：
- UTC 时刻：
- 民用时 / 平太阳时 / 近似地方视太阳时：
- 经度修正 / 均时差 / 总修正：
- 年月日界、子时与起运规则：
- 年月柱比较：以候选 `absolute_utc` 直接比较冻结节气的绝对事件时刻；北京固定 UTC+8 仅用于现代中国农历 frame：
- Node 日历核心 SHA-256（`engine.node_core_sha256`）：
- 冻结历法数据 SHA-256（`engine.calendar_dataset.sha256`）：
- 核心自证哈希一致性：

## B. 时间归一化（L1A TIME）

列出原始输入、UTC、历史偏移、fold、经度和修正。

## C. 版本化历法结果（L1B CALENDAR）

先列出候选 `absolute_utc`、所比较的绝对节气事件时刻与事件时间基准，再列四柱。不得用北京历日替代绝对时刻来判断年柱或月柱。

| 年柱 | 月柱 | 日柱 | 时柱 |
| --- | --- | --- | --- |
|  |  |  |  |

### 历法边界证据（`summary.boundary_review`）

把三类条件分开披露；不得互相替代，也不得把 guard 描述为概率或置信区间。

| 类型 | 事件 / 边界 | 绝对事件时刻 | `delta_t_source_code` | `model_guard_seconds` | 影响与候选 |
| --- | --- | --- | --- | --- | --- |
| 调用方 `boundary_guard_seconds` |  |  | 不适用 | 不适用 |  |
| 冻结数据模型 guard |  |  |  |  |  |

#### HKO authority divergence

| 事件 / 日期 | 冻结模型结果 | HKO 发布表 oracle | 来源定位 | 对农历、四柱或起运的影响 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

若没有差异，明确写“本次未命中已登记的 HKO authority divergence”；若命中，完整保留返回的差异事实，不得用 HKO 表行静默覆盖冻结模型。

#### 农历边界不确定性

- 输入农历标签与 leap-month 状态：
- 固定北京 UTC+8 frame 的名义映射与 round-trip 状态：
- 新月起止边界、`delta_t_source_code` 与 `model_guard_seconds`：
- 是否可能跨越北京午夜：
- HKO authority divergence：
- 稳定失败关闭码：

若返回 `LUNAR_BOUNDARY_MODEL_GUARD` 或 `HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE`，在此停止唯一排盘：不得选择唯一公历日期、唯一四柱或唯一传统解释。仅报告未决证据和所需的独立权威复核。

## D. 版本化传统映射（L1C TRAD-MAP）

仅列出本次使用的藏干、十神、长生、纳音、子时或起运 provider；不要把它们称为天文事实。

## E. 条件候选与敏感性（U UNKNOWN）

| 候选 | 成立条件 | 四柱 | 起运 | 距离边界 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### 未认证敏感性带

仅列 `scenario_kind=sensitivity_bracket` 导致的变化，并明确它是假设修正偏移后的反事实检查，不是有效输入候选或概率区间。

## F. 注册规则传统解释（L2 INTERPRET）

| 结论 | 前提 | 规则 ID | 典籍位置 | 适用候选 | 冲突流派 |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## G. 普通版说明

用直白语言解释 D，但保持相同事实、条件和限制。

## H. 现实反思与低风险行动（L3 REFLECT）

- 可验证的现实问题：
- 可逆的小行动：
- 复盘时间与标准：

## I. 未知、限制与不采用的判断

- 缺失或歧义：
- `summary.boundary_review` 中尚未独立认证的计算边界：
- 数据集 / 核心哈希与自证状态：
- 事件 `delta_t_source_code` / `model_guard_seconds`：
- HKO authority divergence 与农历边界不确定性：
- 传统方法之间的冲突：
- 因证据不足而未输出的判断：
