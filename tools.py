"""
Tool layer: narrow, LLM-friendly wrappers around Swytchcode tools.

Every function returns a JSON string so the model always gets predictable,
compact output. All provider calls go through Swytchcode (auth, retries,
validation, policy); nothing here touches provider credentials.
"""
import base64
import json
import os
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText

from dotenv import load_dotenv
from swytchcode_runtime import exec as swy_exec, SwytchcodeError

load_dotenv()

# Canonical IDs (confirmed by spike.py)
GMAIL_SEARCH = "gmail.user.messages.get"     # GET /users/{userId}/messages
GMAIL_READ = "gmail.user.messages.get1"      # GET /users/{userId}/messages/{id}
DRIVE_SEARCH = "drive.file.list"
DRIVE_EXPORT = "drive.file.export.get"
NOTION_SEARCH = "notion.search.create"
NOTION_READ_MD = "notion.markdown.get"
NOTION_READ_BLOCKS = "notion.children.get"
NOTION_CREATE = "notion.page.create"
SLACK_POST = "slack.chat.postmessage.create"
SLACK_HISTORY = "slack.conversations.history.list"
# Gmail has two "send.create" methods (messages/send and drafts/send). Confirm with `swy info`.
GMAIL_SEND = os.getenv("GMAIL_SEND_TOOL", "gmail.user.send.create")

NOTION_VERSION = os.getenv("NOTION_VERSION", "2025-09-03")
MAX_CHARS = int(os.getenv("MAX_DOC_CHARS", "6000"))


# ---------- helpers ----------

def _data(result):
    """Swytchcode wraps provider responses as {"data": ..., "request": ..., "status_code": ...}."""
    if isinstance(result, dict) and "data" in result:
        return result["data"]
    return result


def _raw_body(out) -> str:
    """Raw-mode output is a JSON envelope string with the provider body under "body"."""
    if isinstance(out, bytes):
        out = out.decode("utf-8", "replace")
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except json.JSONDecodeError:
            return out.lstrip("\ufeff")
    if isinstance(out, dict):
        body = out.get("body", out.get("data", out))
        return (body if isinstance(body, str) else json.dumps(body)).lstrip("\ufeff")
    return str(out)


def _notion_exec(tool: str, args: dict):
    """Send Notion-Version as a header; if the manifest wants it as an input field, retry that way."""
    args = dict(args)
    args["headers"] = {**args.get("headers", {}), "Notion-Version": NOTION_VERSION}
    try:
        return swy_exec(tool, args)
    except SwytchcodeError as e:
        if "Notion-Version" not in (e.message or ""):
            raise
        args["params"] = {**args.get("params", {}), "Notion-Version": NOTION_VERSION}
        return swy_exec(tool, args)


def _exec_flex(tool: str, fields: dict):
    """Some manifests want inputs as the JSON body, others as params. Try body, then params."""
    try:
        return swy_exec(tool, {"body": fields})
    except SwytchcodeError as e:
        if "validation" not in (e.message or "").lower():
            raise
        return swy_exec(tool, {"params": fields})


