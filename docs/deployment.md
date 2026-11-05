# Deployment: Railway and Cloudflare R2

How to run the customer portal on Railway, with files in Cloudflare R2, and how to move the data
from the local Docker stack the first time.

**Status: not deployed yet.** The images have been built and run together locally against a scratch
database, behind a simulated proxy, and the copy script against a scratch bucket. Nothing has run on
Railway or R2 yet. Sizes were measured on 2026-11-01, so check them again before cutover.

## Architecture

| Piece      | Runs on    | Start command                                  | Network               |
| ---------- | ---------- | ---------------------------------------------- | --------------------- |
| `api`      | Railway    | Image default (`uvicorn` on port 8001)         | Private               |
| `worker`   | Railway    | `python -m app.worker`                         | None; run one instance |
| `web`      | Railway    | Image default (`next start` on port 3001)      | Public domain, for users and webhooks |
| `Postgres` | Railway    | Railway's image                                | Private               |
| Files      | R2         | Not applicable                                 | S3 API over HTTPS     |

The browser calls `web`, and `web` calls `api` over Railway's private network. PestPac and GoCanvas
post webhooks to `web` too, which forwards them to FastAPI, so `web` is the only public domain. While
`web` is down, webhooks are refused along with the UI.

Both images bind to `0.0.0.0`, as Railway's docs say to. Don't change that to `::`: uvicorn then
listens on IPv6 only. Private DNS only resolves to IPv4 in environments created after October 16,
2025, so use a new project rather than an older environment.

Data to move: a 136 MB database at migration `140240b074ee`, and 22,342 stored files totalling
about 30 GB.

Use Railway's Pro plan. Hobby caps volumes at 5 GB.

## 1. Before you start

The deploy files are `Dockerfile` (`api` and `worker`), `web/Dockerfile` (`web`), and a
`.dockerignore` beside each.

- [ ] Merge the work you want to ship. Railway only builds what's pushed.
- [ ] Review what you stage. `docs/risk-submissions/` and the sample report PDF in `docs/` are
      untracked and not gitignored, so `git add -A` would pick them up. Submissions can hold
      customer data.
- [ ] Install the local tools. `pg_dump` and `pg_restore` run through Docker, so they aren't needed
      on the host.

```bash
brew install rclone railway
```

## 2. Cloudflare R2

1. In the Cloudflare dashboard, open **R2 Object Storage** and create a bucket named
   `customer-portal`. Choose a location hint near your Railway region.
2. Leave public access off. Files only reach users through the API.
3. Under **Manage API Tokens**, create a token with **Object Read & Write**, limited to this bucket.
4. Put the token's **Access Key ID** and **Secret Access Key**, and your **Account ID**, in the
   `R2_*` settings in local `.env`. The secret is shown only once. `scripts/copy_files_to_r2.sh`
   reads these, and the app doesn't.

### Test the app against R2

`app/storage.py` forces path-style addressing, and boto3 sends checksums by default. Cloudflare's
docs don't confirm how either behaves here, so test before copying 30 GB.

Run this from the repository root. These variables override `.env` for this shell only.

```bash
export S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com S3_REGION=auto S3_BUCKET=customer-portal S3_ACCESS_KEY_ID=<key> S3_SECRET_ACCESS_KEY=<secret>
```

```bash
.venv/bin/python -c "from app.storage import get_storage; s = get_storage(); s.put('smoke-test/hello.txt', b'ok', 'text/plain'); print(s.get('smoke-test/hello.txt'))"
```

It should print a `StoredObject` containing `b'ok'`. A checksum or signature error means the client
config in `app/storage.py` needs a small change first. Close the shell afterwards so later commands
don't use these values by accident, and delete `smoke-test/hello.txt` in the R2 dashboard.

## 3. Railway project

1. Create an empty project.
2. Add **Postgres**. Keep the service name `Postgres`, since the variables below refer to it.
3. Under the Postgres service's **Settings → Networking**, enable **Public Access**. This fills in
   `DATABASE_PUBLIC_URL`, which you need for the restore. You'll remove it in step 8.
4. Create `api`, `worker`, and `web` as empty services, and **don't connect the repository yet**. The
   `api` pre-deploy command runs migrations, and they must not reach the database before the restore
   (step 5). You'll connect `augmentws/selectx-customer-portal` in step 6. If a deploy starts by
   accident, cancel it and check the database is still empty.

Check that Postgres is 17 or newer. Local data comes from 17.11.

```bash
docker run --rm postgres:17 psql "$DATABASE_PUBLIC_URL" -At -c "select version();"
```

## 4. Configure the services

### Service settings

