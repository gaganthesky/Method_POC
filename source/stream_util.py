from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
import os
import random
import uuid

import streamlit as st

from source.config import DEFAULT_BORROWER, DEFAULTS_REFERENCE, METHOD_REFERENCE, REFERENCE_RESPONSES, TEST_ACCOUNT_PROFILES
from source.method_api import ApiLogEntry, MethodApiError, MethodClient, build_curl_command


def init_session_state() -> None:
    defaults = {
        "current_step": 0,
        "borrower_form": DEFAULT_BORROWER.copy(),
        "api_logs": [],
        "entity": None,
        "connect": None,
        "accounts": [],
        "entity_products": None,
        "selected_account_ids": [],
        "selected_account_amounts": {},
        "loan_selection_errors": [],
        "loan_selection_info": "",
        "webhooks": [],
        "subscriptions": [],
        "payment_instruments": [],
        "payment": None,
        "selected_test_phone": DEFAULT_BORROWER["phone"],
        "applied_test_phone": DEFAULT_BORROWER["phone"],
        "source_account_id": "",
        "webhook_url": METHOD_REFERENCE["webhook"]["default_local_url"],
        "webhook_internal_token": generate_webhook_internal_token(),
        "webhook_auth_token": "",
        "webhook_expected_auth_header": "",
        "webhook_hmac_secret": generate_webhook_hmac_secret(),
        "api_key_override": "",
        "base_url": os.getenv("METHOD_BASE_URL", METHOD_REFERENCE["default_base_url"]),
        "method_version": os.getenv("METHOD_VERSION", METHOD_REFERENCE["default_method_version"]),
        "approved_loan_amount_cents": generate_approved_loan_amount_cents(),
        "payment_description": DEFAULTS_REFERENCE["payment_description"],
        "payment_amount_usd": DEFAULTS_REFERENCE["payment_amount_usd"],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    refresh_webhook_state()


def build_client() -> MethodClient | None:
    api_key = st.session_state["api_key_override"].strip()
    if not api_key:
        st.error("`METHOD_API_KEY` is missing. Add it in `.env` or the sidebar.")
        return None

    return MethodClient(
        api_key=api_key,
        base_url=st.session_state["base_url"],
        method_version=st.session_state["method_version"],
    )


def add_log(log: ApiLogEntry) -> None:
    st.session_state["api_logs"].append(log)


def generate_webhook_internal_token() -> str:
    return str(uuid.uuid4())


def generate_approved_loan_amount_cents() -> int:
    loan_defaults = DEFAULTS_REFERENCE["approved_loan_amount"]
    min_usd = int(loan_defaults["min_usd"])
    max_usd = int(loan_defaults["max_usd"])
    interval_usd = int(loan_defaults["interval_usd"])
    return random.randrange(min_usd, max_usd + interval_usd, interval_usd) * 100


def generate_webhook_hmac_secret() -> str:
    return f"{METHOD_REFERENCE['webhook']['default_hmac_secret_prefix']}-{uuid.uuid4()}"


def base64_encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def refresh_webhook_state() -> None:
    internal_token = st.session_state.get("webhook_internal_token", "")
    if not internal_token:
        internal_token = generate_webhook_internal_token()
        st.session_state["webhook_internal_token"] = internal_token

    auth_token = base64_encode(internal_token)
    st.session_state["webhook_auth_token"] = auth_token
    st.session_state["webhook_expected_auth_header"] = base64_encode(auth_token)


def regenerate_webhook_credentials() -> None:
    st.session_state["webhook_internal_token"] = generate_webhook_internal_token()
    st.session_state["webhook_hmac_secret"] = generate_webhook_hmac_secret()
    refresh_webhook_state()


def get_test_account_profiles() -> list[dict[str, Any]]:
    return TEST_ACCOUNT_PROFILES


def get_test_account_profile(phone: str) -> dict[str, Any] | None:
    normalized_phone = phone.strip()
    for profile in TEST_ACCOUNT_PROFILES:
        if profile.get("phone") == normalized_phone:
            return dict(profile)
    return None


def has_resource_id(resource: Any) -> bool:
    return isinstance(resource, dict) and bool(resource.get("id"))


def get_connect_product_status() -> dict[str, Any] | None:
    products = st.session_state.get("entity_products")
    if isinstance(products, dict):
        connect_product = products.get("connect")
        if isinstance(connect_product, dict):
            return connect_product
    return None


def get_account_update_product(account: dict[str, Any]) -> dict[str, Any]:
    update = account.get("update") or {}
    return (
        update.get("credit_card")
        or update.get("personal_loan")
        or update.get("auto_loan")
        or update.get("mortgage")
        or update.get("student_loans")
        or {}
    )


def get_account_balance_cents(account: dict[str, Any]) -> int | None:
    product = get_account_update_product(account)
    balance = product.get("balance")
    if balance in (None, ""):
        return None
    try:
        return int(balance)
    except (TypeError, ValueError):
        return None


def get_account_summary(account: dict[str, Any]) -> dict[str, str]:
    product = get_account_update_product(account)

    apr = product.get("interest_rate_percentage")
    if apr is None:
        apr = product.get("interest_rate_percentage_max")

    return {
        "balance": format_cents(product.get("balance")),
        "min_payment": format_cents(product.get("next_payment_minimum_amount")),
        "due_date": product.get("next_payment_due_date", "—"),
        "apr": f"{apr}%" if apr is not None else "—",
    }


def format_cents(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        cents = Decimal(str(value))
    except InvalidOperation:
        return "—"
    dollars = cents / Decimal("100")
    sign = "-" if dollars < 0 else ""
    return f"{sign}${abs(dollars):,.2f}"


def parse_dollars_to_cents(value: str) -> int | None:
    try:
        normalized = str(value).strip().replace("$", "").replace(",", "")
        dollars = Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return None
    if dollars <= 0:
        return None
    return int((dollars * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


def cents_to_dollar_string(value: int | None) -> str:
    if value in (None, ""):
        return ""
    try:
        cents = Decimal(str(value))
    except InvalidOperation:
        return ""
    dollars = cents / Decimal("100")
    return f"{dollars:.2f}"


def get_selected_account_amounts() -> dict[str, int]:
    selected_amounts = st.session_state.get("selected_account_amounts", {})
    if not isinstance(selected_amounts, dict):
        return {}
    sanitized: dict[str, int] = {}
    for account_id, amount in selected_amounts.items():
        try:
            amount_cents = int(amount)
        except (TypeError, ValueError):
            continue
        if amount_cents > 0:
            sanitized[account_id] = amount_cents
    return sanitized


def get_total_selected_account_amount_cents() -> int:
    return sum(get_selected_account_amounts().values())


def get_available_loan_funds_cents() -> int:
    approved_cents = int(st.session_state.get("approved_loan_amount_cents", 0))
    return approved_cents - get_total_selected_account_amount_cents()


def render_loan_funds_side_panel() -> None:
    approved_cents = int(st.session_state["approved_loan_amount_cents"])
    selected_cents = get_total_selected_account_amount_cents()
    available_cents = approved_cents - selected_cents
    selected_count = len(st.session_state.get("selected_account_ids", []))
    panel_value_class = "loan-panel-value"
    if available_cents < 0:
        panel_value_class += " is-negative"

    alert_blocks: list[str] = []
    selection_info = str(st.session_state.get("loan_selection_info", "")).strip()
    selection_errors = st.session_state.get("loan_selection_errors", [])
    if available_cents < 0:
        alert_blocks.append(
            f"<div class='loan-panel-alert loan-panel-alert-error'>Over selected by {format_cents(abs(available_cents))}. "
            "Reduce a selected amount or deselect a liability.</div>"
        )
    elif selection_info:
        alert_blocks.append(f"<div class='loan-panel-alert loan-panel-alert-info'>{selection_info}</div>")

    if isinstance(selection_errors, list):
        for error in selection_errors[:3]:
            alert_blocks.append(f"<div class='loan-panel-alert loan-panel-alert-error'>{error}</div>")

    alert_markup = "".join(alert_blocks)

    st.markdown(
        f"""
        <div class="loan-panel-fixed">
          <div class="loan-panel">
            <div class="loan-panel-kicker">Funding Snapshot</div>
            <div class="loan-panel-title">Available Loan Funds</div>
            <div class="{panel_value_class}">{format_cents(available_cents)}</div>
            <div class="loan-panel-row"><span>Approved Loan Amount</span><strong>{format_cents(approved_cents)}</strong></div>
            <div class="loan-panel-row"><span>Selected Liability Amount</span><strong>{format_cents(selected_cents)}</strong></div>
            <div class="loan-panel-row"><span>Selected Liabilities</span><strong>{selected_count}</strong></div>
            {alert_markup}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_account_option(account: dict[str, Any] | None) -> str:
    if not account:
        return "Unknown account"
    liability = account.get("liability", {})
    name = liability.get("name", account.get("id", "Account"))
    mask = liability.get("mask", "----")
    account_id = account.get("id", "")
    return f"{name} ••••{mask} ({account_id[-6:]})"


def show_summary_card(items: dict[str, str]) -> None:
    lines = "".join(
        f"<div class='summary-row'><span>{label}</span><strong>{value}</strong></div>"
        for label, value in items.items()
    )
    st.markdown(f"<div class='summary-card'>{lines}</div>", unsafe_allow_html=True)


def show_success_banner(message: str) -> None:
    st.markdown(f"<div class='success-banner'>{message}</div>", unsafe_allow_html=True)


def render_method_error(exc: MethodApiError) -> None:
    if exc.response_body:
        st.error(f"{exc}")
        st.json(exc.response_body)
    else:
        st.error(str(exc))


def render_invalid_state(resource_name: str, payload: Any) -> None:
    st.error(
        f"The stored `{resource_name}` response is missing an `id`, so the workflow cannot continue from this step."
    )
    if payload is not None:
        st.json(payload)
    if st.button(f"Clear invalid {resource_name} state", use_container_width=True):
        st.session_state[resource_name] = None
        if resource_name == "entity":
            st.session_state["connect"] = None
            st.session_state["accounts"] = []
            st.session_state["entity_products"] = None
            st.session_state["selected_account_ids"] = []
            st.session_state["selected_account_amounts"] = {}
            st.session_state["loan_selection_errors"] = []
            st.session_state["loan_selection_info"] = ""
            st.session_state["webhooks"] = []
            st.session_state["subscriptions"] = []
            st.session_state["payment_instruments"] = []
            st.session_state["payment"] = None
            st.session_state["current_step"] = 0
        st.rerun()


def reset_poc() -> None:
    keys_to_clear = [
        "current_step",
        "borrower_form",
        "api_logs",
        "entity",
        "connect",
        "accounts",
        "entity_products",
        "selected_account_ids",
        "selected_account_amounts",
        "loan_selection_errors",
        "loan_selection_info",
        "webhooks",
        "subscriptions",
        "payment_instruments",
        "payment",
        "selected_test_phone",
        "applied_test_phone",
        "source_account_id",
        "webhook_url",
        "webhook_internal_token",
        "webhook_auth_token",
        "webhook_expected_auth_header",
        "webhook_hmac_secret",
        "approved_loan_amount_cents",
        "payment_description",
        "payment_amount_usd",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    account_checkbox_keys = [key for key in st.session_state if key.startswith("account_select_")]
    for key in account_checkbox_keys:
        del st.session_state[key]

    account_amount_keys = [key for key in st.session_state if key.startswith("account_amount_")]
    for key in account_amount_keys:
        del st.session_state[key]

    init_session_state()


def render_api_inspector() -> None:
    current_step = st.session_state["current_step"]
    logs = [log for log in st.session_state["api_logs"] if log.step == current_step]

    st.markdown(
        """
        <div class="inspector-shell">
          <div class="inspector-title">API Inspector</div>
          <div class="inspector-sub">Requests from the active step appear here.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not logs:
        st.info("No API calls yet for this step.")
        return

    for index, log in enumerate(logs, start=1):
        title = f"{index}. {log.method} {log.url} · {log.response_status} · {log.duration_ms}ms"
        with st.expander(title, expanded=index == len(logs)):
            st.caption(log.label)
            st.markdown("**Request headers**")
            st.json(log.request_headers)
            if log.request_body is not None:
                st.markdown("**Request body**")
                st.json(log.request_body)
            st.markdown("**Response body**")
            st.json(log.response_body)
            st.markdown("**cURL**")
            st.code(build_curl_command(log), language="bash")


def render_default_api_responses() -> None:
    st.markdown(
        """
        <div class="inspector-shell">
          <div class="inspector-title">Default API Responses</div>
          <div class="inspector-sub">Reference responses from the local JSON files.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for index, item in enumerate(REFERENCE_RESPONSES):
        with st.expander(f"{item['title']} · {item['endpoint']}", expanded=index == 0):
            st.json(item["response"])


def render_api_side_panel() -> None:
    live_tab, defaults_tab = st.tabs(["Live API Inspector", "Default API Responses"])
    with live_tab:
        render_api_inspector()
    with defaults_tab:
        render_default_api_responses()


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --page-bg: radial-gradient(circle at top right, rgba(0, 48, 135, 0.10), transparent 28rem), linear-gradient(180deg, #f4f7fb 0%, #eef2f8 100%);
          --surface: rgba(255, 255, 255, 0.94);
          --surface-strong: #ffffff;
          --border-subtle: rgba(15, 23, 42, 0.10);
          --text-strong: #172033;
          --text-muted: #536179;
          --text-soft: #6b778c;
          --accent-soft: #e8f0ff;
          --success-bg: #ecfdf3;
          --success-border: #abefc6;
          --success-text: #027a48;
          --input-bg: #ffffff;
          --input-border: rgba(23, 32, 51, 0.16);
          --input-border-focus: rgba(11, 77, 180, 0.52);
          --input-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
          --soft-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
        }
        @media (prefers-color-scheme: dark) {
          :root {
            --page-bg: radial-gradient(circle at top right, rgba(74, 144, 217, 0.18), transparent 24rem), linear-gradient(180deg, #09111f 0%, #0d1728 100%);
            --surface: rgba(10, 18, 32, 0.88);
            --surface-strong: rgba(17, 26, 42, 0.96);
            --border-subtle: rgba(165, 180, 201, 0.16);
            --text-strong: #edf3ff;
            --text-muted: #c2cee3;
            --text-soft: #97a6bf;
            --accent-soft: rgba(27, 73, 146, 0.30);
            --success-bg: rgba(6, 78, 59, 0.32);
            --success-border: rgba(52, 211, 153, 0.28);
            --success-text: #9df3cb;
            --input-bg: rgba(12, 20, 33, 0.96);
            --input-border: rgba(165, 180, 201, 0.24);
            --input-border-focus: rgba(122, 179, 232, 0.64);
            --input-shadow: 0 12px 28px rgba(0, 0, 0, 0.26);
            --soft-shadow: 0 12px 26px rgba(0, 0, 0, 0.24);
          }
        }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: transparent !important; }
        .stApp { background: var(--page-bg); color: var(--text-strong); }
        .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
        .block-container h1, .block-container h2, .block-container h3, .block-container h4, .block-container h5, .block-container h6, .block-container label { color: var(--text-strong); }
        .block-container [data-testid="stMarkdownContainer"] p, .block-container [data-testid="stCaptionContainer"] { color: var(--text-muted); }
        [data-testid="stSidebar"] {
          background: linear-gradient(180deg, rgba(11, 18, 32, 0.98) 0%, rgba(18, 28, 44, 0.98) 100%);
          border-right: 1px solid rgba(255, 255, 255, 0.06);
        }
        [data-testid="stSidebar"] * { color: #eef4ff !important; }
        .hero-card {
          background: linear-gradient(135deg, #003087 0%, #0e4aa8 100%);
          color: white;
          border-radius: 24px;
          padding: 1.5rem;
          box-shadow: 0 18px 40px rgba(0, 48, 135, 0.22);
          margin-bottom: 1rem;
        }
        .hero-card h1 { margin: 0.1rem 0 0.4rem; font-size: clamp(1.9rem, 3vw, 3.1rem); line-height: 1.05; letter-spacing: -0.03em; }
        .hero-card p { margin: 0; color: rgba(255, 255, 255, 0.88); font-size: 1.02rem; max-width: 48rem; }
        .hero-kicker { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.18em; color: rgba(255, 255, 255, 0.74); }
        .summary-card, .account-card, .inspector-shell {
          background: var(--surface);
          border: 1px solid var(--border-subtle);
          border-radius: 22px;
          padding: 1rem 1.1rem;
          box-shadow: var(--soft-shadow);
        }
        [data-testid="column"]:has(.loan-panel-fixed) {
          align-self: flex-start !important;
        }
        .loan-panel-fixed {
          position: fixed;
          top: 4.85rem;
          right: 1.35rem;
          width: min(24rem, calc(100vw - 2rem));
          z-index: 20;
        }
        .loan-panel {
          background: var(--surface);
          border: 1px solid var(--border-subtle);
          border-radius: 24px;
          padding: 1.1rem 1.15rem;
          box-shadow: var(--soft-shadow);
        }
        .loan-panel-kicker {
          color: var(--text-soft);
          font-size: 0.74rem;
          font-weight: 700;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          margin-bottom: 0.45rem;
        }
        .loan-panel-title {
          color: var(--text-muted);
          font-size: 0.95rem;
          font-weight: 700;
        }
        .loan-panel-value {
          color: var(--text-strong);
          font-size: clamp(1.9rem, 3vw, 2.55rem);
          font-weight: 800;
          letter-spacing: -0.03em;
          margin: 0.2rem 0 0.95rem;
        }
        .loan-panel-value.is-negative { color: #ffb4b4; }
        .loan-panel-row {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          padding: 0.5rem 0;
          border-top: 1px solid var(--border-subtle);
        }
        .loan-panel-row span { color: var(--text-muted); }
        .loan-panel-row strong { color: var(--text-strong); }
        .loan-panel-alert {
          margin-top: 0.75rem;
          border-radius: 16px;
          padding: 0.8rem 0.9rem;
          font-weight: 600;
        }
        .loan-panel-alert-error {
          background: rgba(179, 59, 59, 0.16);
          border: 1px solid rgba(179, 59, 59, 0.32);
          color: #f6c7c7;
        }
        .loan-panel-alert-info {
          background: rgba(11, 77, 180, 0.14);
          border: 1px solid rgba(11, 77, 180, 0.22);
          color: var(--text-strong);
        }
        .summary-row { display: flex; justify-content: space-between; gap: 1rem; padding: 0.35rem 0; font-size: 0.95rem; }
        .summary-row span { color: var(--text-muted); }
        .summary-row strong { color: var(--text-strong); }
        .success-banner {
          background: var(--success-bg);
          border: 1px solid var(--success-border);
          color: var(--success-text);
          border-radius: 16px;
          padding: 0.85rem 1rem;
          margin: 0.5rem 0 1rem;
          font-weight: 600;
        }
        .account-card { margin: 0.65rem 0 0.35rem; }
        .account-head { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: 0.8rem; align-items: start; }
        .account-name { font-size: 1rem; font-weight: 700; color: var(--text-strong); }
        .account-sub { font-size: 0.85rem; color: var(--text-muted); margin-top: 0.1rem; }
        .account-badge { border-radius: 999px; padding: 0.35rem 0.7rem; font-size: 0.76rem; font-weight: 700; white-space: nowrap; }
        .badge-ok { background: var(--success-bg); color: var(--success-text); }
        .badge-muted { background: rgba(127, 138, 161, 0.16); color: var(--text-muted); }
        .account-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; }
        .account-grid span { display: block; color: var(--text-muted); font-size: 0.78rem; margin-bottom: 0.2rem; }
        .account-grid strong { font-size: 0.95rem; color: var(--text-strong); }
        .inspector-shell { background: linear-gradient(180deg, #101828 0%, #1d2939 100%); color: white; margin-bottom: 1rem; }
        .inspector-title { font-size: 1rem; font-weight: 800; }
        .inspector-sub { color: rgba(255, 255, 255, 0.72); font-size: 0.85rem; margin-top: 0.2rem; }
        .spacer-12 { height: 0.75rem; }
        [data-testid="stForm"] {
          background: var(--surface);
          border: 1px solid var(--border-subtle);
          border-radius: 24px;
          padding: 1.1rem 1.1rem 0.7rem;
          box-shadow: var(--soft-shadow);
        }
        div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="select"] > div, .stTextInput > div > div, .stNumberInput > div > div {
          background: var(--input-bg) !important;
          border: 1px solid var(--input-border) !important;
          border-radius: 16px !important;
          box-shadow: var(--input-shadow) !important;
          min-height: 3.1rem;
        }
        div[data-baseweb="input"]:focus-within, div[data-baseweb="base-input"]:focus-within, div[data-baseweb="select"]:focus-within > div, .stTextInput > div > div:focus-within, .stNumberInput > div > div:focus-within {
          border-color: var(--input-border-focus) !important;
          box-shadow: 0 0 0 4px rgba(11, 77, 180, 0.12) !important;
        }
        div[data-baseweb="input"] input, div[data-baseweb="base-input"] input, .stTextInput input, .stNumberInput input, textarea {
          color: var(--text-strong) !important;
          -webkit-text-fill-color: var(--text-strong) !important;
          background: transparent !important;
          font-weight: 600 !important;
        }
        .stButton > button, .stFormSubmitButton > button {
          border: 0 !important;
          border-radius: 16px !important;
          min-height: 3rem;
          font-weight: 700 !important;
          background: linear-gradient(135deg, #003087 0%, #0e4aa8 100%) !important;
          color: white !important;
          box-shadow: 0 14px 30px rgba(0, 48, 135, 0.22) !important;
        }
        .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; margin-bottom: 0.9rem; }
        .stTabs [data-baseweb="tab"] {
          background: var(--surface) !important;
          border: 1px solid var(--border-subtle) !important;
          border-radius: 999px !important;
          color: var(--text-muted) !important;
        }
        .stTabs [aria-selected="true"] { background: var(--accent-soft) !important; color: var(--text-strong) !important; }
        [data-testid="stInfo"] {
          background: linear-gradient(90deg, rgba(11, 77, 180, 0.14), rgba(122, 179, 232, 0.14)) !important;
          border: 1px solid rgba(11, 77, 180, 0.14) !important;
          color: var(--text-strong) !important;
          border-radius: 18px !important;
        }
        .stDataFrame, [data-testid="stDataFrame"] {
          border-radius: 18px;
          overflow: hidden;
          border: 1px solid var(--border-subtle);
          box-shadow: var(--soft-shadow);
        }
        @media (max-width: 1100px) {
          .loan-panel-fixed {
            position: static;
            width: 100%;
          }
        }
        @media (max-width: 900px) { .account-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        @media (max-width: 640px) { .hero-card { padding: 1.2rem 1.15rem; } .hero-card p { font-size: 0.96rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
