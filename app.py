# app.py
import streamlit as st
from utils.ui import page_header, status_badge
from services.data_memory import (
    init_demo_data, list_sessions, list_signups_for_session,
    list_signups_for_user, count_confirmed, create_signup,
    update_signup_status, get_session
)

# --- Init demo data (in-memory) ---
init_demo_data()

# --- Identify the current user (works in Streamlit Cloud) ---
# If you're running locally, you can fallback to a manual input
user_email = ""
user_name = ""

# Streamlit Community Cloud exposes the user email in experimental_user when auth is enabled
if hasattr(st, "experimental_user") and st.experimental_user is not None:
    user_email = st.experimental_user.email or ""
    user_name = st.experimental_user.name or ""
else:
    # Fallback for local runs – change to your address for testing
    user_email = st.sidebar.text_input("Your work email", value="you@company.com")
    user_name = st.sidebar.text_input("Your name", value="Johann Woodcock")

# --- Nav ---
st.sidebar.title("Navigation")
view = st.sidebar.radio("Go to", ["Participant", "Facilitator"])

# --- Participant View ---
if view == "Participant":
    page_header("Sessions", "Sign up for a session")

    sessions = list_sessions(active_only=True)
    session_titles = {f"{s['Title']} — {s['StartDateTime'][:16].replace('T',' ')}": s["ID"] for s in sessions}
    selected_label = st.selectbox("Select a session", list(session_titles.keys()) if session_titles else ["No sessions"])
    if session_titles:
        session_id = session_titles[selected_label]
        sess = get_session(session_id)
        st.write(f"**Type:** {sess['SessionType']}")
        st.write(f"**Facilitator:** {sess['FacilitatorEmail']}")
        st.write(f"**When:** {sess['StartDateTime']} → {sess['EndDateTime']}")
        st.write(f"**Capacity:** {sess['Capacity']} | **Confirmed:** {count_confirmed(session_id)}")

        st.divider()
        st.subheader("Sign up")
        if st.button("Request a spot"):
            rec = create_signup(session_id, user_email, user_name or user_email.split("@")[0])
            st.success(f"Request submitted as **Pending**. (Signup ID: {rec['ID'][:8]})")

        st.divider()
        st.subheader("My Signups")
        my_rows = list_signups_for_user(user_email)
        if not my_rows:
            st.info("You have no signups yet.")
        else:
            for r in my_rows:
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    s = get_session(r["SessionId"])
                    st.write(f"**{s['Title']}**")
                    st.caption(f"{s['StartDateTime']} → {s['EndDateTime']}")
                with col2:
                    status_badge(r["Status"])
                with col3:
                    st.caption(f"ID: {r['ID'][:8]}")

# --- Facilitator View ---
if view == "Facilitator":
    page_header("Facilitator Dashboard", "Review and manage signups for your sessions")

    # Sessions where current user is the facilitator
    my_sessions = [s for s in list_sessions() if s["FacilitatorEmail"].lower() == (user_email or "").lower()]
    if not my_sessions:
        st.warning("You are not a facilitator for any active sessions.")
    else:
        session_map = {f"{s['Title']} — {s['StartDateTime'][:16].replace('T',' ')}": s["ID"] for s in my_sessions}
        pick = st.selectbox("Your sessions", list(session_map.keys()))
        session_id = session_map[pick]
        sess = get_session(session_id)
        st.write(f"**Capacity:** {sess['Capacity']} | **Confirmed:** {count_confirmed(session_id)}")
        st.divider()

        st.subheader("Roster (Pending + Confirmed)")
        rows = list_signups_for_session(session_id, statuses=("Pending", "Confirmed"))
        if not rows:
            st.info("No participants have signed up yet.")
        else:
            for r in rows:
                c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
                with c1:
                    st.write(f"**{r['ParticipantName']}**")
                    st.caption(r["ParticipantEmail"])
                with c2:
                    status_badge(r["Status"])
                with c3:
                    if r["Status"] == "Pending" and st.button("Approve", key=f"approve_{r['ID']}"):
                        # Capacity check
                        if count_confirmed(session_id) >= sess["Capacity"]:
                            st.warning("Capacity reached. Cannot confirm more participants.")
                        else:
                            update_signup_status(r["ID"], "Confirmed")
                            st.success("Approved.")
                    if r["Status"] == "Pending" and st.button("Reject", key=f"reject_{r['ID']}"):
                        update_signup_status(r["ID"], "Rejected")
                        st.info("Rejected.")
                with c4:
                    if r["Status"] in ("Pending", "Confirmed") and st.button("Kick Out", key=f"remove_{r['ID']}"):
                        update_signup_status(r["ID"], "Removed")
                        st.error("Removed.")

        st.divider()
        st.caption("Tips: Approve confirms a seat (capacity enforced). Reject declines a request. Kick Out removes someone already in roster.")