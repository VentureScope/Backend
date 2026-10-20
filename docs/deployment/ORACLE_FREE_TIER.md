# VentureScope — Oracle Always Free (FALLBACK only)

> **Primary path is AWS EC2.** Use this guide only if you have a **real** Visa/Mastercard (Oracle rejects virtual cards).  
> Primary: [`AWS_FREE_TIER.md`](./AWS_FREE_TIER.md) · Friend handoff: [`HANDOFF_AWS_MIGRATION.md`](../../../HANDOFF_AWS_MIGRATION.md)

Replace Azure with a **$0** Always Free ARM VM (API + Celery + Caddy). Frontend stays on **Vercel Hobby**.

> CareerCompass is separate — see [`NEXT_STEPS.md`](../../../NEXT_STEPS.md) Phase 2.

---

## Architecture

```
venturescope.tech  ──►  Vercel (Next.js)
api.venturescope.tech ──►  Oracle VM (Caddy :443 → FastAPI :8000)
                              ├── venturescope-api
                              └── venturescope-worker (Celery)
                                    │
                    Supabase / Upstash / Mailgun / LLM
```

Prefer AWS scripts: [`deploy/aws/`](../../deploy/aws/). On Oracle you can use the same `deploy/aws/` compose (Ubuntu VM). Legacy wrappers: `deploy/oracle/*.sh` → forward to aws.

---

## Checklist before you start

- [ ] Supabase project **not paused** (Free plans pause after ~1 week idle — wake it)
- [ ] Upstash Redis REST URL + token + `rediss://` connect string
- [ ] Mailgun API key + sending domain still verified
- [ ] DNS control for `venturescope.tech`
- [ ] GitHub org access (`VentureScope/Backend`, `VentureScope/Frontend`)
- [ ] LLM token (`HOSTED_LLM_TOKEN`) + optional `SERPER_API_KEY`
- [ ] Oracle Cloud account (Always Free) — card may be required for verification; compute stays $0 if you stay in Always Free shapes

---

## Part 1 — Oracle VM (you do this in the console)

### 1. Create Always Free Ampere instance

1. Open [Oracle Cloud Console](https://cloud.oracle.com) → **Compute → Instances → Create**.
2. Shape: **VM.Standard.A1.Flex** (Ampere). Start with **2 OCPU / 12 GB RAM** if your tenancy free quota allows (Always Free: up to 4 OCPU / 24 GB total across A1 instances).
3. Image: **Canonical Ubuntu 22.04** or **24.04** (aarch64).
4. Networking: assign a **public IPv4**.
5. SSH keys: add your public key.
6. Create the instance. If you see **Out of capacity**, try another **home-region AD** or a different Always Free–eligible region and retry.

### 2. Open firewall in Oracle (VCN)

On the subnet **Security List** or **NSG**, allow ingress:

| Port | Source | Purpose |
|------|--------|---------|
| 22 | Your IP `/32` (preferred) | SSH |
| 80 | `0.0.0.0/0` | HTTP (ACME + redirect) |
| 443 | `0.0.0.0/0` | HTTPS |

### 3. First SSH

```bash
ssh -i ~/.ssh/your_key ubuntu@VM_PUBLIC_IP
# Some images use: opc@...
```

### 4. Clone Backend and run setup

```bash
sudo mkdir -p /opt/venturescope && sudo chown "$USER":"$USER" /opt/venturescope
cd /opt/venturescope
git clone https://github.com/VentureScope/Backend.git
cd Backend
git checkout master-v2

bash deploy/aws/setup.sh
# log out / newgrp docker
newgrp docker
```

### 5. Production `.env`

```bash
cd /opt/venturescope/Backend
cp .env.production.example .env
nano .env   # paste real secrets from Supabase / Upstash / Mailgun / OAuth / LLM
```

Critical values:

- `DATABASE_URL` / `SUPABASE_URL` — Supabase pooler + SSL
- `UPSTASH_REDIS_*` + `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
- `FRONTEND_URL=https://venturescope.tech`
- `GOOGLE_REDIRECT_URI` / `GITHUB_REDIRECT_URI` → `https://api.venturescope.tech/...`

### 6. Point DNS **before** first TLS issue

At your DNS provider:

| Record | Name | Value |
|--------|------|-------|
| A | `api` | `VM_PUBLIC_IP` |

Wait until `dig +short api.venturescope.tech` returns the VM IP.

### 7. Deploy stack

```bash
cd /opt/venturescope/Backend
bash deploy/aws/deploy.sh
```

Caddy will obtain Let's Encrypt certs for `api.venturescope.tech`.

```bash
curl -fsS https://api.venturescope.tech/health
docker compose -f deploy/aws/docker-compose.yml logs -f --tail=100
```

---

## Part 2 — Frontend on Vercel

1. [vercel.com](https://vercel.com) → Import `VentureScope/Frontend` (branch `main`).
2. Environment variables:

   | Name | Value |
   |------|--------|
   | `NEXT_PUBLIC_API_URL` | `https://api.venturescope.tech` |
   | `API_URL` | `https://api.venturescope.tech` |

3. Domains: add `venturescope.tech` and `www.venturescope.tech`.
4. DNS: follow Vercel’s apex/`www` instructions (A/CNAME or nameservers).

---

## Part 3 — Auth cutover

In **Google Cloud Console** and **GitHub OAuth App**, set callback URLs to:

- `https://api.venturescope.tech/api/auth/oauth/google/callback`
- `https://api.venturescope.tech/api/auth/oauth/github/callback`

Authorized JS origins / homepage: `https://venturescope.tech`.

---

## Part 4 — GitHub Actions auto-deploy

In `VentureScope/Backend` → Settings → Secrets:

| Secret | Example |
|--------|---------|
| `AWS_EC2_HOST` | `x.x.x.x` |
| `AWS_EC2_USER` | `ubuntu` |
| `AWS_EC2_SSH_KEY` | full PEM private key |
| `AWS_EC2_DEPLOY_PATH` | `/opt/venturescope/Backend` |

On each push to `master-v2`, [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) SSHes in, `git pull`, and runs `deploy/aws/deploy.sh`.

You can remove old `AZURE_*` / `ORACLE_*` secrets.

---

## Smoke tests

1. `GET https://api.venturescope.tech/health`
2. Open `https://venturescope.tech` — landing loads
3. Register / login + OTP email
4. OAuth Google/GitHub
5. Dashboard chat (WebSocket streaming)
6. CV upload (Supabase Storage)
7. `docker logs venturescope-worker` after a profile update (embedding task)

---

## Ops cheatsheet

```bash
cd /opt/venturescope/Backend
docker compose -f deploy/aws/docker-compose.yml ps
docker compose -f deploy/aws/docker-compose.yml logs -f backend
docker compose -f deploy/aws/docker-compose.yml logs -f worker
bash deploy/aws/deploy.sh          # rebuild after pull
docker compose -f deploy/aws/docker-compose.yml restart worker
```

**Supabase paused?** Unpause in dashboard, then restart containers.

**TLS failing?** DNS must already point at the VM; ports 80/443 open in **both** UFW and Oracle NSG.

**Out of Oracle capacity?** Retry create in another AD/region; temporary fallback is Render free (sleeps — bad for WebSockets), then move back.

---

## Cost reality

| Component | Cost |
|-----------|------|
| Oracle A1 Always Free VM | $0 |
| Vercel Hobby | $0 |
| Supabase / Upstash / Mailgun free tiers | $0 (quotas / pause rules) |
| LLM + Serper | Usage-based (not hosting) |

Stay on Always Free shapes and do not attach paid block volumes beyond free limits.
