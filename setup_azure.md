# Azure App Registration Setup

## Step 1 — Register an Azure AD Application

1. Go to <https://portal.azure.com> and sign in with the Microsoft account you use for Outlook.
2. Search for **"App registrations"** and click **New registration**.
3. Fill in:
   - **Name**: `Outlook Email Tracker` (or anything you like)
   - **Supported account types**: *Accounts in any organizational directory and personal Microsoft accounts*
   - **Redirect URI**: leave blank (device code flow doesn't need one)
4. Click **Register**.
5. Copy the **Application (client) ID** — this is your `AZURE_CLIENT_ID`.

## Step 2 — Add API Permissions

1. In your app registration, go to **API permissions → Add a permission → Microsoft Graph → Delegated permissions**.
2. Search for and add:
   - `Mail.Read`
   - `User.Read`
   - `offline_access`
3. Click **Grant admin consent** (if you have admin rights) or just save — the user will consent during sign-in.

## Step 3 — Enable Public Client Flow

1. Go to **Authentication → Advanced settings**.
2. Set **Allow public client flows** to **Yes**.
3. Save.

## Step 4 — Set Up Your .env

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
AZURE_CLIENT_ID=<your application client id from step 1>
AZURE_TENANT_ID=common
ANTHROPIC_API_KEY=<your key from https://console.anthropic.com>
FLASK_SECRET_KEY=<any long random string>
```

## Step 5 — Run the App

```bash
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000> — you'll be guided through Microsoft sign-in via device code flow.
After signing in, click **Refresh Now** to fetch and analyze your first batch of emails.
The app then polls for new emails automatically every 5 minutes.
