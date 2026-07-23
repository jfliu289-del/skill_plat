# Output format

How a summary is presented depends on the mode.

- **Full mode**: youtube2md has already produced a complete, detailed Markdown summary. Output that Markdown **verbatim** as the final answer — do not condense it, re-summarize it, drop chapters or bullets, or reflow it into the compact template below. Append only the `Mode: full` line at the end. The package's detail (which scales with video length and the `--detail` level) is the deliverable; preserve it in full.
- **Simple / transcript modes**: Claude authors the summary from the transcript. Use the structure below.

## Preferred structure — simple / transcript-derived summaries (Markdown)

```md
# <Video Title>

> [Watch on YouTube](<canonical_url>) | Duration: <MM:SS> | Published: <YYYY-MM-DD>

## Summary
<1 dense paragraph (5-9 sentences) covering: context, setup/use, measurements, comparison, caveats, and conclusion>

## Chapters
### <Chapter 1 title>
- <fact-based bullet>
- <fact-based bullet>

### <Chapter 2 title>
- <fact-based bullet>
- <fact-based bullet>

## Key Takeaways
- <practical takeaway>
- <practical takeaway>
- <practical takeaway>

Mode: <full|simple|simple (fallback from full; no summarization provider available)>
```

For transcript-only requests, use the requested transcript format and end with:

```md
Mode: transcript
```

## Section rules

These rules apply to **simple / transcript-derived** summaries that Claude authors. In full mode the package's Markdown is passed through verbatim, so these counts do not apply — never trim the package output down to them.

- **Summary**: write one compact but substantial narrative paragraph, not fragmented mini-bullets. Preserve the argument, setup, evidence, caveats, and conclusion without rewriting the whole transcript.
- **Chapters**: chronological sections with short headings; each section should have 2-4 bullets. Bullets should explain what changed or was learned in that section, not just restate the topic.
- **Key Takeaways**: 6-10 bullets, practical and decision-oriented. Emphasize what matters, why it matters, and any constraints.
- **Scale with length**: the counts above are baselines for a ~10-30 minute video. For longer or denser videos, expand proportionally (more chapters, more bullets, a multi-paragraph summary) rather than compressing everything into the minimum.
- **Mode line**: always end each video result with one plain line showing the actual user-facing mode used: `Mode: full`, `Mode: simple`, `Mode: simple (fallback from full; no summarization provider available)`, or `Mode: transcript`.
- Keep numbers/units explicit when present (price, speed, ping, watts, distance, dates).
- For Korean videos or Korean user requests, write natural Korean with enough context; avoid overly compressed note-style Korean.

## Source-policy-aware usage

- **Full mode succeeded**: the youtube2md Markdown output (`.md`) **is** the final summary. Present it verbatim (appending only the mode line); do not treat it as raw material to re-summarize or shorten.
- **Simple mode**: Claude summarizes from the timestamped transcript text (`.txt`) written by the CLI extract path (`--extract-format timestamped-text`), using the structure above.
- **Transcript mode**: return transcript content or requested transcript artifact details, not a summary.

## Delivery — inline, never as a file

- Deliver the summary as **inline Markdown in the reply itself**, in full. This holds no matter how long it is — a 3-hour video with 100+ timestamped chapters still gets its complete summary pasted into the response.
- **Never** replace the summary with a file attachment, a download/link, or a meta-description of it (e.g. "the summary is long, so I attached it as a Markdown document with 116 chapters and key takeaways"). Length is never a reason to attach, truncate, collapse, or summarize-the-summary.
- The runner writes a `.md/.txt/.json` file as a side effect of running youtube2md; that file is an artifact, not the deliverable. Do not surface its path by default, and do not hand the file over in place of the content.
- Produce a file/export or share a path only when the user explicitly asks for one.
