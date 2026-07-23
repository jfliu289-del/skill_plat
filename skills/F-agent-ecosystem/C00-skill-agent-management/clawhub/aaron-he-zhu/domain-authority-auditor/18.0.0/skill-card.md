## Description: <br>
Audits domain authority, trust, and citation credibility with a peer-relative 40-item CITE profile, evidence coverage checks, and verified manipulation or penalty veto checks. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[aaron-he-zhu](https://clawhub.ai/user/aaron-he-zhu) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Marketing, SEO, and growth teams use this skill to evaluate one domain against a locked peer cohort for trust, citation authority, entity identity, and risk signals. It supports domain-level audit decisions and reruns, not page-level content quality reviews or backlink profiling alone. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The audit may use public and user-supplied SEO, analytics, backlink, console, or security evidence. <br>
Mitigation: Provide only evidence you are comfortable using for the audit and mark private or unavailable data as Unknown rather than treating absence as failure. <br>
Risk: Incomplete peer cohort, market, stage, or domain-type context can produce an undecided or unscored result. <br>
Mitigation: Declare the canonical domain, observation date, market, entity stage, domain type, and locked peer cohort before relying on the report. <br>
Risk: Persisted audit reports may contain sensitive domain evidence. <br>
Mitigation: Persist reports only after explicit authorization and validate the target path and artifact before saving. <br>


## Reference(s): <br>
- [Project homepage](https://github.com/aaron-he-zhu/aaron-marketing-skills) <br>
- [Standalone Auditor Runtime](references/auditor-runtime.md) <br>
- [CITE Domain Authority Report Example](references/example-report.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown report with tables, verdicts, evidence notes, and optional bash commands for validation.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May save a validated audit artifact only after explicit user authorization; returns NOT_SCORED when required scorer inputs or runtime are unavailable.] <br>

## Skill Version(s): <br>
18.0.0 (source: server release evidence and skill frontmatter) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
