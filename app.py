from __future__ import annotations

from pathlib import Path
import os

import streamlit as st
from dotenv import load_dotenv

from source.config import APP_REFERENCE, METHOD_REFERENCE, STEP_TITLES
from source.logging import configure_logging
from source.stream_steps import render_active_step
from source.stream_util import (
    init_session_state,
    inject_css,
    regenerate_webhook_credentials,
    render_loan_funds_side_panel,
    reset_poc,
)


load_dotenv(dotenv_path=Path(".env"), override=False)
configure_logging()

st.set_page_config(
    page_title=APP_REFERENCE["page_title"],
    page_icon=APP_REFERENCE["page_icon"],
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    inject_css()
    init_session_state()
    render_sidebar()

    left, right = st.columns([1.45, 1], gap="large")
    with left:
        render_header()
        render_step_progress()
        render_active_step()
    with right:
        render_loan_funds_side_panel()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## Runtime")
        env_api_key = os.getenv("METHOD_API_KEY", "")
        default_api_key = st.session_state["api_key_override"] or env_api_key
        api_key = st.text_input(
            "Method API key",
            value=default_api_key,
            type="password",
            help="Reads METHOD_API_KEY from .env automatically, but you can override it here.",
        )
        st.session_state["api_key_override"] = api_key

        base_url = st.selectbox(
            "Environment",
            METHOD_REFERENCE["environment_options"],
            index=METHOD_REFERENCE["environment_options"].index(st.session_state["base_url"])
            if st.session_state["base_url"] in METHOD_REFERENCE["environment_options"]
            else 0,
            help="Choose the Method environment used by this POC.",
        )
        st.session_state["base_url"] = base_url

        method_version = st.text_input(
            "Method-Version",
            value=st.session_state["method_version"],
        )
        st.session_state["method_version"] = method_version.strip() or METHOD_REFERENCE["default_method_version"]

        st.markdown("## Webhooks")
        st.caption("Method expects a webhook endpoint that returns `200` within five seconds. The app now generates internal webhook credentials for you.")
        st.session_state["webhook_url"] = st.text_input(
            "Webhook URL",
            value=st.session_state["webhook_url"],
            placeholder=METHOD_REFERENCE["webhook"]["default_local_url"],
        )
        st.text_input(
            "Webhook internal token",
            value=st.session_state["webhook_internal_token"],
            disabled=True,
            help="Internally generated UUID used as the source value for the auth token.",
        )
        st.text_input(
            "Webhook auth_token payload",
            value=st.session_state["webhook_auth_token"],
            disabled=True,
            help="Base64-encoded internal token sent as `auth_token` in the Method webhook create request.",
        )
        st.text_input(
            "Expected Authorization header",
            value=st.session_state["webhook_expected_auth_header"],
            disabled=True,
            help="Method sends the Authorization header as base64(auth_token). This is the value your receiver should expect with the current generated token.",
        )
        st.session_state["webhook_hmac_secret"] = st.text_input(
            "Webhook HMAC secret",
            value=st.session_state["webhook_hmac_secret"],
        )
        if st.button("Regenerate webhook credentials", use_container_width=True):
            regenerate_webhook_credentials()
            st.rerun()

        st.markdown("## Payments")
        st.caption(
            "The demo's last step creates a Method payment. That requires an existing Method source account ID for the lender/disbursement account."
        )
        st.session_state["source_account_id"] = st.text_input(
            "Source account ID",
            value=st.session_state["source_account_id"],
            placeholder="acc_...",
        )

        st.markdown("## Shortcuts")
        st.markdown(
            f"[Citi demo]({APP_REFERENCE['links']['demo']})  \n[Method docs]({APP_REFERENCE['links']['docs']})"
        )

        if not api_key:
            st.warning("`METHOD_API_KEY` is not loaded. Calls are disabled until a key is available.")

        if st.button("Reset POC", use_container_width=True):
            reset_poc()
            st.rerun()


def render_header() -> None:
    st.markdown(
        f"""
        <div class="hero-card">
          <div class="hero-kicker">{APP_REFERENCE["hero_kicker"]}</div>
          <h1>{APP_REFERENCE["hero_title"]}</h1>
          <p>{APP_REFERENCE["hero_description"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_step_progress() -> None:
    current_step = st.session_state["current_step"]
    st.caption(f"Current step: {current_step + 1} of {len(STEP_TITLES)}")
    st.markdown(f"### {STEP_TITLES[current_step]}")
    st.markdown("<div class='spacer-12'></div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
