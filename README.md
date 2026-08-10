# 财神上下左右

> 语音加手势驱动的人机协同中枢

财神上下左右，是一套运行在 OpenClaw + 小智机器人上的语音加手势驱动分发系统。把日常管理代入方向感——向上汇报、向下委派、向左存档、向右交给AI、居中决策。说句话，指个方向，信息自动流向该去的地方。

```
                    ┌──────────────┐
                    │  ↑ UP 上报    │
                    │  向上级汇报    │
                    ├──────────────┤
    ┌───────────┐   │  ⊙ CENTER    │   ┌───────────┐
    │ ← LEFT    │───│   中枢决策     │───│ RIGHT →   │
    │  任务存档   │   │              │   │ Agent分派  │
    └───────────┘   └──────┬───────┘   └───────────┘
                           ▼
                    ┌──────────────┐
                    │  ↓ DOWN 委派  │
                    │  向下属分派    │
                    └──────────────┘
```

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **语音意图解析** | 中文语音文本 → 结构化意图 JSON（方向+目标+内容+置信度） |
| **手势识别** | 小智Pro手势识别，支持「手势选人 → 语音说事」二段式交互 |
| **多通道分发** | 邮件（SMTP）、企业微信（应用消息）、电话（Stepone AI） |
| **AI Agent 执行** | DeepSeek API 驱动，后台子进程异步执行 |
| **电话通知** | notify（通知）/ inquiry（询问）双模式，角色模板约束 AI 行为 |
| **任务管理** | 完整生命周期：创建 → 执行 → 完成 → 归档 |

---

## 功能全景

财神上下左右将你的管理动作抽象为五个方向，每句话系统自动找到对应的人、走对应的通道、执行对应的操作。下面以配置好的联系人为例，展示实际效果。

### ↑ 上报 — 把结果推给上级

可以向不同的上级汇报，每人可以走不同的通道。具体有哪些上级、每人用什么通道，在 `contacts.json` 里自己设定。

**举例**（假设配置了以下上级）：

| 上级 | 说什么 | 走什么通道 | 对方收到什么 |
|------|--------|-----------|------------|
| 张总 | "汇报给张总项目第一阶段已完成" | 邮件 + 企业微信 | HTML汇报邮件 + 企微卡片消息 |
| 李经理 | "发微信告诉李经理周报已提交" | 仅企业微信 | 企微卡片："汇报 — 财神，周报已提交" |
| 王总监 | "发邮件通知王总监明天上午汇报" | 仅邮件 | HTML汇报邮件 |

可用的三种通道：**邮件**（SMTP，支持QQ/Gmail/163/企业邮箱）、**企业微信**（应用消息，推送到员工企微）、**电话**（Stepone AI拨打，接通后语音告知）。

### ↓ 委派 — 把任务分给下属

同样，下属是谁、每人用什么方式接收，在 `contacts.json` 里设定。框架支持三种通道，给每个下属自由组合。

**举例**（假设配置了以下下属）：

| 下属 | 配置的通道 | 说什么 | 实际效果 |
|------|-----------|--------|---------|
| 小王 | 企业微信 | "发消息给小王下午3点开会" | 小王企微收到任务卡片 |
| 小明 | 邮件 + 企业微信 | "分派给小明整理会议纪要" | 同时收到邮件 + 企微卡片 |
| 小莲 | 邮件 + 电话 + 企业微信 | "打电话告诉小莲下午3点开会" | 小莲手机响起，AI语音通知 |
| 小莲 | 同上 | "打电话询问小莲明天能否参会" | AI拨打→询问→听取答复→复述确认 |

三种通道的实际表现：

| 通道 | 对方怎么收到 | 适用场景 |
|------|------------|---------|
| 邮件 | 格式化HTML邮件，标题区分"汇报"或"任务委派"，正文包含内容和时间戳 | 正式通知、需要留痕的任务 |
| 企业微信 | 企业微信弹出卡片消息，标题"任务委派 — 财神"，正文为任务内容 | 即时提醒、日常轻量委派 |
| 电话 | 手机振铃，AI语音说出通知内容。通知模式说完即挂，询问模式等待回复 | 紧急通知、需要确认的事项 |

### ← 存档 — 本地任务管理

