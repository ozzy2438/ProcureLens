"""Professional Streamlit decision workspace for the ProcureLens release demo."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pandas as pd
import streamlit as st

API_BASE_URL = os.getenv("PROCURELENS_API_URL", "http://127.0.0.1:8000").rstrip("/")
OPPORTUNITY_PATH = Path(os.getenv("DEMO_OPPORTUNITIES_PATH", "config/demo_opportunities.json"))
DRAFT_BANNER = "DRAFT — analyst review required"
FIT_COLOURS = {"strong_fit": "#0B7A53", "review": "#B26A00", "low_fit": "#B42318"}
RISK_COLOURS = {"low": "#0B7A53", "medium": "#B26A00", "high": "#B42318"}

st.set_page_config(
    page_title="ProcureLens | Federal Bid Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root { --ink:#102A43; --muted:#627D98; --line:#D9E2EC; --blue:#1463FF; }
      .stApp { background: #F5F8FC; color: var(--ink); }
      [data-testid="stSidebar"] { background: #0B1F33; }
      [data-testid="stSidebar"] * { color: #EAF2F8; }
      [data-testid="stSidebar"] .stButton button { border-color:#486581; }
      .block-container { max-width: 1500px; padding-top: 1.4rem; padding-bottom: 3rem; }
      .pl-hero {
        border-radius: 18px; padding: 1.4rem 1.6rem; margin-bottom: 1rem;
        color: white; background: linear-gradient(115deg,#071D33 0%,#123F68 60%,#1463FF 130%);
        box-shadow: 0 12px 30px rgba(16,42,67,.14);
      }
      .pl-hero h1 { margin:0; font-size:2rem; letter-spacing:-.03em; }
      .pl-hero p { margin:.35rem 0 0; color:#D9EAF7; }
      .pl-kicker { text-transform:uppercase; letter-spacing:.13em; font-size:.72rem;
        font-weight:700; color:#9FB3C8; }
      .pl-card { background:white; border:1px solid var(--line); border-radius:14px;
        padding:1.05rem 1.15rem; min-height:100%; }
      .pl-card h3 { margin:.15rem 0 .4rem; color:var(--ink); }
      .pl-card p { color:var(--muted); }
      .pl-pill { display:inline-block; padding:.22rem .58rem; border-radius:999px;
        font-size:.74rem; font-weight:700; margin-right:.25rem; }
      .pl-draft { border:1px solid #F4C95D; background:#FFF8E1; color:#7A5200;
        border-radius:12px; padding:.8rem 1rem; font-weight:700; }
      .pl-source { border-left:3px solid #1463FF; padding-left:.75rem; margin:.5rem 0; }
      [data-testid="stMetric"] { background:white; border:1px solid var(--line);
        border-radius:14px; padding:.8rem 1rem; }
      [data-testid="stMetric"] * { color:var(--ink) !important; }
      [data-testid="stDataFrame"] { border:1px solid var(--line);
        border-radius:14px; overflow:hidden; }
      div[data-testid="stTabs"] button { font-weight:650; color:#526D82 !important; }
      div[data-testid="stTabs"] button[aria-selected="true"] { color:#D9485F !important; }
      [data-testid="stMain"] p, [data-testid="stMain"] li,
      [data-testid="stMain"] h1, [data-testid="stMain"] h2,
      [data-testid="stMain"] h3, [data-testid="stMain"] h4,
      [data-testid="stMain"] label { color:var(--ink); }
      [data-testid="stMain"] a { color:#087EA4; }
      [data-testid="stMain"] [data-testid="stCaptionContainer"] p { color:var(--muted); }
      [data-testid="stChatMessage"] { background:white; border:1px solid var(--line);
        border-radius:14px; }
      [data-testid="stMain"] .pl-hero, [data-testid="stMain"] .pl-hero h1,
      [data-testid="stMain"] .pl-hero p { color:white !important; }
      [data-testid="stMain"] .pl-card p { color:var(--muted) !important; }
      [data-testid="stMain"] .pl-source, [data-testid="stMain"] .pl-source strong,
      [data-testid="stMain"] .pl-source small { color:var(--ink) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_demo_catalogue(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("opportunities"), list):
        raise ValueError("demo opportunity catalogue is invalid")
    return payload


def api_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=90) as client:
        response = client.request(method, f"{API_BASE_URL}{path}", json=payload)
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        raise ValueError("API returned a non-object response")
    return body


@st.cache_data(ttl=15, show_spinner=False)
def load_health(_api_url: str) -> dict[str, Any]:
    return api_json("GET", "/health/ready")


def fit_payload(opportunity: dict[str, Any], as_of_date: str) -> dict[str, Any]:
    keys = (
        "tender_id",
        "unspsc_category",
        "agency",
        "estimated_value_aud",
        "procurement_method",
        "tender_title",
        "tender_description",
        "close_date",
        "agency_recent_tech_spend_aud",
        "agency_familiarity_count",
        "supplier_hhi",
    )
    return {**{key: opportunity.get(key) for key in keys}, "as_of_date": as_of_date}


def risk_payload(opportunity: dict[str, Any]) -> dict[str, Any]:
    return {
        "agency": opportunity["agency"],
        "unspsc_category": opportunity["unspsc_category"],
        "procurement_method": opportunity["procurement_method"],
        "contract_value_aud": opportunity["estimated_value_aud"],
        "contract_duration_days": opportunity["contract_duration_days"],
        "award_date": opportunity["published_date"],
        "supplier_prior_contracts": opportunity["supplier_prior_contracts"],
        "supplier_prior_amendment_rate": opportunity["supplier_prior_amendment_rate"],
        "supplier_agency_prior_contracts": opportunity["supplier_agency_prior_contracts"],
    }


@st.cache_data(ttl=300, show_spinner=False)
def score_catalogue(
    _api_url: str, catalogue_json: str, as_of_date: str
) -> list[dict[str, Any]]:
    opportunities = json.loads(catalogue_json)
    if not isinstance(opportunities, list):
        raise ValueError("opportunities must be a list")
    scored = [{**item} for item in opportunities]
    with httpx.Client(timeout=120) as client:
        risk_response = client.post(
            f"{API_BASE_URL}/predict/amendment-risk/batch",
            json={"items": [risk_payload(item) for item in scored]},
        )
        risk_response.raise_for_status()
        risks = risk_response.json()["predictions"]
        for index, item in enumerate(scored):
            fit_response = client.post(
                f"{API_BASE_URL}/predict/fit-score",
                json=fit_payload(item, as_of_date),
            )
            fit_response.raise_for_status()
            item["fit"] = fit_response.json()
            item["risk"] = risks[index]
            item["days_to_close"] = (
                date.fromisoformat(item["close_date"]) - date.fromisoformat(as_of_date)
            ).days
    return scored


def money(value: Any) -> str:
    return f"${float(value):,.0f}" if value is not None else "Not disclosed"


def pill(label: str, colour: str) -> str:
    return (
        f'<span class="pl-pill" style="color:{colour};background:{colour}18;">'
        f"{label.replace('_', ' ').title()}</span>"
    )


def opportunity_context(opportunity: dict[str, Any], as_of_date: str) -> dict[str, Any]:
    tender_keys = (
        "tender_id",
        "tender_title",
        "agency",
        "estimated_value_aud",
        "procurement_method",
        "close_date",
    )
    return {
        "agency": opportunity["agency"],
        "tender": {key: opportunity.get(key) for key in tender_keys},
        "fit_score": fit_payload(opportunity, as_of_date),
        "amendment_risk": risk_payload(opportunity),
    }


def render_sources(sources: list[dict[str, Any]]) -> None:
    if not sources:
        st.caption("No external sources were returned for this response.")
        return
    for source in sources:
        st.markdown(
            f"<div class='pl-source'><strong>{source['document']}</strong> · "
            f"p. {source['page']} · <a href='{source['url']}' target='_blank'>official source</a>"
            f"<br><small>{source.get('section', '')}</small></div>",
            unsafe_allow_html=True,
        )


def invoke_agent(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    return api_json(
        "POST",
        "/agent/query",
        {
            "question": prompt,
            "session_id": st.session_state.agent_session_id,
            "context": context,
        },
    )


for key, default in {
    "agent_session_id": uuid4().hex,
    "messages": [],
    "latest_brief": None,
    "latest_brief_sources": [],
    "selected_opportunity_id": "DEMO-ATM-001",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

try:
    catalogue = load_demo_catalogue(str(OPPORTUNITY_PATH))
except (OSError, ValueError, json.JSONDecodeError) as exc:
    st.error(f"Opportunity catalogue unavailable: {exc}")
    st.stop()

try:
    health = load_health(API_BASE_URL)
    api_ready = health.get("status") == "ok"
except (httpx.HTTPError, ValueError):
    health = {"status": "unavailable", "models": {}, "observability": {}}
    api_ready = False

with st.sidebar:
    st.markdown("<div class='pl-kicker'>Decision workspace</div>", unsafe_allow_html=True)
    st.markdown("## ◈ ProcureLens")
    st.caption("Federal procurement intelligence")
    st.divider()
    status_colour = "#4ADE80" if api_ready else "#FB7185"
    st.markdown(
        f"<span style='color:{status_colour};font-size:1.2rem'>●</span> "
        f"API **{health['status']}**",
        unsafe_allow_html=True,
    )
    models = health.get("models", {})
    st.caption(
        " · ".join(
            [
                f"Risk v{models.get('amendment_risk', {}).get('version', '—')}",
                f"Fit v{models.get('fit_scorer', {}).get('version', '—')}",
                f"Agent v{models.get('bid_agent', {}).get('version', '—')}",
            ]
        )
    )
    st.divider()
    dataset = health.get("data", catalogue["dataset"])
    st.markdown("**Release snapshot**")
    st.metric("Contracts", f"{dataset['contract_count']:,}")
    st.caption(
        f"{catalogue['dataset']['release_count']:,} releases · "
        f"{dataset['agency_count']} agencies · "
        f"snapshot v{dataset['snapshot_version']}"
    )
    if st.button("Refresh service state", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.button("Start a new analysis", use_container_width=True):
        st.session_state.agent_session_id = uuid4().hex
        st.session_state.messages = []
        st.session_state.latest_brief = None
        st.session_state.latest_brief_sources = []
        st.rerun()
    st.divider()
    st.caption("Human decision support · public procurement data · audit logged")

st.markdown(
    """
    <div class="pl-hero">
      <div class="pl-kicker">Federal procurement intelligence</div>
      <h1>Find the work worth bidding for.</h1>
      <p>Prioritise opportunities, interrogate market evidence and create an
      analyst-ready bid brief.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not api_ready:
    st.warning(
        "Model API is unavailable. The catalogue remains visible, but scoring and agent "
        "actions are disabled."
    )

