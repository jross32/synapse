# Synapse Accounts - shared identity service

Host this single durable identity service over HTTPS for all Synapse desktop clients. All clients use the same `SYNAPSE_ACCOUNTS_BASE_URL`. Each desktop keeps its project data locally; only its profile/preferences/host metadata are synced.

- Image: `cloud/accounts/Dockerfile` with source context at the repository root
- Service port: `8788`, healthcheck: `/v1/health`
- Mount a **persistent** Railway volume at `/data`
- Set `SYNAPSE_ACCOUNTS_DATABASE_URL=sqlite:////data/synapse-accounts.sqlite`
- Set `SYNAPSE_ACCOUNTS_BASE_URL` to the service's public HTTPS base URL
- Set `SYNAPSE_GOOGLE_CLIENT_ID` and `SYNAPSE_GOOGLE_CLIENT_SECRET` in Railway secrets *only after* configuring a Google OAuth web client. Its authorized redirect URI must be `https://<account-service-host>/v1/oauth/google/callback`.

**Never** commit OAuth secrets, passwords, session tokens, or the persistent account database. Use one replica with SQLite and a durable mounted volume; migrate to Postgres before scaling replicas. Do not expose local daemon auth tokens to the account backend. Sharing one login is not permission to execute commands on another computer; remote MCP routing needs an independently authenticated device relay.
