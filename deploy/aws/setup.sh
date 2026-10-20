#!/usr/bin/env bash
# First-time setup on AWS EC2 (Ubuntu) — also works on any Ubuntu VPS.
# Run as a sudo-capable user:  bash deploy/aws/setup.sh
set -euo pipefail

echo "==> VentureScope AWS/EC2 setup"

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run as a normal user with sudo, not as root."
  exit 1
fi

echo "==> Installing Docker Engine + Compose plugin"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl git ufw

if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

sudo usermod -aG docker "$USER" || true

echo "==> Configuring UFW (22/80/443)"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw --force enable || true

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f .env ]]; then
  echo ""
  echo "WARNING: $REPO_ROOT/.env is missing."
  echo "Copy .env.production.example -> .env and fill secrets before deploy."
  echo "  cp .env.production.example .env && nano .env"
fi

echo ""
echo "Setup complete."
echo "1. Log out and back in (or: newgrp docker) so docker works without sudo."
echo "2. Ensure DNS A record api.venturescope.tech -> this EC2 public / Elastic IP."
echo "3. Put production secrets in $REPO_ROOT/.env"
echo "4. Run:  bash deploy/aws/deploy.sh"
echo ""
echo "AWS Console: Security Group must also allow TCP 22, 80, 443."
