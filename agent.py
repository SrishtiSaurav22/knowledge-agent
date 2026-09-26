"""
Knowledge agent: a Gemini tool-calling loop over Gmail, Drive, Notion and Slack.

The loop is written by hand (automatic function calling disabled) so every
step can be streamed to the UI as an event: tool calls, results and the answer.

CLI:  python agent.py "What's the status of the Orion contract?"
"""
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

import tools  # noqa: E402

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_STEPS = int(os.getenv("MAX_STEPS", "8"))

SYSTEM_PROMPT = """You are a knowledge worker agent for a small team. You answer questions
by searching and reading the team's Gmail, Google Drive and Notion, then synthesising
what you find. You can also save notes to Notion, post to Slack and send email.

How to work:
1. Plan which sources are likely to hold the answer. Usually search more than one.
2. Search, then READ the most relevant items before drawing conclusions. Snippets are not enough.
3. Follow references: if an email, page or message mentions a document, meeting or person,
   search for it in the other tools. Chaining sources this way is the core of your job.
4. When sources disagree (e.g. different dates or numbers), prefer the most recent one and
   point out the conflict explicitly.
5. Actions that change things (create_notion_page, post_slack, send_email) happen ONLY when
   the user explicitly asks for them. Never email anyone the user did not name.
   When you post to Slack or send an email after saving a Notion page, include the page link.
6. Be economical: every step costs a model call. Issue ALL independent tool calls in the
   same step (e.g. search every source at once, then read every relevant item at once).
   Aim to finish within 4 steps.

Answer format:
- Lead with a 1-2 sentence direct answer.
- Then sections as useful: Decided, Open items (with owner and deadline if known), Conflicts.
- Cite every claim inline like [Gmail: <subject>], [Drive: <file name>], [Notion: <page title>].
- End with an "Actions taken" line if you saved, posted or sent anything.
- If you couldn't find something, say so instead of guessing.
"""

TOOL_FUNCS = {f.__name__: f for f in tools.TOOLS}


def _text_of(content) -> str:
    parts = getattr(content, "parts", None) or []
    return "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))


# Free-tier quotas are per model, so rotating across models multiplies the daily budget.
# GEMINI_FALLBACK_MODEL may be a comma-separated list, tried in order.
MODELS = [MODEL] + [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODEL", "").split(",")
                    if m.strip() and m.strip() != MODEL]
EXHAUSTED: set[str] = set()  # models whose DAILY quota is used up (kept for the process lifetime)
RETRYABLE = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded", "high demand")


def _retry_after(err: str) -> float:
    m = re.search(r"retry in ([\d.]+)s", err)
    return min(float(m.group(1)), 30) if m else 0


def _generate(client, contents, config):
    """Return (response, model). Skips models with exhausted daily quota, backs off on transient errors."""
    last = None
    for model in [m for m in MODELS if m not in EXHAUSTED]:
        for attempt in range(3):
            try:
                return client.models.generate_content(model=model, contents=contents, config=config), model
            except Exception as e:  # noqa: BLE001
                last, err = e, str(e)
                if not any(tag in err for tag in RETRYABLE):
                    raise
                if "PerDay" in err:          # daily cap: waiting won't help, move to the next model
                    EXHAUSTED.add(model)
                    break
                time.sleep(_retry_after(err) or 2 * 2 ** attempt)  # per-minute cap or overload
    if last is None:
        raise RuntimeError(f"All models have hit their daily free-tier quota: {sorted(EXHAUSTED)}")
    raise last


def run_agent(question: str):
    """Yield events: {"type": "tool_call" | "tool_result" | "thinking" | "final" | "error", ...}."""
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools.TOOLS,  # the SDK builds function declarations from signatures + docstrings
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    current_model = None

    for step in range(1, MAX_STEPS + 1):
        try:
            resp, model = _generate(client, contents, config)
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "text": f"LLM call failed: {e}"}
            return
        if model != current_model:
            if current_model is not None:
                yield {"type": "thinking", "text": f"Switched model: {current_model} -> {model} (quota/overload)"}
            current_model = model

        if not resp.candidates or resp.candidates[0].content is None:
            yield {"type": "error", "text": "The model returned no content (possibly blocked)."}
            return

        content = resp.candidates[0].content
        contents.append(content)  # keep the model turn as-is (preserves thought signatures)
        calls = resp.function_calls or []
        text = _text_of(content)

        if not calls:
            yield {"type": "final", "text": text or "(no answer)", "steps": step - 1}
            return
        if text:
            yield {"type": "thinking", "text": text}

        response_parts = []
        for call in calls:
            args = dict(call.args or {})
            yield {"type": "tool_call", "step": step, "name": call.name, "args": args}
            started = time.time()
            try:
                result = TOOL_FUNCS[call.name](**args)
                ok = "error" not in json.loads(result)
            except Exception as e:  # noqa: BLE001 - report tool errors back to the model so it can recover
                result = json.dumps({"error": f"{type(e).__name__}: {getattr(e, 'message', None) or e}"})
                ok = False
            yield {"type": "tool_result", "step": step, "name": call.name, "ok": ok,
                   "seconds": round(time.time() - started, 1), "result": result}
            response_parts.append(types.Part.from_function_response(name=call.name, response={"result": result}))

        contents.append(types.Content(role="user", parts=response_parts))

    yield {"type": "final", "text": "Stopped after reaching the step limit. Try a narrower question.",
           "steps": MAX_STEPS}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What's the status of the Orion vendor contract, and what's still open?"
    for ev in run_agent(q):
        if ev["type"] == "tool_call":
            print(f"\n[{ev['step']}] -> {ev['name']}({json.dumps(ev['args'], ensure_ascii=False)})")
        elif ev["type"] == "tool_result":
            status = "ok" if ev["ok"] else "ERROR"
            print(f"    <- {status} in {ev['seconds']}s: {ev['result'][:300]}")
        elif ev["type"] == "thinking":
            print(f"\n(thinking) {ev['text']}")
        else:
            print(f"\n=== {ev['type'].upper()} ===\n{ev['text']}")
