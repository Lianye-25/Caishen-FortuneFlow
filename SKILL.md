---
name: caishen-intent-parser
description: 当用户通过小智语音通道输入中文自然语言指令时触发。解析 财神上下左右方向（上报/委派/存档/Agent分派/中枢），提取目标联系人和内容负载，输出结构化 JSON。触发短语包括：向上汇报、向下分派、委派给、存档、标记完成、归档、交给 Agent、AI处理、意图解析、分析意图、语音指令解析、五维中枢、handsfree。
---

# 财神上下左右 — 意图解析器

## 架构概述

本 Skill 实现 财神 五维方向中枢的意图解析层。系统接收来自小智机器人的中文语音文本，识别用户在五维方向上的意图，并将自然语言转化为结构化 JSON。

**五维方向定义**：

```
                    ┌──────────────┐
                    │   UP/上报     │
                    │  向上级汇报   │
                    ├──────────────┤
    ┌───────────┐   │   CENTER     │   ┌───────────┐
    │ LEFT/执行  │───│   中枢       │───│ RIGHT/配置 │
    │ 任务存档    │   │  意图接收    │   │ Agent分派  │
    └───────────┘   └──────┬───────┘   └───────────┘
                           ▼
                    ┌──────────────┐
                    │  DOWN/委派    │
                    │  向下属分派   │
                    └──────────────┘
```

**当前范围**：意图解析 + 消息分发。解析语音文本输出结构化 JSON，并可选择通过 `--dispatch` 标志自动执行邮件分发。微信通道预留接口。

## 首次设置（First-time Setup）

**重要：每次加载本 Skill 时，必须在处理任何用户语音指令之前，先执行以下配置检查流程。**

### 步骤 1：检测配置状态

读取 `assets/config.json`，逐项检查以下字段是否为占位符值（占位符表示用户尚未配置）：

| 字段路径 | 占位符值 | 含义 |
|---------|---------|------|
| `email.username` | `"your-email@qq.com"` | 邮件未配置 |
| `email.password` | `"your-smtp-auth-code"` | SMTP未配置 |
| `llm.api_key` | `"sk-xxx"` | LLM未配置 |
| `voice_call.stepone_api_key` | `"sk-xxx"` | 电话未配置 |

如果所有字段都不是占位符值且联系人已替换，则跳过设置流程，直接进入正常的意图解析模式。

### 步骤 2：引导配置（必填 — 邮件通道）

如果 `email.username` 或 `email.password` 为占位符值，**逐项**向用户询问（一次只问一个问题，等用户回复后再问下一个）。

**注意：邮箱不限于QQ邮箱，支持所有SMTP邮箱（QQ、Gmail、163、企业邮箱等），根据用户提供的邮箱地址自动判断 SMTP 服务器。**

**第 1 问：**
> 检测到 财神 邮件通道尚未配置。我将逐项引导你完成设置。
> 首先，请提供你的**邮箱地址**（将作为发件邮箱，用于发送汇报/委派邮件）：

**第 2 问**（用户回复第1问后）：

根据用户提供的邮箱地址自动判断 SMTP 配置：

| 邮箱域名 | smtp_server | smtp_port | 说明 |
|---------|-------------|-----------|------|
| `@qq.com` | smtp.qq.com | 587 | 需SMTP授权码（非登录密码） |
| `@gmail.com` | smtp.gmail.com | 587 | 需应用专用密码 |
| `@163.com` | smtp.163.com | 465 | 需客户端授权密码 |
| `@outlook.com` | smtp-mail.outlook.com | 587 | 需登录密码 |
| 其他 | 询问用户 | 询问用户 | 企业邮箱等 |

> 请提供此邮箱的 **SMTP 密码/授权码**。（注意：QQ邮箱需在「设置 → 账户 → POP3/SMTP服务」生成授权码；Gmail需生成应用专用密码；163邮箱需设置客户端授权密码。通常都不是邮箱登录密码。）

**第 3 问**（用户回复第2问后）：
> 邮件发件人的**显示名称**是什么？比如「财神上下左右」或你自己的名字。收件人会看到这个名称：

每获取一个回答立即写入 `assets/config.json` 对应字段：
- `email.username` ← 用户回答1
- `email.password` ← 用户回答2
- `email.from_name` ← 用户回答3
- `email.smtp_server` 和 `email.smtp_port` ← 根据邮箱域名按上表自动设置

### 步骤 3：引导配置（必填 — LLM API）

如果 `llm.api_key` 为占位符值，向用户询问：

