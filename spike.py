"""
Spike test: proves search -> read works for Gmail, Drive and Notion
through the Swytchcode Python runtime (the same path the agent will use).

Run from the project folder (C:\\dev\\knowledge-agent) with the venv active:
    python spike.py

If a call fails with a validation error, run `swy info <tool_id>` and fix the
param names below. Every failure prints the full error, so paste it back if stuck.
"""
import json
import os

from dotenv import load_dotenv
from swytchcode_runtime import exec, SwytchcodeError

load_dotenv()

# --- Gmail: confirm with `swy info` which one ends in /messages (search) vs /messages/{id} (read)
GMAIL_SEARCH = "gmail.user.messages.get"
GMAIL_READ = "gmail.user.messages.get1"

DRIVE_SEARCH = "drive.file.list"
DRIVE_EXPORT = "drive.file.export.get"

NOTION_SEARCH = "notion.search.create"
NOTION_READ = "notion.markdown.get"


def find_key(obj, key):
    """Return the first value for `key` anywhere in a nested dict/list (handles response wrappers)."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            hit = find_key(v, key)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = find_key(v, key)
            if hit is not None:
                return hit
    return None


def run(label, tool, args):
    try:
        result = exec(tool, args)
        preview = json.dumps(result, default=str)[:400]
        print(f"OK    {label}  ({tool})\n      {preview}\n")
        return result
    except SwytchcodeError as e:
        print(f"FAIL  {label}  ({tool})\n      {e.message}\n")
        return None


def gmail():
    res = run("gmail search", GMAIL_SEARCH, {"params": {"userId": "me", "maxResults": 3}})
    msgs = find_key(res, "messages") if res else None
    if not msgs:
        print("      -> no message ids found; check GMAIL_SEARCH is the list endpoint\n")
        return
    run("gmail read", GMAIL_READ,
        {"params": {"userId": "me", "id": msgs[0]["id"], "format": "metadata"}})


def drive():
    res = run("drive search", DRIVE_SEARCH, {"params": {
        "q": "mimeType='application/vnd.google-apps.document' and trashed=false",
        "pageSize": 5,
        "fields": "files(id,name,modifiedTime)",
    }})
    files = find_key(res, "files") if res else None
    if not files:
        print("      -> no Google Docs found; create one in the test account's Drive\n")
        return
    # Export returns plain text, not JSON, so ask the runtime for raw output.
    label = f"drive export '{files[0].get('name')}'"
    try:
        text = exec(DRIVE_EXPORT,
                    {"params": {"fileId": files[0]["id"], "mimeType": "text/plain"}},
                    raw=True)
        print(f"OK    {label}  ({DRIVE_EXPORT})\n      {str(text).lstrip(chr(0xFEFF))[:400]}\n")
    except SwytchcodeError as e:
        print(f"FAIL  {label}  ({DRIVE_EXPORT})\n      {e.message}\n")


def notion():
    res = run("notion search", NOTION_SEARCH, {"body": {
        "query": "",
        "filter": {"property": "object", "value": "page"},
        "page_size": 5,
    }})
    pages = find_key(res, "results") if res else None
    if not pages:
        print("      -> no pages visible; reconnect Notion and tick your pages "
              "(swy auth disconnect notion; swy auth connect notion)\n")
        return
    run("notion read", NOTION_READ, {
        "params": {"page_id": pages[0]["id"]},
        "headers": {"Notion-Version": os.getenv("NOTION_VERSION", "2025-09-03")},
    })


def llm():
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        print("SKIP  llm  (no GEMINI_API_KEY in .env)\n")
        return
    try:
        from google import genai
        client = genai.Client(api_key=key)
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        r = client.models.generate_content(model=model, contents="Reply with just: ok")
        print(f"OK    llm ({model}): {r.text.strip()}\n")
    except Exception as e:  # noqa: BLE001 - spike script, show whatever broke
        print(f"FAIL  llm: {e}\n")


if __name__ == "__main__":
    gmail()
    drive()
    notion()
    llm()
