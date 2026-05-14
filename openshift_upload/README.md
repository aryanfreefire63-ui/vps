# Telegram Prediction Bot

OpenShift-ready Python Telegram prediction bot.

## Run

The container starts with:

```text
python openshift_start.py
```

## Required OpenShift Environment Variables

```text
TG_BOT_TOKEN
PREMIUM_SESSION_B64
```

Optional:

```text
ADMIN_CONFIG_JSON
PREDICTION_STATE_JSON
```

See `OPENSHIFT_DEPLOY.md` for setup steps.
