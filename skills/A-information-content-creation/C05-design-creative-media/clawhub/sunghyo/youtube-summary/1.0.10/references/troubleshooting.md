# Troubleshooting

Use `--json` (`YOUTUBE2MD_JSON=1`) when possible to get a structured result envelope with `ok`, `code`, and `outputPath`.

## Quick checks

- Node.js 20.18.1+ installed
- `youtube2md` installed on PATH (recommended pinned install: `npm i -g youtube2md@1.1.0`)
- URL is a valid YouTube link (watch, youtu.be, Shorts, Live, Embed, Music, youtube-nocookie embed)
- URLs containing `&` are quoted in the shell
- A summarization provider is available for full mode:
  - Codex ChatGPT login (`codex login status`), or
  - `OPENAI_API_KEY`
- If captions/audio require signed-in YouTube access, set one of:
  - `YOUTUBE_COOKIES_PATH`
  - `YOUTUBE_COOKIE_HEADER`
- Legacy env override is not set:
  - `YOUTUBE2MD_BIN`

> **Secret handling:** `OPENAI_API_KEY`, `YOUTUBE_COOKIES_PATH`, and `YOUTUBE_COOKIE_HEADER` are credentials. Never paste them into chat or command output, and never commit them. Supply them through secure secret storage or a local `.env`/env file rather than inline in a prompt. Prefer a file-based cookie export (`YOUTUBE_COOKIES_PATH`) over a raw `YOUTUBE_COOKIE_HEADER` string, redact these values from any logs you share, and remember that enabling a provider or Whisper fallback sends transcript/audio-derived content to a third party (OpenAI). See `references/security.md`.

## Common failures and fixes

### 1) `youtube2md` not found

Fix:
- Install pinned binary:
  - `npm i -g youtube2md@1.1.0`
- Verify with:
  - `youtube2md --version`
  - `youtube2md --help`

### 2) Legacy override env rejected

Symptom:
- Runner exits with an error about `YOUTUBE2MD_BIN`.

Fix:
- Unset the env var and rerun:
  - `unset YOUTUBE2MD_BIN`
- Keep using local installed `youtube2md` binary on PATH.

### 3) Full mode without a summarization provider

Symptom:
- Runner warns "no summarization provider available" and switches to simple mode, or `E_SUMMARIZER_UNAVAILABLE` is returned.

Fix:
- Default runner behavior auto-falls back to simple mode; a summary is still produced from the transcript.
- To force hard-fail behavior instead, set:
  - `YOUTUBE2MD_ALLOW_EXTRACT_FALLBACK=0`
- For full mode output, either:
  - log in to Codex with ChatGPT: `codex login` then `codex login status` (requires the optional `@openai/codex-sdk` peer: `npm i -g @openai/codex-sdk`), or
  - set `OPENAI_API_KEY`.
- A Codex session authenticated with an API key does not count as the keyless Codex path.

### 4) Force a specific provider

Fix:
- `YOUTUBE2MD_PROVIDER=codex scripts/run_youtube2md.sh <url> full`
- `YOUTUBE2MD_PROVIDER=openai scripts/run_youtube2md.sh <url> full`
- Default `auto` tries Codex ChatGPT login first, then the OpenAI API.

### 5) Adjust summary detail density

Fix:
- `YOUTUBE2MD_DETAIL=exhaustive scripts/run_youtube2md.sh <url> full` (near transcript-replacement detail)
- `YOUTUBE2MD_DETAIL=concise scripts/run_youtube2md.sh <url> full` (quick overview)
- Upstream default is `balanced`; invalid values fail with `E_INVALID_INPUT` (CLI) or runner exit code 9.
- Requires `youtube2md@1.1.0+` (`--detail` is unknown to older versions).

### 6) Change the full-mode model

Fix:
- Per run, pass the fifth runner argument:
  - `scripts/run_youtube2md.sh <url> full ./summaries/video.md Korean gpt-5.6-luna`
