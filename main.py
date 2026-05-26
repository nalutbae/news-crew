"""
News Crew 메인 실행기 (main.py)

APScheduler BlockingScheduler로 5분 간격 크롤링 작업 실행.
모든 모듈을 통합한 완전한 파이프라인 구동.

작업 흐름:
1. DB에서 활성화된 피드 목록 조회
2. 각 피드에 대해 적절한 파서(RSSParser/WebParser) 선택
3. 새로운 아티클 발견 시 번역 → 텔레그램 전송 파이프라인 실행
4. 전송 성공 시 DB 업데이트 (sent_at)
"""

import os
import sys
import signal
import logging
from datetime import datetime
from typing import List

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobEvent

from config import get_config, validate_config
from logging_config import setup_logging
from models import get_engine, get_session, Article, Feed, Base
from init_db import init_database
from crawl import NewsCrawler
from translator import translate_article
from telegram_bot import send_to_default_channel

logger = logging.getLogger('news_crew')


# ── 전역 상태 ──
_running = True
_first_run = True


def _signal_handler(signum, frame):
    """종료 시그널 처리 (Ctrl+C 등)"""
    global _running
    logger.info("종료 시그널 수신, 정상 종료 중...")
    _running = False
    sys.exit(0)


def _scheduler_error_listener(event: JobEvent):
    """APScheduler 이벤트 리스너 - 에러/누락 로깅"""
    if event.exception:
        logger.error(f"스케줄 작업 에러: {event.exception}", exc_info=event.exception)
    if event.code == EVENT_JOB_MISSED:
        logger.warning(f"스케줄 작업 누락: {event.job_id}")


def crawl_job():
    """
    크롤링 작업 (스케줄러에서 5분 간격 호출)
    
    전체 파이프라인: 크롤링 → 번역 → 텔레그램 전송 → DB 업데이트
    
    스케줄러는 5분마다 실행되지만, 각 피드의 crawl_interval에 따라
    실제 크롤링 대상은 필터링됨 (due_only=True).
    """
    global _first_run
    
    config = get_config()
    job_start = datetime.utcnow()
    
    logger.info("=" * 60)
    logger.info(f"크롤링 작업 시작: {job_start.isoformat()}")
    if _first_run:
        logger.info("(첫 실행: 기존 피드 전체 크롤링)")
    logger.info("=" * 60)
    
    try:
        # 1. 크롤링 (첫 실행: 전체, 이후: interval 도래 피드만)
        crawler = NewsCrawler(db_path=config.database.path)
        due_only = not _first_run
        new_articles = crawler.crawl_all(due_only=due_only)
        
        if not new_articles:
            logger.info("새로운 아티클 없음")
            _first_run = False
            return
        
        logger.info(f"새 아티클 {len(new_articles)}개 발견, 번역/전송 시작")
        
        # 2. 번역 → 텔레그램 전송 파이프라인
        session = get_session(get_engine(config.database.path))
        sent_count = 0
        error_count = 0
        
        try:
            for article in new_articles:
                try:
                    # 세션에서 아티클 다시 로드 (다른 세션으로 저장했으므로)
                    db_article = session.query(Article).get(article.id)
                    if not db_article:
                        logger.warning(f"아티클 ID {article.id} DB에서 찾을 수 없음")
                        continue
                    
                    # 이미 전송된 경우 건너뜀
                    if db_article.sent_at:
                        logger.debug(f"이미 전송됨: ID={db_article.id}")
                        continue
                    
                    # 2-1. 번역
                    feed = db_article.feed
                    logger.info(f"번역 시작: [{feed.name}] {db_article.title[:50]}")
                    
                    success, translated_title, translated_content = translate_article(
                        db_article, session=session
                    )
                    
                    if not success or not translated_title:
                        logger.error(f"번역 실패: article_id={db_article.id}")
                        error_count += 1
                        continue
                    
                    # DB에서 최신 상태 다시 로드 (번역 후)
                    session.refresh(db_article)
                    
                    # 2-2. 텔레그램 전송
                    logger.info(f"텔레그램 전송: [{feed.name}] {translated_title[:50]}")
                    
                    send_success = send_to_default_channel(
                        title=translated_title,
                        content=translated_content or '',
                        url=db_article.url,
                        source_name=feed.name,
                        hashtag=feed.hashtag,
                    )
                    
                    # 2-3. 전송 결과 DB 업데이트
                    if send_success:
                        db_article.sent_at = datetime.utcnow()
                        session.commit()
                        sent_count += 1
                        logger.info(f"전송 성공: article_id={db_article.id}")
                    else:
                        logger.error(f"텔레그램 전송 실패: article_id={db_article.id}")
                        error_count += 1
                        
                except Exception as e:
                    logger.error(f"아티클 처리 실패 (ID={article.id}): {e}", exc_info=True)
                    error_count += 1
                    session.rollback()
                    
        finally:
            session.close()
        
        # 작업 결과 요약
        job_end = datetime.utcnow()
        duration = (job_end - job_start).total_seconds()
        
        logger.info("-" * 60)
        logger.info(f"크롤링 작업 완료: {job_end.isoformat()}")
        logger.info(f"  소요 시간: {duration:.1f}초")
        logger.info(f"  신규 아티클: {len(new_articles)}개")
        logger.info(f"  전송 성공: {sent_count}개")
        logger.info(f"  전송 실패: {error_count}개")
        logger.info("-" * 60)
        
    except Exception as e:
        logger.error(f"크롤링 작업 치명적 오류: {e}", exc_info=True)
    
    _first_run = False


