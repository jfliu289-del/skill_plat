# 面向人类需求的 Agent Skill 百科分类与推荐系统设计

- 文档状态：已确认设计，待用户书面审阅
- 版本：1.0
- 日期：2026-07-21
- 适用范围：Skill 汇总仓库、搜索目录、需求分析与推荐服务

## 1. 背景

Agent Skill 生态已经从少量编程提示扩展为覆盖办公文档、科研、软件工程、营销、产品管理、企业运营、个人效率和生活自动化的大型生态。

现有目录通常采用以下一种方式组织内容：

- 按工具或产物分类，例如 PDF、PPT、React、AWS；
- 按行业或角色分类，例如开发者、营销人员、研究人员、CFO；
- 按发布者或平台分类，例如 Anthropic、OpenAI、Vercel、Claude Code；
- 按工作流阶段分类，例如发现、计划、实现、验证、发布。

这些方式各有价值，但任何单一维度都不足以回答人类真正关心的问题：

> 我现在想完成某件事，在我的工具环境和风险承受范围内，应该使用哪个 Skill？

因此，本项目采用“任务意图为主入口、多轴标签为检索基础、风险作为硬过滤、质量证据决定排序”的设计。

## 2. 调研基础

设计基于 2026-07-21 前后的 GitHub 生态调研：

