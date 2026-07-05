# Brand Watcher dedicated-tenant template (bwtemplate)

`bwtemplate.aunoo.ai` is the golden template for spinning up dedicated Brand Watcher
tenants — full monolith instances that expose only the Brand Watcher surface.
New customer tenants are stamped out from it (dir + venv + DB dump), then seeded
with the customer's brand.

## Dedicated mode

Two env vars turn a tenant into a Brand-Watcher-only instance:

```
BW_DEDICATED_MODE=1            # hides the non-BW surface, lands on Brand Watcher
ENABLED_MODULES=brand_watcher  # disables the other analysis modules
```

`BW_DEDICATED_MODE` is read by `app/core/modules.py::is_dedicated_bw()` and exposed
to the frontend as `dedicated_mode` on `GET /api/modules`. Effects:

- `/` redirects to `/explore` (`stats_routes.py`)
- Explore page pins to the Brand Watcher tab; News Feed / Emerging Topics /
  Observer Agents / Saved / Briefing Desk tabs and the module-config gear are hidden
  (`NewsFeedPage.tsx`)
- Sidebar shows only the Brand Watcher entry (Operations HQ / Anticipate / Gather
  hidden), settings trimmed to App Configuration, "Brand Watcher" subtitle under the
  logo (`SharedNavigation.tsx`)
- Topic filter header and "Set up topic" button hidden
- The first-login topic wizard is skipped entirely: login and change-password
  redirects bypass `/onboarding` (`auth_routes.py`, `main.py`), and the
  `/onboarding` page itself redirects to `/explore`
- The frontend caches `dedicated_mode` in sessionStorage
  (`useModules.ts::getCachedDedicatedMode`) and hides the gated chrome while the
  state is unknown, so the full menu never flashes before `/api/modules` resolves;
  `SharedNavigation` determines the mode itself, so every page trims correctly

The flag is off (absent) on bugfixing/wileytest/wiley — nothing changes there.
Other pages (`/gather`, `/trend-convergence`, …) are still reachable by direct URL
behind auth; dedicated mode is UI scoping, not route lockdown.

## What's in the template

- **Code**: clone of bugfixing.aunoo.ai at provisioning time (branch
  emergencybugfix/wiley26062026foresight state, incl. Five Signals + dedicated mode)
- **DB** (`bwtemplate`, dump at `/var/tmp/bw_template.dump`, alembic head
  `bw_017_signals_xnet`): full schema (164 tables) with all tenant data wiped.
  Kept: `mediabias` (MBFC reference), `organizational_profiles` (generic ones,
  "Generic Enterprise" is default), `auspex_prompts`, settings/monitor-status
  singletons, `alembic_version`. Wiped: articles and everything derived, all bw_*
  data (zero brands), keyword groups/monitored keywords, observer agents, module
  data, forecasts, saved artifacts, notifications, training samples.
- **Users**: `admin` only, `force_password_change=true`. Credentials in
  `/var/tmp/bwtemplate_dbpw.txt` (root-only; DB password line 1, admin password line 2).
- **config.json** (`app/config/config.json`): single generic "Brand Monitoring"
  topic carrying the BW taxonomy (categories/future signals/sentiment scale) as the
  seed pattern for per-brand topics.
- **API keys**: inherited from bugfixing `.env` (shared OpenAI/Anthropic/collectors/
  `AUNOO_SAAS_MCP_KEY`/`XPOZ_API_KEY`). Per-customer tenants should get their own
  saas MCP key (quota attribution) — mint per tenant via saas `create_workspace_key`.
- `.env` is encrypted at rest (`.env.encrypted`, systemd decrypt/encrypt hooks like
  bugfixing). `models` is a symlink to `/home/orochford/shared-models`.

## First-run onboarding wizard

