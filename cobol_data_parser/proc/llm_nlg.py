"""LLM-assisted natural-language rendering for docgen.py's to_markdown_ipo().

An alternative to the mechanical Japanese sentence templates in docgen.py:
takes the same deterministic per-paragraph facts (input items, output items,
already-templated process sentences -- never raw COBOL source) and asks an
LLM to phrase the process section as prose. Each call covers exactly one
paragraph's facts, so cost/latency/context-length scale with paragraph
count, not with overall program size.

Needs the Anthropic Python SDK: pip install cobol-data-parser[llm]
Reads the ANTHROPIC_API_KEY environment variable (standard SDK behavior).
If a `.env` file is present in the current directory (or a parent), it's
loaded first via python-dotenv -- same `.env`/`.env.example` convention as
../mainframe-kotlin -- so ANTHROPIC_API_KEY doesn't need to be exported by
hand. An already-exported environment variable always wins over `.env`.
"""
from __future__ import annotations

try:
    import anthropic
    from dotenv import load_dotenv

    IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # anthropic/python-dotenv not installed
    anthropic = None  # type: ignore[assignment]
    load_dotenv = None  # type: ignore[assignment]
    IMPORT_ERROR = exc

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = (
    "あなたはCOBOLプログラムの仕様書作成を支援するアシスタントです。"
    "与えられた「入力」「出力」「処理内容（機械的に生成された文）」の事実だけを根拠に、"
    "その段落の処理内容を1〜3文の自然な日本語の説明文に書き直してください。"
    "事実にない情報を推測・創作しないでください。説明文のみを出力し、前置きや見出しは付けないでください。"
)


def render_paragraph_narrative(
    paragraph: str,
    inputs: list[str],
    outputs: list[str],
    process_sentences: list[str],
    model: str = _DEFAULT_MODEL,
) -> str:
    """Render one paragraph's IPO facts as natural-language Japanese prose.

    Raises ImportError (with a pip-install hint) if the `anthropic` package
    isn't installed.
    """
    if IMPORT_ERROR is not None:
        raise ImportError(
            "the llm renderer needs the anthropic SDK: pip install cobol-data-parser[llm]"
        ) from IMPORT_ERROR

    load_dotenv()  # picks up ANTHROPIC_API_KEY from ./.env if not already exported

    facts = (
        f"段落名: {paragraph}\n"
        f"入力: {'、'.join(inputs) if inputs else '(なし)'}\n"
        f"出力: {'、'.join(outputs) if outputs else '(なし)'}\n"
        f"処理内容（機械生成）:\n" + "\n".join(f"- {s}" for s in process_sentences)
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": facts}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


__all__ = ["render_paragraph_narrative"]
