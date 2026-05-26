#!/bin/bash
# News Crew 실행 스크립트

set -e

# 프로젝트 디렉토리
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 확인/생성
if [ ! -d ".venv" ]; then
    echo "가상환경 생성 중..."
    python3 -m venv .venv
fi

# 가상환경 활성화
source .venv/bin/activate

# 의존성 설치
echo "의존성 확인 중..."
pip install -q -r requirements.txt 2>/dev/null

# .env 파일 확인
if [ ! -f ".env" ]; then
    echo "경고: .env 파일이 없습니다. .env.example을 복사하세요."
    echo "  cp .env.example .env"
    echo "  그 후 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHANNEL_ID를 설정하세요."
    exit 1
fi

# 로그 디렉토리 생성
mkdir -p logs

# 데이터베이스 초기화 (첫 실행 시에만)
if [ ! -f "news_crew.db" ]; then
    echo "데이터베이스 초기화 중..."
    python init_db.py
fi

# 메인 실행
echo "News Crew 시작..."
python main.py