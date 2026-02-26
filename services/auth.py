import os
import time
import uuid
import urllib.parse
from typing import Optional, Dict, Any, List

import msal
import streamlit as st


OIDC_SCOPES = ["openid", "profile", "email"]


def _csv_to_list(csv_str: Optional[str]) -> List[str]:
    if not csv_str:
        return []
    return [s.strip() for s in csv_str.split(",") if s.strip()]


class AuthManager:
    """
    Minimal MSAL Auth Code Flow wrapper for Streamlit (identity-only).
    - Builds sign-in URL with state & nonce.
    - Redeems authorization code for ID token (via MSAL).
    - Stores minimal user info in st.session_state["user"].
    """

    def __init__(self):
        self.tenant_id = st.secrets["TENANT_ID"]
        self.client_id = st.secrets["CLIENT_ID"]
        self.client_secret = st.secrets.get("CLIENT_SECRET")
        self.authority = st.secrets.get("AUTHORITY") or f"https://login.microsoftonline.com/{self.tenant_id}"
        self.redirect_uri = st.secrets["REDIRECT_URI"]
        self.allowed_domains_raw = st.secrets.get("ALLOWED_EMAIL_DOMAINS", "")
        self.facilitator_emails_raw = st.secrets.get("FACILITATOR_EMAILS", "")

        self.allowed_domains = self._normalize_domains(_csv_to_list(self.allowed_domains_raw))
        self.facilitator_emails = {e.lower() for e in _csv_to_list(self.facilitator_emails_raw)}

        # MSAL Confidential Client
        self.app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority,
        )

        # Session keys
        self.S_KEY_STATE = "oidc_state"
        self.S_KEY_NONCE = "oidc_nonce"
        self.S_KEY_USER = "user"

    @staticmethod
    def _normalize_domains(domains: List[str]) -> List[str]:
        norm = []
        for d in domains:
            d = d.lower()
            if d.startswith("@"):
                d = d[1:]
            norm.append(d)
        return norm

    def _new_state(self) -> str:
        s = uuid.uuid4().hex + "." + str(int(time.time()))
        st.session_state[self.S_KEY_STATE] = s
        return s

    def _new_nonce(self) -> str:
        n = uuid.uuid4().hex
        st.session_state[self.S_KEY_NONCE] = n
        return n

    def get_sign_in_url(self) -> str:
        """
        Build the authorize URL for auth code flow.
        """
        state = self._new_state()
        nonce = self._new_nonce()

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "response_mode": "query",
            "scope": " ".join(OIDC_SCOPES),
            "state": state,
            "nonce": nonce,  # ID token validation (even if we only need code here)
        }
        return f"{self.authority}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"

    def handle_redirect(self, query_params: Dict[str, List[str]]) -> Optional[Dict[str, Any]]:
        """
        Call this when the page loads and query params contain ?code=...
        Validates state, exchanges code for token, stores user in session_state.
        """
        code = (query_params.get("code") or [None])[0]
        state = (query_params.get("state") or [None])[0]
        error = (query_params.get("error") or [None])[0]

        if error:
            # You could capture error_description as well for UI.
            return {"error": error}

        if not code or not state:
            return None

        expected_state = st.session_state.get(self.S_KEY_STATE)
        if not expected_state or state != expected_state:
            return {"error": "invalid_state"}

        result = self.app.acquire_token_by_authorization_code(
            code=code,
            scopes=OIDC_SCOPES,
            redirect_uri=self.redirect_uri,
        )
        # MSAL returns dict with "id_token_claims" for OIDC success
        if "id_token_claims" not in result:
            return {"error": result.get("error_description") or "token_exchange_failed"}

        claims = result["id_token_claims"]
        # Common claim patterns: preferred_username or upn/email
        email = (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
        )
        name = claims.get("name") or email
        oid = claims.get("oid")
        tid = claims.get("tid")

        user = {
            "name": name,
            "email": (email or "").lower(),
            "oid": oid,
            "tid": tid,
            "id_token_claims": claims,  # keep for debugging; omit in production logs
        }
        st.session_state[self.S_KEY_USER] = user

        # Clear one-time state/nonce after use
        st.session_state.pop(self.S_KEY_STATE, None)
        st.session_state.pop(self.S_KEY_NONCE, None)

        return user

    def is_signed_in(self) -> bool:
        return bool(st.session_state.get(self.S_KEY_USER))

    def current_user(self) -> Optional[Dict[str, Any]]:
        return st.session_state.get(self.S_KEY_USER)

    def is_domain_allowed(self) -> bool:
        user = self.current_user()
        if not user or not user.get("email"):
            return False
        domain = user["email"].split("@")[-1].lower()
        return domain in self.allowed_domains if self.allowed_domains else True

    def is_facilitator_stub(self) -> bool:
        """
        Dev-only stub: treat users in FACILITATOR_EMAILS as facilitators.
        (We’ll replace with SharePoint lookup in a later step.)
        """
        user = self.current_user()
        if not user:
            return False
        return user["email"] in self.facilitator_emails

    def get_sign_out_url(self) -> str:
        """
        Front-channel logout; redirects back to the app (home).
        Ensure your post_logout_redirect_uri is an allowed/registered URL.
        """
        params = {
            "post_logout_redirect_uri": self.redirect_uri,
            "client_id": self.client_id,  # harmless with v2.0 logout
        }
        return f"{self.authority}/oauth2/v2.0/logout?{urllib.parse.urlencode(params)}"