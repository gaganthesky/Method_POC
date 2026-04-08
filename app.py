from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
import os

import streamlit as st
from dotenv import load_dotenv

from source.method_api import (
    ApiLogEntry,
    MethodApiError,
    MethodClient,
    build_curl_command,
)
from source.logging import configure_logging
from source.reference_data import load_reference_data


load_dotenv(dotenv_path=Path(".env"), override=False)
configure_logging()
REFERENCE_DATA = load_reference_data()
APP_REFERENCE = REFERENCE_DATA["app"]
METHOD_REFERENCE = REFERENCE_DATA["method"]
DEFAULTS_REFERENCE = REFERENCE_DATA["defaults"]
REFERENCE_RESPONSES = REFERENCE_DATA["reference_responses"]
STEP_TITLES = APP_REFERENCE["steps"]
SUPPORTED_PAYMENT_TYPES = set(METHOD_REFERENCE["supported_payment_types"])

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
        render_api_side_panel()


def init_session_state() -> None:
    defaults = {
        "current_step": 0,
        "borrower_form": REFERENCE_DATA["demo_borrower"].copy(),
        "api_logs": [],
        "entity": None,
        "connect": None,
        "accounts": [],
        "selected_account_ids": [],
        "webhooks": [],
        "subscriptions": [],
        "payment_instruments": [],
        "payment": None,
        "source_account_id": "",
        "webhook_url": "",
        "webhook_auth_token": "",
        "webhook_hmac_secret": "",
        "api_key_override": "",
        "base_url": os.getenv("METHOD_BASE_URL", METHOD_REFERENCE["default_base_url"]),
        "method_version": os.getenv("METHOD_VERSION", METHOD_REFERENCE["default_method_version"]),
        "payment_description": DEFAULTS_REFERENCE["payment_description"],
        "payment_amount_usd": DEFAULTS_REFERENCE["payment_amount_usd"],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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
        st.caption("Step 4 needs a public HTTPS endpoint that returns `200` within five seconds.")
        st.session_state["webhook_url"] = st.text_input(
            "Webhook URL",
            value=st.session_state["webhook_url"],
            placeholder="https://your-app.example.com/method/webhook",
        )
        st.session_state["webhook_auth_token"] = st.text_input(
            "Webhook auth token",
            value=st.session_state["webhook_auth_token"],
            type="password",
        )
        st.session_state["webhook_hmac_secret"] = st.text_input(
            "Webhook HMAC secret",
            value=st.session_state["webhook_hmac_secret"],
            type="password",
        )

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
    step_title = STEP_TITLES[current_step]
    st.caption(f"Current step: {current_step + 1} of {len(STEP_TITLES)}")
    st.markdown(f"### {step_title}")
    st.markdown("<div class='spacer-12'></div>", unsafe_allow_html=True)


def render_active_step() -> None:
    current_step = st.session_state["current_step"]
    if current_step == 0:
        render_create_entity_step()
    elif current_step == 1:
        render_connect_step()
    elif current_step == 2:
        render_accounts_step()
    elif current_step == 3:
        render_subscriptions_step()
    elif current_step == 4:
        render_payment_instruments_step()
    else:
        render_disbursement_step()


def render_create_entity_step() -> None:
    borrower_form = st.session_state["borrower_form"]
    st.subheader("Borrower Onboarding")
    st.write("Create a borrower entity in Method. This mirrors the first screen from the Citi demo.")

    if entity := st.session_state["entity"]:
        show_success_banner(f"Entity ready: `{entity['id']}`")

    with st.form("create_entity_form"):
        col1, col2 = st.columns(2)
        borrower_form["first_name"] = col1.text_input("First name", value=borrower_form["first_name"])
        borrower_form["last_name"] = col2.text_input("Last name", value=borrower_form["last_name"])

        borrower_form["email"] = st.text_input("Email", value=borrower_form["email"])

        col3, col4 = st.columns(2)
        borrower_form["phone"] = col3.text_input("Phone", value=borrower_form["phone"])
        borrower_form["dob"] = col4.text_input("Date of birth", value=borrower_form["dob"], help="YYYY-MM-DD")
        borrower_form["ssn"] = st.text_input("SSN", value=borrower_form["ssn"], help="9 digits")

        st.caption("Address")
        borrower_form["line1"] = st.text_input("Address line 1", value=borrower_form["line1"])
        borrower_form["line2"] = st.text_input("Address line 2", value=borrower_form["line2"])

        col5, col6, col7 = st.columns([2, 1, 1])
        borrower_form["city"] = col5.text_input("City", value=borrower_form["city"])
        borrower_form["state"] = col6.text_input("State", value=borrower_form["state"])
        borrower_form["zip"] = col7.text_input("ZIP", value=borrower_form["zip"])

        submitted = st.form_submit_button("Create borrower →", use_container_width=True)

    st.session_state["borrower_form"] = borrower_form

    if submitted:
        client = build_client()
        if client is None:
            return

        required_fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "dob",
            "ssn",
            "line1",
            "city",
            "state",
            "zip",
        ]
        missing = [field.replace("_", " ").title() for field in required_fields if not borrower_form.get(field)]
        if missing:
            st.error(f"Missing required fields: {', '.join(missing)}")
            return

        try:
            entity, log = client.create_individual(borrower_form)
        except MethodApiError as exc:
            render_method_error(exc)
            return

        add_log(log)
        st.session_state["entity"] = entity
        st.session_state["current_step"] = 1
        st.rerun()


