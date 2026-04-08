from __future__ import annotations

from typing import Any

import streamlit as st

from source.config import DEFAULTS_REFERENCE, METHOD_REFERENCE
from source.method_api import MethodApiError
from source.stream_util import (
    add_log,
    build_client,
    format_account_option,
    get_account_summary,
    get_connect_product_status,
    get_test_account_profile,
    get_test_account_profiles,
    has_resource_id,
    parse_dollars_to_cents,
    render_invalid_state,
    render_method_error,
    show_success_banner,
    show_summary_card,
)


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

    test_profiles = get_test_account_profiles()
    phone_options = [profile["phone"] for profile in test_profiles]
    if st.session_state.get("selected_test_phone") not in phone_options:
        st.session_state["selected_test_phone"] = phone_options[0]

    selected_test_phone = st.selectbox(
        "Dev test phone number",
        phone_options,
        index=phone_options.index(st.session_state["selected_test_phone"]),
        help="Select a Method-provisioned dev phone number to prefill the borrower profile.",
    )
    st.session_state["selected_test_phone"] = selected_test_phone

    if st.session_state.get("applied_test_phone") != selected_test_phone:
        selected_profile = get_test_account_profile(selected_test_phone)
        if selected_profile is not None:
            borrower_form = selected_profile
            st.session_state["borrower_form"] = selected_profile.copy()
            st.session_state["applied_test_phone"] = selected_test_phone

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
    summary_items = {
        "Entity ID": entity["id"],
        "Borrower": f"{entity['individual']['first_name']} {entity['individual']['last_name']}",
        "Entity status": entity.get("status", "unknown"),
    }
    connect_product = get_connect_product_status()
    if connect_product:
        summary_items["Connect product status"] = connect_product.get("status", "unknown")
    show_summary_card(summary_items)

    if connect_product and connect_product.get("status") != "available":
        status_error = connect_product.get("status_error") or {}
        st.warning(
            f"Connect is currently `{connect_product.get('status', 'unknown')}` for this entity. "
            f"{status_error.get('message', 'Method did not return an availability message.')}"
        )
        if status_error:
            st.json(status_error)

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
            products, products_log = client.list_entity_products(entity["id"])
            add_log(products_log)
            st.session_state["entity_products"] = products
            connect_product = products.get("connect", {})
            if connect_product and connect_product.get("status") != "available":
                status_error = connect_product.get("status_error") or {}
                raise MethodApiError(
                    status_error.get("message", "Connect is unavailable for this organization."),
                    response_body=products,
                )
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
    selected_ids: list[str] = []

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Accounts found", len(accounts))
    metric_col2.metric("Selectable accounts", len(accounts))
    metric_col3.metric("Currently selected", len(st.session_state["selected_account_ids"]))

    st.markdown("<div class='spacer-12'></div>", unsafe_allow_html=True)

    for account in accounts:
        account_id = account["id"]
        liability = account.get("liability", {})
        key = f"account_select_{account_id}"
        if key not in st.session_state:
            st.session_state[key] = account_id in st.session_state["selected_account_ids"]

        summary = get_account_summary(account)
        st.markdown(
            f"""
            <div class="account-card">
              <div class="account-head">
                <div>
                  <div class="account-name">{liability.get('name', account_id)}</div>
                  <div class="account-sub">{liability.get('type', 'liability')} ••••{liability.get('mask', '----')}</div>
                </div>
                <div class="account-badge badge-ok">Available</div>
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
        )
        if checked:
            selected_ids.append(account_id)

    st.session_state["selected_account_ids"] = selected_ids

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
            "Webhook auth_token": "Generated" if st.session_state["webhook_auth_token"] else "Missing",
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
