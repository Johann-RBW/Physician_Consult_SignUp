# utils/ui.py
import streamlit as st

def page_header(title: str, subtitle: str = None):
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)

def status_badge(status: str):
    colors = {
        "Pending": "orange",
        "Confirmed": "green",
        "Removed": "red",
        "Rejected": "gray"
    }
    color = colors.get(status, "blue")
    st.markdown(f"<span style='background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:12px;'>{status}</span>", unsafe_allow_html=True)