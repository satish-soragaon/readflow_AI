"""
AI provider adapters for ReadFlow AI.

Architecture:
  - BaseAIProvider     — interface every adapter must implement.
  - AnthropicProvider  — calls Claude via the anthropic SDK.
  - OpenAIProvider     — calls GPT via the openai SDK.
  - DisabledAIProvider — text-extraction fallback when no key is configured.
  - get_ai_provider()  — factory that reads Flask app config and returns the
                         right adapter; always falls back to Disabled gracefully.
"""

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Maximum words forwarded to any AI provider.
# Keeps costs predictable and avoids context-window limits on huge documents.
_MAX_AI_WORDS = 10_000

# Shared (title, instruction) pairs for each task type.
_TASK_PROMPTS: dict[str, tuple[str, str]] = {
    "summary": (
        "Summary",
        "Write a clear, concise summary of the following text in 3-5 paragraphs. "
        "Focus on the main ideas, key arguments, and important conclusions. "
        "Use Markdown formatting.",
    ),
    "takeaways": (
        "Key Takeaways",
        "List the 5-7 most important takeaways from the following text. "
        "Use a Markdown bullet list. Each bullet should be one or two sentences.",
    ),
    "flashcards": (
        "Flashcards",
        "Create 8-10 study flashcards for the following text. "
        "Format each card as:\n**Q:** question\n**A:** answer\n\n"
        "Cover key concepts, definitions, and facts.",
    ),
    "quiz": (
        "Comprehension Quiz",
        "Create a 5-question multiple-choice comprehension quiz for the following text. "
        "Number each question. Provide four options (A-D) per question. "
        "Add an 'Answers:' section at the end listing the correct letters.",
    ),
    "study_notes": (
        "Study Notes",
        "Create detailed study notes for the following text. "
        "Use Markdown with ## headers for major topics, ### for subtopics, "
        "and bullet lists for key points and definitions.",
    ),
    "vocabulary": (
        "Vocabulary Builder",
        "Identify 10-15 advanced or domain-specific vocabulary words from the following text. "
        "For each word provide: the word in bold, its definition, and a usage example "
        "from the text. Use a Markdown bullet list.",
    ),
}


@dataclass
class AIResult:
    title: str
    content: str        # Markdown string; rendered to HTML in the template
    is_error: bool = field(default=False)


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseAIProvider:
    """Contract that every provider adapter must fulfil."""
    name = "base"

    def generate(self, task: str, text: str) -> AIResult:
        raise NotImplementedError


# ── Disabled (text-extraction fallback) ──────────────────────────────────────

class DisabledAIProvider(BaseAIProvider):
    """
    Fallback provider — extracts key sentences from the text without any
    API call.  Used when AI_PROVIDER=disabled or an API key is missing.
    """
    name = "disabled"

    def generate(self, task: str, text: str) -> AIResult:
        words = text.split()
        sentences = [
            s.strip()
            for s in text.replace("?", ".").replace("!", ".").split(".")
            if s.strip()
        ]
        top = sentences[:6] or [" ".join(words[:120]) or "No readable content."]
        title, _ = _TASK_PROMPTS.get(task, ("AI Output", ""))

        if task == "summary":
            return AIResult(title, "\n\n".join(top[:3]))
        if task == "takeaways":
            bullets = "\n".join(f"- {s}" for s in top[:5])
            return AIResult(title, bullets)
        if task == "flashcards":
            cards = "\n\n".join(
                f"**Q:** What is the main idea of passage {i + 1}?\n**A:** {s}"
                for i, s in enumerate(top[:5])
            )
            return AIResult(title, cards)
        if task == "quiz":
            questions = "\n\n".join(
                f"{i + 1}. What does this imply: _{s[:120]}_?"
                for i, s in enumerate(top[:5])
            )
            return AIResult(title, questions)
        if task == "study_notes":
            bullets = "\n".join(f"- {s}" for s in top[:6])
            return AIResult(title, f"## Notes\n\n{bullets}")
        if task == "vocabulary":
            candidates = sorted(
                {w.strip(".,;:!?()[]\"'").lower() for w in words if len(w.strip(".,;:!?()[]\"'")) > 8}
            )[:12]
            if candidates:
                lines = "\n".join(
                    f"- **{w}**: _definition not available without an AI provider_"
                    for w in candidates
                )
            else:
                lines = "_No advanced vocabulary detected._"
            return AIResult(title, lines)

        return AIResult(title, " ".join(words[:200]))