| Setting        | `api`                         | `worker`               | `web`                                |
| -------------- | ----------------------------- | ---------------------- | ------------------------------------ |
| Root directory | `/`                           | `/`                    | `/web`                               |
| Watch paths    | `/app/**`, `/alembic/**`, `/alembic.ini`, `/Pipfile*`, `/Dockerfile` | Same as `api` | `/web/**` |
| Start command  | Leave empty                   | `python -m app.worker` | Leave empty                          |
| Health check   | `/health`                     | None                   | `/login`                             |
| Public domain  | No                            | No                     | Yes, port 3001                       |

`api` also needs this pre-deploy command:

```text
/bin/sh -c "alembic upgrade head && python -m app.bootstrap"
```

If it exits non-zero, the deploy stops. It isn't retried.

Generate the `web` domain now, because the variables below use it. If you add a custom domain through
Cloudflare DNS, start with that record set to **DNS only** (grey cloud).

### Variables for `api` and `worker`

Put these in project shared variables and reference them as `${{shared.NAME}}`, so the two services
can't drift apart.

| Variable                      | Value                                                       |
| ----------------------------- | ----------------------------------------------------------- |
| `DATABASE_URL`                | `${{Postgres.DATABASE_URL}}`                                |
| `APP_ENCRYPTION_KEYS`         | **Copy from local `.env`**                                  |
| `JWT_SECRET`                  | New value; `python -c 'import secrets;print(secrets.token_urlsafe(48))'` |
| `WEB_ORIGIN`                  | `https://<web domain>`                                      |
| `S3_ENDPOINT_URL`             | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`             |
| `S3_REGION`                   | `auto`                                                      |
| `S3_BUCKET`                   | `customer-portal`                                           |
| `S3_ACCESS_KEY_ID`            | From the R2 token                                           |
| `S3_SECRET_ACCESS_KEY`        | From the R2 token                                           |
| `BOOTSTRAP_ADMIN_EMAIL`       | **Your existing admin's email**                             |
| `BOOTSTRAP_ADMIN_PASSWORD`    | New random value                                            |
| `OPENROUTER_API_KEY`          | Copy from local `.env`                                      |
| `OPENROUTER_DEFAULT_MODEL`    | Copy from local `.env`                                      |
| `FINDINGS_FALLBACK_MODEL`     | Copy from local `.env`                                      |
| `SYNC_ACTIVE`                 | `false` until step 7                                        |
| `API_DOCS_ENABLED`            | `false`                                                     |
| `PESTPAC_DEBUG_BODIES`        | `false`                                                     |
| `OPENROUTER_DEBUG_BODIES`     | `false`                                                     |

- **`APP_ENCRYPTION_KEYS` must match local.** Stored PestPac and GoCanvas credentials can't be
  decrypted without the same keys.
- **A new `JWT_SECRET` signs everyone out once.** Nothing else depends on it.
- **`BOOTSTRAP_ADMIN_EMAIL` must already exist in the restored data.** `app.bootstrap` runs on every
  `api` deploy and creates a new platform admin with this password if it doesn't find that email.
  It never changes an existing user's password.

Leave out `POSTGRES_*`, `MINIO_*`, and `TEST_DATABASE_URL`: they're local only.

### Variables for one service

| Service | Variable      | Value                                                 |
| ------- | ------------- | ----------------------------------------------------- |
| `api`   | `PORT`        | `8001`                                                |
| `web`   | `PORT`        | `3001`                                                |
| `web`   | `API_URL`     | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}` |
| `web`   | `APP_ORIGINS` | `https://<web domain>`                                |

`APP_ORIGINS` is required: without it the CSRF origin check refuses every sign-in with a 403, because
behind a proxy the app doesn't see its public address. List custom and Railway domains if both are
in use, separated by commas.

## 5. Move the data

`scripts/copy_files_to_r2.sh` copies from MinIO to R2 using the `S3_*` and `R2_*` settings in local
`.env`, then compares the two. It's safe to re-run: it skips files already in R2 and never deletes
anything. It refuses to run if `S3_ENDPOINT_URL` isn't the local MinIO, so keep `.env` pointed at
MinIO, and put production's R2 values only in Railway.

### First file copy (local stays live)

This takes about 40 minutes at 100 Mbps upload. Run it ahead of the cutover so the final pass only
has a little to do. To see what it would do first, add `--dry-run`.

```bash
scripts/copy_files_to_r2.sh
```

### Cutover

1. **Stop the local API and worker**, and leave Docker's Postgres and MinIO running. Webhooks that
   arrive from here until step 7 are lost, and step 7 catches up on them.

2. **Dump the database.** The file holds customer data, so keep it outside the repository and
   delete it when you retire the local stack.

   ```bash
   docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > ~/customer_portal.dump
   ```

3. **Restore it to Railway.** The target must be empty.

   ```bash
   docker run --rm -i postgres:17 pg_restore --no-owner --no-acl --single-transaction --exit-on-error -d "$DATABASE_PUBLIC_URL" < ~/customer_portal.dump
   ```

