# ClawHub 官方注册表适配器设计

- 文档状态：已确认
- 版本：1.0
- 日期：2026-07-22
- 决策：采用方案 A

## 1. 目标

用 ClawHub 官方公共 API 替代已经不可访问的 `openclaw/skills` 历史归档，导入 VoltAgent 固定快照中仍然公开、发布者身份仍一致、安全状态允许的完整 Skill 发布 bundle。

适配器必须固定 `owner_handle`、`slug` 和显式 `version`，保存官方版本文件清单，对下载归档和每个发布文件分别计算或校验 SHA-256，并把无法安全导入的历史条目写入 `reports/unresolved.json`。

## 2. 已确认边界

1. ClawHub 官方 v1 API 是 OpenClaw Skill bundle 的唯一注册表来源。
2. 不使用非官方镜像，不从已下架的 `openclaw/skills` GitHub 归档恢复内容。
3. 只处理 VoltAgent `awesome-openclaw-skills` 固定 commit 中的条目；不顺带镜像 ClawHub 当前全部目录。
4. 完整 bundle 指 ClawHub 正式发布物中的全部 Skill 文件，不等同于发布者本地工作区中被 ignore、symlink 或发布规则排除的文件。
5. `_meta.json` 是 ClawHub 添加的注册表元数据，不属于版本文件清单。适配器允许它出现在 hosted ZIP 中并记录其哈希，但不把它复制为上游 Skill 内容。
6. 不执行 bundle 中的脚本、安装器、Hook、测试或二进制文件。
7. GitHub-backed Skill 只接受官方 `public-github` handoff，固定完整 commit SHA 和 Skill 路径，并以 ClawHub 版本清单逐文件验证抽取结果。

## 3. 当前数量基线

固定快照包含 5,177 个唯一 OpenClaw 链接。规范化和去重后得到 5,155 个唯一候选；2026-07-22 使用 `nonSuspiciousOnly=true` 逐条验证时：

- 4,533 个 owner/slug 仍安全且精确一致；
- 564 个缺失、隐藏或未通过安全过滤；
- 58 个 slug 存在但 owner 已变化；
- 18 个索引条目无法无歧义解析。

240 条分层抽样中，212 条安全精确匹配，209 条返回 hosted ZIP，3 条下载返回冲突。因此预计方案 A 可新增约 4,450 个完整 bundle，最终以实际锁文件和逐文件验证结果为准。

## 4. 发现与身份解析

### 4.1 支持的索引链接

- `https://clawskills.sh/skills/<legacy-owner-plus-slug>`
- `https://clawhub.ai/<owner>/<slug>`
- `https://clawhub.ai/<owner>/skills/<slug>`

对 `clawskills.sh` 旧链接，Markdown 标签是 claimed slug。不能按第一个连字符切分 owner，因为 owner 和 slug 都可能包含连字符。

解析流程：

1. 从固定索引记录 `index_path`、原始 URL、Markdown 标签和 legacy id。
2. 请求 `/api/v1/search?q=<slug>&nonSuspiciousOnly=true`。
3. 只保留 `result.slug == claimed_slug` 的结果。
4. 旧链接要求 `ownerHandle + "-" + slug == legacy_id`；新链接要求 owner 精确相等。
5. 必须恰好得到一个候选，否则写入 `mapping-unresolved`。
6. 请求 Skill 详情并再次验证响应中的 owner 和 slug。

同一 owner/slug 在多个分类文件出现时只下载一次，但保留所有索引路径和原始 URL 作为发现 provenance。

### 4.2 安全门

下列条件必须同时成立：

- 搜索使用 `nonSuspiciousOnly=true`；
- 详情响应 owner/slug 精确一致；
- `moderation.isSuspicious` 不是 `true`；
- `moderation.isMalwareBlocked` 不是 `true`；
- `moderation.verdict` 为空或为 `clean`；
- 显式版本详情中的 `security.status == "clean"`；
- 版本包含非空文件清单，并且根目录包含普通文件 `SKILL.md`。

`security.hasWarnings=true` 不自动拒绝，但必须把完整 security snapshot 保存到 provenance。`pending`、`error`、`suspicious`、`malicious` 或缺失安全状态都 fail closed。

## 5. 固定版本和完整性

初次同步从详情响应读取 `latestVersion.version`，随后只使用显式版本端点和显式版本下载，不使用 latest tag。

每个成功条目保存：

- owner handle 和 registry owner id；
- slug、version、published_at、canonical URL；
- 索引来源 id、固定 commit、索引路径和原始 URL；
- 规范序列化后的稳定版本清单 SHA-256；清单只包含 owner、slug、version、published_at 和排序后的文件 path/size/SHA-256/content-type，不包含可能随重新扫描变化的 security checkedAt 或 scanner 文本；
- 下载归档 SHA-256；
- 每个文件的 path、size、SHA-256 和 content type；
- security snapshot；
- artifact kind：`hosted` 或 `public-github`；
- GitHub handoff 的 repo、commit、path、contentHash 和 archiveUrl（如适用）。

不能把 `security.sha256hash`、`contentHash` 或 `/resolve` fingerprint 当成 ZIP SHA-256。它们作为 registry 声明值保存，下载归档哈希由本项目独立计算。

## 6. ZIP 和路径安全

Hosted ZIP 在写入缓存前必须：

