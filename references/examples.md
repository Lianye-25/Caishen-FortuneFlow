# 财神 意图解析 — 测试用例集

## 用例格式说明

每条用例包含：
- **输入**：模拟 ASR 转写的原始中文文本
- **direction**：期望方向（UP/DOWN/LEFT/RIGHT/CENTER）
- **target_name**：期望匹配的联系人名称（null 表示无）
- **content**：期望提取的内容（null 表示无）
- **confidence_min**：最低置信度
- **说明**：用例解释

---

## UP 方向（上报/汇报）

### U1 — 标准汇报
- 输入：`向上汇报给张总今天的项目进展已完成`
- direction: UP
- target_name: 张总
- content: 今天的项目进展已完成
- confidence_min: 0.8
- 说明：标准"汇报给+人名+内容"模式

### U2 — 简化汇报
- 输入：`报告给李经理周报已写好`
- direction: UP
- target_name: 李经理
- content: 周报已写好
- confidence_min: 0.8
- 说明："报告"替代"汇报"

### U3 — 提交模式
- 输入：`提交给王总监架构方案请审批`
- direction: UP
- target_name: 王总监
- content: 架构方案请审批
- confidence_min: 0.8
- 说明："提交"关键词，带审批请求

### U4 — 无介词
- 输入：`通知张总会议推迟到下午三点`
- direction: UP
- target_name: 张总
- content: 会议推迟到下午三点
- confidence_min: 0.8
- 说明："通知"直接跟人名

### U5 — ASR 同音字错误
- 输入：`汇报给章总报告进展`
- direction: UP
- target_name: null (模糊匹配可能不命中)
- content: null
- confidence_min: 0.4
- 说明："章总"与"张总"不同字，SequenceMatcher 难以匹配

### U6 — 报给模式
- 输入：`报给张总项目已上线`
- direction: UP
- target_name: 张总
- content: 项目已上线
- confidence_min: 0.8
- 说明："报给"口语化表达

---

## DOWN 方向（委派/分派）

### D1 — 标准分派
- 输入：`向下分派给小王整理会议纪要`
- direction: DOWN
- target_name: 小王
- content: 整理会议纪要
- confidence_min: 0.8
- 说明：标准"分派给+人名+任务"模式

### D2 — 委派模式
- 输入：`委派给小明做数据分析报告`
- direction: DOWN
- target_name: 小明
- content: 做数据分析报告
- confidence_min: 0.8
- 说明："委派"关键词

### D3 — 安排模式
- 输入：`安排小红设计新的登录页面`
- direction: DOWN
- target_name: 小红
- content: 设计新的登录页面
- confidence_min: 0.8
- 说明："安排"关键词

### D4 — 让XX做模式
- 输入：`让小王去测试新功能`
- direction: DOWN
- target_name: 小王
- content: 去测试新功能
- confidence_min: 0.8
- 说明："让"关键词，口语化委派

### D5 — 分配给模式
- 输入：`分配给小明修复这个bug`
- direction: DOWN
- target_name: 小明
- content: 修复这个bug
- confidence_min: 0.8
- 说明："分配"关键词

### D6 — 交给下属
- 输入：`交给小王来做吧`
- direction: DOWN
- target_name: 小王
- content: 来做吧
- confidence_min: 0.7
- 说明："交给" + 下属名称 → DOWN 方向

---

## LEFT 方向（存档/标记完成）

### L1 — 存档任务
- 输入：`存档这个结果`
- direction: LEFT
- target_name: null
- content: 这个结果
- confidence_min: 0.6
- 说明：LEFT 无目标联系人

### L2 — 标记完成
- 输入：`标记任务完成`
- direction: LEFT
- target_name: null
- content: null
- confidence_min: 0.5
- 说明：纯状态管理命令

### L3 — 归档操作
- 输入：`归档这份文档`
- direction: LEFT
- target_name: null
- content: 这份文档
- confidence_min: 0.6
- 说明："归档"关键词

### L4 — 关闭任务
- 输入：`关闭任务这个bug已修复`
- direction: LEFT
- target_name: null
- content: 这个bug已修复
- confidence_min: 0.6
- 说明："关闭任务"关键词

### L5 — 标记为完成
- 输入：`标记为完成项目第一阶段`
- direction: LEFT
- target_name: null
- content: 项目第一阶段
- confidence_min: 0.6
- 说明："标记为完成"连用

---

## RIGHT 方向（Agent 分派）

### R1 — 交给 Agent
- 输入：`交给代码审查Agent检查这段代码`
- direction: RIGHT
- target_name: 代码审查Agent
- content: 检查这段代码
- confidence_min: 0.8
- 说明："交给" + Agent 名称 → RIGHT

### R2 — Agent 处理模式
- 输入：`让文档润色Agent处理这份报告`
- direction: RIGHT
- target_name: 文档润色Agent
- content: 处理这份报告
- confidence_min: 0.8
- 说明："让" + Agent 名称 → RIGHT（消歧规则）

### R3 — AI 处理
- 输入：`AI处理这个数据表格`
- direction: RIGHT
- target_name: null (无具体 Agent 名称)
- content: 这个数据表格
- confidence_min: 0.6
- 说明："AI处理"关键词，无指定 Agent

### R4 — 智能处理
- 输入：`智能处理这份合同条款分析`
- direction: RIGHT
- target_name: null
- content: 这份合同条款分析
- confidence_min: 0.6
- 说明："智能处理"关键词

### R5 — 自动处理
- 输入：`自动处理这个审批流程`
- direction: RIGHT
- target_name: null
- content: 这个审批流程
- confidence_min: 0.6
- 说明："自动处理"关键词

---

## CENTER 方向（中枢/无方向）

### C1 — 信息查询
- 输入：`今天有什么任务`
- direction: CENTER
- target_name: null
- content: 今天有什么任务
- confidence_min: 0.3
- 说明：无方向关键词，默认中枢

### C2 — 状态询问
- 输入：`现在的进度怎么样了`
- direction: CENTER
- target_name: null
- content: 现在的进度怎么样了
- confidence_min: 0.3
- 说明：纯信息查询

### C3 — 空输入
- 输入：` `
- direction: CENTER
- target_name: null
- content: null
- confidence_min: 0.3
- 说明：空输入的边界处理

---

## 歧义/边界情况

### A1 — 双方向（第一优先）
- 输入：`汇报给张总然后分派给小王去执行`
- direction: UP
- target_name: 张总
- content: 然后分派给小王去执行
- confidence_min: 0.8
- 说明：多方向关键词，取最早出现者

### A2 — 交给 + Agent（消歧为 RIGHT）
- 输入：`交给代码审查Agent优化`
- direction: RIGHT
- target_name: 代码审查Agent
- content: 优化
- confidence_min: 0.8
- 说明：消歧规则："交给" + Agent → RIGHT

### A3 — 无联系人匹配
- 输入：`汇报给赵总完成了设计`
- direction: UP
- target_name: null
- content: null
- confidence_min: 0.4
- 说明："赵总"不在联系人列表中
