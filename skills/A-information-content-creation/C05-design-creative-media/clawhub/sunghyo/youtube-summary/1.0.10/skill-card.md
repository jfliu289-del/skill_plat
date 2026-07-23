## Description: <br>
Summarize YouTube videos with youtube2md, including bare YouTube URLs with no instructions, chaptered notes, timestamp links, transcript extraction, and key takeaways. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[sunghyo](https://clawhub.ai/user/sunghyo) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External users and developers use this skill to summarize YouTube videos, extract timestamped transcripts, and produce chaptered Markdown notes with key takeaways. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The local youtube2md CLI and its dependencies process YouTube links and are part of the trust boundary. <br>
Mitigation: Install the pinned youtube2md version documented by the skill and review upstream dependencies before sensitive or production use. <br>
Risk: Full mode may send transcript-derived content to OpenAI through the Codex or OpenAI API provider paths. <br>
Mitigation: For sensitive videos, use simple or transcript mode and avoid enabling provider credentials unless that data sharing is acceptable. <br>
Risk: YouTube cookie configuration can expose signed-in YouTube context to the local tool runtime. <br>
Mitigation: Use cookie options only when needed, keep them out of chat and logs, and prefer short-lived file-based exports. <br>
Risk: Captionless videos can use Whisper STT when captions-only behavior is disabled. <br>
Mitigation: Keep captions-only extraction enabled by default and opt in to audio upload only when it is appropriate for the video. <br>


## Reference(s): <br>
- [youtube2md README](https://github.com/sunghyo/youtube2md#readme) <br>
- [Output Format](references/output-format.md) <br>
- [Summarization Behavior](references/summarization-behavior.md) <br>
- [Security and Installation Considerations](references/security.md) <br>
- [Troubleshooting](references/troubleshooting.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, shell commands, configuration, guidance] <br>
**Output Format:** [Inline Markdown summaries, timestamped transcript text, optional JSON envelopes, and shell command guidance.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Full mode passes through youtube2md Markdown; simple mode summarizes timestamped transcript text; transcript mode returns transcript content.] <br>

## Skill Version(s): <br>
1.0.10 (source: frontmatter and server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
