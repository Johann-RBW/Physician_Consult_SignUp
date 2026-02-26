# services/data_memory.py
import uuid
from datetime import datetime, timedelta

# In-memory “database” (resets on app restart; perfect for a POC demo)
_DB = {
    "sessions": [],
    "signups": []
}

def init_demo_data():
    if _DB["sessions"]:
        return
    now = datetime.utcnow()
    # Two sessions, one with your UPN as facilitator demo@example.com - replace later via UI
    _DB["sessions"] = [
        {
            "ID": 1,
            "Title": "Intro to Claims",
            "SessionType": "Training",
            "FacilitatorEmail": "you@company.com",
            "StartDateTime": (now + timedelta(days=1)).isoformat(),
            "EndDateTime": (now + timedelta(days=1, hours=1)).isoformat(),
            "Capacity": 10,
            "Active": True,
            "SessionCalendarEventID": "",
            "TeamsJoinUrl": ""
        },
        {
            "ID": 2,
            "Title": "Ops Deep Dive",
            "SessionType": "Workshop",
            "FacilitatorEmail": "someoneelse@company.com",
            "StartDateTime": (now + timedelta(days=2)).isoformat(),
            "EndDateTime": (now + timedelta(days=2, hours=2)).isoformat(),
            "Capacity": 2,
            "Active": True,
            "SessionCalendarEventID": "",
            "TeamsJoinUrl": ""
        }
    ]
    _DB["signups"] = [
        {
            "ID": str(uuid.uuid4()),
            "Title": "Signup 1",
            "SessionId": 1,
            "ParticipantEmail": "participant1@company.com",
            "ParticipantName": "Participant One",
            "Status": "Confirmed",
            "CalendarEventId": ""
        }
    ]

# Sessions
def list_sessions(active_only=True):
    sessions = _DB["sessions"]
    if active_only:
        sessions = [s for s in sessions if s.get("Active", True)]
    return sorted(sessions, key=lambda s: s["StartDateTime"])

def get_session(session_id: int):
    return next((s for s in _DB["sessions"] if s["ID"] == session_id), None)

# Signups
def list_signups_for_session(session_id: int, statuses=("Pending", "Confirmed")):
    return [r for r in _DB["signups"] if r["SessionId"] == session_id and r["Status"] in statuses]

def list_signups_for_user(user_email: str):
    return [r for r in _DB["signups"] if r["ParticipantEmail"].lower() == user_email.lower()]

def count_confirmed(session_id: int):
    return sum(1 for r in _DB["signups"] if r["SessionId"] == session_id and r["Status"] == "Confirmed")

def create_signup(session_id: int, participant_email: str, participant_name: str):
    rec = {
        "ID": str(uuid.uuid4()),
        "Title": f"{participant_name} signup",
        "SessionId": session_id,
        "ParticipantEmail": participant_email,
        "ParticipantName": participant_name,
        "Status": "Pending",
        "CalendarEventId": ""
    }
    _DB["signups"].append(rec)
    return rec

def update_signup_status(signup_id: str, new_status: str):
    for r in _DB["signups"]:
        if r["ID"] == signup_id:
            r["Status"] = new_status
            return r
    return None