- 调研 40 多个官方、社区和垂直 Skill 仓库；
- 抽查 8 个代表仓库中的 787 个实际 SKILL.md；
- 分析 [Awesome OpenClaw Skills](https://github.com/VoltAgent/awesome-openclaw-skills) 固定快照的 30 个分类文件；分类头部名义合计 5,382，但实际解析为 5,180 条、5,177 个唯一链接，因此后续统计必须以固定 commit 的实际解析结果为准；
- 对比 Skill、Agent、Command、Rule、Prompt、Plugin、MCP、Tool 和 Workflow 等相邻形态；
- 重点检查分类噪声、重复搬运、兼容性声明、依赖披露和供应链风险。

代表来源包括：

- [Agent Skills 开放规范](https://github.com/agentskills/agentskills)
- [Anthropic Skills](https://github.com/anthropics/skills)
- [OpenAI Plugins](https://github.com/openai/plugins)
- [GitHub Awesome Copilot](https://github.com/github/awesome-copilot)
- [Vercel Agent Skills](https://github.com/vercel-labs/agent-skills)
- [Hugging Face Skills](https://github.com/huggingface/skills)
- [NVIDIA Skills](https://github.com/NVIDIA/skills)
- [Superpowers](https://github.com/obra/superpowers)
- [Composio Awesome Claude Skills](https://github.com/ComposioHQ/awesome-claude-skills)
- [K-Dense Scientific Agent Skills](https://github.com/K-Dense-AI/scientific-agent-skills)
- [PM Skills](https://github.com/phuryn/pm-skills)
- [Marketing Skills](https://github.com/coreyhaines31/marketingskills)
- [Trail of Bits Skills](https://github.com/trailofbits/skills)
- [Alireza Rezvani Claude Skills](https://github.com/alirezarezvani/claude-skills)
- [Awesome OpenClaw Skills](https://github.com/VoltAgent/awesome-openclaw-skills)

## 3. 产品目标

### 3.1 核心目标

1. 帮助普通用户用自然语言描述需要，而不要求用户了解 Skill 名称或技术平台。
2. 为每个需要推荐最合适、可运行、可信且风险可接受的 Skill。
3. 支持按任务、行业、工作流阶段、产物、平台和风险进行浏览与筛选。
4. 区分真正的 Agent Skill 与相邻资源，避免数量虚高和错误安装。
5. 追踪 Skill 的来源、版本、依赖、权限、质量和安全证据。
6. 将重复、镜像、fork 和衍生版本聚合为一个 canonical 条目。
7. 为推荐结果提供人类可理解的解释。

### 3.2 非目标

第一版不承担以下职责：

- 不自动运行未经用户批准的第三方 Skill；
- 不把 GitHub Stars 当作 Skill 效果证明；
- 不保证安全扫描通过的 Skill 绝对安全；
- 不把医疗、法律、金融输出描述为专业意见；
- 不假设同一个 SKILL.md 在所有 Agent 平台上完全兼容；
- 不把所有 Prompt、Rule、Agent 或 MCP 自动转换为 Skill；
- 不在没有来源证据时宣称某个条目是官方版本。

## 4. 术语与资源类型

系统必须先判断资源类型，再进入分类和推荐。

| 资源类型 | 定义 | 是否作为标准 Skill 推荐 |
|---|---|---|
| skill | 包含 SKILL.md 的可复用知识、流程和资源包 | 是 |
| agent | 有独立角色、上下文、工具权限或生命周期的执行主体 | 作为相邻资源 |
| command | 用户显式调用的命令或快捷工作流 | 作为相邻资源 |
| rule / instruction | 持续生效或按文件范围生效的约束 | 作为相邻资源 |
| prompt | 一次性或可复制的提示模板 | 作为相邻资源 |
| plugin | 可包含 skills、agents、MCP、hooks 和 assets 的分发容器 | 展开后逐项记录 |
| MCP / tool | 向 Agent 提供外部系统访问能力的接口 | 作为依赖和相邻资源 |
| workflow | 多个步骤、Skill、Agent 或 Tool 的编排 | 可作为复合资源 |
| harness | 负责计划、路由、状态和多 Agent 调度的运行框架 | 作为运行环境 |

标准 Skill 的最低识别条件为：

1. 存在 SKILL.md；
2. 包含可解析的 name 和 description；
3. 包含面向 Agent 的可执行说明；
4. 来源路径和版本可以确定；
5. 配套脚本、引用和资源可以被完整枚举。

不满足最低条件的条目可以被收录为相邻资源，但不得显示为“标准 Skill”。

## 5. 分类设计原则

### 5.1 主任务优先

分类首先回答“用户想得到什么结果”，而不是“Skill 使用了什么工具”。

例如：

- 创建销售汇报 PPT：主类是营销、销售与客户增长，产物标签是 slides；
- 修复 PPT 排版：主类是文档与办公成果；
- 自动把报告发到 Slack：若重点是跨应用自动发送，则主类是应用与自动化；
- 分析临床试验数据：主类是科学与学术研究，能力标签是 statistical-analysis。

### 5.2 一个主类，多个辅助标签

每个 Skill 只能有一个 primary_category，但可以有多个：

- secondary_categories；
- task verbs；
- workflow stages；
- artifacts；
- domains；
- audiences；
- platform and runtime tags；
- risk tags。

### 5.3 稳定编号与可变名称分离

分类编号 C00 至 C19 为稳定标识。中文名称、英文名称和展示文案可以迭代，但不得随意改变编号语义。

分类合并或废弃时保留 alias 和 successor，确保旧链接和历史数据可追踪。

### 5.4 供给不能决定分类

当前 GitHub Skill 供给明显偏向软件实现、测试和代码审查。如果仅依靠自动聚类，分类会复制现有供给偏差。

本分类以人类任务空间为基础，保留翻译、本地化、教育、企业职能和生活服务等当前供给相对不足的场景。

## 6. 六大导航类与二十个任务场景

| 导航类 | 包含的任务场景 |
|---|---|
| A. 信息、内容与创作 | C01 搜索、调研与知识获取；C02 写作、语言与沟通；C03 文档与办公成果；C04 数据分析与决策情报；C05 设计与创意媒体 |
| B. 软件、系统与自动化 | C06 软件设计与开发；C07 调试、测试与质量；C08 Git、交付与基础设施；C09 安全、隐私与合规；C10 AI、机器学习与智能系统；C19 应用、浏览器与设备自动化 |
| C. 产品、组织与商业 | C11 产品、项目与团队协作；C12 战略、创业与管理决策；C13 企业职能与专业服务；C14 营销、销售与客户增长 |
| D. 研究与学习 | C15 科学与学术研究；C16 教育、学习与培训 |
| E. 个人与生活 | C17 个人效率、知识与职业；C18 生活、健康与实体世界 |
| F. Agent 生态自身 | C00 Skill 与 Agent 管理 |

编号是稳定的数据标识，不代表首页展示顺序。用户首先看到六大导航类，再进入对应任务场景。

### A. 信息、内容与创作

#### C01 搜索、调研与知识获取

覆盖：

- 网页搜索、浏览、抓取和信息抽取；
- 深度研究、新闻和趋势追踪；
- 市场、公司、人物和竞争对手研究；
- 学术文献、专利、法规和档案检索；
- OCR、网页正文提取和文档问答；
- 事实核查、来源验证和证据综合；
- 知识库、RAG、资料归档和检索。

不覆盖：

- 以发表论文为目标的完整科研工作流，归入 C15；
- 以营销决策为目标的竞品研究，主类可归入 C14；
- 单纯操作浏览器完成跨应用动作，归入 C19。

#### C02 写作、语言与沟通

覆盖：

- 构思、起草、续写、改写和协作写作；
- 校对、润色、风格调整和可读性优化；
- 摘要、提纲、纪要和行动项；
- 翻译、本地化、术语管理和字幕；
- 邮件、聊天、内部沟通和领导简报；
- 技术文档、文章、新闻稿和内容发布；
- 语音转写后的文本整理。

不覆盖：

- 主要目标是生成特定 Office 文件，归入 C03；
- 营销文案和销售内容的完整工作流，主类归入 C14；
- 论文、审稿和学术规范工作流，归入 C15。

#### C03 文档与办公成果

覆盖：

- PDF 创建、提取、合并、标注、表单和渲染检查；
- Word 文档创建、编辑、批注和修订；
- Excel 和其他电子表格的公式、格式、图表和校验；
- PowerPoint 和其他幻灯片的生成、编辑和演示设计；
- 流程图、架构图、思维导图和信息图；
- 模板、品牌格式和批量文档处理；
- Markdown、HTML、EPUB 和 Office 格式转换。

#### C04 数据分析与决策情报

覆盖：

- 数据获取、解析、清洗、转换和质量检查；
- CSV、JSON、Parquet、数据库和数据仓库；
- SQL、数据建模和查询优化；
- 探索性数据分析和描述统计；
- 推断统计、因果分析、实验分析和 A/B 测试；
- 时间序列、预测、优化和仿真；
- BI、仪表盘、数据可视化和决策报告；
- 地理空间和网络数据分析。

#### C05 设计与创意媒体

覆盖：

- 品牌、视觉方向、设计系统和 UI/UX；
- 海报、封面、社交图片、插图和图标；
- 图片生成、编辑、抠图、压缩和批处理；
- 视频脚本、分镜、生成、剪辑和程序化视频；
- 音频、配音、播客、音乐和声音设计；
- 动画、3D 模型、像素画和游戏素材；
- 程序化艺术和互动视觉作品。

### B. 软件、系统与自动化

#### C06 软件设计与开发

覆盖：

- 软件需求、技术规格和架构设计；
- 前端、后端、全栈和 API 开发；
- 移动端、桌面端、游戏、区块链和嵌入式开发；
- 数据库设计、Schema 和迁移；
- 代码生成、修改、重构和简化；
- 技术栈迁移、依赖升级和兼容性适配；
- 代码库理解、入门导览和开发文档。

#### C07 调试、测试与质量

覆盖：

- 错误定位、根因分析和恢复；
- 单元、集成、端到端和浏览器测试；
- TDD、属性测试、变异测试和覆盖率；
- 代码审查、静态分析和规范一致性；
- 性能分析和优化；
- 可访问性、Web 质量和多设备验证；
- 日志、Tracing、监控、SLO 和可观测性；
- 规格与实现的一致性检查。

#### C08 Git、交付与基础设施

覆盖：

- Git、GitHub、GitLab、分支、提交和 Pull Request；
- CI/CD、构建、制品和发布；
- 部署、回滚、环境和配置管理；
- 云平台、Serverless 和边缘计算；
- Docker、Kubernetes、Helm 和基础设施即代码；
- 事故响应、Runbook、容量和灾备；
- 云成本、资源利用和 FinOps；
- 密钥和环境变量的工程化管理。

#### C09 安全、隐私与合规

覆盖：

- 安全编码、威胁建模和安全架构；
- 漏洞扫描、模糊测试、静态和动态分析；
- 渗透测试、CTF、逆向和数字取证；
- 密码学和智能合约安全；
- 供应链、依赖、密钥和凭证风险；
- 隐私、权限、数据治理和审计；
- SOC 2、ISO 27001、ISO 42001、GDPR、EU AI Act；
- FDA、医疗质量体系和其他监管准备。

#### C10 AI、机器学习与智能系统

覆盖：

- 模型、数据集和基准选择；
- 数据标注、训练、微调和蒸馏；
- 模型评测、红队、可解释性和偏差分析；
- RAG、Embedding、向量库和 Agent Memory；
- MLOps、LLMOps、实验追踪和推理部署；
- 多模态、语音、视觉和生成模型；
- AI Agent、Tool、MCP 和智能工作流的工程开发；
- 机器学习在科学和业务领域的应用。

Skill 创建、安装和治理本身归入 C00；用于业务目标的 AI 应用仍以业务目标分类。

#### C19 应用、浏览器与设备自动化

覆盖：

- 浏览器自动化、网页操作和 RPA；
- 桌面、移动端和 CLI 应用控制；
- Gmail、Slack、Notion、Jira、CRM 等 SaaS 集成；
- Webhook、定时任务和事件驱动自动化；
- 跨应用数据同步和消息发布；
- 智能家居、IoT、打印机和机器人控制；
- 外部 API 和 MCP 驱动的实际动作。

只有当“连接系统或自动执行动作”是主要结果时使用 C19。若自动化只是完成营销、财务或项目管理任务的手段，业务任务类仍为主类。

### C. 产品、组织与商业

#### C11 产品、项目与团队协作

覆盖：

- 用户研究、访谈、Persona 和用户旅程；
- 产品发现、问题定义和机会树；
- PRD、用户故事、验收标准和测试场景；
- 优先级、RICE、路线图和资源规划；
- OKR、Sprint、Scrum、看板和复盘；
- 项目风险、依赖和状态沟通；
- 利益相关者管理和会议协作；
- 产品发布和变更管理。

#### C12 战略、创业与管理决策

覆盖：

- 市场规模、竞争格局和趋势；
- 商业模式、价值主张和商业画布；
- GTM、定价、包装和商业化；
- 创业构思、验证和增长路径；
- 战略选择、情景规划和压力测试；
- 创始人、CEO、C-level 和董事会决策；
- 组织设计、文化和国际扩张；
- 收购、合作和组合策略。

#### C13 企业职能与专业服务

覆盖：

- 财务分析、会计、预算、预测和估值；
- 投资研究、财报和资产分析；
- 法务、合同、NDA、政策和知识产权；
- 人力资源、招聘、绩效和组织健康；
- 采购、供应商和容量管理；
- 商务政策、Deal Desk、合作和渠道经济；
- RFP、投标、尽职调查和专业报告；
- 行政、知识运营和企业内部流程。

医疗、法律和金融相关条目必须同时标记 high_stakes 和适用范围。

#### C14 营销、销售与客户增长

覆盖：

- 客户和竞争对手研究；
- 定位、品牌叙事和产品营销；
- 文案、内容策略、社交和公关；
- SEO、GEO、AEO、ASO 和结构化数据；
- 广告、创意、投放和活动分析；
- CRO、落地页、注册、付费墙和弹窗；
- 线索、Prospecting、Cold Email 和销售赋能；
- CRM、RevOps、转化和收入流程；
- Onboarding、激活、留存、推荐、流失预防和客服。

### D. 研究与学习

#### C15 科学与学术研究

覆盖：

- 选题、问题定义、假设和研究设计；
- 文献检索、系统综述和引用管理；
- 实验、统计功效和方法学；
- 论文写作、图表、海报和学术幻灯片；
- 同行评审、修改、投稿和审稿回复；
- 基金、研究计划和专利；
- 生物、化学、医学、药物、神经科学；
- 物理、材料、地球和环境科学；
- 经济、政治、社会、心理、教育和公共政策实证研究；
- 实验室、科学数据库和研究设备集成。

#### C16 教育、学习与培训

覆盖：

- 课程体系、教学计划和教案；
- 教材、讲义、练习和题库；
- 形成性和总结性测评；
- 个性化辅导和学习路径；
- 间隔学习、提取练习和认知负荷；
- 教师备课和课堂活动；
- 企业培训、岗位培训和知识转移；
- Syllabus、课程总结和学习笔记。

### E. 个人与生活

#### C17 个人效率、知识与职业

覆盖：

- 任务、日历、邮件和文件整理；
- 笔记、Obsidian、PKM 和个人知识库；
- 目标、周回顾、深度工作和反思；
- 会议准备、记录和跟进；
- 职位搜索、匹配和申请跟踪；
- 简历、作品集、面试和谈薪准备；
- 个人决策、习惯和自我管理。

#### C18 生活、健康与实体世界

覆盖：

- 健康记录、健身、营养和健康教育；
- 旅行、酒店、路线、交通和票务；
- 购物、比价、愿望清单和家庭账务；
- 菜谱、烹饪、食材和膳食计划；
- 家庭、智能家居和个人设备；
- 娱乐、媒体、游戏和兴趣爱好；
- 家庭史、族谱和个人档案；
- 社区、社交和生活服务。

无障碍、儿童、老年人、隐私敏感和多语言适配作为跨类强制标签，而不是孤立类别。

### F. Agent 生态自身

#### C00 Skill 与 Agent 管理

覆盖：

- Skill 查找、安装、更新、删除和迁移；
- Skill 创建、改进、描述优化和测试；
- Skill 评测、基准、质量审核和安全扫描；
- Agent、Prompt、Rule、Command 和 Plugin 创建；
- Agent 编排、多 Agent 协作和任务分解；
- Context、Memory、Token 和成本管理；
- MCP、Tool 和 App 能力装配；
- Agent 权限、治理和运行安全。

## 7. 跨类标签体系

### 7.1 Task：用户动作

建议受控词表：

- discover
- search
- retrieve
- extract
- organize
- generate
- create
- edit
- transform
- analyze
- compare
- decide
- review
- validate
- debug
- test
- deploy
- monitor
- communicate
- automate
- orchestrate
- teach

### 7.2 Stage：工作流阶段

- discover
- define
- plan
- prepare
- execute
- verify
- review
- release
- monitor
- maintain
- archive

### 7.3 Artifact：处理对象或交付物

核心值包括：

- code、repository、website、application、api；
- database、dataset、query、dashboard、chart；
- document、pdf、spreadsheet、slides、diagram；
- image、video、audio、music、3d-asset；
- email、message、meeting、ticket、report；
- contract、invoice、resume、paper、lesson；
- cloud-resource、device、workflow。

### 7.4 Domain：领域

领域标签不承担主导航职责，用于筛选和 rerank：

- software、data、ai-ml、security、cloud；
- office、design、media、research、education；
- product、project-management、marketing、sales；
- finance、legal、hr、operations、healthcare；
- science、government、personal、lifestyle。

### 7.5 Audience：目标用户

- beginner、general、professional、expert；
- developer、researcher、teacher、student；
- marketer、sales、product-manager、executive；
- legal-professional、finance-professional、health-professional；
- team、enterprise、individual。

### 7.6 Accessibility 与本地化

独立字段记录：

- 支持语言和输出语言；
- 地区和司法辖区；
- WCAG 或其他无障碍适配；
- 儿童、老年人和辅助技术适配；
- 文化、术语和专业语域。

## 8. 数据模型

每个条目必须保存以下七组信息。

### 8.1 身份与来源

| 字段 | 说明 |
|---|---|
| canonical_skill_id | 平台内部稳定标识 |
| name | SKILL.md 中的规范名称 |
| display_name | 面向人类的显示名称 |
| aliases | 旧名称、别名和本地化名称 |
| artifact_type | skill、agent、command、rule、prompt、plugin、mcp、workflow |
| source_repo | 原始 Git 仓库 |
| source_path | 仓库内准确路径 |
| source_commit | 已抓取的 commit SHA |
| upstream | 原始或上游来源 |
| publisher | 发布者 |
| provenance | official、verified-partner、community、unknown |
| license | 许可证 |
| version | Skill 或发布版本 |
| content_hash | 规范化内容 Hash |

### 8.2 用户意图

| 字段 | 说明 |
|---|---|
| summary | 面向人类的一句话说明 |
| jobs_to_be_done | Skill 能完成的用户任务 |
| trigger_examples | 应触发的自然语言例句 |
| anti_trigger_examples | 不应触发的近似例句 |
| when_not_to_use | 明确边界 |
| expected_inputs | 预期输入 |
| expected_outputs | 预期输出 |
| success_criteria | 成功标准 |

### 8.3 分类

| 字段 | 说明 |
|---|---|
| primary_category | C00 至 C19 中的一个 |
| secondary_categories | 相关辅助类别 |
| tasks | 受控任务动词 |
| stages | 工作流阶段 |
| artifacts | 输入和输出产物 |
| domains | 行业和专业领域 |
| audiences | 目标用户 |

### 8.4 运行与兼容

| 字段 | 说明 |
|---|---|
| supported_clients | Claude、Codex、Cursor、Copilot、Gemini、OpenClaw 等 |
| compatibility_status | native、compatible、requires-adapter、unknown |
| os | macOS、Linux、Windows 或跨平台 |
| runtimes | Python、Node、Java、Docker 等 |
| binaries | 所需命令行程序 |
| packages | 所需软件包 |
| mcp_dependencies | 所需 MCP |
| api_dependencies | 所需 API |
| credential_requirements | 所需密钥或账号 |
| network_domains | 访问的外部域名 |
| estimated_cost | 免费、按量或订阅 |
| context_footprint | 元数据和主体的上下文规模 |

### 8.5 权限与风险

| 字段 | 说明 |
|---|---|
| permissions | read、write、execute、network、secrets、external-account 等 |
| destructive_actions | 删除、覆盖、发布、支付、部署等动作 |
| high_stakes_domains | medical、legal、financial、offensive-security |
| risk_level | R0 至 R4 |
| human_approval_points | 必须由人类确认的步骤 |
| data_sensitivity | public、internal、confidential、personal、regulated |

### 8.6 质量与安全证据

| 字段 | 说明 |
|---|---|
| schema_valid | 是否通过结构验证 |
| tests | 测试和验证脚本 |
| evals | 评测集和基线比较 |
| human_review | 人工审查信息 |
| security_scans | 扫描器、版本、日期和结果 |
| signature | 签名和可验证来源 |
| sbom | 软件物料清单 |
| last_substantive_update | 最近实质内容变化 |
| maintenance_health | Issue、修复和发布活跃度 |
| skill_installs | Skill 级安装量 |
| user_feedback | 用户反馈和成功案例 |

效果质量和安全可信度必须分成两个独立分数，不得合成一个含义不清的总分。

### 8.7 推荐解释

每个推荐结果必须能够生成：

- 为什么匹配当前需要；
- 它会产生什么结果；
- 需要安装或配置什么；
- 会访问哪些文件、网络、账号或密钥；
- 有哪些风险和人工确认点；
- 有哪些质量和安全证据；
- 为什么它优于更热门的其他条目；
- 有哪些低风险或无外部依赖的替代方案。

## 9. 风险分级

| 等级 | 定义 | 默认行为 |
|---|---|---|
| R0 | 纯说明、只读推理、不访问外部系统 | 可直接推荐 |
| R1 | 本地文件、文档或代码写入，可通过版本控制恢复 | 显示写入范围 |
| R2 | 运行脚本、安装依赖或访问网络 | 显示依赖和联网目标 |
| R3 | 使用密钥、账号、发送消息、发布内容、部署或交易 | 必须显式确认 |
| R4 | 不可逆、高价值、高影响决策或进攻性安全行为 | 强制人工审批和专业复核 |

以下场景无论脚本复杂度如何，至少进入 R4 或 high_stakes：

- 医疗诊断、治疗和患者决策；
- 法律结论、合同签署和司法行为；
- 投资交易、支付和高价值财务决策；
- 真实目标的渗透、攻击或凭证操作；
- 删除生产数据、基础设施或不可恢复内容。

## 10. Canonical、去重与版本治理

### 10.1 去重层级

1. 精确 Hash：规范化文件内容后完全相同；
2. 结构 Hash：SKILL.md、脚本和资源树结构相同；
3. 语义近重复：说明、步骤和脚本高度相似；
4. 来源关系：fork、mirror、vendored copy、translated copy；
5. 功能重叠：不同实现但解决同一个任务。

### 10.2 Canonical 选择顺序

优先级为：

1. 官方或已验证发布者；
2. 可追踪的原始上游；
3. 有明确许可证；
4. 有测试、评测和安全证据；
5. 最近有实质维护；
6. 兼容范围和依赖披露更完整；
7. 社区反馈更可靠。

其他副本作为 variants 展示，保留：

- 翻译版；
- 平台适配版；
- 企业定制版；
- 新旧版本；
- 功能增强版。

## 11. 推荐流程

### 11.1 需求解析

将用户自然语言解析为：

- job_to_be_done；
- 预期产物；
- 当前工作流阶段；
- 行业和角色；
- 运行平台；
- 已有工具和依赖；
- 数据敏感度；
- 可接受风险；
- 时间、成本和语言约束。

### 11.2 硬过滤

过滤以下条目：

- 平台或操作系统不兼容；
- 必需工具、API 或密钥不可用；
- 许可证与使用场景冲突；
- 风险等级超过用户或组织策略；
- 已弃用且存在明确继任者；
- 来源无法确定或内容缺失；
- 安全策略禁止的依赖和网络目标。

### 11.3 语义召回

以 job_to_be_done、artifact 和 stage 为主要召回文本。

Domain、role、task primitive 和自然语言 trigger 用于扩大召回，但不能单独决定结果。

### 11.4 去重聚合

召回结果先按 canonical cluster 聚合。同一 Skill 的 fork、镜像和搬运版本只显示一个主结果。

### 11.5 排序

| 因素 | 权重 |
|---|---:|
| 任务适配度 | 40% |
| 产物与工作流阶段 | 15% |
| 平台、依赖和环境就绪度 | 15% |
| 测试、评测和实际效果 | 10% |
| 来源可信度与安全证据 | 10% |
| 维护活跃度 | 5% |
| Skill 级安装量和社区信号 | 5% |

GitHub Stars 只进入最后 5% 的社区信号，并采用对数缩放。仓库 Stars 不得直接复制为仓库内每个 Skill 的质量分。

### 11.6 推荐输出

默认返回：

1. 最匹配的 1 至 3 个 Skill；
2. 每项的匹配理由；
3. 依赖和风险摘要；
4. 质量与安全证据；
5. 一个低风险或低依赖替代项；
6. 复杂任务所需的 Skill 组合和执行顺序。

## 12. 系统组件

### 12.1 Source Collector

负责：

- Git 仓库、官方目录和 registry 抓取；
- commit、tag、release 和许可证记录；
- 原始文件和目录快照；
- 速率限制和增量更新。

### 12.2 Artifact Detector

负责识别：

- 标准 Skill；
- Agent、Command、Rule、Prompt；
- Plugin 中包含的子资源；
- MCP、Tool、Workflow 和 Harness。

### 12.3 Metadata Normalizer

负责：

- 解析 frontmatter；
- 标准化名称、版本和许可证；
- 推断依赖、网络、密钥和权限；
- 生成面向人类的摘要和触发示例；
- 保留原始值和推断值的来源区别。

### 12.4 Taxonomy Classifier

负责：

- primary_category；
- secondary_categories；
- task、stage、artifact、domain 和 audience；
- 分类置信度和解释；
- 低置信度条目的人工复核队列。

### 12.5 Provenance and Dedup Engine

负责：

- 内容 Hash；
- fork、mirror 和 upstream 关系；
- 近重复聚类；
- canonical 选择；
- 版本和变体关系。

### 12.6 Risk and Trust Analyzer

负责：

- 权限和数据敏感度；
- 脚本、依赖和网络行为；
- 安全扫描和签名；
- high_stakes 和 risk_level；
- 人工审批点。

### 12.7 Search and Recommender

负责：

- 需求解析；
- 硬过滤；
- 语义召回；
- rerank；
- Skill 组合；
- 可解释推荐。

### 12.8 Human Review Console

负责：

- 分类修正；
- canonical 合并；
- 来源和官方身份审核；
- 风险和安全结果复核；
- 下架、弃用和继任关系；
- 用户反馈处理。

## 13. 数据流

完整数据流为：

1. Collector 获取来源和固定 commit；
2. Detector 判断资源类型并展开 Plugin；
3. Normalizer 解析结构、依赖和权限；
4. Dedup Engine 建立来源图和 canonical cluster；
5. Classifier 分配任务分类与标签；
6. Risk Analyzer 生成风险和可信度证据；
7. Human Review 处理低置信度和高风险条目；
8. Search Index 生成面向搜索和推荐的索引；
9. Recommender 根据用户需要完成过滤、召回和排序；
10. UI 输出推荐理由、依赖、风险和替代方案。

## 14. 异常与错误处理

| 异常 | 处理方式 |
|---|---|
| SKILL.md 缺失 | 标记为相邻资源，不作为标准 Skill |
| frontmatter 无法解析 | 保存原文，进入修复或人工审核队列 |
| name 与目录不一致 | 标记 schema warning，不自动改写来源 |
| 来源访问失败 | 使用上次成功快照并标记 stale |
| API 限流 | 指数退避，保留增量同步位置 |
| 许可证缺失 | 标记 unknown，不允许默认企业推荐 |
| 依赖或权限不明 | compatibility_status 设为 unknown，降低推荐 |
| 安全扫描失败 | 标记 scan-incomplete，不显示“安全通过” |
| 高风险但无人工检查 | 不进入默认推荐 |
| 分类置信度低 | 允许搜索命中，但进入人工复核且不进入精选榜 |
| 多个来源宣称官方 | 依据组织、签名和官方链接人工确认 |
| 已弃用 | 展示警告，并优先推荐 successor |
| 近重复过多 | 聚合到 canonical，只展示 variants 数量 |

## 15. 用户界面原则

### 15.1 浏览

首页展示六大导航类，不直接平铺二十个任务场景。

进入大类后展示：

- 任务场景；
- 常见自然语言需求；
- 热门但经过质量过滤的 Skill；
- 新增和最近实质更新；
- 无外部依赖、官方、已评测等快捷筛选。

### 15.2 搜索

搜索框提示用户描述目标，而不是输入 Skill 名称，例如：

- 帮我把调研结果制作成公司模板 PPT；
- 查找能审查 React 性能问题的 Skill；
- 我需要做系统性文献综述并管理引用；
- 自动整理发票但不要把数据上传到外部服务。

### 15.3 Skill 详情页

详情页必须优先显示：

1. 它能帮助你完成什么；
2. 什么时候适合和不适合使用；
3. 输入、输出和示例；
4. 支持的平台；
5. 依赖、密钥、费用和网络；
6. 权限和风险；
7. 质量、安全和维护证据；
8. 来源、版本和许可证；
9. canonical、上游和变体；
10. 替代项和可组合 Skill。

## 16. 测试与评测

### 16.1 结构验证

- 使用官方规范验证 name、description 和目录结构；
- 验证资源引用不会越界；
- 检查损坏链接、缺失脚本和非法路径；
- 检查版本、许可证和来源字段。

### 16.2 分类评测

建立至少 300 个经人工标注的代表 Skill 集：

- 覆盖 C00 至 C19；
- 包含跨类边界样例；
- 包含应触发和不应触发样例；
- 包含中文、英文和多语言描述；
- 包含 Skill 与相邻资源混合样例。

指标：

- artifact_type 准确率；
- primary_category 准确率；
- 多标签 precision 和 recall；
- 分类置信度的校准程度；
- 人工复核率。

### 16.3 去重评测

测试：

- 完全复制；
- fork 后轻微修改；
- 翻译版；
- 平台适配版；
- 同名不同功能；
- 不同名同功能。

### 16.4 推荐评测

建立至少 100 个真实用户任务：

- 简单单 Skill 任务；
- 多阶段组合任务；
- 平台和依赖受限任务；
- 隐私敏感任务；
- 医疗、法律、金融和安全高风险任务；
- 当前没有合适 Skill 的任务。

验证：

- Top 1 和 Top 3 相关性；
- 不兼容 Skill 是否被过滤；
- 高风险条目是否正确警示；
- 推荐解释是否完整；
- 在无合适 Skill 时是否能够明确拒绝或推荐创建新 Skill。

### 16.5 安全评测

- Prompt Injection；
- 环境变量和凭证读取；
- 数据外传；
- 远程脚本下载；
- 依赖投毒；
- Symlink 和路径穿越；
- Hook 和权限滥用；
- 隐藏网络请求；
- 跨 Skill 组合风险；
- 自然语言诱导 Agent 生成恶意代码。

安全扫描结果只能作为证据，不能作为安全保证。[Cisco Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner)也明确声明无发现不代表绝对安全。

## 17. 验收标准

设计进入可实施状态需满足：

1. 所有收录条目都有 artifact_type 和可追踪来源；
2. 所有标准 Skill 都保存 source repo、path 和 commit；
3. 至少 95% 的标准 Skill 通过结构解析；
4. 人工金标准集上的 primary_category 一致率达到 90%；
5. 精确复制和明确 fork 的 canonical 聚合准确率达到 95%；
6. 100 个推荐任务中，至少 80% 的 Top 3 结果被人工评为可用；
7. 不兼容平台、缺失硬依赖和超风险条目不会进入默认结果；
8. R3 和 R4 条目始终显示显式确认或专业复核要求；
9. 推荐页不会把 repo Stars 表述为 Skill 成功率；
10. 安全扫描不会被展示为绝对安全认证；
11. 已弃用 Skill 能链接到继任者；
12. 中文用户无需知道具体 Skill 名称即可完成搜索。

## 18. 第一版范围

第一版聚焦：

- GitHub 公开仓库；
- 标准 SKILL.md；
- 官方 Plugin 中可识别的 Skill；
- 英文和中文元数据；
- 六大导航类和 C00 至 C19；
- 来源追踪、Hash 去重和 canonical；
- 基本兼容性、依赖和风险；
- 自然语言搜索和可解释 Top 3 推荐；
- 人工审核后台的最小闭环。

第一版不自动安装或执行第三方 Skill。安装和执行能力在来源、风险和权限模型稳定后单独设计。

## 19. 后续演进

第二阶段可增加：

- Skill 安装量和真实任务反馈；
- 自动生成并运行 eval；
- 组织内部私有 Skill；
- Registry 和 marketplace 同步；
- Skill 组合和工作流推荐；
- 依赖解析与锁文件；
- 签名、SBOM 和安全策略；
- 平台适配器；
- Skill 请求和缺口发现。

第三阶段可增加：

- 受控安装；
- 沙箱试运行；
- 组织策略；
- 运行效果观测；
- 基于成功轨迹的动态排序；
- 自动发现需要创建的新 Skill。

## 20. 已确认的设计决策

1. 采用任务型主分类，不采用单纯行业树。
2. 首页使用六大导航类，底层使用二十个稳定任务编号。
3. 每个 Skill 只有一个主类，但允许多轴标签。
4. Skill、Agent、Command、Rule、Prompt、Plugin、MCP 分开记录。
5. 风险先过滤，质量和适配度决定排序。
6. Stars 只占很低权重。
7. 效果质量和安全可信度分别评分。
8. fork、镜像和搬运版本聚合到 canonical。
9. 高风险领域必须保留人工审批和专业复核。
10. 第一版只做发现、评估和推荐，不自动执行第三方 Skill。

## 21. 研究结论对设计的影响

- 现有目录覆盖广但分类噪声大，因此需要人工定义的任务空间和低置信度复核。
- 同一仓库的 Stars 常被错误复制到所有 Skill，因此社区热度只能作为弱信号。
- Skill、Plugin、MCP 和 Agent 经常混放，因此 artifact_type 必须先于分类。
- Skill 内容具有复制和搬运特征，因此 canonical 和来源图是核心能力，而不是后期优化。
- SKILL.md 的强制元数据过少，因此平台必须补充依赖、权限、网络和风险信息。
- Skill 可以包含自然语言和可执行代码，安全必须覆盖语义、脚本、依赖和运行时。
- 人类真正需要的是“当前任务、当前环境和可接受风险内证据最充分的 Skill”，而不是最热门的 Skill。

相关研究：

- [From Registry to Repository: How AI Agent Skills Are Written, Adapted, and Maintained](https://arxiv.org/abs/2607.00911)
- [Malicious Agent Skills in the Wild](https://arxiv.org/abs/2602.06547)
- [Towards Secure Agent Skills](https://arxiv.org/abs/2604.02837)
