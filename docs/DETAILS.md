# Syslog-demo: full details

[Back to the short README](../README.md)

**Live demo:** https://syslog.albertycliu.xyz (fake data, no login)

A syslog alert portal, built as a demo for SRE work. It runs on containers locally and on Kubernetes (K3s) through GitOps with Argo CD.

## 1. What it is and why it matters for SRE

**What it does.** A network or NOC team receives syslog lines from routers, switches, load balancers and firewalls. This portal turns those lines into a short list of alerts per infra (`ALPHA` and `BRAVO`) and per device. People can acknowledge an alert, pause it, mute the same error for a while, escalate it, and set rules per device: which severities alert, which keywords always alert, which keywords are ignored, and auto-ack time windows. Every change is written to an audit log with the name the person typed.

**Who uses it.** An on-call network team that needs to see what is open, who touched it and why.

**SRE skills it shows**

- GitOps: manifests live in a separate repo and Argo CD applies them (app-of-apps, automated sync with prune and self-heal).
- CI/CD: GitHub Actions tests, builds two images, pushes them to GHCR and commits the new image tag to the GitOps repo.
- Containers: one Dockerfile per component, a compose file for local runs, a stateless backend behind an nginx proxy.
- Kubernetes: Deployments, Services, a MariaDB StatefulSet with a volume, Secrets created by hand, namespace per app.
- Operations: a health endpoint, a collector status API and page, an audit log, rollback with `git revert`.

**What is deliberately simple or simulated**

- All devices are fictional (20 of them, on the documentation IP ranges 192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24).
- The real portal read logs from Elasticsearch. Here a **demo log generator** replaces it, and the collector reads fake lines from `backend/demo_data.py` every 20 seconds.
- The rule engine, pause and mute logic, auto-ack, audit log and the collector run history are the real code paths. Only the input is fake.

## 2. Architecture

