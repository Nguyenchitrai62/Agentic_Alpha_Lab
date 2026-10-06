# Privacy fix note 2026-10-06 (ops_privacyfix)

Follow-up to `SECRETSCAN_20261006.md`: `.env.example:3-4` and `docs/WEB_DEPLOY.md:30`
now use `admin@example.com` placeholders with a comment that the real mailbox
lives only in the local gitignored `.env`. `.env` was never opened.

## Remaining default in `backend/config.py:34`

Not edited by design: `admin_contact_email` (`backend/config.py:34`) still falls back
to the personal mailbox when `WEB_ADMIN_CONTACT_EMAIL` is unset (see that line;
value not quoted here so this note does not re-commit it).

Changing this default before the owner confirms the local `.env` sets a proper
contact could change the contact shown on locked pipelines / admin fallback, so
it was left for the owner (same reason as the brief: avoid locking the owner out).

## Owner check (local only, do not commit output)

1. Confirm the local `.env` (gitignored, never commit) defines both values:
   `ADMIN_EMAILS` and `WEB_ADMIN_CONTACT_EMAIL` with the real mailbox.
2. Restart the backend and verify the admin login / contact address still works.

## One-line change the owner can make afterwards

In `backend/config.py:34`, replace the hardcoded mailbox default with the placeholder:

```python
admin_contact_email: str = os.getenv("WEB_ADMIN_CONTACT_EMAIL", "admin@example.com").strip()
```

(or `""` to fail closed), once step 1 above is confirmed.

## Git history

The personal mailbox is already in git history (`git log -S ADMIN_EMAILS` = 6 commits
per the scan). Current-tree placeholders do not remove history. Whether to accept
the exposure (spam/phishing + identity-linkage risk) or rewrite history + force-push
(coordinate with all workers; disruptive) is the owner's call. No key rotation is
needed (no API keys/tokens found as values).
