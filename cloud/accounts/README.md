# Synapse Accounts - shared identity service

Host this single durable identity service over HTTPS for all Synapse desktop clients. All clients use the same `SYNAPSE_ACCOUNTS_BASE_URL`. Each desktop keeps its project data locally; only its profile/preferences/host metadata are synced.

- Image: `cloud/accounts/Dockerfile` with source context at the repository root
- Service port: `8788`, healthcheck: `/v1/health`
- Mount a **persistent** Railway volume at `/data`
- Set `SYNAPSE_ACCOUNTS_DATABASE_URL=sqlite:////data/synapse-accounts.sqlite`
- Set `SYNAPSE_ACCOUNTS_BASE_URL` to the service's public HTTPS base URL
- Set `SYNAPSE_GOOGLE_CLIENT_ID` and `SYNAPSE_GOOGLE_CLIENT_SECRET` in Railway secrets *only after* configuring a Google OAuth web client. Its authorized redirect URI must be `https://<account-service-host>/v1/oauth/google/callback`.

**Never** commit OAuth secrets, passwords, session tokens, or the persistent account database. Use one replica with SQLite and a durable mounted volume; migrate to Postgres before scaling replicas. Do not expose local daemon auth tokens to the account backend. Sharing one login is not permission to execute commands on another computer; remote MCP routing needs an independently authenticated device relay.

## Device remote-write policy

Authenticated users can GET /v1/devices/access and PUT /v1/devices/{device_id}/access with {remote_write_enabled:true|false}. Enrolled devices default to true. Unknown devices are denied and account isolation is enforced. Any future cloud MCP relay MUST check the device policy immediately before dispatch, not only at enrollment. This policy alone is not a remote transport and does not enable remote code execution.

## Unified MCP relay (v0.1.212)

Required Railway variable: `SYNAPSE_RELAY_SIGNING_KEY`, a unique high-entropy server secret (>=48 characters), configured privately in the service environment. Do not rotate casually: it changes all stable account connector links. The shared service must use durable SQLite in one replica or migrate to Postgres before running multiple writers.

- Every signed-in Synapse Windows daemon registers its current account host using an encrypted, per-device credential and polls `GET /v1/relay/devices/{id}/jobs/next` outbound over HTTPS.
- Signed-in users retrieve the **same** account-level MCP URL at `GET /v1/relay/connector`, can rotate it at `POST /v1/relay/connector/rotate`, and choose a selected computer via `PUT /v1/relay/connector/selection`.
- External clients POST JSON-RPC to `/mcp/<opaque-secret>`. The cloud service never receives a local Synapse daemon auth token and never executes tools itself.
- The dispatch path checks account/device membership and the account-owned `remote_write_enabled` toggle on job creation and again when a device claims the job. The local agent checks the live policy a third time just before invoking localhost MCP. When Off, requests are pinned to `?mode=read` locally. In-flight commands cannot be rolled back after execution begins.
- Account sessions, connector secrets, and device credentials are **separate**. Token hashes are stored in the cloud; each Windows device encrypts its token with per-user DPAPI. Logout attempts cloud revocation and clears the local credential.
- Completed queued JSON-RPC payloads/results are erased once the caller receives them; orphaned/expired jobs are pruned. The cloud does process transient tool inputs and outputs during routing, so avoid sending secrets unless the trust boundary is understood.
- A connector token grants full remote MCP permission to the *selected*, enabled device. Keep the link private and rotate it if exposed. A URL query parameter cannot override the account-selected computer.
- No external ChatGPT/Claude configuration is installed silently; the user copies the single MCP link once into each provider's connector settings.