4. **Copy any new files.** The script ends by comparing the buckets, and exits non-zero if they
   differ.

   ```bash
   scripts/copy_files_to_r2.sh
   ```

5. **Check the restored database.** Compare the row count with the same query on local (22,342 on
   2026-11-01). The version should be `140240b074ee`, or newer migrations will run on the first
   deploy.

   ```bash
   docker run --rm postgres:17 psql "$DATABASE_PUBLIC_URL" -At -c "select version_num from alembic_version;" -c "select count(*) from stored_files;"
   ```

## 6. Deploy and test

Connect `augmentws/selectx-customer-portal` to each service and choose the branch to deploy. Deploy
`api` first, then `worker` and `web`. With `SYNC_ACTIVE=false`, nothing calls PestPac on its own yet.

Check all of these on the public `web` domain:

- [ ] Sign in, then sign out.
- [ ] While signed out, open `/operators`. It should redirect to `/login` on the public domain.
- [ ] Open a stored document and an inspection photo (reads from R2).
- [ ] Finalize a test service report (WeasyPrint and a write to R2).
- [ ] Verify a PestPac connection on the operator page (proves the encryption keys carried over).
- [ ] Open `https://<web domain>/v1/webhooks/gocanvas/00000000-0000-0000-0000-000000000000`. It should
      answer `{"status":"accepted"}` and store nothing, which proves `web` forwards webhooks to `api`.
- [ ] Check the `worker` logs for `Worker started` and the warning that `SYNC_ACTIVE` is off.

## 7. Go live

1. Set `SYNC_ACTIVE=true`, which redeploys `api` and `worker`.
2. Change the webhook URLs. Operator IDs carry over in the restore, so only the host changes.
   - PestPac: `https://<web domain>/v1/webhooks/pestpac`
   - GoCanvas: `https://<web domain>/v1/webhooks/gocanvas/{operator_id}`
3. Confirm new deliveries appear on the operator page's Webhooks and GoCanvas tabs.
4. Catch up on what the gap missed:
   - Run **Orders and notes** on your bill-tos in the UI. This also picks up invoices and conditions.
   - Queue **Sync location** everywhere:

   ```bash
   railway ssh --service worker -- python -m app.resync_locations --dry-run
   ```

   ```bash
   railway ssh --service worker -- python -m app.resync_locations
   ```

GoCanvas webhook deliveries are stored and routed by form root id. The migration sets each risk form it finds to Risk Assessment; check the GoCanvas API tab's Form Processing table.

## 8. After cutover

- [ ] Remove **Public Access** from Postgres, and take `DATABASE_PUBLIC_URL` out of any local shell.
- [ ] Turn on Railway's Postgres backups, and check which ones your plan includes.
- [ ] Schedule a copy of the R2 bucket to a second location. R2 doesn't implement versioning, so an
      overwrite or delete can't be undone, and PestPac files older than
      `PESTPAC_DOCUMENTS_START_DATE` can't be downloaded again.
- [ ] Keep the local stack and the dump until you've run on Railway for a while, then delete them.
- [ ] Test restoring a backup.

## Rollback

- **Before step 7:** restart the local API and worker. Local data is unchanged, and PestPac and
  GoCanvas still point at the old address.
- **After step 7:** Railway has data that local doesn't, so reverse the data move rather than just
  switching back. Set `SYNC_ACTIVE=false`, dump Railway, restore into an empty local database, copy
  R2 back to MinIO, then point the webhooks at the old address.

## Routine deploys

Pushing to the deploy branch redeploys whichever services' watch paths changed. `api` runs new
migrations in its pre-deploy command before the new version starts, while the old version is still
serving, so keep migrations compatible with the running code. A migration that fails stops the
`api` deploy and leaves the old version running.

`worker` deploys from the same pushes but doesn't wait for `api`'s pre-deploy, so it can start on new
code before a migration has run. Make new worker code tolerate that, or deploy the migration first.

## References

- Railway: [Postgres](https://docs.railway.com/guides/postgresql),
  [private networking](https://docs.railway.com/networking/private-networking/how-it-works),
  [monorepos](https://docs.railway.com/guides/monorepo),
  [config as code](https://docs.railway.com/reference/config-as-code),
  [pre-deploy commands](https://docs.railway.com/guides/pre-deploy-command),
  [CLI ssh](https://docs.railway.com/cli/ssh),
  [pricing](https://docs.railway.com/reference/pricing/plans)
- Cloudflare R2: [boto3](https://developers.cloudflare.com/r2/examples/aws/boto3/),
  [S3 compatibility](https://developers.cloudflare.com/r2/api/s3/api/),
  [pricing](https://developers.cloudflare.com/r2/pricing/)
