## Description: <br>
Builds a competitor-relative coverage map of missing topics, keyword gaps, and editorial-calendar opportunities when a user asks to find content gaps or compare what competitors have published. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[aaron-he-zhu](https://clawhub.ai/user/aaron-he-zhu) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>


## Use Case: <br>
Marketing, SEO, GEO, and editorial planning teams use this skill to compare their own site against competitor domains, identify missing topics and formats, and turn prioritized gaps into a content calendar. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Competitor-relative recommendations can be misleading when competitor domains, current site inventory, or analytics data are missing. <br>
Mitigation: Ask for the user's site and 1-3 competitor domains before running the analysis, and mark unavailable metrics as N/A rather than inventing values. <br>
Risk: Private strategy, analytics, or search-console details may be written into reusable memory notes. <br>
Mitigation: Review saved memory notes and avoid storing sensitive business details unless the user has approved that persistence. <br>
Risk: Optional competitor-research connectors may collect external website content and produce estimated signals. <br>
Mitigation: Respect connector boundaries and label each metric as Measured, User-provided, Estimated, or N/A in the final brief. <br>


## Reference(s): <br>
- [Analysis Templates](artifact/references/analysis-templates.md) <br>
- [Gap Analysis Frameworks](artifact/references/gap-analysis-frameworks.md) <br>
- [Example Report](artifact/references/example-report.md) <br>
- [Project Homepage](https://github.com/aaron-he-zhu/aaron-marketing-skills) <br>
- [ClawHub Skill Page](https://clawhub.ai/aaron-he-zhu/skills/content-gap-analysis) <br>
- [Publisher Profile](https://clawhub.ai/user/aaron-he-zhu) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, guidance, configuration] <br>
**Output Format:** [Markdown analysis brief with tables, prioritized recommendations, calendar entries, and a reusable handoff summary] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Labels metrics as Measured, User-provided, Estimated, or N/A; may save reusable summaries to memory/research paths when supported by the host agent.] <br>

## Skill Version(s): <br>
18.0.0 (source: frontmatter and server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