def _truncate(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n...[truncated]"


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


# ---------- Gmail ----------

def _headers(payload: dict) -> dict:
    h = {x["name"].lower(): x["value"] for x in payload.get("headers", [])}
    if h.get("subject", "").lower().startswith("subject:"):
        h["subject"] = h["subject"][len("subject:"):].strip()
    return h


def _decode(b64: str) -> str:
    return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8", "replace")


def _email_text(payload: dict) -> str:
    """Prefer text/plain parts; fall back to tag-stripped text/html."""
    plain, html = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            html.append(_decode(data))
        for p in part.get("parts") or []:
            walk(p)

    walk(payload)
    if plain:
        return "\n".join(plain)
    return re.sub(r"<[^>]+>", " ", "\n".join(html))


def search_gmail(query: str, max_results: int = 5) -> str:
    """Search the user's Gmail inbox.

    Args:
        query: Gmail search syntax, e.g. "Orion contract", "from:dana subject:pricing", "newer_than:30d Orion".
        max_results: Number of emails to return (1-10).

    Returns id, from, subject, date and snippet for each matching email. Use read_email for the full body.
    """
    n = max(1, min(int(max_results), 10))
    res = _data(swy_exec(GMAIL_SEARCH, {"params": {"userId": "me", "q": query, "maxResults": n}}))
    emails = []
    for m in (res.get("messages") or [])[:n]:
        d = _data(swy_exec(GMAIL_READ, {"params": {"userId": "me", "id": m["id"], "format": "metadata"}}))
        h = _headers(d.get("payload", {}))
        emails.append({
            "id": m["id"],
            "from": h.get("from"),
            "subject": h.get("subject"),
            "date": h.get("date"),
            "snippet": d.get("snippet"),
        })
    return _dumps({"source": "gmail", "query": query, "results": emails})


def read_email(message_id: str) -> str:
    """Read the full body of one email by its id (from search_gmail)."""
    d = _data(swy_exec(GMAIL_READ, {"params": {"userId": "me", "id": message_id, "format": "full"}}))
    payload = d.get("payload", {})
    h = _headers(payload)
    return _dumps({
        "source": "gmail",
        "id": message_id,
        "from": h.get("from"),
        "to": h.get("to"),
        "subject": h.get("subject"),
        "date": h.get("date"),
        "body": _truncate(_email_text(payload)),
    })


def send_email(to: str, subject: str, body: str) -> str:
    """Send a plain-text email from the user's Gmail account.

    Only use this when the user explicitly asks to send or email something, and only to
    recipients the user named. Sending is restricted to an allow-list of addresses.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.
    """
    allowed = [a.strip().lower() for a in os.getenv("EMAIL_ALLOWED_RECIPIENTS", "").split(",") if a.strip()]
    if not allowed:
        return _dumps({"error": "Email sending is disabled (EMAIL_ALLOWED_RECIPIENTS is empty in .env)"})
    if to.strip().lower() not in allowed:
        return _dumps({"error": f"Recipient {to} is not on the allow-list; not sent. Allowed: {allowed}"})
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"], msg["subject"] = to, subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    res = swy_exec(GMAIL_SEND, {"params": {"userId": "me"}, "body": {"raw": raw}})
    d = _data(res) or {}
    # Gmail returns the new message id on success; no id means it wasn't actually sent.
    if not d.get("id"):
        return _dumps({"source": "gmail", "error": "Gmail did not confirm the send (no message id)",
                       "response": res})
    return _dumps({"source": "gmail", "sent": True, "to": to, "subject": subject, "id": d["id"]})


# ---------- Google Drive ----------

def search_drive(query: str, max_results: int = 5) -> str:
    """Search Google Drive by file name and full-text content.

    Args:
        query: Words or a document name to look for, e.g. "Orion Pricing Proposal".
        max_results: Number of files to return (1-10).

    Returns id, name, type, last-modified time and link. Use read_drive_file to read a document.
    """
    n = max(1, min(int(max_results), 10))
    q = query.replace("\\", "\\\\").replace("'", "\\'")
    res = _data(swy_exec(DRIVE_SEARCH, {"params": {
        "q": f"(name contains '{q}' or fullText contains '{q}') and trashed=false",
        "pageSize": n,
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
    }}))
    return _dumps({"source": "drive", "query": query, "results": res.get("files", [])})


def read_drive_file(file_id: str) -> str:
    """Read the text content of a Google Doc (or a Sheet as CSV) by its file id (from search_drive)."""
    last_err = None
    for mime in ("text/plain", "text/csv"):
        try:
            out = swy_exec(DRIVE_EXPORT, {"params": {"fileId": file_id, "mimeType": mime}}, raw=True)
            return _dumps({"source": "drive", "id": file_id, "content": _truncate(_raw_body(out))})
        except SwytchcodeError as e:
            last_err = e.message
    return _dumps({"source": "drive", "id": file_id,
                   "error": f"Could not export this file (only Google Docs/Sheets are supported): {last_err}"})


# ---------- Notion ----------

def _notion_title(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "Untitled"
    return "Untitled"


def search_notion(query: str, max_results: int = 5) -> str:
    """Search Notion pages the integration can access, by title/content.

    Args:
        query: Words to look for, e.g. "Orion evaluation". An empty string lists recent pages.
        max_results: Number of pages to return (1-10).

    Returns id, title, url and last-edited time. Use read_notion_page to read a page.
    """
    n = max(1, min(int(max_results), 10))
    res = _data(swy_exec(NOTION_SEARCH, {"body": {
        "query": query,
        "filter": {"property": "object", "value": "page"},
        "page_size": n,
    }}))
    pages = [{
        "id": p["id"],
        "title": _notion_title(p),
        "url": p.get("url"),
        "last_edited": p.get("last_edited_time"),
    } for p in res.get("results", [])[:n]]
    return _dumps({"source": "notion", "query": query, "results": pages})


def _blocks_to_text(blocks: list) -> str:
    lines = []
    for b in blocks:
        t = b.get("type", "")
        rich = (b.get(t) or {}).get("rich_text", [])
        text = "".join(r.get("plain_text", "") for r in rich)
        if not text:
            continue
        prefix = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### ",
                  "bulleted_list_item": "- ", "numbered_list_item": "1. ", "to_do": "- [ ] "}.get(t, "")
        lines.append(prefix + text)
    return "\n".join(lines)


def read_notion_page(page_id: str) -> str:
    """Read the content of a Notion page by its id (from search_notion)."""
    try:
        d = _data(_notion_exec(NOTION_READ_MD, {"params": {"page_id": page_id}}))
        text = d.get("markdown") if isinstance(d, dict) else d
        if not isinstance(text, str):
            text = _dumps(d)
    except SwytchcodeError:
        # Fallback: read the page's blocks and flatten them to text.
        d = _data(_notion_exec(NOTION_READ_BLOCKS, {"params": {"block_id": page_id, "page_size": 100}}))
        text = _blocks_to_text(d.get("results", []))
    return _dumps({"source": "notion", "id": page_id, "content": _truncate(text)})


def _markdown_to_blocks(content: str) -> list:
    blocks = []
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        kind, text = "paragraph", s
        for pfx, k in (("### ", "heading_3"), ("## ", "heading_2"), ("# ", "heading_1"),
                       ("- ", "bulleted_list_item"), ("* ", "bulleted_list_item")):
            if s.startswith(pfx):
                kind, text = k, s[len(pfx):]
                break
        blocks.append({"object": "block", "type": kind,
                       kind: {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]}})
    return blocks[:100]  # Notion limit per request


