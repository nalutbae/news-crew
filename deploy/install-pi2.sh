#!/bin/bash
# ==============================================================================
# News Crew - Raspberry Pi 2 설치 스크립트
#
# 사용법:
#   chmod +x deploy/install-pi2.sh
#   ./deploy/install-pi2.sh
#
# 기본 설치 경로: /home/pi/news-crew
# Python 가상환경: /home/pi/news-crew/venv
# ==============================================================================

set -euo pipefail

# ── 설정 ──
INSTALL_DIR="${INSTALL_DIR:-/home/pi/news-crew}"
SERVICE_NAME="news-crew"
SERVICE_FILE="deploy/news-crew.service"
VENV_DIR="${INSTALL_DIR}/venv"
CURRENT_USER="$(whoami)"

echo "========================================"
echo " News Crew - Raspberry Pi 2 설치"
echo "========================================"
echo "설치 경로: ${INSTALL_DIR}"
echo "서비스:    ${SERVICE_NAME}.service"
echo ""

# ── 1. 시스템 요구사항 확인 ──
echo "[1/7] 시스템 요구사항 확인..."

# Python 3.9+ 확인
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3가 설치되어 있지 않습니다."
    echo "설치: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python 버전: ${PYTHON_VERSION}"

if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "  Python 버전 OK (3.9+)"
else
    echo "ERROR: Python 3.9 이상이 필요합니다. 현재: ${PYTHON_VERSION}"
    exit 1
fi

# pip 확인
if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null; then
    echo "  pip3 설치 중..."
    sudo apt update && sudo apt install -y python3-pip
fi

# ── 2. /dev/shm (tmpfs) 설정 ──
echo ""
echo "[2/7] tmpfs 로그 디렉토리 설정 (SD 카드 보호)..."

SHM_LOG_DIR="/dev/shm/news-crew/logs"
sudo mkdir -p "${SHM_LOG_DIR}"
sudo chown "${CURRENT_USER}:${CURRENT_USER}" "/dev/shm/news-crew"
sudo chown "${CURRENT_USER}:${CURRENT_USER}" "${SHM_LOG_DIR}"
echo "  tmpfs 로그 경로: ${SHM_LOG_DIR}"
echo "  참고: 재부팅 시 로그가 삭제됩니다 (Pi 정상 동작)."

# ── 3. 가상환경 생성 ──
echo ""
echo "[3/7] Python 가상환경 생성..."

if [ -d "${VENV_DIR}" ]; then
    echo "  기존 가상환경 발견, 재사용: ${VENV_DIR}"
else
    python3 -m venv "${VENV_DIR}"
    echo "  가상환경 생성 완료: ${VENV_DIR}"
fi

# ── 4. 의존성 설치 ──
echo ""
echo "[4/7] 의존성 설치..."

"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" --quiet
echo "  의존성 설치 완료"

# ── 5. .env 파일 확인 ──
echo ""
echo "[5/7] 환경 설정 (.env) 확인..."

ENV_FILE="${INSTALL_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    echo "  WARNING: .env 파일이 없습니다!"
    echo "  필수 환경변수:"
    echo "    TELEGRAM_BOT_TOKEN=your_bot_token"
    echo "    TELEGRAM_CHANNEL_ID=your_channel_id"
    echo ""
    echo "  .env 파일을 생성해주세요: nano ${ENV_FILE}"
    echo ""
    # 템플릿 생성
    cat > "${ENV_FILE}" <<'ENVEOF'
# News Crew 환경 설정
# 이 파일을 수정한 후 서비스를 재시작하세요:
#   sudo systemctl restart news-crew

# 필수 설정
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=

# Pi 2 최적화 (이미 systemd 서비스에 설정됨, 필요시 오버라이드)
# PI2_MODE=on
# DB_PATH=/home/pi/news-crew/news_crew.db
# LOG_DIR=/dev/shm/news-crew/logs
# CRAWL_MAX_CONCURRENT=1
# MAX_ARTICLES_PER_FEED=50
ENVEEOF
    echo "  .env 템플릿 생성됨: ${ENV_FILE}"
else
    echo "  기존 .env 파일 발견: ${ENV_FILE}"
    # 필수값 확인
    if grep -q "^TELEGRAM_BOT_TOKEN=$" "${ENV_FILE}" 2>/dev/null || \
       ! grep -q "^TELEGRAM_BOT_TOKEN=.\+" "${ENV_FILE}" 2>/dev/null; then
        echo "  WARNING: TELEGRAM_BOT_TOKEN이 설정되지 않았습니다!"
    fi
    if grep -q "^TELEGRAM_CHANNEL_ID=$" "${ENV_FILE}" 2>/dev/null || \
       ! grep -q "^TELEGRAM_CHANNEL_ID=.\+" "${ENV_FILE}" 2>/dev/null; then
        echo "  WARNING: TELEGRAM_CHANNEL_ID가 설정되지 않았습니다!"
    fi
fi

# ── 6. DB 초기화 ──
echo ""
echo "[6/7] 데이터베이스 초기화..."

cd "${INSTALL_DIR}"
"${VENV_DIR}/bin/python" init_db.py
echo "  DB 초기화 완료"

# ── 7. systemd 서비스 설치 ──
echo ""
echo "[7/7] systemd 서비스 설치..."

# 서비스 파일의 경로를 실제 설치 경로로 치환
TEMP_SERVICE=$(mktemp)
sed -e "s|/home/pi/news-crew|${INSTALL_DIR}|g" \
    -e "s|User=pi|User=${CURRENT_USER}|g" \
    -e "s|Group=pi|Group=${CURRENT_USER}|g" \
    "${INSTALL_DIR}/${SERVICE_FILE}" > "${TEMP_SERVICE}"

sudo cp "${TEMP_SERVICE}" "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "${TEMP_SERVICE}"

# 서비스 리로드 및 활성화
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
echo "  서비스 설치 완료: ${SERVICE_NAME}.service"
echo "  부팅 시 자동 시작 활성화됨"

# ── 완료 ──
echo ""
echo "========================================"
echo " 설치 완료!"
echo "========================================"
echo ""
echo "다음 단계:"
echo ""
echo "  1. .env 파일에 텔레그램 설정 추가:"
echo "     nano ${ENV_FILE}"
echo ""
echo "  2. 서비스 시작:"
echo "     sudo systemctl start ${SERVICE_NAME}"
echo ""
echo "  3. 상태 확인:"
echo "     sudo systemctl status ${SERVICE_NAME}"
echo ""
echo "  4. 로그 확인 (tmpfs):"
echo "     ls -la /dev/shm/news-crew/logs/"
echo "     tail -f /dev/shm/news-crew/logs/news_crew.log"
echo ""
echo "  5. 저널 로그 (systemd):"
echo "     journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "SD 카드 보호 상태:"
echo "  - 로그: tmpfs (/dev/shm) -> SD 쓰기 제로"
echo "  - DB:   WAL 모드, synchronous=NORMAL"
echo "  - 아티클: 피드당 최대 50개 유지"
echo ""