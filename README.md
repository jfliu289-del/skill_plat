# Skill 百科全书分类库

本仓库按人类任务场景收录完整 Skill bundle，并为每个 Skill 添加来源、分类、跨类标签和完整性信息。它既可以供人类浏览，也可以作为大模型的 Skill 检索数据源。

> 重要边界：本仓库是“完整 bundle 归档 + 初步机器分类索引”，不是可以一次性全部安装的 Skill 包。检索到候选后，必须阅读候选的 `SKILL.md`，检查依赖、权限、目标工具兼容性和安全信息，再决定是否安装。不得把 `risk_level: R0` 当作安全审计通过。

## 给大模型的最短操作指令

如果你是第一次读取本仓库的大模型，请严格按以下顺序工作：

1. 读取本 README，理解目录、标签和限制。
2. 把用户 Prompt 拆成：任务 `tasks`、阶段 `stages`、期望产物 `artifacts`、领域 `domains`、用户角色 `audiences` 和关键词。
3. 查询 `reports/overall-catalog.jsonl`，先宽召回并统计命中量；初次不要向上下文输出超过 50 条路径。
4. 合并标签和全文结果、去重并缩小范围后，只对排名靠前的 3 至 10 个候选读取根目录的 `skill-atlas.json` 和 `SKILL.md`；需要时继续读取 `references/`、`scripts/`、`assets/` 和依赖文件。
5. 检查格式、目标开发工具、外部命令、MCP、运行时、凭据、网络、文件写入、副作用、安全信息、许可证和重名冲突。
6. 最多推荐少量最合适的候选，说明证据、依赖、风险、兼容性和本地路径；不要自动执行上游脚本。
7. 只有用户明确要求安装或下载时，才根据 `provenance` 获取固定来源链接或安装所选 Skill。