> 接下来配置 AI Agent 的 LLM 后端。
> 请提供你的 **DeepSeek API Key**（可从 platform.deepseek.com 获取）。
> 默认使用 DeepSeek 官方接口，如果你用的是其他兼容 OpenAI API 的服务（如 Ollama 本地模型），请在 API Key 后面备注服务地址，例如：`sk-xxx | http://localhost:11434/v1`

收到用户回复后：
- 如果回复包含 `|` 分隔符 → 前半部分作为 `llm.api_key`，后半部分（去掉空格）作为 `llm.api_base`
- 如果回复不包含 `|` → 整段作为 `llm.api_key`，`llm.api_base` 保持默认 `https://api.deepseek.com/v1`
- 写入 `llm.api_key` 和 `llm.api_base`

### 步骤 4：引导配置（可选 — 企业微信通知）

检查 `config.json` 中 `channels.wechat` 段。如果 `enabled` 为 `false` 或配置值为占位符，向用户明确提供选择：

> 是否配置**企业微信通知**？开启后，你可以说「发消息给小莲下午三点开会」，系统会通过企业微信应用直接将任务卡片推送到员工的企业微信。
>
> 此功能需要在企业微信管理后台创建一个自建应用，获取以下信息：
> - 企业ID（corp_id）
> - 应用ID（agent_id）
> - 应用Secret
>
> 同时下属联系人需填写 `wechat_userid`（员工企业微信账号）。
>
> 请选择：
> - **添加** → 请提供上述三项信息
> - **跳过** → 暂不开启，后续需要时手动编辑 config.json

- 用户回复「添加」「开启」「需要」「好」等 → 依次询问 corp_id、agent_id、secret → 写入 `config.json` 的 `channels.wechat` 段，同时将 `enabled` 设为 `true`
- 用户回复「跳过」「不用」「暂不需要」等 → 保持 `enabled: false`，不修改其他字段

### 步骤 5：引导配置（可选 — 电话通知）

如果 `voice_call.stepone_api_key` 为占位符值，向用户明确提供选择：

> 是否添加**电话通知**功能？
> 开启后，你可以说「打电话告诉小莲下午开会」，系统会自动拨打对方电话用 AI 语音通知。
>
> 此功能需要 Stepone AI API Key 和 `stepone-call` CLI（资费约 ¥0.20/通）。
>
> 请选择：
> - **添加** → 请提供 Stepone API Key
> - **跳过** → 暂不开启，后续需要时手动编辑 config.json

- 用户回复「添加」「开启」「需要」「好」等肯定表述 → 追问 API Key → 写入 `voice_call.stepone_api_key`
- 用户回复「跳过」「不用」「暂不需要」等 → 不修改 `voice_call` 配置，`stepone_api_key` 保持占位符值，电话功能不可用

### 步骤 6：引导联系人设置

必填配置全部完成后，向用户说：

> 基本配置已完成。当前联系人列表包含的是**示例数据**（张总、李经理、小明等），建议替换为你的真实组织架构。是否现在设置？
>
> 你可以直接告诉我你的组织，例如：「我的上级是陈总，邮箱 chen@qq.com；下属有张三和李四，张三邮箱 zhangsan@qq.com……」
>
> 如果暂不设置，回复「跳过」，后续可手动编辑 `assets/contacts.json`。

- 用户回复「跳过」「稍后」「暂不」等 → 保留示例数据，提醒用户后续可编辑文件
- 用户提供了联系人信息 → 根据用户描述，解析并覆写 `assets/contacts.json` 的 `superiors` 和 `subordinates` 数组。每个联系人包含 `name`、`channels`（用户提供了邮箱则含 "email"）、`address`（用户提供的邮箱）。保留 `title` 字段为用户描述的角色（如"上级""下属"）。

`agents` 列表（代码审查Agent、文档润色Agent）是通用功能Agent，**无需替换**，保留即可。用户在使用中可通过语音动态创建新 Agent。

### 步骤 7：完成确认

全部设置完成后，向用户说：

> 财神上下左右配置完成！现在你可以通过语音使用以下功能：
>
> - 「向上汇报给 [上级名] [内容]」→ 自动发送汇报邮件
> - 「分派给 [下属名] [任务]」→ 自动发送委派邮件
> - 「交给 [Agent名] [任务]」→ AI Agent 后台执行并播报结果
> - 「存档这个结果」→ 任务归档
>
> 如需修改配置，可随时编辑 `assets/config.json` 和 `assets/contacts.json`。

### 已配置检测规则

如果步骤1中所有占位符字段已填入真实值（非占位符），则跳过步骤2-5。但仍需检查 `contacts.json` 中 `superiors`/`subordinates` 是否仍为示例数据（包含"张总""李经理""小明"等示例姓名）——如果仍是示例数据，执行步骤6提示用户替换。

