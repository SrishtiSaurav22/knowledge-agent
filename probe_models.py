"""
Probe which Gemini models your key can actually use for THIS agent (tool calling).

Each model gets exactly one small request (1 of its daily free-tier quota).
Run:  python probe_models.py
"""
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Text models that support function calling, best first. TTS/image/audio/robotics/
# computer-use/deep-research/antigravity/gemma models are excluded: they can't run this agent.
CANDIDATES = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
    "gemini-3.8-flash",
]


def search_notion(query: str) -> str:
    """Search Notion pages by keyword."""
    return "[]"


def classify(err: str) -> str:
    if "PerDay" in err:
        return "DAILY QUOTA USED UP (try after reset)"
    if "429" in err or "RESOURCE_EXHAUSTED" in err:
        return "rate limited / no free quota"
    if "503" in err or "UNAVAILABLE" in err:
        return "overloaded right now (retry later)"
    if "404" in err or "NOT_FOUND" in err or "no longer available" in err:
        return "not available to your key"
    return "error: " + err[:120].replace("\n", " ")


def main():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    config = types.GenerateContentConfig(
        tools=[search_notion],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0,
    )
    usable = []
    for model in CANDIDATES:
        try:
            r = client.models.generate_content(
                model=model, contents="Find the Notion page about Orion. Use the tool.", config=config)
            if r.function_calls:
                status = "OK: tool calling works"
                usable.append(model)
            else:
                status = "responds, but did NOT call the tool (unsuitable)"
        except Exception as e:  # noqa: BLE001
            status = classify(str(e))
        print(f"{model:28s} {status}")

    print()
    if usable:
        print("Put this in .env:")
        print(f"GEMINI_MODEL={usable[0]}")
        if len(usable) > 1:
            print(f"GEMINI_FALLBACK_MODEL={','.join(usable[1:4])}")
    else:
        print("No model is usable right now. Paste this output back.")


if __name__ == "__main__":
    main()
