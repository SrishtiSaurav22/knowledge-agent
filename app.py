"""Streamlit UI: a workspace briefing console, not a chat window.

Left: the task and a live timeline of what the agent is doing.
Right: the answer, the sources it actually read, and the actions it took.
Run:  python -m streamlit run app.py
"""
import html
import json
import time
from pathlib import Path

import streamlit as st

from agent import MODEL, run_agent

st.set_page_config(page_title="Knowledge Agent", page_icon="🧭", layout="wide")

SOURCES = {
    "gmail": {"label": "Gmail", "icon": "📧", "color": "#EA4335"},
    "drive": {"label": "Drive", "icon": "📁", "color": "#1FA463"},
    "notion": {"label": "Notion", "icon": "📝", "color": "#8B8B8B"},
    "slack": {"label": "Slack", "icon": "💬", "color": "#A259D9"},
}
TOOL_SOURCE = {
    "search_gmail": "gmail", "read_email": "gmail", "send_email": "gmail",
    "search_drive": "drive", "read_drive_file": "drive",
    "search_notion": "notion", "read_notion_page": "notion", "create_notion_page": "notion",
    "read_slack_channel": "slack", "post_slack": "slack",
}
ACTION_TOOLS = {"send_email", "create_notion_page", "post_slack"}
VERB = {
    "search_gmail": "Searching Gmail", "read_email": "Reading email", "send_email": "Sending email",
    "search_drive": "Searching Drive", "read_drive_file": "Reading document",
    "search_notion": "Searching Notion", "read_notion_page": "Reading Notion page",
    "create_notion_page": "Saving to Notion", "read_slack_channel": "Reading Slack",
    "post_slack": "Posting to Slack",
}

TASKS = {
    "📊 Status check": "What's the current status of the Orion vendor contract? What's decided and what's still open?",
    "🗂️ Brief & save": "Brief me on the Orion vendor contract: decisions, open items with owners, and any "
                       "conflicting information. Save the brief to Notion.",
    "📣 Brief & notify": "Prepare a brief on the Orion contract for the decision meeting, save it to Notion, "
                        "and post the link with the top open items on Slack.",
    "✉️ Brief & email": "Summarise the open items on the Orion contract and email them to me.",
}