def setup_scheduler() -> BlockingScheduler:
    """
    APScheduler BlockingScheduler 설정
    
    - 5분 간격 crawl_job 실행
    - 재시작 전략: last_checked 기반으로 마지막 체크포인트부터 재개
    """
    config = get_config()
    sched_config = config.scheduler
    
    scheduler = BlockingScheduler()
    
    # 크롤링 작업 등록
    scheduler.add_job(
        crawl_job,
        'interval',
        minutes=sched_config.interval_minutes,
        id='crawl_job',
        name='News Crawl Job',
        coalesce=sched_config.coalesce,
        misfire_grace_time=sched_config.misfire_grace_time,
        max_instances=sched_config.max_instances,
    )
    
    # 에러 이벤트 리스너 등록
    scheduler.add_listener(_scheduler_error_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    
    logger.info(
        f"스케줄러 설정 완료: {sched_config.interval_minutes}분 간격, "
        f"misfire_grace={sched_config.misfire_grace_time}s"
    )
    
    return scheduler


def first_run_crawl():
    """
    첫 실행 시 전체 피드 크롤링
    
    이후에는 5분 주기 반복
    """
    logger.info("첫 실행: 전체 피드 크롤링 시작")
    crawl_job()


def run():
    """
    메인 실행 진입점
    
    1. 설정 검증
    2. DB 초기화
    3. 첫 실행 (전체 크롤링)
    4. 스케줄러 시작 (5분 주기)
    """
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    # 로깅 설정
    setup_logging()
    
    logger.info("News Crew 시작")
    
    # 설정 검증
    config = get_config()
    errors = validate_config(config)
    
    if errors:
        for err in errors:
            logger.warning(f"설정 경고: {err}")
        
        # 텔레그램 토큰/채널 누락은 치명적
        critical_errors = [e for e in errors if 'TELEGRAM' in e]
        if critical_errors:
            logger.error("텔레그램 설정이 누락되었습니다. .env 파일을 확인하세요.")
            logger.error("전송 기능 없이 크롤링만 실행합니다.")
    
    # DB 초기화
    logger.info(f"데이터베이스 초기화: {config.database.path}")
    engine = init_database(config.database.path)
    
    # 첫 실행: 전체 크롤링
    try:
        first_run_crawl()
    except Exception as e:
        logger.error(f"첫 실행 크롤링 실패: {e}", exc_info=True)
    
    # 스케줄러 시작
    scheduler = setup_scheduler()
    
    logger.info("스케줄러 시작 (Ctrl+C로 종료)")
    try:
        scheduler.start()
    except (KeyboardError, SystemExit):
        logger.info("스케줄러 종료")
    finally:
        scheduler.shutdown(wait=False)
        logger.info("News Crew 정상 종료")


if __name__ == '__main__':
    run()