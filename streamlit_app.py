# app.py
import streamlit as st
from utils.ui import page_header, status_badge

# ---- Use ephemeral SQLite data layer ----
from services.data_sqlite_ephemeral import (
    list_sessions,
    list_signups_for_session,
    list_signups_for_user,
    count_confirmed,
    create_signup,
    update_signup_status,
    get_session,
    # Admin/facilitator helpers
    upsert_facilitator,
    list_facilitators,
    remove_facilitator,
)

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

# --- Admin gate (who can access the Admin screen) ---
ADMIN_EMAILS = []
try:
    ADMIN_EMAILS = [e.strip().lower() for e in (st.secrets.get("ADMIN_EMAILS", "")).split(",") if e.strip()]
except Exception:
    pass

is_admin = (user_email or "").lower() in ADMIN_EMAILS

# --- Nav ---
st.sidebar.title("Navigation")
nav_items = ["Participant", "Facilitator"]
if is_admin:
    nav_items.append("Admin")
view = st.sidebar.radio("Go to", nav_items)

# --- Participant View ---
if view == "Participant":
    page_header("Sessions", "Sign up for a session")

    sessions = list_sessions(active_only=True)
    session_titles = {
        f"{s['Title']} — {s['StartDateTime'][:16].replace('T',' ')}": s["ID"] for s in sessions
    }
    selected_label = st.selectbox(
        "Select a session", list(session_titles.keys()) if session_titles else ["No sessions"]
    )
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
                        # Capacity check (fixed: use >=)
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

# --- Admin View (manage facilitator privileges) ---
if view == "Admin":
    if not is_admin:
        st.error("You do not have access to this page.")
        st.stop()

    st.header("Admin")
    st.subheader("Manage Facilitators")

    with st.form("add_fac_form", clear_on_submit=True):
        new_email = st.text_input("Facilitator email", placeholder="user@company.com").strip().lower()
        new_name  = st.text_input("Display name (optional)")
        submit = st.form_submit_button("Add / Update Facilitator", use_container_width=True)
        if submit:
            if not new_email or "@" not in new_email:
                st.warning("Enter a valid email.")
            else:
                upsert_facilitator(new_email, new_name or None)
                st.success(f"Saved facilitator: {new_email}")

    st.divider()
    st.subheader("Current Facilitators")
    facs = list_facilitators()
    if not facs:
        st.info("No facilitators yet.")
    else:
        for row in facs:
            c1, c2, c3 = st.columns([3, 3, 2])
            with c1:
                st.write(f"**{row['email']}**")
            with c2:
                st.caption(row["display_name"] or "")
            with c3:
                if st.button("Remove", key=f"rm_{row['email']}"):
                    remove_facilitator(row["email"])
                    st.toast(f"Removed {row['email']}", icon="🗑️")
                    st.rerun()