RUN_LOG = Path("runs/last_run.json")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1400px;}
.hero {border-radius: 16px; padding: 22px 26px; margin-bottom: 18px;
       background: linear-gradient(120deg, #1e3a8a 0%, #4f46e5 55%, #7c3aed 100%); color: #fff;}
.hero h1 {margin: 0; font-size: 1.7rem; color: #fff;}
.hero p {margin: 6px 0 0; opacity: .88;}
.chips {display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px;}
.chip {flex: 1; min-width: 120px; border-radius: 12px; padding: 10px 14px;
       border: 1px solid rgba(128,128,128,.25); background: rgba(128,128,128,.06);}
.chip .n {font-size: 1.35rem; font-weight: 700;}
.chip .l {font-size: .8rem; opacity: .75;}
.step {border-left: 4px solid var(--c); padding: 7px 12px; margin: 6px 0; border-radius: 0 10px 10px 0;
       background: rgba(128,128,128,.07); font-size: .92rem;}
.step .meta {opacity: .65; font-size: .78rem;}
.step.fail {background: rgba(234,67,53,.10);}
.src {display: flex; gap: 8px; align-items: baseline; padding: 6px 0;
      border-bottom: 1px dashed rgba(128,128,128,.25); font-size: .9rem;}
.tag {font-size: .7rem; font-weight: 700; padding: 2px 8px; border-radius: 999px; color: #fff; background: var(--c);}
.action {border-radius: 10px; padding: 10px 14px; margin: 6px 0; font-size: .92rem;
         background: rgba(31,164,99,.12); border: 1px solid rgba(31,164,99,.35);}
.action.fail {background: rgba(234,67,53,.10); border-color: rgba(234,67,53,.35);}
.muted {opacity: .6; font-size: .9rem;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🧭 Knowledge Agent")
    st.caption("Searches your workspace, connects the dots across tools, and acts on what it finds.")
    st.markdown("**Connected sources**")
    for s in SOURCES.values():
        st.markdown(f"{s['icon']} {s['label']}")
    st.caption("All API calls run through **Swytchcode**: managed OAuth, retries, schema validation.")
    st.caption(f"Model: `{MODEL}`")
    st.divider()
    replay = st.toggle("Replay last run", value=False,
                       help="Re-plays runs/last_run.json with no LLM or API calls. For UI work and demo recording.")

st.markdown("""<div class="hero"><h1>🧭 Knowledge Agent</h1>
<p>Ask about anything in your team's Gmail, Drive, Notion and Slack. Get a cited brief, and
have it saved, shared or emailed.</p></div>""", unsafe_allow_html=True)

if "q" not in st.session_state:
    st.session_state.q = ""

left, right = st.columns([5, 7], gap="large")

with left:
    st.markdown("##### What do you need to know?")
    tcols = st.columns(2)
    for i, (label, prompt) in enumerate(TASKS.items()):
        tcols[i % 2].button(label, use_container_width=True,
                            on_click=lambda p=prompt: st.session_state.update(q=p))
    question = st.text_area("Task", key="q", height=100, label_visibility="collapsed",
                            placeholder="e.g. What did we decide about the Orion pricing, and who owns the open items?")
    go = st.button("Run agent  →", type="primary", use_container_width=True, disabled=not question.strip())
    st.markdown("##### Activity")
    chips_ph = st.empty()
    timeline = st.container()

with right:
    answer_box = st.container(border=True)
    st.markdown("##### Actions taken")
    actions_ph = st.empty()
    st.markdown("##### Sources read")
    sources_ph = st.empty()


def render_chips(counts: dict):
    cells = "".join(
        f'<div class="chip" style="border-top:3px solid {s["color"]}">'
        f'<div class="n">{counts.get(k, 0)}</div><div class="l">{s["icon"]} {s["label"]} calls</div></div>'
        for k, s in SOURCES.items())
    chips_ph.markdown(f'<div class="chips">{cells}</div>', unsafe_allow_html=True)


def summarise_args(args: dict) -> str:
    for key in ("query", "to", "title", "text", "limit"):
        if key in args:
            return f"{key}: {str(args[key])[:70]}"
    return ""


def link_for(source: str, item: dict) -> str:
    if item.get("url"):
        return item["url"]
    if source == "gmail" and item.get("id"):
        return f"https://mail.google.com/mail/u/0/#all/{item['id']}"
    return ""


def replay_events():
    for ev in json.loads(RUN_LOG.read_text(encoding="utf-8"))["events"]:
        time.sleep(0.35)
        yield ev


# Initial empty state
render_chips({})
if not go:
    with answer_box:
        st.markdown('<p class="muted">The brief will appear here: a direct answer first, then decisions, '
                    'open items with owners, and any conflicts between sources, each claim cited.</p>',
                    unsafe_allow_html=True)
    actions_ph.markdown('<p class="muted">Nothing yet. Actions only happen when you ask for them.</p>',
                        unsafe_allow_html=True)
    sources_ph.markdown('<p class="muted">Documents, emails and pages the agent actually read.</p>',
                        unsafe_allow_html=True)
    st.stop()

if replay and not RUN_LOG.exists():
    st.warning("No saved run yet. Turn replay off and run the agent once.")
    st.stop()

counts, catalog, read_items, actions, events = {}, {}, [], [], []
final, pending = None, {}
source_iter = replay_events() if replay else run_agent(question)

with answer_box:
    status = st.status("Working through your workspace…", expanded=False)

for ev in source_iter:
    events.append(ev)
    kind = ev["type"]

    if kind == "tool_call":
        src = TOOL_SOURCE.get(ev["name"], "")
        counts[src] = counts.get(src, 0) + 1
        render_chips(counts)
        pending[ev["name"]] = ev["args"]
        status.update(label=f"{VERB.get(ev['name'], ev['name'])}…")

    elif kind == "tool_result":
        name, src = ev["name"], TOOL_SOURCE.get(ev["name"], "")
        color = SOURCES.get(src, {}).get("color", "#888")
        args = pending.get(name, {})
        try:
            data = json.loads(ev["result"])
        except json.JSONDecodeError:
            data = {}

        # Build a catalog of items seen in search results so reads can be labelled with titles/links.
        for item in data.get("results", []) if isinstance(data.get("results"), list) else []:
            if item.get("id"):
                catalog[item["id"]] = {"source": src,
                                       "title": item.get("subject") or item.get("name") or item.get("title"),
                                       "link": link_for(src, item)}

        read_id = args.get("message_id") or args.get("file_id") or args.get("page_id")
        if read_id and ev["ok"]:
            info = catalog.get(read_id, {"source": src, "title": data.get("subject") or read_id, "link": ""})
            if all(r["id"] != read_id for r in read_items):
                read_items.append({"id": read_id, **info})
        if name == "read_slack_channel" and ev["ok"]:
            read_items.append({"id": "slack", "source": "slack",
                               "title": f"{len(data.get('results', []))} recent channel messages", "link": ""})

        if name in ACTION_TOOLS:
            if ev["ok"]:
                text = {"create_notion_page": f"📝 Saved to Notion: {data.get('url') or 'page created'}",
                        "post_slack": "💬 Posted to Slack",
                        "send_email": f"✉️ Emailed {data.get('to')}: “{data.get('subject')}”"}[name]
            else:
                text = f"⚠️ {VERB[name]} failed: {data.get('error', 'unknown error')}"
            actions.append((ev["ok"], text))

        with timeline:
            st.markdown(
                f'<div class="step{"" if ev["ok"] else " fail"}" style="--c:{color}">'
                f'{"✅" if ev["ok"] else "❌"} <b>{VERB.get(name, name)}</b> '
                f'<span class="meta">{html.escape(summarise_args(args))} · {ev["seconds"]}s</span></div>',
                unsafe_allow_html=True)

    elif kind == "thinking":
        with timeline:
            st.caption(f"💭 {ev['text'][:300]}")

    elif kind == "error":
        status.update(label="Agent stopped", state="error")
        with answer_box:
            st.error(ev["text"])

    elif kind == "final":
        final = ev["text"]

    # Live refresh of the right-hand panels
    if actions:
        actions_ph.markdown("".join(
            f'<div class="action{"" if ok else " fail"}">{html.escape(t)}</div>' for ok, t in actions),
            unsafe_allow_html=True)
    if read_items:
        rows = []
        for r in read_items:
            s = SOURCES.get(r["source"], {"label": "?", "color": "#888"})
            title = html.escape(str(r["title"] or r["id"]))
            title = f'<a href="{html.escape(r["link"])}" target="_blank">{title}</a>' if r["link"] else title
            rows.append(f'<div class="src"><span class="tag" style="--c:{s["color"]}">{s["label"]}</span>{title}</div>')
        sources_ph.markdown("".join(rows), unsafe_allow_html=True)

if not actions:
    actions_ph.markdown('<p class="muted">None requested.</p>', unsafe_allow_html=True)

if final is not None:
    n_calls = sum(counts.values())
    status.update(label=f"Done · {n_calls} tool calls across {len([c for c in counts.values() if c])} sources",
                  state="complete")
    with answer_box:
        st.markdown(final)
    if not replay:
        RUN_LOG.parent.mkdir(exist_ok=True)
        RUN_LOG.write_text(json.dumps({"question": question, "events": events}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