1. 限制响应体为 55 MiB；
2. 先读取 central directory，再创建输出文件；
3. 拒绝绝对路径、盘符、反斜杠、NUL、`.`/`..` 段和非规范 UTF-8 路径；
4. 拒绝 symlink、设备文件、FIFO、socket、加密条目和其他非普通文件；
5. 拒绝原始、NFC、casefold 或 NFC+casefold 后的路径碰撞；
6. 最多接受 10,000 个文件、51 MiB 总解压大小和 200:1 的单文件压缩比；
7. 文件集合必须与版本详情完全一致，只允许额外的根级 `_meta.json`；
8. 逐文件验证 size 和 SHA-256；
9. 只把版本清单中的文件抽取到新建临时目录；
10. 所有检查通过后原子发布缓存目录。

GitHub-backed handoff 必须额外校验：

- `repo` 是规范 `owner/repo`；
- `commit` 是小写 40 位 SHA；
- `path` 是留在仓库根内的规范相对路径；
- `archiveUrl` 只允许与 repo/commit 对应的 GitHub 或 codeload HTTPS 地址；
- 只抽取 handoff path 下的文件并去掉归档顶层目录；
- 抽取后的文件集合、size 和 SHA-256 与 ClawHub 版本清单完全一致。

## 7. 缓存与重试

缓存键为 `owner/slug/version/version_metadata_sha256`。缓存完成标记保存归档哈希和逐文件验证结果；缺少标记、标记不匹配、符号链接或文件哈希变化都视为缓存损坏并重新获取。

HTTP 客户端必须：

- 使用 HTTPS 固定 `https://clawhub.ai`；
- 对 owner、slug、version 和查询参数进行 URL 编码；
- 对 `429` 优先遵守 `Retry-After`，对可重试的 5xx 使用有上限退避；
- 对每个请求设置连接和读取超时；
- 使用有界并发，但所有锁文件、报告和物化顺序最终按稳定键排序；
- 不把认证 token 写入命令、报告、日志或缓存。

## 8. 锁文件与重建

新增 `reports/clawhub.lock.json`，与 `sources.lock.json` 分离。前者按 `(owner_handle, slug, version)` 排序，记录成功和失败条目的确定性状态。

首次同步可以解析当前 latest；`--locked` 重建不得选择新版本，只重放锁定的 owner/slug/version 和哈希。但是即使使用 lock，也必须重新检查当前公开性和安全状态：已隐藏、删除或拦截的条目不再物化，而是写入 unresolved。无法重新确认安全状态时 fail closed。复查只充当 gate；若仍公开且 clean，继续使用锁内原始 security snapshot，不用新的扫描时间或 scanner 文本改写锁和 sidecar。

删除 `config/sources.json` 中不可访问的 `openclaw/skills` archive 项；它不再参与 Git source lock。`openclaw/clawhub` 代码仓库仍是 reference source，注册表配置独立保存在 `config/clawhub.json`。

## 9. Sidecar provenance

`skill-atlas.json` schema 升级为 2.0，并使用严格 tagged provenance 兼容两种来源；运行时 `SkillRecord` 也使用 Git/ClawHub 来源联合类型，不伪造 registry 的 Git repository 或 commit：

- Git provenance：保留 repository、commit、source_path 和现有许可字段；
- ClawHub provenance：记录 registry、owner、slug、version、canonical URL、归档与版本元数据哈希、文件清单、安全 snapshot、索引 provenance 和可选 GitHub handoff。

Hosted ClawHub 发布物按官方 registry policy 记录 `MIT-0` 和 policy URL。GitHub-backed 条目在未独立取得仓库许可证据前一律设置 `redistribution_review=true`；如果以后发现仓库许可与 registry policy 冲突，不得覆盖或隐藏冲突。

目录路由仍只由分类决定。ClawHub 条目的来源路径固定为：

```text
skills/<group>/<category>/<owner>/clawhub/<version>/<slug>/
```

跨类标签仍只写入相邻的 `skill-atlas.json`，不得修改上游 `SKILL.md`。

## 10. 错误和退出语义

下架、隐藏、安全拦截、owner 漂移和旧索引格式错误属于预期 unresolved；它们不阻止其他安全 Skill 发布。

API 响应结构错误、重试耗尽、ZIP 路径违规、文件集合变化、size/SHA-256 不一致、缓存污染或 lock 矛盾属于完整性失败。目录可以原子发布已经验证的条目，但 `all` 必须返回非零，避免把不完整运行宣称为成功。

报告必须区分：

- index_claims；
- normalized_claims；
- exact_safe_matches；
- artifact_verified；
- hosted_verified；
- github_backed_verified；
- artifact_failure；
- materialization_failure；
- unavailable_or_hidden；
- moderation_blocked；
- owner_mismatch；
- api_failure；
- transport_failure；
- integrity_failure（artifact_failure 与 materialization_failure 的合计）；
- imported；
- duplicate。

长时间同步的进度每 100 个规范 claim 写入 stderr；stdout 始终只输出一个可解析 JSON 结果。进度不得包含 token、临时目录、请求 id 或其他敏感/非确定性数据。

## 11. 验收标准

1. 固定 fixture 覆盖 hosted ZIP、GitHub handoff、403、404、409、429、安全非 clean、owner 漂移和哈希不一致。
2. 所有新功能遵循 RED-GREEN-REFACTOR；不依赖真实网络才能运行单元测试。
3. 对一个真实公开 Skill 连续下载两次，得到相同 ZIP SHA-256 和相同目录哈希。
4. 锁定重建不升级版本，并拒绝被篡改的 lock、缓存和文件。
5. 每个成功导入的 ClawHub Skill 包含完整版本文件集合、原样 `SKILL.md` 和固定位置 sidecar。
6. 最终全量运行输出精确统计、所有 unresolved 原因、重复聚类和结构验证报告。
