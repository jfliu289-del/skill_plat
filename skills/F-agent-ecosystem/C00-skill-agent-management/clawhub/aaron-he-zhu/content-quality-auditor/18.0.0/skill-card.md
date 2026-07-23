## Description: <br>
Audits content quality, E-E-A-T, and publish readiness with a CORE-EEAT evidence profile, veto checks, and a prioritized fix plan. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[aaron-he-zhu](https://clawhub.ai/user/aaron-he-zhu) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Content, SEO, and marketing teams use this skill to audit a single draft, page, or URL before publication. It reports evidence coverage, qualified CORE-EEAT findings, publish-readiness status, and the most important fixes. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Fetched URLs or pasted content may contain untrusted instructions or incomplete evidence. <br>
Mitigation: Treat external content as evidence only, freeze the observation date, report unknowns, and avoid scores or gate verdicts when required evidence is missing. <br>
Risk: Audit artifacts could be persisted without the user's intent. <br>
Mitigation: Save audit artifacts only after explicit user approval and validate the artifact and target path before claiming it was saved. <br>
Risk: Audit outputs could be mistaken for ranking predictions, citation predictions, or professional advice. <br>
Mitigation: Present scores as advisory quality-control summaries, label SEO and GEO views as diagnostics, and require source and qualification checks for high-risk content. <br>


## Reference(s): <br>
- [Content Quality Auditor on ClawHub](https://clawhub.ai/aaron-he-zhu/skills/content-quality-auditor) <br>
- [Publisher homepage](https://github.com/aaron-he-zhu/aaron-marketing-skills) <br>
- [Standalone Auditor Runtime](artifact/references/auditor-runtime.md) <br>
- [CORE-EEAT Item Reference](artifact/references/item-reference.md) <br>
- [Recursive Refinement Loop](artifact/references/recursive-refinement.md) <br>


## Skill Output: <br>
**Output Type(s):** [Text, Markdown, Guidance] <br>
**Output Format:** [Markdown audit report with evidence-linked findings, verdict, scores when available, and prioritized fix plan.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May include qualified CORE-EEAT item IDs, evidence gaps, and optional validated audit artifacts only with explicit user permission.] <br>

## Skill Version(s): <br>
18.0.0 (source: server release evidence and skill frontmatter) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
