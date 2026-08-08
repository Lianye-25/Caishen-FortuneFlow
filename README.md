# HANDSFREE 五维中枢

> 语音驱动的人机协同中枢 — 动嘴不动手

HANDSFREE（**H**ands-free **A**utomated **N**otification & **D**elegation **S**ystem **F**or **R**esponsive **E**xecution）五维中枢，是一套运行在 OpenClaw + 小智机器人上的语音驱动分发系统。将日常管理工作抽象为五个方向，通过自然语言语音指令驱动信息流转。

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
    "from_name": "HANDSFREE 五维中枢"
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

## 五维方向

### ↑ UP — 上报（Report）

向上级汇报工作成果，自动发送 HTML 汇报邮件。

| 关键词 | 匹配 | 分发 |
|--------|------|------|
| 汇报、上报、提交、报告、通知、告诉、呈报、报给、发给、反馈给 | superiors | 邮件 |

### ↓ DOWN — 委派（Delegate）

向下属分派任务，邮件或电话通知。

| 关键词 | 匹配 | 分发 |
|--------|------|------|
| 分派、委派、分配、交给、让、安排、派给、下发、布置、叫 | subordinates | 邮件 / 电话 |

### ← LEFT — 存档（Archive）

任务完成/归档，纯本地状态管理。手势：**1指=标记完成，2指=归档**。

| 关键词 | 匹配 | 分发 |
|--------|------|------|
| 存档、标记完成、归档、关闭任务、结束任务、完成任务 | 无 | 无 |

### → RIGHT — Agent 分派

AI Agent 后台子进程异步执行，完成后小智 TTS 播报结果。支持**动态 Agent 创建**。

| 关键词 | 匹配 | 分发 |
|--------|------|------|
| Agent处理、AI处理、智能处理、机器处理、自动处理 | agents（动态） | LLM 子进程 |

### ⊙ CENTER — 中枢

无方向关键词时的默认状态，信息查询。

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

## Agent 执行

```
用户语音 → RIGHT → 创建任务(pending) → 后台子进程(running)
    → DeepSeek API 执行 → 更新(completed/failed)
        → 小智轮询 task_status → TTS 播报 → 用户决策下一步
```

**回调闭环：**
- 「存档这个结果」→ LEFT 归档
- 「汇报给张总」→ UP 邮件转发
- 「分派给小王修改」→ DOWN 委派跟进

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

## 典型工作流

### 场景1：语音汇报（邮件）
```
用户：「向上汇报给张总今天的项目进展已完成第一阶段」
系统：解析 → UP, 张总 → HTML汇报邮件 → SMTP发送
```

### 场景2：手势选人 + 电话通知
```
用户：打开摄像头 → 做手势（朝下，2指）
系统：「已选中小莲，请说内容」
用户：「下午3点来办公室开会」
系统：合并手势目标 → notify模式 → 拨打小莲电话
```

### 场景3：电话询问模式
```
用户：「打电话询问小莲明天下午3点能不能来参加项目评审」
系统：phone通道 → DOWN(联系人反推) → inquiry模式
AI：「您好，想询问您明天下午3点能不能来参加项目评审？」
小莲：「可以的」
AI：「好的，确认您明天下午3点可以参加，再见」
```

### 场景4：Agent处理 → 审阅 → 存档
```
用户：「交给文档润色Agent润色这份报告」
系统：创建任务 → DeepSeek执行 → 完成
小智：TTS播报润色结果
用户：「不错，存档这个结果」
系统：LEFT归档
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
│   ├── five_dimensions.md      # 五维方向语义规范
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

**HANDSFREE 五维中枢** — 动嘴不动手，语音驱动人机协同。
