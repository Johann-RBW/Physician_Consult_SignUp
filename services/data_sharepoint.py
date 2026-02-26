"""
TEMPORARY SHIM:
Exports the exact functions the app imports while you finish the real
SharePoint/Graph implementation from Step 3. Safe to deploy.
Remove/replace with your SharePoint code when ready.
"""

from services.data_memory import (
    list_sessions as _mem_list_sessions,
    get_session as _mem_get_session,
    list_signups_for_session as _mem_list_signups_for_session,
    list_signups_for_user as _mem_list_signups_for_user,
    count_confirmed as _mem_count_confirmed,
    create_signup as _mem_create_signup,
    update_signup_status as _mem_update_signup_status,
)

def list_sessions(active_only: bool = True):
    return _mem_list_sessions(active_only=active_only)

def get_session(session_id):
    return _mem_get_session(session_id)

def list_signups_for_session(session_id, statuses=("Pending", "Confirmed")):
    return _mem_list_signups_for_session(session_id, statuses)

def list_signups_for_user(user_email: str):
    return _mem_list_signups_for_user(user_email)

def count_confirmed(session_id):
    return _mem_count_confirmed(session_id)

def create_signup(session_id, participant_email: str, participant_name: str):
    return _mem_create_signup(session_id, participant_email, participant_name)

def update_signup_status(signup_id, new_status: str):
    return _mem_update_signup_status(signup_id, new_status)