- Or set the runner default env var:
  - `YOUTUBE2MD_DEFAULT_MODEL=<model> scripts/run_youtube2md.sh <url> full`
- Per provider (when `--model` is not passed): `CODEX_MODEL` for the Codex path, `OPENAI_MODEL` for the OpenAI API path.
- If the Codex backend rejects the default model (its catalog changes independently of the OpenAI API), set a supported `CODEX_MODEL`.

### 7) Transcript unavailable or YouTube blocks anonymous access

Symptom:
- Captions are missing/blocked or `E_TRANSCRIPT_UNAVAILABLE` is returned

Fix:
- Prefer a specific caption track first: `YOUTUBE2MD_CAPTION_LANG=<code>` (e.g. `en`, `ko`).
- Retry later / try another video.
- If the video is available only to a signed-in session, provide a YouTube cookie source (treat these as secrets — keep them out of chat, logs, and version control; a file export is safer than an inline header):
  - `YOUTUBE_COOKIES_PATH=./cookies.youtube.json scripts/run_youtube2md.sh <url> extract`
  - `YOUTUBE_COOKIE_HEADER='VISITOR_INFO1_LIVE=...; ...' scripts/run_youtube2md.sh <url> extract`
- For captionless videos, allow the Whisper STT fallback (sends audio to OpenAI; requires `OPENAI_API_KEY`; audio under 24 MB):
  - `YOUTUBE2MD_CAPTIONS_ONLY=0 scripts/run_youtube2md.sh <url> extract`

### 8) Video unavailable

Symptom:
- `E_VIDEO_UNAVAILABLE` (private, deleted, age-restricted) or `E_UNSUPPORTED_URL`

Fix:
- Verify the URL opens in a browser.
- For age-restricted or membership content, provide YouTube cookies (see above).

### 9) OpenAI rate limit

Fix:
- youtube2md retries transient failures with exponential backoff internally; retry the run after a pause if it still fails.
- Optionally use a different model with the fifth runner argument or `YOUTUBE2MD_DEFAULT_MODEL`.

### 10) Output file missing / write failure

Fix:
- Provide explicit writable path:
  - Full: `scripts/run_youtube2md.sh <url> full ./summaries/custom.md`
  - Extract: `scripts/run_youtube2md.sh <url> extract ./summaries/custom.txt`
- Or provide an output directory:
  - `YOUTUBE2MD_OUT_DIR=./output scripts/run_youtube2md.sh <url> extract`
- With `YOUTUBE2MD_JSON=1`, read the exact written path from the envelope's `outputPath`.

### 11) Package trust / version policy

Symptom:
- Security policy blocks unreviewed package installs

Fix:
- Use pinned install: `npm i -g youtube2md@1.1.0`
- Prefer vetted internal mirrors or vendored artifacts in strict environments.
- See `references/security.md` for installation-time risk decisions.

## Structured error codes (`--json`)

Error envelopes are versioned: `{ "schemaVersion": 1, "ok": false, "mode": "...", "code": "...", "message": "..." }`.

- `E_INVALID_INPUT` — missing or invalid CLI argument
- `E_UNSUPPORTED_URL` — unsupported YouTube URL shape or invalid video ID
- `E_VIDEO_UNAVAILABLE` — video is private, deleted, age-restricted, or otherwise unavailable
- `E_TRANSCRIPT_UNAVAILABLE` — no caption track and no usable Whisper path
- `E_SUMMARIZER_UNAVAILABLE` — neither Codex SDK nor the OpenAI API fallback could summarize
- `E_OPENAI_AUTH` — the configured `OPENAI_API_KEY` fallback is invalid
- `E_OPENAI_RATE_LIMIT`
- `E_WHISPER_FAILED`
- `E_NETWORK`
- `E_WRITE_FAILED`
- `E_UNKNOWN` — unexpected unclassified failure

## Recovery response pattern

1. State what failed in one line.
2. Give one concrete retry/fix command.
3. Ask whether to retry automatically.