def render_connect_step() -> None:
    entity = st.session_state["entity"]
    if not entity:
        st.warning("Create an entity first.")
        return
    if not has_resource_id(entity):
        render_invalid_state("entity", entity)
        return

    st.subheader("Connect Liabilities")
    st.write("Ask Method to discover the borrower's liability accounts across its network.")
    show_summary_card(
        {
            "Entity ID": entity["id"],
            "Borrower": f"{entity['individual']['first_name']} {entity['individual']['last_name']}",
            "Entity status": entity.get("status", "unknown"),
        }
    )

    if connect := st.session_state["connect"]:
        show_success_banner(
            f"Connect request complete: `{connect.get('id', 'n/a')}` with status `{connect.get('status', 'unknown')}`"
        )
        if st.button("Continue to Retrieve Accounts →", use_container_width=True):
            st.session_state["current_step"] = 2
            st.rerun()
        return

    if st.button("Connect accounts →", use_container_width=True):
        client = build_client()
        if client is None:
            return

        try:
            connect, log = client.connect_liabilities(entity["id"])
        except MethodApiError as exc:
            render_method_error(exc)
            return

        add_log(log)
        st.session_state["connect"] = connect
        st.session_state["current_step"] = 2
        st.rerun()


def render_accounts_step() -> None:
    entity = st.session_state["entity"]
    if not entity:
        st.warning("Create an entity first.")
        return
    if not has_resource_id(entity):
        render_invalid_state("entity", entity)
        return

    st.subheader("Retrieve Accounts")
    st.write("Load liability accounts, inspect the returned balances/update data, and choose which accounts to pay.")

    if not st.session_state["accounts"]:
        st.info("No accounts loaded yet.")
        if st.button("Load accounts →", use_container_width=True):
            fetch_accounts(entity["id"])
        return

    accounts = st.session_state["accounts"]
    selected_ids = []
    supported_count = 0

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Accounts found", len(accounts))
    metric_col2.metric(
        "Supported for disbursement",
        sum(1 for account in accounts if is_supported_account(account)),
    )
    metric_col3.metric("Currently selected", len(st.session_state["selected_account_ids"]))

    st.markdown("<div class='spacer-12'></div>", unsafe_allow_html=True)

    for account in accounts:
        account_id = account["id"]
        liability = account.get("liability", {})
        key = f"account_select_{account_id}"
        if key not in st.session_state:
            st.session_state[key] = account_id in st.session_state["selected_account_ids"]

        supported = is_supported_account(account)
        if supported:
            supported_count += 1

        summary = get_account_summary(account)
        status_badge = "Supported" if supported else "Unsupported in this POC"
        st.markdown(
            f"""
            <div class="account-card">
              <div class="account-head">
                <div>
                  <div class="account-name">{liability.get('name', account_id)}</div>
                  <div class="account-sub">{liability.get('type', 'liability')} ••••{liability.get('mask', '----')}</div>
                </div>
                <div class="account-badge {'badge-ok' if supported else 'badge-muted'}">{status_badge}</div>
              </div>
              <div class="account-grid">
                <div><span>Balance</span><strong>{summary.get('balance', '—')}</strong></div>
                <div><span>Min payment</span><strong>{summary.get('min_payment', '—')}</strong></div>
                <div><span>Due date</span><strong>{summary.get('due_date', '—')}</strong></div>
                <div><span>APR</span><strong>{summary.get('apr', '—')}</strong></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        checked = st.checkbox(
            f"Select {liability.get('name', account_id)}",
            key=key,
            disabled=not supported,
        )
        if checked:
            selected_ids.append(account_id)

    st.session_state["selected_account_ids"] = selected_ids

    if supported_count == 0:
        st.warning(
            "No supported account types were returned. This POC currently enables: "
            f"{', '.join(METHOD_REFERENCE['supported_payment_types'])}."
        )
        return

    if st.button(
        f"Continue with {len(selected_ids)} account(s) →",
        use_container_width=True,
        disabled=not selected_ids,
    ):
        st.session_state["current_step"] = 3
        st.rerun()


def render_subscriptions_step() -> None:
    selected_ids = st.session_state["selected_account_ids"]
    if not selected_ids:
        st.warning("Select at least one account first.")
        return

    st.subheader("Subscribe Updates")
    webhook_events = ", ".join(f"`{event}`" for event in METHOD_REFERENCE["webhook_event_types"])
    subscription_name = METHOD_REFERENCE["subscription_enroll"]
    st.write(
        f"Register {webhook_events} webhooks, then subscribe each selected liability to the `{subscription_name}` subscription."
    )
    show_summary_card(
        {
            "Selected accounts": str(len(selected_ids)),
            "Webhook URL": st.session_state["webhook_url"] or "Not configured",
            "Webhook auth token": "Configured" if st.session_state["webhook_auth_token"] else "Missing",
        }
    )

    if st.session_state["webhooks"] and st.session_state["subscriptions"]:
        show_success_banner(
            f"{len(st.session_state['webhooks'])} webhooks and {len(st.session_state['subscriptions'])} subscriptions created."
        )
        if st.button("Continue to Payment Instruments →", use_container_width=True):
            st.session_state["current_step"] = 4
            st.rerun()
        return

    if st.button("Create webhooks & subscribe →", use_container_width=True):
        client = build_client()
        if client is None:
            return

        webhook_url = st.session_state["webhook_url"].strip()
        auth_token = st.session_state["webhook_auth_token"].strip()
        hmac_secret = st.session_state["webhook_hmac_secret"].strip()

        if not webhook_url or not auth_token:
            st.error("Webhook URL and webhook auth token are required for this step.")
            return

        created_webhooks: list[dict[str, Any]] = []
        created_subscriptions: list[dict[str, Any]] = []

        try:
            for event_type in METHOD_REFERENCE["webhook_event_types"]:
                webhook, log = client.create_webhook(
                    event_type=event_type,
                    url=webhook_url,
                    auth_token=auth_token,
                    hmac_secret=hmac_secret or None,
                )
                created_webhooks.append(webhook)
                add_log(log)

            for account_id in selected_ids:
                subscription, log = client.subscribe_account(
                    account_id,
                    enroll=METHOD_REFERENCE["subscription_enroll"],
                )
                created_subscriptions.append(subscription)
                add_log(log)
        except MethodApiError as exc:
            render_method_error(exc)
            return

        st.session_state["webhooks"] = created_webhooks
        st.session_state["subscriptions"] = created_subscriptions
        st.session_state["current_step"] = 4
        st.rerun()


def render_payment_instruments_step() -> None:
    selected_ids = st.session_state["selected_account_ids"]
    if not selected_ids:
        st.warning("Select at least one account first.")
        return

    st.subheader("Payment Instruments")
    st.write("Generate inbound ACH/Wire details for each selected liability account.")

    if st.session_state["payment_instruments"]:
        render_payment_instrument_table()
        if st.button("Continue to Disbursement →", use_container_width=True):
            st.session_state["current_step"] = 5
            st.rerun()
        return

    if st.button("Generate payment instruments →", use_container_width=True):
        client = build_client()
        if client is None:
            return

        created_instruments: list[dict[str, Any]] = []
        try:
            for account_id in selected_ids:
                instrument, log = client.create_payment_instrument(
                    account_id,
                    instrument_type=METHOD_REFERENCE["payment_instrument_type"],
                )
                created_instruments.append(instrument)
                add_log(log)
        except MethodApiError as exc:
            render_method_error(exc)
            return

        st.session_state["payment_instruments"] = created_instruments
        st.session_state["current_step"] = 5
        st.rerun()


def render_disbursement_step() -> None:
    payment_instruments = st.session_state["payment_instruments"]
    selected_ids = st.session_state["selected_account_ids"]
    accounts = {account["id"]: account for account in st.session_state["accounts"]}

    st.subheader("Disburse Funds")
    st.write(
        "This screen mirrors the demo's final step. For Citi's real-world flow, the routing/account numbers below can be used for outbound disbursement. If you also have a Method source account, you can create a Method `/payments` record here."
    )

    if payment_instruments:
        render_payment_instrument_table()
    else:
        st.info("Generate payment instruments first.")
        return

    st.markdown("<div class='spacer-12'></div>", unsafe_allow_html=True)
    st.markdown("### Optional Method Payment")

    account_options = {format_account_option(accounts[account_id]): account_id for account_id in selected_ids}
    if not account_options:
        st.warning("No destination accounts are selected.")
        return

    destination_label = st.selectbox("Destination account", list(account_options.keys()))
    destination_account_id = account_options[destination_label]

    col1, col2 = st.columns(2)
    st.session_state["payment_amount_usd"] = col1.text_input(
        "Amount (USD)",
        value=st.session_state["payment_amount_usd"],
    )
    st.session_state["payment_description"] = col2.text_input(
        "Description",
        value=st.session_state["payment_description"],
    )

    source_account_id = st.session_state["source_account_id"].strip()
    if not source_account_id:
        st.warning("Add a lender/source `acc_...` in the sidebar to call `POST /payments`.")

    if payment := st.session_state["payment"]:
        show_success_banner(
            f"Payment created: `{payment.get('id', 'n/a')}` with status `{payment.get('status', 'unknown')}`"
        )
        st.json(payment)

    amount_cents = parse_dollars_to_cents(st.session_state["payment_amount_usd"])
    disabled = source_account_id == "" or amount_cents is None
    if amount_cents is None:
        st.error("Enter a valid payment amount such as `50.00`.")

    if st.button("Create Method payment →", use_container_width=True, disabled=disabled):
        client = build_client()
        if client is None:
            return

        try:
            payment, log = client.create_payment(
                source=source_account_id,
                destination=destination_account_id,
                amount=amount_cents,
                description=st.session_state["payment_description"].strip() or DEFAULTS_REFERENCE["payment_description"],
            )
        except MethodApiError as exc:
            render_method_error(exc)
            return

        add_log(log)
        st.session_state["payment"] = payment
        st.rerun()


def render_payment_instrument_table() -> None:
    accounts = {account["id"]: account for account in st.session_state["accounts"]}
    rows = []
    for instrument in st.session_state["payment_instruments"]:
        account = accounts.get(instrument["account_id"], {})
        liability = account.get("liability", {})
        inbound = instrument.get(METHOD_REFERENCE["payment_instrument_response_key"]) or {}
        rows.append(
            {
                "Account": liability.get("name", instrument["account_id"]),
                "Type": liability.get("type", "liability"),
                "Method account ID": instrument["account_id"],
                "Payment instrument ID": instrument["id"],
                "Routing number": inbound.get("routing_number", "—"),
                "Account number": inbound.get("account_number", "—"),
                "Status": instrument.get("status", "unknown"),
            }
        )

    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)


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


def render_api_side_panel() -> None:
    live_tab, defaults_tab = st.tabs(["Live API Inspector", "Default API Responses"])
    with live_tab:
        render_api_inspector()
    with defaults_tab:
        render_default_api_responses()


def render_default_api_responses() -> None:
    st.markdown(
        """
        <div class="inspector-shell">
          <div class="inspector-title">Default API Responses</div>
          <div class="inspector-sub">Reference responses from the demo/docs, loaded from the local reference JSON.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for index, item in enumerate(REFERENCE_RESPONSES):
        with st.expander(f"{item['title']} · {item['endpoint']}", expanded=index == 0):
            st.json(item["response"])


def fetch_accounts(entity_id: str) -> None:
    client = build_client()
    if client is None:
        return

    try:
        accounts, log = client.list_accounts(
            entity_id,
            account_type=METHOD_REFERENCE["account_filters"]["type"],
            status=METHOD_REFERENCE["account_filters"]["status"],
            expand=METHOD_REFERENCE["account_filters"].get("expand", []),
        )
    except MethodApiError as exc:
        render_method_error(exc)
        return

    add_log(log)
    st.session_state["accounts"] = accounts
    for account in accounts:
        key = f"account_select_{account['id']}"
        if key not in st.session_state:
            st.session_state[key] = False
    st.rerun()


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


def has_resource_id(resource: Any) -> bool:
    return isinstance(resource, dict) and bool(resource.get("id"))


def is_supported_account(account: dict[str, Any]) -> bool:
    liability_type = account.get("liability", {}).get("type")
    return liability_type in SUPPORTED_PAYMENT_TYPES


def get_account_summary(account: dict[str, Any]) -> dict[str, str]:
    update = account.get("update") or {}
    product = (
        update.get("credit_card")
        or update.get("personal_loan")
        or update.get("auto_loan")
        or update.get("mortgage")
        or update.get("student_loans")
        or {}
    )

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
    return f"${dollars:,.2f}"


def parse_dollars_to_cents(value: str) -> int | None:
    try:
        dollars = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return None
    if dollars <= 0:
        return None
    return int((dollars * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


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
            st.session_state["selected_account_ids"] = []
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
        "selected_account_ids",
        "webhooks",
        "subscriptions",
        "payment_instruments",
        "payment",
        "source_account_id",
        "webhook_url",
        "webhook_auth_token",
        "webhook_hmac_secret",
        "payment_description",
        "payment_amount_usd",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    account_checkbox_keys = [key for key in st.session_state if key.startswith("account_select_")]
    for key in account_checkbox_keys:
        del st.session_state[key]

    init_session_state()


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --page-bg: radial-gradient(circle at top right, rgba(0, 48, 135, 0.10), transparent 28rem), linear-gradient(180deg, #f4f7fb 0%, #eef2f8 100%);
          --surface: rgba(255, 255, 255, 0.94);
          --surface-strong: #ffffff;
          --surface-muted: #f7f9fc;
          --surface-contrast: #0f172a;
          --border-subtle: rgba(15, 23, 42, 0.10);
          --border-strong: rgba(0, 48, 135, 0.20);
          --text-strong: #172033;
          --text-muted: #536179;
          --text-soft: #6b778c;
          --accent: #0b4db4;
          --accent-soft: #e8f0ff;
          --success-bg: #ecfdf3;
          --success-border: #abefc6;
          --success-text: #027a48;
          --input-bg: #ffffff;
          --input-border: rgba(23, 32, 51, 0.16);
          --input-border-focus: rgba(11, 77, 180, 0.52);
          --input-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
          --card-shadow: 0 16px 36px rgba(15, 23, 42, 0.08);
          --soft-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
        }
        @media (prefers-color-scheme: dark) {
          :root {
            --page-bg: radial-gradient(circle at top right, rgba(74, 144, 217, 0.18), transparent 24rem), linear-gradient(180deg, #09111f 0%, #0d1728 100%);
            --surface: rgba(10, 18, 32, 0.88);
            --surface-strong: rgba(17, 26, 42, 0.96);
            --surface-muted: rgba(24, 34, 51, 0.96);
            --surface-contrast: #dce6f7;
            --border-subtle: rgba(165, 180, 201, 0.16);
            --border-strong: rgba(74, 144, 217, 0.34);
            --text-strong: #edf3ff;
            --text-muted: #c2cee3;
            --text-soft: #97a6bf;
            --accent: #7ab3e8;
            --accent-soft: rgba(27, 73, 146, 0.30);
            --success-bg: rgba(6, 78, 59, 0.32);
            --success-border: rgba(52, 211, 153, 0.28);
            --success-text: #9df3cb;
            --input-bg: rgba(12, 20, 33, 0.96);
            --input-border: rgba(165, 180, 201, 0.24);
            --input-border-focus: rgba(122, 179, 232, 0.64);
            --input-shadow: 0 12px 28px rgba(0, 0, 0, 0.26);
            --card-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
            --soft-shadow: 0 12px 26px rgba(0, 0, 0, 0.24);
          }
        }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
          background: transparent !important;
        }
        .stApp {
          background:
            var(--page-bg);
          color: var(--text-strong);
        }
        .block-container {
          padding-top: 1.2rem;
          padding-bottom: 2rem;
        }
        .block-container h1,
        .block-container h2,
        .block-container h3,
        .block-container h4,
        .block-container h5,
        .block-container h6,
        .block-container label,
        .block-container [data-testid="stMarkdownContainer"] p,
        .block-container [data-testid="stCaptionContainer"] {
          color: var(--text-strong);
        }
        .block-container [data-testid="stMarkdownContainer"] p,
        .block-container [data-testid="stCaptionContainer"] {
          color: var(--text-muted);
        }
        [data-testid="stSidebar"] {
          background: linear-gradient(180deg, rgba(11, 18, 32, 0.98) 0%, rgba(18, 28, 44, 0.98) 100%);
          border-right: 1px solid rgba(255, 255, 255, 0.06);
        }
        [data-testid="stSidebar"] * {
          color: #eef4ff !important;
        }
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] div[data-baseweb="input"],
        [data-testid="stSidebar"] div[data-baseweb="select"] > div {
          background: rgba(255, 255, 255, 0.08) !important;
          border-color: rgba(255, 255, 255, 0.14) !important;
        }
        .hero-card {
          background: linear-gradient(135deg, #003087 0%, #0e4aa8 100%);
          color: white;
          border-radius: 24px;
          padding: 1.5rem 1.5rem 1.3rem;
          box-shadow: 0 18px 40px rgba(0, 48, 135, 0.22);
          margin-bottom: 1rem;
        }
        .hero-card h1 {
          margin: 0.1rem 0 0.4rem;
          font-size: clamp(1.9rem, 3vw, 3.1rem);
          line-height: 1.05;
          letter-spacing: -0.03em;
        }
        .hero-card p {
          margin: 0;
          color: rgba(255, 255, 255, 0.88);
          font-size: 1.02rem;
          max-width: 48rem;
        }
        .hero-kicker {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.18em;
          color: rgba(255, 255, 255, 0.74);
        }
        .summary-card, .account-card, .inspector-shell {
          background: var(--surface);
          border: 1px solid var(--border-subtle);
          border-radius: 22px;
          padding: 1rem 1.1rem;
          box-shadow: var(--soft-shadow);
        }
        .summary-row {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          padding: 0.35rem 0;
          font-size: 0.95rem;
        }
        .summary-row span {
          color: var(--text-muted);
        }
        .summary-row strong {
          color: var(--text-strong);
        }
        .success-banner {
          background: var(--success-bg);
          border: 1px solid var(--success-border);
          color: var(--success-text);
          border-radius: 16px;
          padding: 0.85rem 1rem;
          margin: 0.5rem 0 1rem;
          font-weight: 600;
        }
        .account-card {
          margin: 0.65rem 0 0.35rem;
        }
        .account-head {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          margin-bottom: 0.8rem;
          align-items: start;
        }
        .account-name {
          font-size: 1rem;
          font-weight: 700;
          color: var(--text-strong);
        }
        .account-sub {
          font-size: 0.85rem;
          color: var(--text-muted);
          margin-top: 0.1rem;
        }
        .account-badge {
          border-radius: 999px;
          padding: 0.35rem 0.7rem;
          font-size: 0.76rem;
          font-weight: 700;
          white-space: nowrap;
        }
        .badge-ok {
          background: var(--success-bg);
          color: var(--success-text);
        }
        .badge-muted {
          background: rgba(127, 138, 161, 0.16);
          color: var(--text-muted);
        }
        .account-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 0.75rem;
        }
        .account-grid span {
          display: block;
          color: var(--text-muted);
          font-size: 0.78rem;
          margin-bottom: 0.2rem;
        }
        .account-grid strong {
          font-size: 0.95rem;
          color: var(--text-strong);
        }
        .inspector-shell {
          background: linear-gradient(180deg, #101828 0%, #1d2939 100%);
          color: white;
          margin-bottom: 1rem;
          box-shadow: var(--card-shadow);
        }
        .inspector-title {
          font-size: 1rem;
          font-weight: 800;
        }
        .inspector-sub {
          color: rgba(255, 255, 255, 0.72);
          font-size: 0.85rem;
          margin-top: 0.2rem;
        }
        .spacer-12 {
          height: 0.75rem;
        }
        [data-testid="stForm"] {
          background: var(--surface);
          border: 1px solid var(--border-subtle);
          border-radius: 24px;
          padding: 1.1rem 1.1rem 0.7rem;
          box-shadow: var(--soft-shadow);
        }
        [data-testid="stForm"] [data-testid="stWidgetLabel"] p,
        .stTextInput label p,
        .stSelectbox label p,
        .stCheckbox label p,
        .stNumberInput label p {
          color: var(--text-muted) !important;
          font-weight: 600;
          letter-spacing: 0.01em;
        }
        div[data-baseweb="input"],
        div[data-baseweb="base-input"],
        div[data-baseweb="select"] > div,
        .stTextInput > div > div,
        .stNumberInput > div > div {
          background: var(--input-bg) !important;
          border: 1px solid var(--input-border) !important;
          border-radius: 16px !important;
          box-shadow: var(--input-shadow) !important;
          min-height: 3.1rem;
        }
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="base-input"]:focus-within,
        div[data-baseweb="select"]:focus-within > div,
        .stTextInput > div > div:focus-within,
        .stNumberInput > div > div:focus-within {
          border-color: var(--input-border-focus) !important;
          box-shadow: 0 0 0 4px rgba(11, 77, 180, 0.12) !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input,
        .stTextInput input,
        .stNumberInput input,
        textarea {
          color: var(--text-strong) !important;
          -webkit-text-fill-color: var(--text-strong) !important;
          caret-color: var(--accent) !important;
          font-weight: 600 !important;
          background: transparent !important;
        }
        div[data-baseweb="input"] input::placeholder,
        div[data-baseweb="base-input"] input::placeholder,
        .stTextInput input::placeholder,
        .stNumberInput input::placeholder,
        textarea::placeholder {
          color: var(--text-soft) !important;
          opacity: 0.9 !important;
        }
        .stButton > button,
        .stFormSubmitButton > button {
          border: 0 !important;
          border-radius: 16px !important;
          min-height: 3rem;
          font-weight: 700 !important;
          letter-spacing: 0.01em;
          background: linear-gradient(135deg, #003087 0%, #0e4aa8 100%) !important;
          color: white !important;
          box-shadow: 0 14px 30px rgba(0, 48, 135, 0.22) !important;
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
          filter: brightness(1.03);
          transform: translateY(-1px);
        }
        .stTabs [data-baseweb="tab-list"] {
          gap: 0.5rem;
          margin-bottom: 0.9rem;
        }
        .stTabs [data-baseweb="tab"] {
          background: var(--surface) !important;
          border: 1px solid var(--border-subtle) !important;
          border-radius: 999px !important;
          color: var(--text-muted) !important;
          padding-left: 1rem !important;
          padding-right: 1rem !important;
        }
        .stTabs [aria-selected="true"] {
          background: var(--accent-soft) !important;
          border-color: var(--border-strong) !important;
          color: var(--text-strong) !important;
        }
        [data-testid="stInfo"] {
          background: linear-gradient(90deg, rgba(11, 77, 180, 0.14), rgba(122, 179, 232, 0.14)) !important;
          border: 1px solid rgba(11, 77, 180, 0.14) !important;
          color: var(--text-strong) !important;
          border-radius: 18px !important;
        }
        [data-testid="stWarning"],
        [data-testid="stError"],
        [data-testid="stSuccess"] {
          border-radius: 18px !important;
        }
        [data-testid="stMetricValue"],
        [data-testid="stMetricLabel"] {
          color: var(--text-strong) !important;
        }
        .stDataFrame, [data-testid="stDataFrame"] {
          border-radius: 18px;
          overflow: hidden;
          border: 1px solid var(--border-subtle);
          box-shadow: var(--soft-shadow);
        }
        @media (max-width: 900px) {
          .account-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
        @media (max-width: 640px) {
          .hero-card {
            padding: 1.2rem 1.15rem;
          }
          .hero-card p {
            font-size: 0.96rem;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
