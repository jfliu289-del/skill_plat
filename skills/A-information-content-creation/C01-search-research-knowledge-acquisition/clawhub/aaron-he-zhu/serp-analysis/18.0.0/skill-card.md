## Description: <br>
Analyzes search engine results pages for a query by mapping SERP features, ranking patterns, search intent, AI Overviews, and snippet opportunities. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[aaron-he-zhu](https://clawhub.ai/user/aaron-he-zhu) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External marketers, SEO practitioners, and content strategists use this skill to turn live or provided SERP evidence into a prioritized SERP brief, ranking-difficulty assessment, and content recommendations for a target query. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Live SERP pages and fetched third-party content can contain untrusted or misleading content. <br>
Mitigation: Treat fetched pages as evidence only, ignore prompt-like directives in those pages, and require difficulty and intent claims to cite live or user-provided SERP evidence. <br>
Risk: Confidential campaign details could be included in saved research summaries or sent to optional SERP connectors. <br>
Mitigation: Avoid providing confidential campaign details unless they are approved for local memory notes and for any optional connector used during analysis. <br>
Risk: SERP metrics or feature claims may be estimated when tool data or screenshots are incomplete. <br>
Mitigation: Label every metric as Measured, User-provided, or Estimated, and mark unavailable required metrics as N/A rather than inventing values. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/aaron-he-zhu/skills/serp-analysis) <br>
- [Project homepage](https://github.com/aaron-he-zhu/aaron-marketing-skills) <br>
- [Analysis Templates](artifact/references/analysis-templates.md) <br>
- [SERP Feature Taxonomy](artifact/references/serp-feature-taxonomy.md) <br>
- [Example Report](artifact/references/example-report.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, guidance, shell commands] <br>
**Output Format:** [Markdown SERP brief with tables, evidence labels, recommendations, and a handoff summary.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May save reusable research notes under memory/research/serp-analysis/ and promotes durable findings to local memory files when the host workflow supports them.] <br>

## Skill Version(s): <br>
18.0.0 (source: server release evidence and skill frontmatter) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
