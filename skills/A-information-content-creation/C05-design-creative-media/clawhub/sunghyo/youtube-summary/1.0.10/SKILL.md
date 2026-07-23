---
name: youtube-summary
description: "Summarize YouTube videos with youtube2md, including bare YouTube URLs with no instructions, chaptered notes, timestamp links, transcript extraction, and key takeaways."
version: 1.0.10
metadata:
  openclaw:
    emoji: "📺"
    homepage: https://github.com/sunghyo/youtube2md#readme
    primaryEnv: OPENAI_API_KEY
    requires:
      bins:
        - youtube2md
    envVars:
      - name: OPENAI_API_KEY
        required: false
        description: Enables the OpenAI API summarization provider and Whisper STT fallback. When set, transcript/audio-derived content may be sent to OpenAI. Omit to use simple or transcript mode when captions are available.
      - name: YOUTUBE2MD_DEFAULT_MODEL
        required: false
        description: Optional runner default model for full mode. When unset, the upstream youtube2md default (gpt-5.6-luna) and per-provider CODEX_MODEL / OPENAI_MODEL env vars apply.
      - name: OPENAI_MODEL
        required: false
        description: Optional youtube2md model for the OpenAI API provider when --model is not passed (default gpt-5.6-luna). Does not affect the Codex provider.
      - name: CODEX_MODEL
        required: false
        description: Optional youtube2md model for the Codex (ChatGPT login) provider when --model is not passed (default gpt-5.6-luna).
      - name: YOUTUBE2MD_PROVIDER
        required: false
        description: Summarization provider for full mode; auto (default), codex, or openai.
      - name: YOUTUBE2MD_DETAIL
        required: false
        description: Full-mode summary detail density; concise, balanced (upstream default), or exhaustive. Passed to youtube2md as --detail when set.
      - name: YOUTUBE2MD_CAPTION_LANG
        required: false
        description: Preferred caption language code (en, ko, pt-BR, ...); youtube2md falls back to another available track when unavailable.
      - name: YOUTUBE_COOKIES_PATH
        required: false
        description: Optional EditThisCookie JSON export for youtube.com; used when captions/audio require signed-in YouTube access.
      - name: YOUTUBE_COOKIE_HEADER
        required: false
        description: Optional raw YouTube Cookie header for authenticated metadata, caption, or audio fallback requests.
---

# YouTube Summary (youtube2md)

Use the official `youtube2md` CLI behavior from the package/repository (pinned `youtube2md@1.1.0`).

## Runtime + security prerequisites

- Require **Node.js 20.18.1+**.
- Require preinstalled `youtube2md` on PATH.
  - Recommended pinned install: `npm i -g youtube2md@1.1.0`
- Default runner uses the local `youtube2md` executable only.
- Runtime npm execution (`npx`) is intentionally not supported by this skill runner.
- The `YOUTUBE2MD_BIN` environment variable override is rejected by the runner.
- Full mode needs a summarization provider; with `--provider auto`, youtube2md tries:
  1. **Codex SDK with ChatGPT login** — used when the optional `@openai/codex-sdk` peer is installed and a ChatGPT-authenticated Codex session exists. `OPENAI_API_KEY` is not passed to Codex.
  2. **OpenAI API** — used when Codex is unavailable or fails and `OPENAI_API_KEY` is set.
- Either provider sends transcript-derived content to OpenAI systems; for sensitive content, use simple or transcript mode when captions are available.
- Model default: the runner passes `--model` only when the fifth runner argument or `YOUTUBE2MD_DEFAULT_MODEL` is set; otherwise the upstream default (`gpt-5.6-luna` for both providers) and the per-provider `CODEX_MODEL` / `OPENAI_MODEL` env vars apply.
- Extract mode passes `--captions-only` by default: audio is never sent to Whisper in simple/transcript mode. Set `YOUTUBE2MD_CAPTIONS_ONLY=0` to allow Whisper STT for captionless videos (requires `OPENAI_API_KEY`).
- `YOUTUBE_COOKIES_PATH` or `YOUTUBE_COOKIE_HEADER` can be used when YouTube blocks anonymous caption/audio access.
- In sensitive environments, audit upstream `youtube2md@1.1.0` and dependencies before installation or future version bumps.