不对外发消息，管理本地任务状态。任务数据存储在 `assets/tasks.json` 文件中。

**状态流转**：
```
pending（待处理）→ running（执行中）→ completed（已完成）→ archived（已归档）
```

| 操作 | 说什么 | 系统做什么 |
|------|--------|-----------|
| 标记完成 | "标记任务完成" / "这个做完了" | 最近一条进行中的任务 → completed |
| 归档 | "存档" / "归档这个结果" | 最近一条已完成的任务 → archived |

**存档后可以继续流转**：存档不代表结束。比如 Agent 帮你写了一份报告，你说"存档"，报告存好了，接下来还可以：
- "把这份报告汇报给张总" → UP 邮件发送给上级
- "分派给小莲根据报告修改代码" → DOWN 委派给下属跟进

### → AI Agent — 把脑力活交给AI

预设了两个通用Agent，核心能力是**动态创建**——描述需求，当场生成一个专门干这活的 Agent。

**预设Agent**：

| Agent | 擅长什么 | 说什么 |
|-------|---------|--------|
| 代码审查Agent | 代码质量审查、Bug分析、改进建议 | "交给代码审查Agent检查这段代码" |
| 文档润色Agent | 文档润色、中英翻译、格式优化 | "交给文档润色Agent润色这份报告" |
| 摇钱树Agent | AI智能财务助手（智能记账、管理会计、成本管控、内部控制、经营BI） | "交给摇钱树Agent帮我分析这个月毛利率" → [详细介绍](https://gitee.com/lianye25/yaoqianshu-skills) |

> 安装摇钱树Agent：将 `yaoqianshu/` 目录下的 5 个 `.skill` 文件一并复制到 Open Claw 的 skills 目录即可，五个模块（会计、管理会计、内部控制、成本管理、经营BI）自动注册为可调用子技能。

**动态Agent**：不需要提前配置。随口说一个不存在的 Agent 名，系统自动创建：

| 说什么 | 系统做什么 |
|--------|-----------|
| "交给市场分析Agent分析这份竞品数据" | 自动创建"市场分析Agent"→后台调用LLM分析→返回结论 |
| "交给周报生成Agent写本周工作总结" | 自动创建"周报生成Agent"→生成结构化报告→播报结果 |
| "交给翻译Agent把这段话翻成英文" | 自动创建"翻译Agent"→翻译→返回译文 |

动态Agent 的本质：**描述要干什么，当场雇一个 AI 来干**。干完后结果回到你手里，可以存档、汇报给上级、或分派给下属继续处理。

**执行过程**：说完 → 任务进入 pending → 后台启动LLM（需几秒到几十秒）→ 完成后小智语音播报结果 → 决定下一步（存档 / 上报 / 委派）。

### ⊙ 中枢

没有方向关键词时，不执行分发，只返回解析结果，相当于"待命"状态。

---

## 快速开始

### 方式 A：安装为 Open Claw Skill（推荐）

将本目录复制到 Open Claw 的 skills 目录下，Open Claw 加载 Skill 后会自动检测配置状态：

1. 如果 `config.json` 中还是占位符（`"sk-xxx"`、`"your-email@qq.com"`），Open Claw 会**主动发起对话引导**，逐项询问你的邮件、LLM API Key、联系人等信息
2. 回答完问题后，Open Claw 自动将你的信息写入配置文件
3. 配置完成，立即可用

**不需要手动编辑任何文件。**

### 方式 B：手动配置（不使用 Open Claw）

如果想独立运行脚本，按以下步骤手动配置。

### 前置依赖

- Python 3.10+
- （可选）`stepone-call` CLI：`npm install -g openclaw-ai-calls-china-phone`
- （可选）DeepSeek API Key

### 1. 配置 `assets/config.json`

```json
{
  "email": {
    "smtp_server": "smtp.qq.com",
    "smtp_port": 587,
    "use_tls": true,
    "username": "your-email@qq.com",
    "password": "your-smtp-auth-code",
    "from_name": "财神上下左右"
  },
  "voice_call": {
    "stepone_api_key": "sk-xxx",
    "notify_mode": true
  },
  "llm": {
    "api_key": "sk-xxx",
    "api_base": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "max_tokens": 4096,
    "temperature": 0.7
  }
}
```

> QQ邮箱需使用 SMTP 授权码（非登录密码），在「设置 → 账户 → POP3/SMTP 服务」中生成。

### 2. 配置 `assets/contacts.json`

按组织架构填写三类联系人：

- **superiors**：上级列表（UP 汇报方向）
- **subordinates**：下属列表（DOWN 委派方向），需要电话通知时填写 `phone` 字段
- **agents**：AI Agent 列表（RIGHT 分派方向）

```json
{
  "superiors": [
    {"name": "张总", "title": "项目负责人", "channels": ["email"], "address": "zhang@example.com"}
  ],
  "subordinates": [
    {"name": "小莲", "channels": ["email", "phone"], "address": "xiaolian@example.com", "phone": "+8613800000000"}
  ],
  "agents": [
    {"name": "代码审查Agent", "type": "code-review", "description": "代码质量审查"}
  ]
}
```

### 3. 测试

```bash
cd scripts
python intent_parser.py "向上汇报给张总项目第一阶段已完成" --dispatch
```

---

## 语音指令

**基本语法：** `[通道]  [方向关键词]  [目标名称]  [具体内容]`

### 通道信号词（句首检测）

| 通道 | 信号词 | 分发方式 |
|------|--------|---------|
| 电话 phone | 打电话、打个电话、电话通知、电话告诉 | stepone-call CLI |
| 邮件 email | 发邮件、发个邮件、邮件通知 | SMTP 发送 |
| 微信 wechat | 发微信、发个微信、微信通知、发消息、发个消息 | 企业微信应用消息 |

### 示例

| 语音输入 | 方向 | 目标 | 内容 |
|----------|------|------|------|
| 向上汇报给张总今天的项目进展 | UP | 张总 | 今天的项目进展 |
| 分派给小明整理会议纪要 | DOWN | 小明 | 整理会议纪要 |
| 标记任务完成 | LEFT | — | — |
| 交给代码审查Agent检查这段代码 | RIGHT | 代码审查Agent | 检查这段代码 |
| 发邮件通知张总周报已提交 | UP | 张总 | 周报已提交 |
| 打电话告诉小莲下午3点开会 | DOWN | 小莲 | 下午3点开会 |
| 打电话询问小莲明天能否参会 | DOWN | 小莲 | 明天能否参会 |
| 发消息给小王下午3点开会 | DOWN | 小王 | 下午3点开会 |
| 发微信通知小明数据报告已生成 | DOWN | 小明 | 数据报告已生成 |

---

## 消歧规则

| 输入特征 | 判定方向 | 理由 |
|----------|---------|------|
| 「交给」+ Agent 名称 | RIGHT | 目标类型优先 |
| 「交给」+ 人名 | DOWN | 目标类型优先 |
| 「完成」+ 目标人物 | DOWN | 委派语义覆盖 |
| 「完成」独立使用 | LEFT | 纯状态管理 |
| 「通知」/「告诉」+ 上级人名 | UP | 联系人列表反推 |
| 「通知」/「告诉」+ 下属人名 | DOWN | 联系人列表反推 |
| 仅指定通道无方向 | 查联系人列表 | **通道反推方向** |

---

## 电话通知

通过 Stepone AI 拨打联系人电话。资费约 ¥0.20/通（~11秒），需安装 `stepone-call` CLI。

### 两种模式

| 模式 | 信号词 | AI 行为 | 适用场景 |
|------|--------|---------|---------|
| **notify**（默认） | 通知、告诉、告知、转告、提醒 | 接通→告知→挂断，禁止闲聊 | 会议通知、截止提醒 |
| **inquiry** | 询问、问一下、问、确认一下、请问 | 接通→询问→听取答复→复述确认→礼貌结束 | 确认时间、收集答复 |

### 模板机制

`notify_mode: true` 时，系统自动包装用户内容为角色提示词：

**通知模板：**
```
【角色】你是电话通知员，不是闲聊朋友。禁止寒暄、禁止反问、禁止聊天。
【任务】接通后立即用自然口语告知对方以下内容，说完即挂断：
【通知内容】下午3点来办公室开会
```

**询问模板：**
```
【角色】你是电话沟通助手，代表用户进行礼貌的询问沟通。
【任务】接通后用自然口语向对方询问以下问题，认真听取对方的答复，
对方回答后复述确认并礼貌结束通话。禁止闲聊其他话题。
【询问内容】下午3点能不能来办公室开会？
```

---

## 手势控制

整合小智Pro手势识别，二段式交互：

1. **手势选人**：做手势（朝下+2指）→ 小智反馈「已选中小莲，请说内容」→ 状态保存 5 分钟
2. **语音说事**：直接说「下午3点来开会」→ 系统自动合并手势方向+目标

### 手势映射

| 手势 | 方向 | 手指数含义 |
|------|------|-----------|
| 朝上 | UP 上报 | 第N指=superiors[N-1] |
| 朝下 | DOWN 委派 | 第N指=subordinates[N-1] |
| 朝左 | LEFT 存档 | 1指=完成, 2指=归档 |
| 朝右 | RIGHT Agent | 第N指=agents[N-1] |
| 握拳 | CENTER 确认 | — |

### 摄像头控制

| 语音指令 | 效果 |
|----------|------|
| 打开摄像头 | 手势识别启动，LED 紫色 |
| 关闭摄像头 | 手势识别停止，LED 熄灭 |

---

## 任务管理

状态流转：`pending → running → completed → archived`

```bash
# 查询最近完成的任务
python scripts/task_status.py --latest-completed

# 查询运行中任务
python scripts/task_status.py --running

# 归档指定任务
python scripts/task_status.py --archive task-20260525-001
```

---

## CLI 参考

### intent_parser.py — 意图解析

```bash
# 仅解析
python scripts/intent_parser.py "向上汇报给张总项目进展"

# 解析 + 分发
python scripts/intent_parser.py "分派给小明整理数据" --dispatch

# 指定配置
python scripts/intent_parser.py "文本" --contacts assets/contacts.json --config assets/config.json --dispatch
```

| 参数 | 说明 |
|------|------|
| `--contacts PATH` | contacts.json 路径（默认 `assets/contacts.json`） |
| `--config PATH` | config.json 路径（默认 `assets/config.json`） |
| `--dispatch` | 解析后自动执行消息分发 |
| `--pretty` | 美化 JSON 输出（默认开启） |

### dispatcher.py — 独立分发

```bash
python scripts/dispatcher.py --intent result.json
python scripts/dispatcher.py --intent result.json --contacts contacts.json --config config.json
```

---

## 项目结构

```
handsfree/
├── SKILL.md                    # Skill 定义文件
├── README.md                   # 本文件
├── assets/
│   ├── config.json             # 配置文件（SMTP + LLM + Voice）
│   └── contacts.json           # 联系人模板
├── references/
│   ├── five_dimensions.md      # 方向语义规范
│   └── examples.md             # 测试用例集
└── scripts/
    ├── intent_parser.py        # 意图解析引擎
    ├── dispatcher.py           # 消息分发引擎
    ├── contact_matcher.py      # 联系人模糊匹配
    ├── xiaozhi_gesture_parser.py # 手势自然语言解析
    ├── task_manager.py         # 任务状态管理
    ├── task_status.py          # 任务状态查询 CLI
    └── agent_runner.py         # AI Agent 执行引擎
```

---

## 配置参考

### config.json

| 字段 | 类型 | 说明 |
|------|------|------|
| `email.smtp_server` | string | SMTP 服务器（QQ: smtp.qq.com） |
| `email.smtp_port` | int | SMTP 端口（QQ: 587） |
| `email.username` | string | 发件邮箱 |
| `email.password` | string | SMTP 授权码 |
| `voice_call.stepone_api_key` | string | Stepone AI API Key |
| `voice_call.notify_mode` | bool | 是否启用电话模板包装（默认 true） |
| `llm.api_key` | string | DeepSeek API Key |
| `llm.model` | string | 模型名称（默认 deepseek-chat） |

### contacts.json

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 联系人姓名 |
| `channels` | []string | 可用通道：email / phone / wechat |
| `address` | string | 邮箱地址（邮件通道必填） |
| `phone` | string | 电话号码（电话通道必填，+86格式） |
| `wechat_userid` | string | 企业微信用户ID（微信通道必填） |

---

**财神上下左右** — 指个方向，开口即达。