如果全部已配置且联系人已替换为非示例数据，则不执行任何设置流程，直接进入意图解析模式。

## 解析流水线

按以下步骤处理每条输入：

### 1. 接收输入

获取原始中文文本。如果通过小智语音通道到达，已由 ASR 转写为文本，直接使用。

### 2. 加载联系人

读取 `assets/contacts.json`，加载上级（superiors）、下属（subordinates）、Agent（agents）三类联系人。文件不存在时使用空列表，解析不中断。

### 3. 检测方向

扫描输入文本，按以下方向关键词表匹配：

| 方向 | 中文关键词 | 匹配联系人 |
|------|-----------|-----------|
| UP (上报) | 上报, 汇报, 提交, 报告, 告诉, 通知, 呈报, 报给, 发给, 反馈给 | superiors |
| DOWN (委派) | 分派, 委派, 分配, 交给, 让, 安排, 派给, 下发, 布置, 叫 | subordinates |
| LEFT (存档) | 存档, 标记完成, 标记任务完成, 标记任务, 任务完成, 归档, 关闭任务, 标记为完成, 结束任务, 完成任务, 标记为 | 无 |
| RIGHT (Agent分派) | Agent处理, agent处理, AI处理, 智能处理, 机器处理, 自动处理 | agents |

**消歧规则**（按优先级）：

1. **"交给" 消歧**：如果关键词是 "交给"，检查后续目标名称：
   - 含 "Agent"/"agent"/"AI" → RIGHT
   - 在 agents 列表中找到 → RIGHT
   - 在 subordinates 列表中找到 → DOWN
   - 文本含 "Agent"/"AI" 字样 → RIGHT
   - 否则 → DOWN

2. **"完成" 消歧**：如果关键词是 "完成"：
   - 文本中在 "完成" 之前有委派关键词（"让""叫""交给"等）→ 主方向为 DOWN
   - "完成" 独立使用或后跟简短内容（≤10字）→ LEFT

3. **多方向歧义**：取最早出现的方向关键词。被覆盖的关键词记录在 `parse_metadata.ambiguities` 中。

未匹配任何方向关键词时，方向为 CENTER（中枢，信息查询/无明确意图）。

### 4. 提取目标

根据检测到的方向，在对应联系人列表中查找目标：
- 直接在关键词后的文本中搜索联系人名称
- 找到精确匹配 → 返回联系人信息，match_type="exact"
- 未找到 → 取关键词后2-4字符进行模糊匹配（容忍 ASR 同音字错误）
- LEFT/CENTER 方向不需要提取目标

### 5. 提取内容

从原始文本中剥离方向关键词和目标名称后，剩余部分即为内容。去除前导标点和空白。为空时置 null。

### 6. 计算置信度

```
confidence = (direction_score + target_score + content_score) / 3

direction_score: 精确关键词=0.9, CENTER默认=0.3
target_score: 精确匹配=0.9, 模糊=0.5, LEFT/CENTER=0.3, 无匹配=0.0
content_score: 有内容(>2字)=0.9, 短内容=0.6, 空=0.4
```

### 7. 输出 JSON

返回结构化结果。格式如下：

```json
{
  "direction": "UP",
  "direction_cn": "上报",
  "target": {
    "name": "张总",
    "title": "项目负责人",
    "channels": ["wechat", "email"],
    "address": "zhang@qq.com",
    "match_type": "exact",
    "candidates": ["张总", "王总监"]
  },
  "content": "今天的项目进展报告",
  "confidence": 0.85,
  "raw_input": "向上汇报给张总今天的项目进展",
  "parse_metadata": {
    "direction_keyword": "汇报",
    "target_keyword": "张总",
    "fuzzy_candidates": ["张总", "王总监"],
    "ambiguities": []
  },
  "timestamp": "2026-05-22T12:00:00+08:00"
}
```

## 消息分发

意图解析完成后，可通过分发引擎将消息实际发送给目标联系人。

### 方向与分发行为

| 方向 | 分发行为 | 说明 |
|------|---------|------|
| UP | 发邮件给上级 | 汇报邮件模板，含内容摘要和时间戳 |
| DOWN | 发邮件给下属 | 任务委派邮件模板 |
| RIGHT | 异步 Agent 执行 | 后台调用 LLM API，完成后小智播报结果 |
| LEFT | 不分发 | 纯本地任务状态管理 |
| CENTER | 不分发 | 信息查询无需分发 |

### 邮件配置

编辑 `assets/config.json`，填入 SMTP 信息：