def create_notion_page(title: str, content: str) -> str:
    """Save a brief/summary as a new Notion page under the configured parent page.

    Args:
        title: Page title, e.g. "Brief: Orion vendor contract status".
        content: Page body in simple markdown (# headings, - bullets, plain paragraphs).
    """
    parent = os.getenv("NOTION_PARENT_PAGE_ID")
    if not parent:
        return _dumps({"error": "NOTION_PARENT_PAGE_ID is not set in .env"})
    d = _data(_notion_exec(NOTION_CREATE, {"body": {
        "parent": {"page_id": parent},
        "properties": {"title": {"title": [{"text": {"content": title}}]}},
        "children": _markdown_to_blocks(content),
    }}))
    return _dumps({"source": "notion", "created": True, "id": d.get("id"), "url": d.get("url")})


# ---------- Slack ----------

def post_slack(text: str) -> str:
    """Post a message to the team's Slack channel (e.g. a link to a new brief and the key open items).

    Only use this when the user asks to share, notify or post something.
    """
    channel = os.getenv("SLACK_CHANNEL_ID")
    if not channel:
        return _dumps({"error": "SLACK_CHANNEL_ID is not set in .env"})
    d = _data(_exec_flex(SLACK_POST, {"channel": channel, "text": text}))
    if isinstance(d, dict) and d.get("ok") is False:  # Slack returns HTTP 200 with ok=false on errors
        return _dumps({"source": "slack", "error": d.get("error")})
    return _dumps({"source": "slack", "posted": True, "channel": channel, "ts": (d or {}).get("ts")})


def read_slack_channel(limit: int = 20) -> str:
    """Read recent messages from the team's Slack channel, newest first.

    Use this for team discussion, quick decisions and updates that may not be in email or docs.

    Args:
        limit: Number of recent messages to fetch (1-50).
    """
    channel = os.getenv("SLACK_CHANNEL_ID")
    if not channel:
        return _dumps({"error": "SLACK_CHANNEL_ID is not set in .env"})
    n = max(1, min(int(limit), 50))
    d = _data(swy_exec(SLACK_HISTORY, {"params": {"channel": channel, "limit": n}}))
    if isinstance(d, dict) and d.get("ok") is False:
        return _dumps({"source": "slack", "error": d.get("error")})
    msgs = []
    for m in (d or {}).get("messages", []):
        if m.get("subtype") in ("channel_join", "bot_add"):
            continue
        ts = float(m.get("ts", 0))
        msgs.append({
            "user": m.get("user") or m.get("username") or m.get("bot_id"),
            "time": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "text": _truncate(m.get("text", "")),
        })
    return _dumps({"source": "slack", "channel": channel, "results": msgs})


TOOLS = [search_gmail, read_email, send_email,
         search_drive, read_drive_file,
         search_notion, read_notion_page, create_notion_page,
         post_slack]
# read_slack_channel is disabled: Swytchcode's Slack connection lacks the channels:history
# scope ("missing_scope"). Add it back to TOOLS once that scope is available.


if __name__ == "__main__":
    # Quick manual check: python tools.py
    print(search_gmail("Orion", 3))
    print(search_drive("Orion", 3))
    print(search_notion("Orion", 3))

