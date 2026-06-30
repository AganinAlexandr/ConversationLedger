from __future__ import annotations

ALLOWED_PLATFORMS: tuple[str, ...] = (
    "codex",
    "chatgpt",
    "claude",
    "claude_code",
    "cursor",
    "gemini",
    "deepseek",
    "import",
)

PLATFORM_ALIASES: dict[str, str] = {
    "codex": "codex",
    "chatgpt": "chatgpt",
    "chat-gpt": "chatgpt",
    "claude": "claude",
    "claudecode": "claude_code",
    "claude-code": "claude_code",
    "claude_code": "claude_code",
    "cursor": "cursor",
    "gemini": "gemini",
    "deepseek": "deepseek",
    "deep-seek": "deepseek",
    "import": "import",
}


def canonicalize_platform(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "").replace("/", "").replace("_", "_")
    normalized = normalized.replace("-", "-")
    alias_key = normalized
    if alias_key in PLATFORM_ALIASES:
        return PLATFORM_ALIASES[alias_key]

    compact = value.strip().lower().replace(" ", "").replace("-", "").replace("/", "").replace("_", "")
    if compact in PLATFORM_ALIASES:
        return PLATFORM_ALIASES[compact]

    raise ValueError(
        f"Unknown platform family: {value}. Supported: {', '.join(ALLOWED_PLATFORMS)}"
    )