# ── Anthropic ─────────────────────────────────────────────────────────────────

class AnthropicProvider(BaseAIProvider):
    """Calls Claude via the `anthropic` SDK."""
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-opus-4-8") -> None:
        self._api_key = api_key
        self._model = model

    def generate(self, task: str, text: str) -> AIResult:
        try:
            import anthropic  # optional dependency

            title, instruction = _TASK_PROMPTS.get(
                task, ("AI Output", "Analyse and summarise the following text.")
            )
            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": f"{instruction}\n\n---\n\n{_truncate(text)}",
                    }
                ],
            )
            content = message.content[0].text if message.content else ""
            return AIResult(title=title, content=content)

        except ImportError:
            log.error("anthropic package is not installed.")
            return _error_result(
                "The `anthropic` package is not installed. Run: `pip install anthropic`"
            )
        except Exception as exc:
            log.exception("Anthropic API error for task=%s", task)
            return _error_result(f"Anthropic API error: {exc}")


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIProvider(BaseAIProvider):
    """Calls GPT via the `openai` SDK."""
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._api_key = api_key
        self._model = model

    def generate(self, task: str, text: str) -> AIResult:
        try:
            from openai import OpenAI  # optional dependency

            title, instruction = _TASK_PROMPTS.get(
                task, ("AI Output", "Analyse and summarise the following text.")
            )
            client = OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": "You are a helpful study assistant."},
                    {
                        "role": "user",
                        "content": f"{instruction}\n\n---\n\n{_truncate(text)}",
                    },
                ],
            )
            content = response.choices[0].message.content or ""
            return AIResult(title=title, content=content)

        except ImportError:
            log.error("openai package is not installed.")
            return _error_result(
                "The `openai` package is not installed. Run: `pip install openai`"
            )
        except Exception as exc:
            log.exception("OpenAI API error for task=%s", task)
            return _error_result(f"OpenAI API error: {exc}")


# ── Factory ───────────────────────────────────────────────────────────────────

def get_ai_provider() -> BaseAIProvider:
    """
    Read Flask app config and return the appropriate provider.

    Falls back to DisabledAIProvider with a warning if the named provider
    is missing its API key or package.
    """
    from flask import current_app

    name = current_app.config.get("DEFAULT_AI_PROVIDER", "disabled")

    if name == "anthropic":
        api_key = current_app.config.get("ANTHROPIC_API_KEY")
        if api_key:
            model = current_app.config.get("ANTHROPIC_MODEL", "claude-opus-4-8")
            return AnthropicProvider(api_key=api_key, model=model)
        log.warning(
            "AI_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set; using disabled provider."
        )

    elif name == "openai":
        api_key = current_app.config.get("OPENAI_API_KEY")
        if api_key:
            model = current_app.config.get("OPENAI_MODEL", "gpt-4o")
            return OpenAIProvider(api_key=api_key, model=model)
        log.warning(
            "AI_PROVIDER=openai but OPENAI_API_KEY is not set; using disabled provider."
        )

    return DisabledAIProvider()


# ── Private helpers ───────────────────────────────────────────────────────────

def _truncate(text: str, max_words: int = _MAX_AI_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return (
        " ".join(words[:max_words])
        + "\n\n_[Document truncated to first 10 000 words for AI analysis.]_"
    )


def _error_result(message: str) -> AIResult:
    return AIResult(
        title="Error",
        content=f"> **AI generation failed.**\n>\n> {message}",
        is_error=True,
    )