When the Brand Watcher tab loads with zero configured brands (every fresh
tenant), it shows a three-step wizard instead of an empty dashboard
(`BrandWatcherOnboarding.tsx`): primary brand (name, description, keywords with
AI suggest), at least one competitor (required — benchmarks and share-of-voice
need a peer; AI-suggested competitor names offered), review & launch. Creation
goes through the existing API: `POST /brands` per brand,
`PUT /brands/{id}/set-primary`, `POST /brands/{id}/setup-monitoring`
(topic + keyword group each). Seeding a brand at provision time is therefore
optional — a tenant can be handed over unseeded and the customer walks the wizard.

## Spinning up a new tenant

`scripts/provision_brand_tenant.py` (run as root) automates the whole playbook
below plus brand seeding and verification:

```
provision_brand_tenant.py provision --slug acme --brand "Acme Publishing" \
    --aliases "Acme Corp,ACME" --keywords "Acme Press"   # full stamp-out
provision_brand_tenant.py provision --slug acme --brand "Acme" --skip-nginx  # no TLS/site
provision_brand_tenant.py destroy --slug acme --yes      # complete teardown
```

Credentials land in `/var/tmp/<slug>_credentials.txt` (root-only). The manual
steps, for reference:

Per tenant X (slug = DB name, user `X_user`), following the proven clone playbook:

1. `rsync -a` bwtemplate dir → `/home/orochford/tenants/X.aunoo.ai/` with ANCHORED
   excludes `/models/`, `/cache/`, `.venv/`, `.env*`, `ui/node_modules/`,
   `__pycache__/`; rsync `.venv/` separately; `ln -sfn /home/orochford/shared-models models`
2. `CREATE ROLE X_user LOGIN PASSWORD '<hex>'`; `createdb -O X_user X`;
   `CREATE EXTENSION vector`; `pg_restore --no-owner --role=X_user -j4 -d X
   /var/tmp/bw_template.dump`
3. `.env`: sed-swap PORT / DOMAIN / DB_NAME / DB_USER / DB_PASSWORD / DATABASE_URL /
   SYNC_DATABASE_URL, regenerate FLASK_SECRET_KEY + NORN_SECRET_KEY, keep
   `BW_DEDICATED_MODE=1` + `ENABLED_MODULES=brand_watcher`; encrypt with
   `env_encryption.py encrypt <dir>` (as orochford)
4. systemd: copy `bwtemplate.aunoo.ai.service`, swap names, `daemon-reload`,
   `enable --now`
5. nginx: `setup_site.py --domain X.aunoo.ai --backend-port <port> --email …
   --no-enable-modsec` — the modsec flag is REQUIRED: this nginx build has no
   ModSecurity module, and without the flag the generated config contains a
   `modsecurity` directive that fails `nginx -t` box-wide. If that happens, comment
   the modsec lines in sites-available and reload. Then certbot if the script
   didn't get there.
6. **Seed the brand**: `bw_brands` row (name, aliases, config incl.
   `social_keyword_excludes`), a "Brand Monitoring <Brand>" keyword group +
   `monitored_keywords`, matching topic in `app/config/config.json` (copy the
   "Brand Monitoring" template topic), reset admin password
7. Verify: service active, `GET /api/modules` → `dedicated_mode: true` + only
   brand_watcher enabled, `/` → `/explore`, BW APIs return clean empty states,
   login forces password change

## Refreshing the template

After code changes ship to bugfixing: rsync code + built static + templates from
bugfixing into bwtemplate, `alembic upgrade head` on the bwtemplate DB, restart,
re-dump to `/var/tmp/bw_template.dump`. The dump must stay readable by the
postgres OS user (`chown root:postgres`, `chmod 640`) — pg_restore runs as
postgres and 600/root breaks provisioning. The DB stays clean as long as nothing
is ingested (no keyword groups exist, so collectors gather nothing).

The bwtemplate service can be left stopped when not needed
(`systemctl stop bwtemplate.aunoo.ai.service`) — the template artifacts are the
directory and the dump.