```json
{
  "email": {
    "smtp_server": "smtp.qq.com",
    "smtp_port": 587,
    "use_tls": true,
    "username": "your-email@qq.com",
    "password": "your-smtp-auth-code",
    "from_name": "财神上下左右"
  }
}
```

> QQ 邮箱需使用 SMTP 授权码（非登录密码），在 QQ 邮箱设置 → 账户 → POP3/SMTP 服务中生成。

### 联系人通道要求

系统仅向同时满足以下条件的联系人发送邮件：
- 联系人 `channels` 列表中包含 `"email"`
- 联系人 `address` 字段填写了有效邮箱地址

无邮箱的联系人（如仅配置了微信通道）会被优雅跳过。

### Agent 异步执行与回调闭环

RIGHT 方向的任务会异步交给 AI Agent 后台执行，完成后小智机器人主动播报结果。

**执行流程**：
```
用户语音 → 解析为 RIGHT → 创建任务 → 后台 Agent 执行 → 完成
                                                          ↓
用户 ← 小智 TTS 播报结果 ← OpenClaw ← 轮询 task_status ←─┘
  ↓
用户决定下一步: "存档" / "汇报给张总" / "分派给小王修改"
```

**动态 Agent 创建**：
- 先在 `contacts.json` 的 agents 列表中匹配
- 匹配不到时，自动从文本中提取 Agent 名称动态创建
- 例如 "交给数据分析Agent分析这份报告" → 自动创建"数据分析Agent"
- 动态 Agent 的 match_type 标记为 "dynamic"

**LLM 配置**：
编辑 `assets/config.json`，在 `llm` 段填入 DeepSeek API 信息：
```json
{
  "llm": {
    "api_key": "sk-xxx",
    "api_base": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "max_tokens": 4096,
    "temperature": 0.7
  }
}
```

**任务状态查询**：
```bash
# 查询最近完成的任务（小智轮询用）
python scripts/task_status.py --latest-completed
# 查询执行中任务
python scripts/task_status.py --running
# 归档已完成任务
python scripts/task_status.py --archive task-20260525-001
```

**闭环操作**：
Agent 完成任务后，小智播报结果。用户听后可通过语音触发下一步：
- "存档这个结果" → LEFT 方向，任务归档
- "汇报给张总[结果内容]" → UP 方向，邮件转发给上级
- "分派给小王根据结果修改" → DOWN 方向，委派下属跟进

## 脚本调用

使用 `scripts/intent_parser.py` 进行命令行解析和分发：

```bash
# 仅意图解析
python scripts/intent_parser.py "向上汇报给张总今天的项目进展"

# 意图解析 + 自动分发
python scripts/intent_parser.py "向上汇报给张总今天的项目进展" --dispatch

# 指定配置路径
python scripts/intent_parser.py "分派给小明整理数据" --dispatch --config assets/config.json
```

也可独立使用分发引擎：

```bash
python scripts/dispatcher.py --intent result.json
```

参数：
- 第一个位置参数：待解析的中文文本（必需）
- `--contacts`：contacts.json 路径（可选，默认 `assets/contacts.json`）
- `--config`：config.json 路径（可选，默认 `assets/config.json`）
- `--dispatch`：解析完成后自动执行消息分发
- `--pretty`：美化 JSON 输出（默认开启）

输出：结构化 JSON 到 stdout（启用 `--dispatch` 时追加分发结果），退出码 0 表示成功。

## 边界情况处理

| 情况 | 处理方式 |
|------|---------|
| 空输入 | 返回 CENTER 方向，note="输入为空" |
| 无方向关键词 | 返回 CENTER 方向 |
| contacts.json 不存在 | 使用空列表，目标匹配跳过 |
| 目标名称不在联系人中 | target.match_type="none"，降低置信度 |
| 多个方向关键词 | 取最早出现者，其余记录到 ambiguities |
| ASR 同音字错误 | 模糊匹配容忍，match_type="fuzzy" |
| 纯英文/混合输入 | 按相同逻辑处理，关键词表含英文等价词 |

## 参考文件

- `references/five_dimensions.md` — 五维方向完整语义规范
- `references/examples.md` — 30+ 条测试用例及预期输出
- `assets/contacts.json` — 联系人模板（上级/下属/Agent）
- `assets/config.json` — SMTP 邮件 + LLM API 配置
- `assets/tasks.json` — 任务状态存储（自动生成）
- `scripts/dispatcher.py` — 消息分发引擎（邮件 + Agent）
- `scripts/task_manager.py` — 任务状态管理
- `scripts/agent_runner.py` — AI Agent 执行引擎
- `scripts/task_status.py` — 任务状态查询 CLI
