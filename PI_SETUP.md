# Raspberry Pi 2 배포 가이드

News Crew를 Raspberry Pi 2 Model B (ARMv7, 1GB RAM, 900MHz)에서 운영하기 위한 완전 가이드.

## 사양 요약

| 항목 | 값 |
|------|------|
| SoC | BCM2836 |
| CPU | ARM Cortex-A7 4코어 900MHz |
| RAM | 1GB LPDDR2 |
| Storage | MicroSD (최대 128GB) |
| OS | Raspberry Pi OS Lite (64비트 권장) |

## 1. OS 준비

### 1.1 Raspberry Pi OS Lite 설치

Raspberry Pi Imager로 MicroSD에 OS 설치:

1. [Raspberry Pi Imager](https://www.raspberrypi.com/software/) 다운로드
2. OS 선택: **Raspberry Pi OS Lite (64-bit)** — 데스크탑 환경 불필요
3. 설정 (Ctrl+Shift+X):
   - 호스트명: `newscrew`
   - SSH 활성화 + 공개키 인증
   - 사용자: `pi` / 비밀번호 설정
   - WiFi 설정 (이더넷 권장, 안정성)
   - 로케일: Asia/Seoul, ko_KR.UTF-8

### 1.2 초기 설정

```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 필수 패키지
sudo apt install -y python3 python3-venv python3-pip git

# 스왑 확인 (1GB RAM에서 중요)
free -h
# 스왑이 없으면 추가:
sudo nano /etc/dphys-swapfile
# CONF_SWAPSIZE=512  (기본 100 -> 512로 변경)
sudo systemctl restart dphys-swapfile
```

### 1.3 SD 카드 수명 연장 (선택, 권장)

```bash
# /var/log를 tmpfs로 마운트 (선택)
sudo tee -a /etc/fstab <<'EOF'
# SD 보호: /var/log를 tmpfs로 (재부팅 시 초기화)
tmpfs /var/log tmpfs defaults,noatime,nosuid,mode=0755,size=32m 0 0
EOF

# noatime 마운트 옵션 (SD 쓰기 감소)
sudo sed -i 's/defaults/noatime,defaults/' /etc/fstab
sudo reboot
```

## 2. News Crew 설치

### 2.1 프로젝트 클론

```bash
cd ~
git clone https://github.com/nalutbae/news-crew.git
cd news-crew
```

### 2.2 자동 설치 스크립트

```bash
chmod +x deploy/install-pi2.sh
./deploy/install-pi2.sh
```

스크립트가 수행하는 작업:
- 시스템 요구사항 확인 (Python 3.9+)
- `/dev/shm/news-crew/logs` tmpfs 로그 디렉토리 생성
- Python 가상환경 생성 및 의존성 설치
- `.env` 템플릿 생성
- DB 초기화
- systemd 서비스 설치 및 부팅 자동 시작 활성화

### 2.3 텔레그램 봇 설정

```bash
nano ~/news-crew/.env
```

필수 항목:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=your_channel_id_here
```

### 2.4 서비스 시작

```bash
sudo systemctl start news-crew
sudo systemctl status news-crew
```

## 3. Pi 2 최적화 상세

### 3.1 SD 카드 보호 전략

SD 카드는 쓰기 횟수가 제한되어 있어, 뉴스 크롤러처럼 24/7으로 동작하는 서비스에서는 반드시 보호해야 합니다.

| 최적화 항목 | 방식 | 효과 |
|------------|------|------|
| 로그 저장 | `/dev/shm` (tmpfs) | 로그 쓰기 0건/SD |
| SQLite WAL | journal_mode=WAL | 읽기 중 쓰기 가능, 체크포인트만 실제 쓰기 |
| synchronous=NORMAL | fsync 빈도 감소 | 쓰기 I/O 대폭 감소 |
| mmap_size=8MB | 메모리 매핑 I/O | 디스크 읽기 최소화 |
| wal_autocheckpoint=500 | 500페이지마다 | 대량 체크포인트로 인한 I/O 버스트 방지 |
| temp_store=MEMORY | 임시 테이블 메모리 | 임시 테이블 SD 쓰기 방지 |
| 아티클 정리 | 50개/피드 유지 | DB 크기 일정 유지 |

**쓰기 감소 효과**: 일반 모드 대비 SD 쓰기 약 80-90% 감소 예상.

### 3.2 메모리 최적화

| 항목 | 설정 | 이유 |
|------|------|------|
| 동시 크롤링 | 1개 (순차) | 1GB RAM에서 병렬 처리 시 OOM 위험 |
| 응답 크기 제한 | 1MB | 대형 웹페이지 파싱 시 메모리 폭증 방지 |
| 번역 청크 크기 | 3000자 | 번역 API 호출 시 메모리 사용량 제한 |
| 세션 TTL | 30분 | 유휴 HTTP 세션 자동 해제 |
| 배치 삭제 | 100개/배치 | 대량 DELETE 시 임시 메모리 사용량 제한 |
| SQLite 캐시 | 2MB | 1GB RAM에서 과도한 캐시 방지 |

### 3.3 CPU 최적화

| 항목 | 설정 | 이유 |
|------|------|------|
| 써드파티 로그 억제 | WARNING 레벨 | 불필요한 문자열 포맷팅 CPU 절약 |
| 피드별 크롤링 주기 | 5~1440분 | 불필요한 HTTP 요청 최소화 |
| 순차 크롤링 | max_concurrent=1 | 4코어 900MHz에서 CPU 경합 방지 |

### 3.4 전원 끊김 대응

`synchronous=NORMAL`은 전원 끊김 시 마지막 수초의 트랜잭션이 손실될 수 있습니다. 하지만:

- 뉴스 크롤러는 재시작 시 마지막 체크포인트부터 크롤링 재개
- 손실된 트랜잭션은 단순히 다음 크롤링 주기에서 재처리
- `synchronous=FULL` 대비 SD 수명 연장이 더 중요 (Pi 2에서 SD 교체 번거로움)

## 4. 운영 명령어

```bash
# 서비스 관리
sudo systemctl start news-crew       # 시작
sudo systemctl stop news-crew        # 정지
sudo systemctl restart news-crew     # 재시작
sudo systemctl status news-crew      # 상태 확인

# 로그 조회
tail -f /dev/shm/news-crew/logs/news_crew.log  # 실시간 로그
journalctl -u news-crew -f                      # systemd 저널
journalctl -u news-crew --since "1 hour ago"     # 최근 1시간

# DB 상태
cd ~/news-crew
source venv/bin/activate
python -c "from models import get_engine; e=get_engine(); print(e.execute('PRAGMA journal_mode').fetchone())"
python -c "from models import get_engine; e=get_engine(); print(e.execute('PRAGMA page_count').fetchone())"

# 메모리 사용량
ps aux | grep main.py
free -h
```

## 5. 문제 해결

### 5.1 메모리 부족 (OOM)

```bash
# 현재 메모리 확인
free -h

# 스왑 추가
sudo nano /etc/dphys-swapfile
# CONF_SWAPSIZE=512

# 서비스 재시작
sudo systemctl restart dphys-swapfile
sudo systemctl restart news-crew
```

### 5.2 SD 카드 I/O 에러

```bash
# 디스크 상태 확인
dmesg | grep -i mmc

# 읽기 전용 마운트 감지 시
sudo fsck.ext4 /dev/mmcblk0p2
```

### 5.3 네트워크 불안정

```bash
# WiFi 신호 강도
iwconfig wlan0 | grep -i quality

# 이더넷 권장 (WiFi 불안정 시)
# /etc/systemd/system/news-crew.service에서 Restart=on-failure로 자동 복구
```

### 5.4 tmpfs 로그 소실 (재부팅 후)

tmpfs는 재부팅 시 내용이 사라집니다. 이는 정상 동작입니다:
- 콘솔(journalctl)로 과거 로그 확인 가능
- 디버깅이 필요하면 `LOG_DIR=logs`로 SD에 로그 저장

```bash
# 임시로 SD에 로그 저장
sudo systemctl edit news-crew
# [Service]
# Environment=LOG_DIR=/home/pi/news-crew/logs
sudo systemctl restart news-crew
```

### 5.5 VACUUM (DB 최적화)

DB가 50MB 이상으로 커진 경우에만 수동 실행:

```bash
cd ~/news-crew
source venv/bin/activate
python -c "
from models import get_engine
e = get_engine()
with e.connect() as c:
    size_before = c.execute('PRAGMA page_count').fetchone()[0]
    c.execute('VACUUM')
    size_after = c.execute('PRAGMA page_count').fetchone()[0]
    print(f'VACUUM: {size_before} -> {size_after} pages')
"
```

## 6. 환경변수 참조

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PI2_MODE` | `auto` | Pi 2 모드: auto/on/off |
| `DB_PATH` | `news_crew.db` | SQLite DB 파일 경로 |
| `LOG_DIR` | (자동) | 로그 디렉토리. Pi 2에서 /dev/shm |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |
| `CRAWL_MAX_CONCURRENT` | `1` | 동시 크롤링 수 |
| `CRAWL_MAX_RESPONSE_BYTES` | `1048576` | HTTP 응답 최대 크기 (1MB) |
| `MAX_ARTICLES_PER_FEED` | `50` | 피드당 유지 아티클 수 |
| `CRAWL_INTERVAL_MINUTES` | `5` | 크롤링 주기 (분) |
| `TELEGRAM_BOT_TOKEN` | (필수) | 텔레그램 봇 토큰 |
| `TELEGRAM_CHANNEL_ID` | (필수) | 텔레그램 채널 ID |

## 7. 업데이트

```bash
cd ~/news-crew
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart news-crew
```