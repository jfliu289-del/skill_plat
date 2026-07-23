#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   run_youtube2md.sh <youtube_url> [mode] [output_path] [language] [model]
#
# mode:
#   full    -> summarize to Markdown (needs a summarization provider:
#              Codex SDK with ChatGPT login, or OPENAI_API_KEY)
#   extract -> transcript-only via --extract-only
#              (default format: timestamped-text -> ./summaries/<video_id>.txt)
#
# Examples:
#   run_youtube2md.sh "https://youtu.be/VIDEO_ID"
#   run_youtube2md.sh "https://youtu.be/VIDEO_ID" full ./summaries/video.md Korean gpt-5.6-luna
#   run_youtube2md.sh "https://youtu.be/VIDEO_ID" extract ./summaries/video.txt
#
# Optional env flags:
#   YOUTUBE2MD_JSON=1                 add --json (stdout carries one JSON envelope only)
#   YOUTUBE2MD_STDOUT=1               add --stdout (write content to stdout, no file)
#   YOUTUBE2MD_OUT_DIR                add --out-dir <dir>
#   YOUTUBE2MD_DEFAULT_MODEL          full-mode model when no model arg is passed.
#                                     Unset: upstream default (gpt-5.6-luna) and the
#                                     per-provider CODEX_MODEL / OPENAI_MODEL env vars apply.
#   YOUTUBE2MD_PROVIDER               auto | codex | openai (default: auto)
#   YOUTUBE2MD_DETAIL                 concise | balanced | exhaustive (default: balanced);
#                                     full-mode summary detail density (youtube2md >= 1.1.0)
#   YOUTUBE2MD_CAPTION_LANG           preferred caption language code (en, ko, pt-BR, ...)
#   YOUTUBE2MD_EXTRACT_FORMAT         json | text | timestamped-text (default: timestamped-text)
#   YOUTUBE2MD_CAPTIONS_ONLY          1 (default) never send audio to Whisper in extract mode;
#                                     0 allows Whisper STT fallback when OPENAI_API_KEY is set
#   YOUTUBE2MD_ALLOW_EXTRACT_FALLBACK 1 (default) auto-switch full -> extract when no
#                                     summarization provider is available
#   YOUTUBE_COOKIES_PATH              forwarded to youtube2md for signed-in YouTube access
#   YOUTUBE_COOKIE_HEADER             forwarded to youtube2md for signed-in YouTube access

log() {
  # Runner status goes to stderr so stdout stays a single data payload
  # in --json / --stdout modes (youtube2md >= 1.0.3 wrapper contract).
  echo "$@" >&2
}

run_youtube2md_cli() {
  local -a cli_args=("$@")
  local youtube2md_path

  youtube2md_path="$(type -P youtube2md || true)"

  if [[ -n "$youtube2md_path" && -x "$youtube2md_path" ]]; then
    "$youtube2md_path" "${cli_args[@]}"
    return $?
  fi

  log "ERROR: youtube2md executable is required on PATH."
  log "Install once: npm i -g youtube2md@1.1.0"
  return 13
}

codex_chatgpt_available() {
  # Only a ChatGPT-authenticated Codex session counts as the keyless provider path.
  command -v codex >/dev/null 2>&1 || return 1
  codex login status 2>&1 | grep -qi 'chatgpt'
}

extract_video_id() {
  local url="$1"
  local id=""

  id="$(printf '%s' "$url" | sed -nE 's#.*[?&]v=([^&#]+).*#\1#p' | head -n1)"
  if [[ -z "$id" ]]; then
    id="$(printf '%s' "$url" | sed -nE 's#.*youtu\.be/([^?&#/]+).*#\1#p' | head -n1)"
  fi
  if [[ -z "$id" ]]; then
    id="$(printf '%s' "$url" | sed -nE 's#.*/(shorts|live|embed)/([^?&#/]+).*#\2#p' | head -n1)"
  fi

  printf '%s' "$id"
}

guess_extract_output_path() {
  local url="$1"
  local ext="$2"
  local video_id
  local out_dir

  video_id="$(extract_video_id "$url")"
  out_dir="${YOUTUBE2MD_OUT_DIR:-./summaries}"

  if [[ -n "$video_id" ]]; then
    printf '%s/%s.%s' "$out_dir" "$video_id" "$ext"
  fi
}

URL="${1:-}"
MODE="${2:-full}"
OUTPUT_PATH="${3:-}"
LANGUAGE="${4:-}"
MODEL="${5:-${YOUTUBE2MD_DEFAULT_MODEL:-}}"
PROVIDER="${YOUTUBE2MD_PROVIDER:-auto}"
DETAIL="${YOUTUBE2MD_DETAIL:-}"
EXTRACT_FORMAT="${YOUTUBE2MD_EXTRACT_FORMAT:-timestamped-text}"

# Security hardening: reject binary override to avoid arbitrary command/path execution.
if [[ -n "${YOUTUBE2MD_BIN:-}" ]]; then
  log "ERROR: YOUTUBE2MD_BIN override is not supported for security reasons."
  exit 14
fi

if [[ -z "$URL" ]]; then
  log "ERROR: missing YouTube URL"
  log "Usage: run_youtube2md.sh <youtube_url> [mode] [output_path] [language] [model]"
  exit 2
fi

if [[ "$MODE" != "full" && "$MODE" != "extract" ]]; then
  log "ERROR: mode must be 'full' or 'extract'"
  exit 5
fi

case "$PROVIDER" in
  auto|codex|openai) ;;
  *)
    log "ERROR: YOUTUBE2MD_PROVIDER must be one of: auto, codex, openai"
    exit 7
    ;;
esac

