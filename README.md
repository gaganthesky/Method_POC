# Method x Citi POC

Streamlit MVP that follows the six-step Citi demo flow with real Method API calls:

1. Create borrower entity
2. Connect liabilities
3. Retrieve and select supported liability accounts
4. Create webhooks and subscribe accounts to `update`
5. Create inbound ACH/Wire payment instruments
6. Optionally create a Method payment if a lender/source `acc_...` is available

## Setup

1. Activate the virtual environment:

```bash
source .venv/bin/activate
```

2. Add your Method API key to `.env`:

```bash
METHOD_API_KEY=sk_...
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the app:

```bash
streamlit run app.py
```

## Notes

- Reference/demo values live in `reference/app_reference.json` so the code stays free of embedded sample borrower data, base URLs, and flow-specific API defaults.
- The app defaults to `https://dev.methodfi.com` to match the Citi demo.
- Step 4 needs a public HTTPS webhook URL plus an auth token.
- Step 6 is optional and needs an existing Method source account ID for the lender/disbursement account.
- The API inspector on the right shows the exact request/response payloads and generated cURL for the active step.
