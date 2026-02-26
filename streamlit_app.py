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
    list_sessions_by_facilitator,
    delete_session,
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
# ---------- Create / Edit Sessions ----------
    st.subheader("Create / Edit Sessions")

    import datetime as dt

    def _combine_iso(date_val, time_val):
        # Store UTC-ish ISO strings for now; adjust later if you add timezone handling
        dt_obj = dt.datetime.combine(date_val, time_val).replace(microsecond=0)
        return dt_obj.isoformat()

    with st.expander("Create a new session", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            new_title = st.text_input("Title", placeholder="e.g., Coaching Circle - Q2")
            new_type = st.text_input("SessionType", placeholder="Workshop / Coaching / Roundtable")
            new_capacity = st.number_input("Capacity", min_value=0, step=1, value=10)
            new_active = st.checkbox("Active", value=True)
        with c2:
            today = dt.date.today()
            start_date = st.date_input("Start date", value=today)
            start_time = st.time_input("Start time", value=dt.time(9, 0))
            end_date = st.date_input("End date", value=today)
            end_time = st.time_input("End time", value=dt.time(10, 0))
            new_teams = st.text_input("TeamsJoinUrl (optional)", placeholder="https://teams.microsoft.com/...")
        if st.button("Create session", type="primary"):
            if not new_title.strip():
                st.warning("Please enter a session Title.")
            else:
                start_iso = _combine_iso(start_date, start_time)
                end_iso = _combine_iso(end_date, end_time)
                if end_iso <= start_iso:
                    st.error("End must be after Start.")
                else:
                    from services.data_sqlite_ephemeral import create_session
                    s = create_session(
                        title=new_title.strip(),
                        session_type=new_type.strip(),
                        facilitator_email=user_email,
                        start_iso=start_iso,
                        end_iso=end_iso,
                        capacity=int(new_capacity),
                        active=bool(new_active),
                        teams_url=new_teams.strip(),
                    )
                    st.success(f"Created: {s['Title']} (ID: {s['ID'][:8]})")
                    st.rerun()

    st.divider()
    st.subheader("Your Sessions")

    my_sessions_all = list_sessions_by_facilitator(user_email)
    if not my_sessions_all:
        st.info("You haven't created any sessions yet.")
    else:
        # Pick one to edit
        label_map = {
            f"{s['Title']} — {s['StartDateTime'][:16].replace('T',' ')}": s["ID"]
            for s in my_sessions_all
        }
        pick_edit_label = st.selectbox("Select a session to edit", list(label_map.keys()))
        edit_session_id = label_map[pick_edit_label]
        sess_edit = get_session(edit_session_id)

        ec1, ec2 = st.columns(2)
        with ec1:
            e_title = st.text_input("Title (edit)", value=sess_edit["Title"])
            e_type = st.text_input("SessionType (edit)", value=sess_edit.get("SessionType", ""))
            e_capacity = st.number_input("Capacity (edit)", min_value=0, step=1, value=int(sess_edit["Capacity"]))
            e_active = st.checkbox("Active (edit)", value=bool(sess_edit["Active"]))
        with ec2:
            # Parse ISO strings to date/time widgets
            def _parse_iso(iso_str: str) -> tuple[dt.date, dt.time]:
                try:
                    d = dt.datetime.fromisoformat(iso_str)
                except Exception:
                    d = dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
                return d.date(), d.time()

            sd, stime = _parse_iso(sess_edit["StartDateTime"])
            ed, etime = _parse_iso(sess_edit["EndDateTime"])

            e_start_date = st.date_input("Start date (edit)", value=sd, key="e_sd")
            e_start_time = st.time_input("Start time (edit)", value=stime, key="e_st")
            e_end_date   = st.date_input("End date (edit)", value=ed, key="e_ed")
            e_end_time   = st.time_input("End time (edit)", value=etime, key="e_et")

            e_teams = st.text_input("TeamsJoinUrl (edit)", value=sess_edit.get("TeamsJoinUrl", ""))

        cc1, cc2, cc3 = st.columns([2,2,2])
        with cc1:
            if st.button("Save changes", key="btn_save_session", type="primary"):
                e_start_iso = _combine_iso(e_start_date, e_start_time)
                e_end_iso   = _combine_iso(e_end_date, e_end_time)
                if e_end_iso <= e_start_iso:
                    st.error("End must be after Start.")
                else:
                    from services.data_sqlite_ephemeral import update_session
                    update_session(
                        edit_session_id,
                        Title=e_title.strip(),
                        SessionType=e_type.strip(),
                        FacilitatorEmail=user_email,  # keep ownership
                        StartDateTime=e_start_iso,
                        EndDateTime=e_end_iso,
                        Capacity=int(e_capacity),
                        Active=1 if e_active else 0,
                        TeamsJoinUrl=e_teams.strip(),
                    )
                    st.success("Session updated.")
                    st.rerun()
        with cc2:
            if st.button("Duplicate as new", key="btn_dup_session"):
                from services.data_sqlite_ephemeral import create_session
                dup = create_session(
                    title=f"{e_title.strip()} (copy)",
                    session_type=e_type.strip(),
                    facilitator_email=user_email,
                    start_iso=_combine_iso(e_start_date, e_start_time),
                    end_iso=_combine_iso(e_end_date, e_end_time),
                    capacity=int(e_capacity),
                    active=bool(e_active),
                    teams_url=e_teams.strip(),
                )
                st.success(f"Duplicated: {dup['Title']} (ID: {dup['ID'][:8]})")
                st.rerun()
        with cc3:
            del_confirm = st.checkbox("Confirm delete", key="chk_del")
            if st.button("Delete session", key="btn_del_session", type="secondary", disabled=not del_confirm):
                delete_session(edit_session_id)
                st.warning("Session deleted.")
                st.rerun()

    st.divider()
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