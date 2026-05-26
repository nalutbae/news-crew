#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# News Crew — Raspberry Pi 설치 스크립트
# ═══════════════════════════════════════════════════════════════
#
# 사용법:
#   sudo bash deploy/install_service.sh
#
# 사전 요구:
#   - Raspberry Pi OS (Debian Bookworm 권장)
#   - Python 3.11+ (apt 설치 권장)
#   - 인터넷 연결 (이더넷)
#   - .env 파일 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
#
set -euo pipefail

# ── 설정 ──
INSTALL_DIR="/opt/news-crew"
SERVICE_USER="newscrew"
REPO_URL="https://github.com/nalutbae/news-crew.git"
BRANCH="main"
LOG_DIR="/dev/shm/news-crew"
VENV_DIR="${INSTALL_DIR}/venv"

echo "═══════════════════════════════════════════════════════"
echo "  News Crew — Raspberry Pi 설치"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── 1. 시스템 패키지 ──
echo "[1/7] 시스템 패키지 설치..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git

# ── 2. 서비스 사용자 생성 ──
echo "[2/7] 서비스 사용자 생성..."
if ! id "$SERVICE_USER" &>/dev/null; then
    sudo useradd -r -m -s /bin/bash "$SERVICE_USER"
    echo "  사용자 ${SERVICE_USER} 생성됨"
else
    echo "  사용자 ${SERVICE_USER} 이미 존재"
fi

# ── 3. 저장소 클론 ──
echo "[3/7] 저장소 클론..."
if [ ! -d "${INSTALL_DIR}/.git" ]; then
    sudo git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
else
    echo "  이미 클론됨, pull 수행"
    cd "$INSTALL_DIR" && sudo git pull
fi
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ── 4. 가상환경 + 의존성 ──
echo "[4/7] Python 가상환경 설정..."
sudo -u "$SERVICE_USER" python3 -m venv "$VENV_DIR"
sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --quiet --upgrade pip
sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

# ── 5. .env 확인 ──
echo "[5/7] .env 파일 확인..."
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    echo "  ⚠️  .env 파일이 없습니다!"
    echo "  다음 형식으로 생성하세요:"
    echo "  sudo -u $SERVICE_USER nano ${INSTALL_DIR}/.env"
    echo ""
    echo "  TELEGRAM_BOT_TOKEN=your_bot_token"
    echo "  TELEGRAM_CHAT_ID=-1003902680445"
    echo ""
    read -p "  .env 없이 계속하시겠습니까? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ── 6. tmpfs 로그 디렉토리 ──
echo "[6/7] tmpfs 로그 디렉토리 설정..."
sudo mkdir -p "$LOG_DIR"
sudo chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"

# 재부팅 후에도 tmpfs 로그 디렉토리 유지 (tmpfiles.d)
sudo tee /etc/tmpfiles.d/news-crew.conf > /dev/null <<EOF
d ${LOG_DIR} 0755 ${SERVICE_USER} ${SERVICE_USER} -
EOF

# ── 7. systemd 서비스 등록 ──
echo "[7/7] systemd 서비스 등록..."
sudo cp "${INSTALL_DIR}/deploy/news-crew.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable news-crew.service

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ 설치 완료!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  서비스 시작:"
echo "    sudo systemctl start news-crew"
echo ""
echo "  상태 확인:"
echo "    sudo systemctl status news-crew"
echo ""
echo "  실시간 로그:"
echo "    sudo journalctl -u news-crew -f"
echo ""
echo "  tmpfs 로그 (상세):"
echo "    ls ${LOG_DIR}/"
echo ""
echo "  업데이트:"
echo "    cd ${INSTALL_DIR} && sudo -u ${SERVICE_USER} git pull"
echo "    sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/pip install -r requirements.txt"
echo "    sudo systemctl restart news-crew"
echo ""