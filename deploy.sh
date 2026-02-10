#!/bin/bash
# Hostinger VPS Deploy Script
# Kullanim: ssh root@your-vps-ip 'bash -s' < deploy.sh

set -e

echo "=== Beslenme Kocu Deploy ==="

# Docker kurulu mu?
if ! command -v docker &> /dev/null; then
    echo "Docker kuruluyor..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

# Docker Compose kurulu mu?
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Docker Compose kuruluyor..."
    apt-get update && apt-get install -y docker-compose-plugin
fi

# Proje dizini
mkdir -p /opt/dietcoach
cd /opt/dietcoach

# Repo'yu klonla veya guncelle
if [ -d ".git" ]; then
    echo "Repo guncelleniyor..."
    git pull origin claude/setup-code-testing-5dSu4
else
    echo "Repo klonlaniyor..."
    git clone https://github.com/kaankayadan/dietcoach.git .
    git checkout claude/setup-code-testing-5dSu4
fi

# .env dosyasi var mi?
if [ ! -f ".env" ]; then
    echo ""
    echo "=== .env dosyasi olusturuluyor ==="
    echo "Asagidaki bilgileri girin:"
    echo ""

    read -p "Telegram Bot Token: " TELEGRAM_TOKEN
    read -p "Anthropic API Key: " ANTHROPIC_API_KEY
    read -p "Senin Telegram ID'n (admin): " ADMIN_IDS
    read -p "VPS IP adresi veya domain: " VPS_IP

    cat > .env << EOF
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
DB_PASSWORD=dietcoach$(date +%s | sha256sum | head -c 12)
ADMIN_IDS=${ADMIN_IDS}
PAYMENT_URL=http://${VPS_IP}:5000/odeme
EOF
    echo ".env dosyasi olusturuldu!"
fi

# Container'lari baslat
echo ""
echo "Container'lar baslatiliyor..."
docker compose down 2>/dev/null || true
docker compose up -d --build

echo ""
echo "=== Deploy tamamlandi! ==="
echo ""
docker compose ps
echo ""
echo "Bot calisiyor! Telegram'dan test edin."
echo "Odeme sayfasi: $(grep PAYMENT_URL .env | cut -d= -f2-)"