try:
    scored_opportunities = (
        score_catalogue(
            API_BASE_URL,
            json.dumps(catalogue["opportunities"], sort_keys=True),
            catalogue["as_of_date"],
        )
        if api_ready
        else [{**item} for item in catalogue["opportunities"]]
    )
except (httpx.HTTPError, ValueError, KeyError) as exc:
    st.warning(f"Live scoring is temporarily unavailable: {exc}")
    scored_opportunities = [{**item} for item in catalogue["opportunities"]]

opportunity_by_id = {item["tender_id"]: item for item in scored_opportunities}
if st.session_state.selected_opportunity_id not in opportunity_by_id:
    st.session_state.selected_opportunity_id = next(iter(opportunity_by_id))

tab_feed, tab_decision, tab_agent, tab_brief, tab_assurance = st.tabs(
    ["Opportunity feed", "Decision workspace", "Agent copilot", "Bid brief", "Assurance"]
)

with tab_feed:
    st.subheader("Opportunity feed")
    st.caption(catalogue["disclaimer"])
    filter_col, band_col, sort_col = st.columns([1.4, 1, 1])
    agencies = sorted({item["agency"] for item in scored_opportunities})
    selected_agency = filter_col.selectbox("Agency", ["All agencies", *agencies])
    selected_band = band_col.selectbox("Fit band", ["All bands", "strong_fit", "review", "low_fit"])
    sort_by = sort_col.selectbox("Sort", ["Fit score", "Closing soon", "Value"])

    filtered = [
        item
        for item in scored_opportunities
        if (selected_agency == "All agencies" or item["agency"] == selected_agency)
        and (
            selected_band == "All bands"
            or item.get("fit", {}).get("fit_band") == selected_band
        )
    ]
    if sort_by == "Closing soon":
        filtered.sort(key=lambda item: item.get("days_to_close", 10_000))
    elif sort_by == "Value":
        filtered.sort(key=lambda item: item["estimated_value_aud"], reverse=True)
    else:
        filtered.sort(key=lambda item: item.get("fit", {}).get("score", -1), reverse=True)

    metric_cols = st.columns(4)
    strong_count = sum(item.get("fit", {}).get("fit_band") == "strong_fit" for item in filtered)
    fit_values = [item["fit"]["score"] for item in filtered if "fit" in item]
    metric_cols[0].metric("Visible opportunities", len(filtered))
    metric_cols[1].metric("Strong fit", strong_count)
    average_fit = f"{sum(fit_values) / len(fit_values):.0f}/100" if fit_values else "—"
    metric_cols[2].metric("Average fit", average_fit)
    metric_cols[3].metric(
        "Closing ≤30 days", sum(0 <= item.get("days_to_close", 999) <= 30 for item in filtered)
    )

    feed_rows = []
    for item in filtered:
        feed_rows.append(
            {
                "ID": item["tender_id"],
                "Opportunity": item["tender_title"],
                "Agency": item["agency"],
                "Value (AUD)": item["estimated_value_aud"],
                "Close": item["close_date"],
                "Days": item.get("days_to_close"),
                "Fit": item.get("fit", {}).get("score"),
                "Fit band": item.get("fit", {}).get("fit_band", "unavailable"),
                "Risk": item.get("risk", {}).get("risk_band", "unavailable"),
            }
        )
    st.dataframe(
        pd.DataFrame(feed_rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Value (AUD)": st.column_config.NumberColumn(format="$%.0f"),
            "Fit": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
            "Close": st.column_config.DateColumn(format="DD MMM YYYY"),
        },
    )
    chosen_id = st.selectbox(
        "Open opportunity",
        [item["tender_id"] for item in filtered] or list(opportunity_by_id),
        format_func=lambda item_id: (
            f"{item_id} · {opportunity_by_id[item_id]['tender_title']}"
        ),
        key="feed_opportunity_picker",
    )
    if st.button("Open in decision workspace", type="primary"):
        st.session_state.selected_opportunity_id = chosen_id
        st.toast("Opportunity loaded into the decision workspace")

