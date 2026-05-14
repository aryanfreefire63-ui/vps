# OpenShift Deploy

## Required Environment Variables

Set these in OpenShift Deployment > Environment:

```text
TG_BOT_TOKEN=your_bot_token
PREMIUM_SESSION_B64=base64 of premium_account.session
ADMIN_CONFIG_JSON=contents of admin_config.json
PREDICTION_STATE_JSON={"sent_issue_numbers":[]}
```

`ADMIN_CONFIG_JSON` and `PREDICTION_STATE_JSON` are optional, but useful for restoring settings.

## Create PREMIUM_SESSION_B64 on Windows PowerShell

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("premium_account.session")) | Set-Content premium_session_b64.txt
```

Open `premium_session_b64.txt` and paste the whole value into OpenShift as `PREMIUM_SESSION_B64`.

## Create ADMIN_CONFIG_JSON

```powershell
Get-Content admin_config.json -Raw | Set-Content admin_config_for_openshift.txt
```

Paste `admin_config_for_openshift.txt` into OpenShift as `ADMIN_CONFIG_JSON`.

## Notes

- Do not commit `.session`, `.env`, or log files to GitHub.
- Use a private GitHub repo if possible.
- OpenShift free/sandbox apps may restart. If it restarts, the env vars restore the session/config at startup.