See `references/security.md` before first-time install/enable.

## Workflow

1. Validate input
   - Accept `youtube.com` and `youtu.be` URLs (watch, Shorts, Live, Embed, Music, and `youtube-nocookie.com` embed shapes are supported; timestamped `&t=` URLs are accepted but the whole video is processed).
   - Quote URLs containing `&` when passing them to the shell.
   - If a message contains only YouTube URL(s), treat it as a request to summarize with this skill.
   - If YouTube URL(s) are provided without an explicit task, default to summary output, not transcript-only output.
   - If URLs are missing, ask for one URL per line.

2. Choose mode
   - **Full mode**: generates Markdown with youtube2md's summarization pipeline (Codex ChatGPT login first, then OpenAI API).
     - If a provider is available (Codex ChatGPT login or `OPENAI_API_KEY`) and external API use is acceptable, try full mode first.
     - Detail density is tunable via `YOUTUBE2MD_DETAIL=concise|balanced|exhaustive` (upstream default: balanced). Use `exhaustive` when the user asks for a very detailed / near-transcript summary, `concise` for a quick overview.
   - **Simple mode**: uses youtube2md `--extract-only --extract-format timestamped-text --captions-only` internally to produce a timestamped `.txt` transcript, then summarizes from that transcript.
     - Use when no provider is available, content is sensitive, external API use is not acceptable, or full mode fails/falls back.
   - **Transcript mode**: uses the same extract path and returns transcript output without a summary.
     - Use when the user asks for transcript extraction, transcript-only output, raw transcript, or machine-readable transcript JSON (`YOUTUBE2MD_EXTRACT_FORMAT=json`).
   - Prefer a **no-error path**: the runner pre-checks provider availability and switches to the extract path automatically when full mode cannot run.

3. Run converter
   - Preferred runner script:
     - `scripts/run_youtube2md.sh <url> full [output_md_path] [language] [model]`
       - If no summarization provider is available, runner auto-falls back to the internal extract path; disclose summary output as simple mode.
       - `[model]` and `YOUTUBE2MD_DEFAULT_MODEL` are optional; when omitted, upstream defaults apply.
     - `scripts/run_youtube2md.sh <url> extract [output_txt_path]`
       - `extract` is the runner/CLI mode name; default artifact is timestamped text (`.txt`).
       - Disclose it as `simple` when summarizing from the `.txt`.
       - Disclose it as `transcript` when returning transcript-only output.
   - Optional machine-readable CLI output:
     - `YOUTUBE2MD_JSON=1 scripts/run_youtube2md.sh <url> full`
     - `YOUTUBE2MD_JSON=1 scripts/run_youtube2md.sh <url> extract`
     - With `--json` or `--stdout` active, stdout carries a single data payload; runner status goes to stderr.
   - Optional stdout/no-file mode:
     - `YOUTUBE2MD_STDOUT=1 scripts/run_youtube2md.sh <url> extract`
   - Optional output directory:
     - `YOUTUBE2MD_OUT_DIR=./output scripts/run_youtube2md.sh <url> extract`
   - Optional caption language preference:
     - `YOUTUBE2MD_CAPTION_LANG=ko scripts/run_youtube2md.sh <url> extract`
   - Optional full-mode detail density:
     - `YOUTUBE2MD_DETAIL=exhaustive scripts/run_youtube2md.sh <url> full`
   - Runtime controls:
     - Use only locally installed `youtube2md` executable.
     - Do not use runtime npm execution (`npx`) for this skill.
   - Direct CLI equivalent:
     - Full: `youtube2md --url <url> [--out <path>] [--out-dir <dir>] [--lang <language>] [--model <model>] [--provider auto|codex|openai] [--detail concise|balanced|exhaustive]`
     - Simple/transcript: `youtube2md --url <url> --extract-only --extract-format timestamped-text --captions-only [--out <path>]`
     - Add `--caption-lang <code>` to prefer a caption language.
     - Add `--json` for a versioned machine-readable result envelope (includes `outputPath`).
     - Add `--stdout` to write output to stdout instead of a file.