case "$EXTRACT_FORMAT" in
  json|text|timestamped-text) ;;
  *)
    log "ERROR: YOUTUBE2MD_EXTRACT_FORMAT must be one of: json, text, timestamped-text"
    exit 8
    ;;
esac

case "$DETAIL" in
  ""|concise|balanced|exhaustive) ;;
  *)
    log "ERROR: YOUTUBE2MD_DETAIL must be one of: concise, balanced, exhaustive"
    exit 9
    ;;
esac

FALLBACK_FROM_FULL=0

if [[ "$MODE" == "full" ]]; then
  PROVIDER_AVAILABLE=0
  case "$PROVIDER" in
    openai)
      [[ -n "${OPENAI_API_KEY:-}" ]] && PROVIDER_AVAILABLE=1
      ;;
    codex)
      codex_chatgpt_available && PROVIDER_AVAILABLE=1
      ;;
    auto)
      if [[ -n "${OPENAI_API_KEY:-}" ]] || codex_chatgpt_available; then
        PROVIDER_AVAILABLE=1
      fi
      ;;
  esac

  if [[ "$PROVIDER_AVAILABLE" != "1" ]]; then
    if [[ "${YOUTUBE2MD_ALLOW_EXTRACT_FALLBACK:-1}" == "1" ]]; then
      log "WARN: no summarization provider available (Codex ChatGPT login or OPENAI_API_KEY); switching to simple mode"
      MODE="extract"
      FALLBACK_FROM_FULL=1

      if [[ -n "$OUTPUT_PATH" ]]; then
        log "WARN: ignoring full-mode output path during fallback: $OUTPUT_PATH"
        OUTPUT_PATH=""
      fi
    else
      log "ERROR: full mode needs a summarization provider (Codex ChatGPT login or OPENAI_API_KEY)"
      exit 6
    fi
  fi
fi

ARGS=(--url "$URL")

if [[ "$MODE" == "extract" ]]; then
  ARGS+=(--extract-only --extract-format "$EXTRACT_FORMAT")

  if [[ "${YOUTUBE2MD_CAPTIONS_ONLY:-1}" == "1" ]]; then
    ARGS+=(--captions-only)
  fi
fi

if [[ -n "$OUTPUT_PATH" ]]; then
  mkdir -p "$(dirname "$OUTPUT_PATH")"
  ARGS+=(--out "$OUTPUT_PATH")
fi

if [[ -n "${YOUTUBE2MD_OUT_DIR:-}" ]]; then
  mkdir -p "$YOUTUBE2MD_OUT_DIR"
  ARGS+=(--out-dir "$YOUTUBE2MD_OUT_DIR")
fi

if [[ -n "${YOUTUBE2MD_CAPTION_LANG:-}" ]]; then
  ARGS+=(--caption-lang "$YOUTUBE2MD_CAPTION_LANG")
fi

if [[ "$MODE" == "full" ]]; then
  if [[ -n "$LANGUAGE" ]]; then
    ARGS+=(--lang "$LANGUAGE")
  fi

  if [[ -n "$MODEL" ]]; then
    ARGS+=(--model "$MODEL")
  fi

  if [[ "$PROVIDER" != "auto" ]]; then
    ARGS+=(--provider "$PROVIDER")
  fi

  if [[ -n "$DETAIL" ]]; then
    ARGS+=(--detail "$DETAIL")
  fi
fi

if [[ "${YOUTUBE2MD_JSON:-0}" == "1" ]]; then
  ARGS+=(--json)
fi

if [[ "${YOUTUBE2MD_STDOUT:-0}" == "1" ]]; then
  ARGS+=(--stdout)
fi

run_youtube2md_cli "${ARGS[@]}"

# In --json / --stdout modes, stdout must stay a single machine payload:
# report completion on stderr only.
if [[ "${YOUTUBE2MD_JSON:-0}" == "1" || "${YOUTUBE2MD_STDOUT:-0}" == "1" ]]; then
  if [[ "$FALLBACK_FROM_FULL" == "1" ]]; then
    log "INFO: completed in simple mode (full-mode fallback)"
  fi
  log "OK: youtube2md completed"
  exit 0
fi

if [[ "$MODE" == "extract" ]]; then
  if [[ "$FALLBACK_FROM_FULL" == "1" ]]; then
    echo "INFO: completed in simple mode (full-mode fallback)"
  fi
  echo "OK: transcript extracted"

  if [[ "$EXTRACT_FORMAT" == "json" ]]; then
    OUTPUT_EXT="json"
    OUTPUT_LABEL="OUTPUT_JSON"
  else
    OUTPUT_EXT="txt"
    OUTPUT_LABEL="OUTPUT_TXT"
  fi

  if [[ -n "$OUTPUT_PATH" ]]; then
    echo "$OUTPUT_LABEL: $OUTPUT_PATH"
  else
    GUESSED_PATH="$(guess_extract_output_path "$URL" "$OUTPUT_EXT")"
    if [[ -n "$GUESSED_PATH" && -f "$GUESSED_PATH" ]]; then
      echo "$OUTPUT_LABEL: $GUESSED_PATH"
    else
      echo "$OUTPUT_LABEL: ./summaries/<video_id>.$OUTPUT_EXT"
    fi
  fi
else
  echo "OK: summary generated"

  if [[ -n "$OUTPUT_PATH" ]]; then
    echo "OUTPUT_MD: $OUTPUT_PATH"
  else
    GUESSED_PATH="$(guess_extract_output_path "$URL" "md")"
    if [[ -n "$GUESSED_PATH" && -f "$GUESSED_PATH" ]]; then
      echo "OUTPUT_MD: $GUESSED_PATH"
    else
      echo "OUTPUT_MD: ./summaries/<video_id>.md"
    fi
  fi
fi
