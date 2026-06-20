#!/usr/bin/env bash
# Install Caddy and terminate TLS for sslip.io hostname (no custom DNS needed).
# Usage on EC2: sudo bash deploy/setup-caddy-sslip.sh [public-ip]
set -euo pipefail

PUBLIC_IP="${1:-$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4)}"
HOSTNAME="${PUBLIC_IP//./-}.sslip.io"

if ! command -v caddy >/dev/null 2>&1; then
  dnf install -y 'dnf-command(copr)' || true
  dnf copr enable -y @caddy/caddy 2>/dev/null || true
  if ! dnf install -y caddy 2>/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/yum.repos.d/caddy-stable.repo
    dnf install -y caddy
  fi
fi

mkdir -p /etc/caddy
cat > /etc/caddy/Caddyfile <<EOF
{
	# Port 80 may be closed on EC2; obtain cert via TLS-ALPN on 443 only.
	acme_ca https://acme-v02.api.letsencrypt.org/directory
}

${HOSTNAME} {
	encode gzip
	tls {
		issuer acme {
			disable_http_challenge
		}
	}
	reverse_proxy 127.0.0.1:8000
}
EOF

systemctl enable --now caddy
systemctl reload caddy || systemctl restart caddy

echo "Caddy listening for https://${HOSTNAME}"
curl -sf "https://${HOSTNAME}/health" | head -c 300
echo