| Component | Tech | Notes |
| --- | --- | --- |
| Frontend | Vue 3 + Quasar (Vite), served by nginx | Same-origin: nginx proxies `/api/` and `/static/` to the backend through the `API_UPSTREAM` variable. Polls every 15 s. Browser says "Alpha alert" or "Bravo alert" for new open alerts (sound switch in the top bar). |
| Backend | Flask + SQLAlchemy, gunicorn | One worker with 4 threads, so the collector thread runs once. Listens on port 5100 (not published). On start it creates tables and loads the demo data. |
| Collector | Thread inside the backend | Every `COLLECT_INTERVAL_SECONDS` it reads fake lines from the last `COLLECT_WINDOW_MINUTES`, matches them to devices, applies the rules and writes alerts. A MariaDB lock stops two workers collecting at once. |
| Database | MariaDB 11.1 | Database `syslog_demo`. Local: your own server or the bundled `db` profile. Kubernetes: a StatefulSet in the app namespace. |
| GitOps repo | Kustomize + Argo CD | [`Albertycl/Gitops-apps`, `manifests/syslog-demo/`](https://github.com/Albertycl/Gitops-apps/tree/main/manifests/syslog-demo). |

**Request flow.** Browser → nginx (frontend container, port 80) → `/api/...` proxied to the backend (port 5100) → MariaDB. The collector thread writes alerts into the same database, and the browser reads them on its next poll.

## 3. Install and run

### (a) Locally with Docker Compose

Prerequisites: Docker with the compose plugin, and a MariaDB or MySQL server you can reach. If you have none, use the bundled one (see below).

```bash
cp .env.example .env
# edit .env: set DATABASE_URL (see below)
docker compose up --build
```

Open <http://localhost:8090>. Stop with `Ctrl+C`, or `docker compose down` if you started it with `-d`.

Variables in `.env`:

| Variable | Meaning | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy URL, for example `mysql+pymysql://root:<password>@<host>:3306/syslog_demo`. Required. | none |
| `MYSQL_ROOT_PASSWORD` | Root password of the bundled database (only with the `db` profile). Required there: MariaDB refuses to start without it. | none |
| `COLLECT_INTERVAL_SECONDS` | How often the demo collector runs. `0` turns it off. | `20` |
| `COLLECT_WINDOW_MINUTES` | How far back each run looks. | `5` |
| `CORS_ORIGINS` | Browser origins allowed to call the API, comma separated. Add the address you open the portal on if it is not `localhost`. | `http://localhost:8090` |

Your own database: create an empty database named `syslog_demo` first (`CREATE DATABASE syslog_demo;`). The tables are created on start.

Bundled database: in `.env` set `MYSQL_ROOT_PASSWORD=<password>` and `DATABASE_URL=mysql+pymysql://root:<password>@mariadb:3306/syslog_demo`, then run `docker compose --profile db up --build`.

The demo data loads on every start. Devices and keywords load only when the device table is empty, so edits you make in the portal stay. The sample alerts are refreshed each time.

### (b) On Kubernetes (K3s) with Argo CD

1. Prerequisites: a K3s cluster with Argo CD installed and `kubectl` pointing at it. The demo is served at https://syslog.albertycliu.xyz through a Traefik IngressRoute and a cert-manager certificate (both in `Gitops-apps`). To reach it without the hostname, use a port-forward to the frontend Service: `kubectl -n syslog-demo port-forward svc/frontend 8090:80` (list the Services with `kubectl -n syslog-demo get svc`).
2. One-time bootstrap. It applies the root Application, which watches `apps/` in the GitOps repo:
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/Albertycl/Gitops-apps/main/argocd/root-app.yaml
   ```
3. Argo CD creates the namespace `syslog-demo` on the first sync. Then create the Secret by hand. It is never stored in Git:
   - Name: `syslog-demo-db`
   - Keys: `database-url` (the SQLAlchemy URL pointing at the in-cluster MariaDB service) and `root-password`.
   ```bash
   kubectl -n syslog-demo create secret generic syslog-demo-db \
     --from-literal=root-password='<choose one>' \
     --from-literal=database-url='mysql+pymysql://root:<same password>@mariadb:3306/syslog_demo'
   ```
   Pods wait until the Secret exists.
4. After the first CI run, set both GHCR packages (`syslog-demo-backend`, `syslog-demo-frontend`) to **public**. The pods have no `imagePullSecrets`, so they show `ImagePullBackOff` until you do.
5. Check:
   ```bash
   kubectl get applications -n argocd      # syslog-demo should be Synced and Healthy
   kubectl get pods -n syslog-demo
   ```

## 4. CI/CD and rollback

Push to `main` runs `.github/workflows/ci.yml`:

1. `test`: install the backend requirements and import the app, then `npm ci && npx quasar build` for the frontend. This also runs on pull requests.
2. `build`: build the backend and frontend images and push them to GHCR (`ghcr.io/albertycl/syslog-demo-backend` and `...-frontend`), tagged with the commit SHA and `latest`.
3. `update-gitops`: run `kustomize edit set image` in `manifests/syslog-demo/` of `Albertycl/Gitops-apps` and push a commit named `deploy <sha>`, using a deploy key stored in the repo secret `GITOPS_DEPLOY_KEY`.
4. Argo CD sees the new commit and syncs (automated, with prune and self-heal).

**Rollback:** `git revert` the `deploy <sha>` commit in `Gitops-apps` and push. Do not use `kubectl rollout undo`, because self-heal puts the old state back.

## 5. Monitoring and known limits

**Monitoring (only what exists)**

- `GET /healthz` on the backend returns `ok`.
- `GET /api/collect/status` returns collector health (last run, failures in 24 h, stale flag). `GET /api/collect/runs` lists recent runs. The **Collector runs** page in the UI shows the same, and a failed or stalled collector shows an error banner.
- The **Log** page shows the audit log (who changed what).
- There are no Prometheus metrics and no alert rules for this app.

**Known limits**

- No real authentication. The name in the "Your name" box is sent as the `X-User` header and is only a typed name. Writes without it get `400 name_required`. The whole write API is open: collecting, and creating, editing and deleting devices, rules and folders need no login, and anyone can send any `X-User` name. The live demo is public on purpose: it holds only made-up data and a reset means deleting the database volume. A real deployment must put authentication in front of it.
- One gunicorn worker (by design, so the collector runs once). It does not scale out as is.
- All data is simulated. Nothing is read from real devices.
- No tests beyond the import and build checks in CI.