完整的模型检索协议见[面向大模型的 Prompt → Skill 检索协议](#面向大模型的-prompt--skill-检索协议)。

## 当前快照

- 已归档 11,839 个完整 Skill bundle。
- GitHub 来源 9,004 个，80 个配置来源均已下载。
- ClawHub 来源 2,835 个，均为采集时公开、注册中心聚合安全状态允许且通过 bundle 校验的固定版本。
- 11,511 个 `SKILL.md` 满足 Codex 最小结构要求：合法 YAML frontmatter，且包含非空 `name` 和 `description`。
- 328 个 bundle 的上游 frontmatter 缺失或不合法；文件仍完整归档，并使用 `classifier_version: 1.0-fallback-metadata` 标记。
- 所有归档条目都有根级 `SKILL.md` 与 `skill-atlas.json`。
- `reports/overall-audit.json` 记录的 11,839 个 bundle 全量内容哈希核对结果为 0 个异常。

这些数字是当前仓库快照，不代表所有条目都适配 Codex、Claude Code、OpenClaw 或其他开发工具。

## 仓库地图

```text
.
├── README.md                         # 人类与大模型共同入口
├── config/
│   ├── sources.json                  # 配置的 GitHub/索引来源
│   ├── clawhub.json                  # ClawHub 采集策略
│   └── taxonomy.json                 # 分类树、受控标签词表和匹配规则
├── skills/                           # 按主分类存放的完整 Skill bundle
├── reports/
│   ├── overall-catalog.jsonl         # 全库查询入口；每行一个 Skill
│   ├── overall-summary.json          # 数量汇总
│   ├── overall-unresolved.json       # 未归档或无法可靠解析的来源条目
│   ├── overall-audit.json            # 完整性审计
│   └── sources.lock.json             # GitHub 来源解析和固定 commit 信息
├── schemas/
│   └── skill-atlas.schema.json       # sidecar 元数据结构
├── src/skill_atlas/                  # 采集、分类和物化实现
├── tests/                            # 实现测试
├── docs/                             # 分类和采集设计文档
└── licenses/                         # 仓库级许可证资料
```

查询全库时优先读取 `reports/overall-catalog.jsonl`。理解或使用单个 Skill 时，以叶子目录内的原始 `SKILL.md` 和其他 bundle 文件为准；`skill-atlas.json` 是本仓库添加的索引信息。

### 报告层级和验证器边界

仓库保留了分阶段采集报告，因此 `reports/` 中同时存在两组入口：

- `catalog.jsonl`、`summary.json`、`validation.json`：基础 GitHub 采集阶段的 6,947 条记录，供原有 Python 管线使用。
- `a5c-babysitter-*`、`clawhub-*`：后续完整归档阶段的分来源报告。
- `overall-catalog.jsonl`、`overall-summary.json`、`overall-unresolved.json`、`overall-audit.json`：合并 GitHub 补采和 ClawHub 后的 11,839 条全库快照，是人类和大模型查询时的权威入口。

当前 `python -m skill_atlas validate` 仍只面向基础 `reports/catalog.jsonl` 和原有 sidecar 形态，不能用来判断合并快照是否完整；直接对当前 `skills/` 全目录运行会把后续新增条目误报为 central-path mismatch，并把 ClawHub 专有完整性字段误报为 schema type。验证全库时使用本 README 最后的 `overall-*` 检查与 `reports/overall-audit.json`。这是当前实现边界，不要把旧验证器的输出解释为 11,839 个 bundle 已损坏。

## 分类目录

```text
skills/
├── A-information-content-creation/
│   ├── C01-search-research-knowledge-acquisition/
│   ├── C02-writing-language-communication/
│   ├── C03-documents-office-deliverables/
│   ├── C04-data-analysis-decision-intelligence/
│   └── C05-design-creative-media/
├── B-software-systems-automation/
│   ├── C06-software-design-development/
│   ├── C07-debugging-testing-quality/
│   ├── C08-git-delivery-infrastructure/
│   ├── C09-security-privacy-compliance/
│   ├── C10-ai-machine-learning-intelligent-systems/
│   └── C19-application-browser-device-automation/
├── C-product-organization-business/
│   ├── C11-product-project-team-collaboration/
│   ├── C12-strategy-entrepreneurship-management-decisions/
│   ├── C13-business-functions-professional-services/
│   └── C14-marketing-sales-customer-growth/
├── D-research-learning/
│   ├── C15-scientific-academic-research/
│   └── C16-education-learning-training/
├── E-personal-life/
│   ├── C17-personal-productivity-knowledge-career/
│   └── C18-life-health-physical-world/
└── F-agent-ecosystem/
    └── C00-skill-agent-management/
```

一个 Skill 只按 `primary_category` 放进一个主目录。它可能同时适用于多个场景，这些关系放在 `secondary_categories` 和五类跨类标签中，不会复制多份 bundle。

分类由规则自动产生。当前 10,412 条记录为 `needs_review: true`，所以目录适合粗筛，不应直接视为人工确认结论。

## 叶子路径的含义

### GitHub Skill

一般结构：

```text
skills/<场景组>/<主分类>/<owner>/<repository>/<上游父路径键>/<Skill目录>/
```

示例：

```text
skills/A-information-content-creation/
  C01-search-research-knowledge-acquisition/
  a5c-ai/
  babysitter/
  _encoded-m-bGlicmFyeS9tZXRob2RvbG9naWVzL3BpbG90LXNoZWxsL3NraWxscw/
  spec-driven-development/
```

含义：

- `a5c-ai`：GitHub owner/组织。
- `babysitter`：GitHub 仓库。
- 最后一层 `spec-driven-development`：Skill 根目录。
- `_encoded-m-*`：为了避免冲突和不安全路径，将上游多层父路径做 URL-safe Base64 编码。

上例编码部分解码为：

```text
library/methodologies/pilot-shell/skills
```

所以原始上游路径是：

```text
library/methodologies/pilot-shell/skills/spec-driven-development
```

不需要手工解码即可获得原始路径：

```bash
jq -r '.provenance.repository, .provenance.commit, .provenance.source_path' \
  "候选Skill目录/skill-atlas.json"
```

如果确实需要解码 `_encoded-*`：

```bash
python3 -c '
import base64, sys
payload = sys.argv[1].split("-", 2)[2]
print(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode())
' '_encoded-m-bGlicmFyeS9tZXRob2RvbG9naWVzL3BpbG90LXNoZWxsL3NraWxscw'
```

编码前缀：

- `_encoded-m-`：编码了多个路径分段。
- `_encoded-s-`：编码了一个必须转义的特殊分段。
- `_root-skill/_repository-root`：Skill 位于 GitHub 仓库根目录。

### ClawHub Skill

结构：

```text
skills/<场景组>/<主分类>/clawhub/<owner>/<slug>/<version>/
```

例如：

```text
skills/A-information-content-creation/
  C01-search-research-knowledge-acquisition/
  clawhub/
  1999azzar/
  search-cluster/
  3.5.1/
```

这里固定了 owner、slug 和 version。页面链接、安全快照、版本元数据和 bundle 哈希保存在 `skill-atlas.json`。

## 每个 Skill 包含什么

叶子目录是完整 bundle，而不是 `SKILL.md` 摘要：

```text
<Skill目录>/
├── SKILL.md                 # 上游说明和工作流
├── scripts/                 # 上游脚本，若存在
├── references/              # 上游参考资料，若存在
├── assets/                  # 上游资源，若存在
├── 其他上游配置或示例
└── skill-atlas.json         # 本仓库添加；固定放在 Skill 根目录
```

普通文件和安全的 bundle 资源按采集快照保留；不包含 Git 历史、`.git` 内部数据和不安全特殊文件。仓库没有执行任何上游 Skill 脚本。

“bundle 完整”只表示上游发布的内容被完整保留，不表示上游作者已经完整声明依赖、权限、兼容平台、API Key、许可证或安全边界。

## `skill-atlas.json`

`skill-atlas.json` 与 `SKILL.md` 并列，是本仓库的固定 sidecar。它不会修改上游 `SKILL.md`。

核心结构：

```json
{
  "schema_version": "1.0",
  "taxonomy_version": "2026-07-21",
  "classifier_version": "1.0",
  "provenance": {},
  "classification": {
    "primary_category": "C01",
    "secondary_categories": ["C12"],
    "tasks": ["manage", "research"],
    "stages": ["discover", "operate"],
    "artifacts": [],
    "domains": [],
    "audiences": [],
    "risk_level": "R0",
    "confidence": 0.275,
    "needs_review": true,
    "reasons": []
  },
  "integrity": {}
}
```

### `provenance`

GitHub 条目通常包含：

- `repository`：上游仓库 URL。
- `commit`：固定的 40 位 commit SHA。
- `source_path`：Skill 在仓库中的原始路径。
- `license`、`license_evidence`：许可证信息；可能为空。

ClawHub 条目通常包含：

- `source_type: clawhub`。
- `registry`、`canonical_url`。
- `owner_handle`、`slug`、`version`。
- `claim_id`、`published_at`。
- `security`：采集时注册中心返回的聚合状态和扫描器详情。

### `classification`

| 字段 | 用途 | Prompt 示例 |
|---|---|---|
| `primary_category` | 唯一主分类，决定物理目录 | “搜索资料” → `C01` |
| `secondary_categories` | 其他相关分类 | 搜索 Skill 同时涉及数据分析 → `C04` |
| `tasks` | 用户要完成的动作 | `research`、`write`、`debug`、`deploy` |
| `stages` | 工作流阶段 | `discover`、`plan`、`create`、`validate` |
| `artifacts` | 期望产物 | `code`、`report`、`document`、`website` |
| `domains` | 业务或技术领域 | `software`、`security`、`marketing` |
| `audiences` | 适用人群 | `developer`、`researcher`、`marketer` |
| `confidence` | 自动分类置信度 | `0` 到 `1` |
| `needs_review` | 是否需要人工/模型复核 | `true` 时不可只凭标签推荐 |
| `reasons` | 触发分类和标签的规则 | 用于解释和排查误分类 |
| `risk_level` | 文本中命中的风险提示等级 | 不是安全审计结果 |

标签受控词表和匹配规则位于 `config/taxonomy.json`。

### 标签覆盖情况

| 标签维度 | 非空记录 | 空记录 |
|---|---:|---:|
| `tasks` | 11,588 | 251 |
| `stages` | 11,588 | 251 |
| `artifacts` | 7,290 | 4,549 |
| `domains` | 7,356 | 4,483 |
| `audiences` | 8,395 | 3,444 |

空标签不表示 Skill 没有该属性，只表示当前规则没有提取出来。查询时必须允许标签不完整，并用 `SKILL.md` 全文搜索补召回。

### `integrity`

通常包含：

- `skill_md_hash`：根级 `SKILL.md` 的 SHA-256。
- `content_hash`：保留的完整 bundle 内容哈希。
- GitHub 的 `excluded_paths`。
- ClawHub 的 `archive_sha256`、`version_metadata_sha256`。

这些字段用于确认文件没有在分类搬运后发生变化，不代表内容安全。

## 查询入口和基础命令

以下命令都从仓库根目录执行。

```bash
CATALOG="reports/overall-catalog.jsonl"
```

JSONL 文件每行是一个独立 JSON 对象，可以直接使用流式 `jq`。

### 查看总量和汇总

```bash
wc -l "$CATALOG"
jq . reports/overall-summary.json
jq '{catalog_records, source_type_counts, findings_count}' \
  reports/overall-audit.json
```

### 按关键词全文搜索

标签可能为空或误判。用户 Prompt 中的产品名、技术名和目标词应同时用于全文搜索：

```bash
rg -l -i 'deep research|web search|competitor research' \
  skills \
  -g 'SKILL.md'
```

### 按主分类筛选

```bash
jq -r '
  select(.classification.primary_category == "C01")
  | .catalog_path
' "$CATALOG"
```

### 按多个辅助标签筛选

示例需求：“调研竞品并输出报告”：

```bash
jq -r '
  select((.classification.tasks | index("research")) != null)
  | select((.classification.tasks | index("analyze")) != null)
  | select((.classification.artifacts | index("report")) != null)
  | .catalog_path
' "$CATALOG" | sort -u > /tmp/skill-atlas-candidates.txt

wc -l /tmp/skill-atlas-candidates.txt
sed -n '1,50p' /tmp/skill-atlas-candidates.txt
```

先看数量，再决定是增加条件还是放宽条件。初次候选集超过 50 条时，不要把全部路径、全文内容或命令输出塞进模型上下文；应先用更多标签、专有关键词、`needs_review` 和来源缩小范围。深读阶段通常只保留 3 至 10 个候选。

先查看自动分类不要求复核的候选：

```bash
jq -r '
  select((.classification.tasks | index("research")) != null)
  | select(.classification.needs_review == false)
  | [.classification.confidence, .catalog_path]
  | @tsv
' "$CATALOG" | sort -nr | head -20
```

如果结果太少，再去掉 `needs_review == false`，但必须阅读原始 `SKILL.md` 复核。

### 按来源筛选

GitHub：

```bash
jq -r '
  select((.provenance.source_type // "github") == "github")
  | .catalog_path
' "$CATALOG"
```

ClawHub：

```bash
jq -r '
  select((.provenance.source_type // "github") == "clawhub")
  | .catalog_path
' "$CATALOG"
```

### 筛选满足 Codex 最小 frontmatter 结构的条目

```bash
jq -r '
  select(.classifier_version != "1.0-fallback-metadata")
  | .catalog_path
' "$CATALOG"
```

当前返回 11,511 条。这只验证 Codex 能识别所需的 `name` 和 `description`，不验证工具、依赖和工作流兼容性。

### 组合筛选

示例：搜索研究分类、任务包含 `research`、面向研究者、自动分类无需复核：

```bash
jq -r '
  select(.classification.primary_category == "C01")
  | select((.classification.tasks | index("research")) != null)
  | select((.classification.audiences | index("researcher")) != null)
  | select(.classification.needs_review == false)
  | .catalog_path
' "$CATALOG"
```

不要假设一次精确标签查询一定有结果。推荐顺序是：

1. 主分类 + 一个核心任务；
2. 加入产物或领域；
3. 全文关键词补召回；
4. 阅读候选 `SKILL.md`；
5. 再按兼容性和安全性淘汰。

## 检查单个候选

把实际候选目录赋给 `SKILL_DIR`：

```bash
SKILL_DIR="skills/A-information-content-creation/C01-search-research-knowledge-acquisition/a5c-ai/babysitter/_encoded-m-bGlicmFyeS9tZXRob2RvbG9naWVzL3BpbG90LXNoZWxsL3NraWxscw/spec-driven-development"
```

查看元数据和说明：

```bash
jq . "$SKILL_DIR/skill-atlas.json"
sed -n '1,240p' "$SKILL_DIR/SKILL.md"
find "$SKILL_DIR" -maxdepth 2 -type f | sort
```

在 bundle 内查找依赖、凭据和危险能力线索：

```bash
rg -n -i \
  'install|requirements|dependencies|pip |npm |brew |mcp|api[_ -]?key|token|secret|curl|wget|sudo|subprocess|shell|bash|write|delete|remove' \
  "$SKILL_DIR"
```

这只是线索扫描，不是完整安全审计。

## 兼容性检查

当前 `skill-atlas.json` 尚未提供完整的结构化 `compatibility` 字段，因此兼容性必须通过 bundle 内容检查。

对每个候选至少回答：

1. **格式**：`SKILL.md` 是否有合法 frontmatter、`name` 和 `description`？
2. **目标生态**：说明是否绑定 Codex、Claude Code、OpenClaw、Cursor 或其他 Agent？
3. **工具名称**：是否引用目标工具不存在的工具、命令、斜杠命令或专有变量？
4. **外部依赖**：是否需要 Python、Node、Homebrew、Docker、浏览器、CLI 或本地应用？
5. **MCP/连接器**：是否需要特定 MCP server、插件或已登录的外部系统？
6. **凭据**：是否需要 API Key、Token、Cookie、SSH Key 或云凭据？
7. **权限和副作用**：是否执行 shell、联网、读写文件、删除数据、修改账户或发布内容？
8. **平台限制**：是否仅支持 macOS、Windows、Linux 或特定 IDE？
9. **名称冲突**：是否与已安装 Skill 使用相同 frontmatter `name`？
10. **安全与许可证**：来源是否可信、脚本是否审查、许可证是否允许使用或再分发？
11. **验证**：是否能在隔离环境使用无敏感数据的 Prompt 做一次最小测试？

建议使用以下兼容性结论：

- `native`：可直接用于目标工具。
- `portable`：标准 Skill 结构，少量通用依赖。
- `adapter-required`：需要替换工具名、路径或平台指令。
- `dependency-missing`：结构可识别，但当前环境缺少依赖。
- `incompatible`：依赖目标工具不存在的专有能力。
- `unknown`：信息不足，不能可靠判断。

结构可识别不等于 `native`。不要因为文件名是 `SKILL.md` 就跳过以上检查。

本仓库可以确定性提供目录、标签、来源、固定版本和完整性证据，但当前不能对所有 Skill 确定性提供运行时兼容、依赖可用性或授权结论。模型阅读 bundle 后仍然没有足够证据时，输出 `unknown` 是正确结果；不得为了给出肯定答案而补写不存在的依赖、权限或兼容性信息。

## 获取来源和下载链接

仓库内已经保存完整 bundle。只有需要更新、核对上游或在别处重新下载时，才需要恢复来源链接。

### 从索引找到本地目录

```bash
jq -r '
  select(.catalog_path | endswith("/spec-driven-development"))
  | .catalog_path
' reports/overall-catalog.jsonl
```

### GitHub：仓库、固定 commit 和原始路径

```bash
jq '{
  repository: .provenance.repository,
  commit: .provenance.commit,
  source_path: .provenance.source_path
}' "$SKILL_DIR/skill-atlas.json"
```

使用以下命令生成固定到 commit 的 GitHub 浏览链接和仓库 ZIP 链接：

```bash
python3 - "$SKILL_DIR/skill-atlas.json" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import quote

metadata = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
source = metadata["provenance"]
repository = source["repository"].rstrip("/")
commit = source["commit"]
source_path = source["source_path"]

print("repository:", repository)
print("skill_tree:", f"{repository}/tree/{commit}/{quote(source_path)}")
print("repository_zip:", f"{repository}/archive/{commit}.zip")
PY
```

GitHub ZIP 是固定 commit 的整个仓库，不一定只包含一个 Skill。下载后应定位 `source_path`，并使用 `integrity.skill_md_hash` 或 `integrity.content_hash` 校验目标 bundle。

### ClawHub：规范页面和固定版本

先把 ClawHub 候选目录赋给 `SKILL_DIR`，然后读取：

```bash
jq '{
  canonical_url: .provenance.canonical_url,
  owner: .provenance.owner_handle,
  slug: .provenance.slug,
  version: .provenance.version,
  archive_sha256: .integrity.archive_sha256
}' "$SKILL_DIR/skill-atlas.json"
```

`canonical_url` 是面向人类的官方 Skill 页面；下载或安装时必须同时固定 `owner_handle`、`slug` 和 `version`，并校验 `archive_sha256`。不要只写 `latest`，也不要根据 slug 猜测 owner。

先读取固定身份：

```bash
OWNER=$(jq -r '.provenance.owner_handle' "$SKILL_DIR/skill-atlas.json")
SLUG=$(jq -r '.provenance.slug' "$SKILL_DIR/skill-atlas.json")
VERSION=$(jq -r '.provenance.version' "$SKILL_DIR/skill-atlas.json")
REF="@${OWNER}/${SLUG}"
```

使用官方 ClawHub CLI 只读核对固定版本和文件清单：

```bash
# 安装方式：npm install -g clawhub
clawhub inspect "$REF" --version "$VERSION" --files --json
```

使用官方 CLI 把同一固定版本安装到一个临时工作区：

```bash
TARGET_WORKDIR="/tmp/clawhub-skill-install"
mkdir -p "$TARGET_WORKDIR"
clawhub --workdir "$TARGET_WORKDIR" install "$REF" --version "$VERSION"
```

在本仓库快照验证时，`clawhub` 0.23.1 的 `install --help` 明确包含 `--version <version>`。如果未来 CLI 改版，应先运行 `clawhub install --help`，不得静默退回 `latest`。

如果需要的是原始 ZIP 下载链接和字节级校验，而不是安装后的目录，可以按当前官方 CLI 使用的 API 路由生成固定版本链接：

```bash
DOWNLOAD_URL=$(python3 - "$SKILL_DIR/skill-atlas.json" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

metadata = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
source = metadata["provenance"]
registry = source.get("registry", "https://clawhub.ai").rstrip("/")
query = urlencode({
    "slug": source["slug"],
    "ownerHandle": source["owner_handle"],
    "version": source["version"],
})
print(f"{registry}/api/v1/download?{query}")
PY
)

ZIP_PATH="/tmp/clawhub-skill.zip"
curl --fail --location "$DOWNLOAD_URL" --output "$ZIP_PATH"

EXPECTED=$(jq -r '.integrity.archive_sha256' "$SKILL_DIR/skill-atlas.json")
ACTUAL=$(shasum -a 256 "$ZIP_PATH" | awk '{print $1}')
test "$ACTUAL" = "$EXPECTED"
```

`test` 返回 0 才表示 ZIP 与本仓库记录的固定版本字节一致。`/api/v1/download` 是当前官方 CLI 使用的路由，但未来可能变化；失效时以最新版官方 CLI 为准。不要去掉 owner 或 version，也不要在哈希不一致时继续安装。

自动化重新下载还应重新检查注册中心当前的可见性和安全状态；如果条目已下架、隐藏、拦截、版本不存在或哈希不一致，应停止并写入 unresolved。若只是把本仓库已经归档的 bundle 交给另一台机器，优先使用下方的本地打包方式，不依赖上游仍然在线。

### 获取候选的统一来源链接

```bash
jq -r '
  if (.provenance.source_type // "github") == "clawhub"
  then .provenance.canonical_url
  else .provenance.repository
  end
' "$SKILL_DIR/skill-atlas.json"
```

### 打包本地完整 bundle

如果目标只是把仓库中已经归档的候选交给另一台机器，不需要重新访问上游：

```bash
ARCHIVE="/tmp/$(basename "$SKILL_DIR").tar.gz"
tar -C "$(dirname "$SKILL_DIR")" -czf "$ARCHIVE" "$(basename "$SKILL_DIR")"
printf '%s\n' "$ARCHIVE"
```

## 选择性安装到 Codex

Codex 当前使用的项目级 Skill 位置是 `.agents/skills/<skill-name>/`，用户全局位置是 `~/.agents/skills/<skill-name>/`。Codex 支持链接到 Skill 目录。

项目级安装示例：

```bash
mkdir -p .agents/skills
ln -s "$PWD/$SKILL_DIR" ".agents/skills/a5c-spec-driven-development"
```

安装后使用 Codex 的 `/skills` 或 `$skill-name` 检查发现结果。如果没有出现，重启 Codex。

不要把整个 `skills/` 目录一次性链接进去：

- 当前有 11,839 个 bundle；
- 其中 328 个 frontmatter 不符合 Codex 最小要求；
- 667 组 Skill 存在重名，涉及 1,579 个条目；
- 大量 Skill 的描述会挤占发现预算，部分 Skill 可能被省略；
- 一些 Skill 绑定其他 Agent 生态或需要未安装依赖；
- GitHub 来源没有全部经过安全审计。

## 面向大模型的 Prompt → Skill 检索协议

### 第 1 步：解析需求

从用户 Prompt 提取：

- 动作：研究、写作、调试、部署、设计、自动化等；
- 对象：代码、文档、数据、网站、图像、科研资料等；
- 产物：报告、代码、配置、网页、论文等；
- 领域：软件、安全、营销、教育、科学等；
- 用户身份：开发者、研究者、运营、营销人员等；
- 明确约束：目标工具、操作系统、禁止联网、已有 MCP、输出格式等；
- 专有关键词：产品、框架、文件格式、平台名称。

不要在此阶段直接选 Skill。

### 第 2 步：生成检索假设

把需求映射到 `config/taxonomy.json` 中存在的分类和受控标签。生成一个宽查询和一个窄查询：

- 宽查询：主分类或一个核心 `tasks` 标签；
- 窄查询：核心任务 + 产物/领域/受众；
- 全文查询：专有关键词和同义词。

如果标签词表没有用户概念，保留原始关键词进行 `SKILL.md` 全文搜索。

### 第 3 步：召回候选

先查询 `reports/overall-catalog.jsonl`。优先看 `needs_review == false`，但不得永久排除 `needs_review == true`，因为当前大部分记录需要复核。

同时进行：

1. 分类/标签召回；
2. `SKILL.md` 全文召回；
3. 必要时按 GitHub/ClawHub 来源召回。

合并结果并去重，不要根据 `catalog_path` 的 Skill 名称独自判断能力。

先统计每一路召回的数量，不要直接打印全量内容。初次结构化候选最多保留 50 条；再结合专有关键词、说明文本、`needs_review` 和目标环境缩小到 3 至 10 条后，才读取完整 bundle。候选很多时，路径计数和截断是检索步骤，不是遗漏。

### 第 4 步：阅读候选证据

对排名靠前的候选读取：

1. `skill-atlas.json`；
2. 完整 `SKILL.md`；
3. `SKILL.md` 明确引用的 references；
4. 依赖和安装文件；
5. 与执行相关的 scripts。

检查 `classification.reasons`，识别仅因一个歧义关键词造成的误分类。

### 第 5 步：兼容性和风险淘汰

按[兼容性检查](#兼容性检查)逐项判断。特别注意：

- `risk_level` 不是安全结论；
- ClawHub 的聚合状态允许，不代表每个扫描器都同意；
- GitHub 条目默认没有统一安全审计；
- 不得执行未审查脚本来“测试”候选；
- 涉及凭据、网络、删除、发布、支付或账户修改时必须向用户说明。

### 第 6 步：排序

建议按以下证据优先级排序：

1. `SKILL.md` 明确覆盖用户任务和产物；
2. 目标开发工具与运行环境兼容；
3. 所需依赖在用户环境中可用；
4. 权限和副作用可接受；
5. 来源、版本、安全信息和许可证更清晰；
6. 最后才参考自动分类置信度。

不要仅按 `confidence` 排名。

### 第 7 步：向用户报告

推荐结果至少包含：

```text
Skill:
本地路径:
来源链接:
固定版本或 commit:
为什么匹配:
需要的工具/依赖:
权限和副作用:
目标工具兼容性:
分类是否需要复核:
建议的下一步:
```

默认给出 1 至 5 个候选。没有可靠候选时明确说“未找到可靠匹配”，并展示使用过的查询条件，不要虚构 Skill。

### 第 8 步：安装或下载

只有用户明确要求后才执行：

1. 确认唯一候选和固定来源；
2. 确认安装范围是项目级还是用户全局；
3. 检查重名；
4. 复核依赖和危险权限；
5. 复制或链接完整 bundle；
6. 验证目标工具能发现 Skill；
7. 使用无敏感数据的最小 Prompt 进行验证。

## 一个完整检索示例

用户 Prompt：

```text
帮我调研三个竞品的网站和功能差异，最后输出 Markdown 报告。
```

需求拆解：

```text
tasks: research, analyze, write
stages: discover, create
artifacts: report, document
domains: business 或 marketing
keywords: competitor, competitive analysis, website research
```

先做标签宽召回：

```bash
jq -r '
  select((.classification.tasks | index("research")) != null)
  | select((.classification.artifacts | index("report")) != null)
  | .catalog_path
' reports/overall-catalog.jsonl
```

再做全文补召回：

```bash
rg -l -i 'competitor|competitive analysis|content gap' \
  skills \
  -g 'SKILL.md'
```

随后读取候选 `skill-atlas.json` 和 `SKILL.md`，检查是否：

- 真正比较多个竞品，而不是普通网页搜索；
- 能输出 Markdown 或报告；
- 需要浏览器、搜索 API、Firecrawl 或其他 MCP；
- 会把用户的私有商业信息发送到外部服务；
- 能在用户指定的开发工具中运行。

最终推荐应引用实际文件内容，不应只复述自动标签。

## 安全、质量和许可证边界

- ClawHub 条目按采集时注册中心聚合安全状态过滤，但 sidecar 中的单项扫描器可能仍给出警告或不同结论。
- GitHub 来源只做来源、结构和完整性记录，不等于安全审计。
- `risk_level` 来自关键词规则，只能作为复核提示。
- `needs_review: true` 表示目录和标签需要阅读原始文件确认。
- `license: null` 表示没有获得可靠的结构化许可证结论，不表示可以任意再分发。
- `license` 非空时仍要读取 `license_evidence` 或 bundle 内许可证文本，不能只凭 SPDX 名称猜测具体义务。
- `license: null` 时应把授权状态标为 `unknown`：可以在用户授权和本地政策允许的前提下做只读评估，但不得声称可复制、发布、销售或再分发；涉及这些动作时必须先找到上游许可证或取得权利人许可。
- ClawHub 当前发布规则声明 Skill 以 MIT-0 发布，但除非该条目的快照或人工复核形成了许可证证据，不要用“当前平台规则”静默回填历史条目的 `license` 字段。
- 本仓库不自动执行上游脚本，不应为了判断 Skill 而运行未知代码。
- 高风险能力包括但不限于：shell、网络请求、凭据读取、浏览器 Cookie、任意文件访问、删除、账户修改、发布内容和支付。

未归档条目及原因见 `reports/overall-unresolved.json`。常见原因包括安全状态不允许、来源不可访问、映射不唯一、上游内容无法解析和可移植路径冲突。

## 验证仓库状态

这里验证的是权威的合并快照，不是只覆盖基础 GitHub 阶段的 `python -m skill_atlas validate`。

```bash
wc -l reports/overall-catalog.jsonl

jq -e '
  has("catalog_path")
  and has("classification")
  and has("provenance")
  and has("integrity")
' reports/overall-catalog.jsonl >/dev/null

jq '{
  catalog_records,
  full_bundle_hashes_checked,
  physical_sidecars,
  source_type_counts,
  findings_count
}' reports/overall-audit.json
```

当前预期：

```text
catalog_records: 11839
full_bundle_hashes_checked: 11839
physical_sidecars: 11839
github: 9004
clawhub: 2835
findings_count: 0
```

如果 README 中的数字与 `reports/overall-summary.json` 或 `reports/overall-audit.json` 不一致，以报告为准，并更新 README。
