# VentureScope Backend — AWS EC2 (primary)

Deploy FastAPI + Celery + Caddy on **Ubuntu EC2** using the AWS Free plan.

Scripts: [`deploy/aws/`](../../deploy/aws/)

- `setup.sh` — Docker + UFW  
- `deploy.sh` — build/up + migrations  
- `docker-compose.yml` — Caddy + API + worker  
- `Caddyfile` — TLS for `api.venturescope.tech`

Research / credits / card policy: [`AWS_RESEARCH_GUIDE.md`](../../../AWS_RESEARCH_GUIDE.md)

**Not forever free:** Free plan credits last ~**6 months** (or until used). Set budget alarms. Frontend stays on Vercel Hobby forever.

---

## 1. Create AWS account

1. https://aws.amazon.com/free/ → Create account → **Free** plan.  
2. Most new customers: **no card**. If a card is required, virtual cards may fail.  
3. Enable root MFA; set a **budget alert**.  
4. Console: https://console.aws.amazon.com/

---

## 2. Launch EC2

1. Region: **`eu-west-2` (London)** or **`eu-central-1` (Frankfurt)** if Supabase is EU.  
2. **EC2 → Launch instance**  
3. Name: `venturescope-api`  
4. AMI: Ubuntu 22.04 or 24.04 LTS  
5. Type: **`t3.small` / `t4g.small`** minimum (2 GB); prefer **medium (4 GB)** if credits allow  
6. Key pair: create + download `.pem`  
7. Security group: SSH **22** (your IP), HTTP **80**, HTTPS **443**  
8. Storage: **20–30 GB gp3**  
9. Launch → copy **public IPv4** (optional: Elastic IP, associate immediately)

---

## 3. SSH, clone, setup

```bash
chmod 400 ~/Downloads/your-key.pem
ssh -i ~/Downloads/your-key.pem ubuntu@EC2_PUBLIC_IP

sudo mkdir -p /opt/venturescope && sudo chown "$USER":"$USER" /opt/venturescope
cd /opt/venturescope
git clone https://github.com/VentureScope/Backend.git
cd Backend
git checkout master-v2

bash deploy/aws/setup.sh
newgrp docker
```

---

## 4. Env + DNS + deploy

```bash
cp .env.production.example .env
nano .env
```

Fill Supabase / Upstash / Mailgun / OAuth / LLM. Set `FRONTEND_URL=https://venturescope.tech`.

DNS **A**: `api.venturescope.tech` → EC2 or Elastic IP.

```bash
bash deploy/aws/deploy.sh
curl -fsS https://api.venturescope.tech/health
```

---

## 5. Frontend

Vercel: `NEXT_PUBLIC_API_URL` + `API_URL` = `https://api.venturescope.tech`  
See [`HANDOFF_AWS_MIGRATION.md`](../../../HANDOFF_AWS_MIGRATION.md).

---

## 6. GitHub Actions

| Secret | Value |
|--------|--------|
| `AWS_EC2_HOST` | EC2 public / Elastic IP |
| `AWS_EC2_USER` | `ubuntu` |
| `AWS_EC2_SSH_KEY` | PEM private key |
| `AWS_EC2_DEPLOY_PATH` | `/opt/venturescope/Backend` |

Workflow: `.github/workflows/deploy.yml` → SSH → `deploy/aws/deploy.sh`.

---

## 7. Before credits expire

Migrate to paid EC2, Hetzner, or Oracle (real card) → update DNS. App data stays in Supabase.

---

## Ops

```bash
cd /opt/venturescope/Backend
docker compose -f deploy/aws/docker-compose.yml ps
docker compose -f deploy/aws/docker-compose.yml logs -f --tail=100
bash deploy/aws/deploy.sh
```

Smoke: `/health`, OTP, OAuth, chat WebSocket, CV upload.
