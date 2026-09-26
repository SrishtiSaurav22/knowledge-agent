"""Streamlit UI: prompt in, live agent trace, final answer out.  Run: streamlit run app.py"""
import json
import time
from pathlib import Path

import streamlit as st

from agent import MODEL, run_agent

st.set_page_config(page_title="Knowledge Agent", page_icon="🔎", layout="wide")

ICONS = {"gmail": "📧", "drive": "📁", "notion": "📝", "slack": "💬"}


def icon_for(tool_name: str) -> str:
    return next((i for k, i in ICONS.items() if k in tool_name), "🔧")


EXAMPLES = {
    "Status check": "What's the current status of the Orion vendor contract? What's decided and what's still open?",
    "Brief + save": "Brief me on the Orion vendor contract: decisions, open items with owners, and any conflicting "
                    "information. Save the brief to Notion.",
    "Brief + notify": "Prepare a brief on the Orion contract for the decision meeting, save it to Notion, "
                      "and notify the team on Slack with the link.",
}

with st.sidebar:
    st.header("Knowledge Agent")
    st.write("Searches **Gmail**, **Google Drive** and **Notion**, reasons over what it finds, "
             "and writes briefs back to Notion / Slack.")
    st.write("All API calls run through **Swytchcode** (auth, retries, validation).")
    st.caption(f"Model: `{MODEL}`")
    st.divider()
    replay = st.toggle("Replay last successful run", value=False,
                       help="Re-plays the saved trace from runs/last_run.json. No LLM or API calls, "
                            "so it costs no quota. Useful for UI work and recording the demo GIF.")

RUN_LOG = Path("runs/last_run.json")


def replay_events():
    for ev in json.loads(RUN_LOG.read_text(encoding="utf-8"))["events"]:
        time.sleep(0.4)
        yield ev

st.title("🔎 Knowledge Agent")

if "q" not in st.session_state:
    st.session_state.q = ""

cols = st.columns(len(EXAMPLES))
for col, (label, prompt) in zip(cols, EXAMPLES.items()):
    col.button(label, use_container_width=True, on_click=lambda p=prompt: st.session_state.update(q=p))

question = st.text_area("Ask a question about your team's knowledge", key="q", height=90)

if st.button("Run agent", type="primary", disabled=not question.strip()):
    final, calls, events = None, 0, []
    if replay and not RUN_LOG.exists():
        st.warning("No saved run yet. Turn replay off and run the agent once.")
        st.stop()
    source = replay_events() if replay else run_agent(question)
    with st.status("Agent working…", expanded=True) as status:
        for ev in source:
            events.append(ev)
            if ev["type"] == "thinking":
                st.info(ev["text"])
            elif ev["type"] == "tool_call":
                calls += 1
                args = json.dumps(ev["args"], ensure_ascii=False)
                st.markdown(f"**Step {ev['step']}** {icon_for(ev['name'])} `{ev['name']}` `{args}`")
            elif ev["type"] == "tool_result":
                label = f"{'✅' if ev['ok'] else '❌'} {ev['name']} result ({ev['seconds']}s)"
                with st.expander(label):
                    try:
                        st.json(json.loads(ev["result"]))
                    except json.JSONDecodeError:
                        st.code(ev["result"])
            elif ev["type"] == "error":
                st.error(ev["text"])
                status.update(label="Agent failed", state="error")
            elif ev["type"] == "final":
                final = ev["text"]
        if final is not None:
            status.update(label=f"Done: {calls} tool calls", state="complete", expanded=False)
            if not replay:
                RUN_LOG.parent.mkdir(exist_ok=True)
                RUN_LOG.write_text(json.dumps({"question": question, "events": events},
                                              ensure_ascii=False, indent=2), encoding="utf-8")

    if final:
        st.subheader("Answer")
        st.markdown(final)