4. Verify output
   - Full mode: Markdown file exists and is non-empty unless `--stdout` is used.
   - Simple mode: timestamped `.txt` transcript exists and is non-empty when file output is used.
   - Transcript mode: `.txt` or `.json` transcript output exists and is non-empty, unless `--stdout` is used.
   - If using `--json`, parse the envelope: `ok: true/false`, `outputPath`, `transcriptSource`, `actualLanguage`, `provider`, `fallbackUsed`; handle error `code` per `references/troubleshooting.md`.

5. Respond to the user
   - Follow `references/output-format.md` for the response shape: full mode is a **verbatim pass-through** of the package Markdown; simple/transcript modes use the compact authored structure.
   - Follow `references/summarization-behavior.md` for source policy and chapter/takeaway density.
   - Deliver the summary **inline in the reply**, in full — never as a file attachment, download link, or a meta-description in place of the content, no matter how long. A 3-hour video with 100+ chapters still gets its complete summary pasted into the response; length is never a reason to attach, truncate, or summarize-the-summary.
   - Do **not** include generated local file path(s) in normal user-facing replies.
   - Share file paths, or produce an export file, only when explicitly requested by the user (e.g., debugging/export workflows).
   - **Summary source policy:**
     - Full mode succeeded -> the youtube2md Markdown output **is** the final summary; present it verbatim (append only the mode line). Do **not** re-summarize, condense, drop chapters/bullets, or reflow it into the compact template — that discards the detail the package produced. This is what makes the skill match the detail of running `youtube2md` directly.
     - Simple mode -> Claude summarizes from the timestamped `.txt` transcript using the compact structure in `references/output-format.md`.
     - Transcript mode -> return transcript content or requested transcript artifact details, not a summary.
   - Always append a final mode line after the user-facing result:
     - `Mode: full`
     - `Mode: simple`
     - `Mode: simple (fallback from full; no summarization provider available)` when full was requested but the runner fell back and a summary was still produced.
     - `Mode: transcript` when transcript-only output was requested.
   - Keep user-facing flow smooth: if no provider is available, use simple output and summarize from `.txt` without surfacing avoidable tool-error noise.

## Multi-video requests

- Process URLs sequentially.
- Return per-video results (omit local file paths unless requested).
- Include the final mode line for each video result.
- If any fail, report successful items first, then failures with fixes.

## Built-in behavior to trust

- Default output paths:
  - Full mode: `./summaries/<video_id>.md`
  - Simple/transcript modes: `./summaries/<video_id>.txt` (timestamped text) or `./summaries/<video_id>.json` (`YOUTUBE2MD_EXTRACT_FORMAT=json`)
- Model defaults: upstream youtube2md defaults to `gpt-5.6-luna` for both providers; `CODEX_MODEL` / `OPENAI_MODEL` override per provider; the fifth runner argument or `YOUTUBE2MD_DEFAULT_MODEL` overrides everything via `--model`.
- Detail levels (`--detail`, full mode): summary density scales with video length and content density at every level; the flag only shifts the target band (`concise` ≈ one bullet per ~360 transcript tokens, `balanced` ≈ ~210 (default), `exhaustive` ≈ ~120, near transcript-replacement). Responses that fall below the requested band are re-requested once automatically.
- Transcript strategy:
  - YouTube captions via watch-page / InnerTube requests, with YouTube cookies when configured; `--caption-lang` prefers an exact match, then the same base language, then another track.
  - `youtube-transcript` fallback.
  - Whisper STT fallback (`whisper-1`, audio under 24 MB) when `OPENAI_API_KEY` is available; skipped under `--captions-only` (the runner's extract-mode default) or when no API key is set.
- Timestamps render as `[MM:SS]` (or `[H:MM:SS]` past one hour); chapter display times and `?t=` links always agree.

## Packaging hygiene

- Do not publish generated outputs (e.g., `summaries/*.md`, `summaries/*.txt`, `summaries/*.json`) inside the skill folder.
- Keep only source files (`SKILL.md`, `scripts/`, `references/`) in release artifacts.

## Resources

- CLI runner: `scripts/run_youtube2md.sh`
- Output guidance: `references/output-format.md`
- Behavior reference: `references/summarization-behavior.md`
- Security/install notes: `references/security.md`
- Troubleshooting and error codes: `references/troubleshooting.md`