with tab_decision:
    st.subheader("Decision workspace")
    selected_id = st.selectbox(
        "Opportunity",
        list(opportunity_by_id),
        index=list(opportunity_by_id).index(st.session_state.selected_opportunity_id),
        format_func=lambda item_id: (
            f"{item_id} · {opportunity_by_id[item_id]['tender_title']}"
        ),
        key="decision_opportunity_picker",
    )
    st.session_state.selected_opportunity_id = selected_id
    selected = opportunity_by_id[selected_id]
    fit = selected.get("fit", {})
    risk = selected.get("risk", {})

    detail_left, detail_right = st.columns([1.7, 1])
    with detail_left:
        fit_band = fit.get("fit_band", "unavailable")
        risk_band = risk.get("risk_band", "unavailable")
        st.markdown(
            f"<div class='pl-card'><div class='pl-kicker'>{selected['tender_id']}</div>"
            f"<h3>{selected['tender_title']}</h3><p>{selected['tender_description']}</p>"
            f"{pill(fit_band, FIT_COLOURS.get(fit_band, '#627D98'))}"
            f"{pill(f'{risk_band} risk', RISK_COLOURS.get(risk_band, '#627D98'))}</div>",
            unsafe_allow_html=True,
        )
        st.markdown("#### Why it scored this way")
        reason_cols = st.columns(2)
        with reason_cols[0]:
            st.markdown("**Positive evidence**")
            for reason in fit.get("positive_reasons", ["Scoring unavailable"]):
                st.markdown(f"- {reason}")
        with reason_cols[1]:
            st.markdown("**Watch items**")
            for reason in fit.get("negative_reasons", ["Scoring unavailable"]):
                st.markdown(f"- {reason}")
        st.markdown("**Amendment-risk drivers**")
        for driver in risk.get("top_drivers", []):
            arrow = "↑" if driver["direction"] == "increases_risk" else "↓"
            st.caption(f"{arrow} {driver['feature']} · SHAP impact {driver['impact']:+.3f}")

    with detail_right:
        score_cols = st.columns(2)
        score_cols[0].metric("Opportunity fit", f"{fit.get('score', '—')}/100")
        probability = risk.get("probability")
        score_cols[1].metric(
            "Amendment risk", f"{float(probability):.1%}" if probability is not None else "—"
        )
        st.markdown(
            f"""
            <div class='pl-card'>
              <div class='pl-kicker'>Opportunity facts</div>
              <p><strong>Agency</strong><br>{selected['agency']}</p>
              <p><strong>Estimated value</strong><br>{money(selected['estimated_value_aud'])}</p>
              <p><strong>Method</strong><br>{selected['procurement_method'].title()}</p>
              <p><strong>Closes</strong><br>{selected['close_date']} ·
              {selected.get('days_to_close', '—')} days</p>
              <p><strong>Versions</strong><br>Fit {fit.get('scorer_version', '—')} ·
              Risk {risk.get('model_version', '—')}</p>
              <p><a href='{selected['source_url']}' target='_blank'>
              {selected['source_label']}</a></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Amendment risk is a delivery-risk proxy, not a tender outcome forecast.")

with tab_agent:
    st.subheader("Bid Intelligence Agent")
    selected = opportunity_by_id[st.session_state.selected_opportunity_id]
    context = opportunity_context(selected, catalogue["as_of_date"])
    st.caption(
        f"Context: {selected['tender_id']} · {selected['agency']} · session "
        f"{st.session_state.agent_session_id[:8]}…"
    )
    shortcut_cols = st.columns(4)
    shortcuts = [
        "Show incumbent suppliers for this agency",
        "How much has this agency spent on contracts?",
        "What do the CPRs say about value for money?",
        "Calculate the opportunity fit and amendment risk",
    ]
    queued_prompt = None
    for column, shortcut in zip(shortcut_cols, shortcuts, strict=True):
        if column.button(shortcut, use_container_width=True):
            queued_prompt = shortcut

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("route"):
                st.caption(f"Tool route: `{message['route']}`")
            render_sources(message.get("sources", []))

    typed_prompt = st.chat_input(
        "Ask about spend, suppliers, CPR rules, model scores or bid strategy"
    )
    prompt = typed_prompt or queued_prompt
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Routing through governed tools…"):
                try:
                    response = invoke_agent(prompt, context)
                except (httpx.HTTPError, ValueError) as exc:
                    st.error(f"Agent service unavailable: {exc}")
                else:
                    st.markdown(response["answer"])
                    st.caption(f"Tool route: `{response['route']}`")
                    render_sources(response.get("sources", []))
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": response["answer"],
                            "route": response["route"],
                            "sources": response.get("sources", []),
                        }
                    )
                    if response.get("brief") and DRAFT_BANNER in response["brief"]:
                        st.session_state.latest_brief = response["brief"]
                        st.session_state.latest_brief_sources = response.get("sources", [])

with tab_brief:
    st.subheader("Bid / no-bid brief")
    selected = opportunity_by_id[st.session_state.selected_opportunity_id]
    st.markdown(f"<div class='pl-draft'>{DRAFT_BANNER}</div>", unsafe_allow_html=True)
    st.caption(
        f"Evidence pack for {selected['tender_id']}. Generated recommendations never replace "
        "analyst approval."
    )
    if st.button("Generate evidence-linked brief", type="primary", disabled=not api_ready):
        with st.spinner("Collecting ML, dbt mart and CPR/ANAO evidence…"):
            try:
                response = invoke_agent(
                    "Create a one-page bid/no-bid brief for this tender",
                    opportunity_context(selected, catalogue["as_of_date"]),
                )
            except (httpx.HTTPError, ValueError) as exc:
                st.error(f"Brief generation failed: {exc}")
            else:
                brief = str(response.get("brief") or "")
                if DRAFT_BANNER not in brief:
                    st.error(
                        "Brief rejected because the mandatory analyst-review warning is missing."
                    )
                else:
                    st.session_state.latest_brief = brief
                    st.session_state.latest_brief_sources = response.get("sources", [])

    if st.session_state.latest_brief:
        st.markdown(st.session_state.latest_brief)
        st.markdown("#### Evidence sources")
        render_sources(st.session_state.latest_brief_sources)
        download_cols = st.columns(2)
        download_cols[0].download_button(
            "Download Markdown brief",
            data=st.session_state.latest_brief,
            file_name=f"{selected['tender_id'].lower()}-bid-brief-draft.md",
            mime="text/markdown",
            use_container_width=True,
        )
        evidence_pack = {
            "draft_warning": DRAFT_BANNER,
            "opportunity": selected,
            "sources": st.session_state.latest_brief_sources,
            "brief_markdown": st.session_state.latest_brief,
        }
        download_cols[1].download_button(
            "Download JSON evidence pack",
            data=json.dumps(evidence_pack, indent=2),
            file_name=f"{selected['tender_id'].lower()}-evidence-pack.json",
            mime="application/json",
            use_container_width=True,
        )
    else:
        st.info("Select an opportunity and generate the brief to preview and download it here.")

with tab_assurance:
    st.subheader("Assurance and operating controls")
    control_cols = st.columns(3)
    controls = [
        (
            "Evidence first",
            "RAG answers include document, page and official URL. SQL is restricted to "
            "allowlisted dbt marts.",
        ),
        (
            "Human decision",
            "Fit is a transparent ranking, not win probability. Every brief is labelled for "
            "analyst review.",
        ),
        (
            "Privacy by design",
            "PII is redacted at LLM boundaries. Observability stores fingerprints and metrics, "
            "not prompt bodies.",
        ),
    ]
    for column, (title, description) in zip(control_cols, controls, strict=True):
        column.markdown(
            f"<div class='pl-card'><div class='pl-kicker'>Production control</div>"
            f"<h3>{title}</h3><p>{description}</p></div>",
            unsafe_allow_html=True,
        )
    st.markdown("#### Verified release evidence")
    evidence_cols = st.columns(4)
    evidence_cols[0].metric("Golden scenarios", "45")
    evidence_cols[1].metric("Eval gates", "4 / 4")
    evidence_cols[2].metric("Branch coverage", "81.42%")
    evidence_cols[3].metric("dbt checks", "23 / 23")
    st.caption(
        "Amendment Risk champion: AUC 0.8664 · PR-AUC 0.6568 · Brier 0.1042 · ECE 0.0316"
    )
    st.markdown(
        "Review the repository AI Assurance Assessment, model cards and production operations "
        "runbook before any use beyond this portfolio demonstration."
    )
