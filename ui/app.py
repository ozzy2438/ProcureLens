"""Streamlit front end: opportunity feed + agent chat + brief download."""
import streamlit as st

st.set_page_config(page_title="ProcureLens", layout="wide")
st.title("ProcureLens — Bid Intelligence")

tab_feed, tab_agent = st.tabs(["Opportunity feed", "Ask the agent"])

with tab_feed:
    st.info("Week 6: live tender feed with fit scores + amendment risk bands.")

with tab_agent:
    st.info("Week 6: chat with the Bid Intelligence Agent. Briefs are drafts — analyst review required.")
