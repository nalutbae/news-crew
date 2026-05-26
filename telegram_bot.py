"""
Telegram Bot 모듈 - 번역된 뉴스를 전송

python-telegram-bot v21+를 사용하여 비동기적으로 메시지 전송
"""

import os
import asyncio
import logging
from typing import Optional
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError, NetworkError, TimedOut
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Telegram 메시지 길이 제한 (4096자)
MAX_MESSAGE_LENGTH = 4096


def escape_markdown_v2(text: str) -> str:
    """
    MarkdownV2 포맷을 위한 이스케이프 문자 처리
    
    MarkdownV2의 특수문자: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    if not text:
        return ""
    
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    escaped = ""
    for char in text:
        if char in escape_chars:
            escaped += f"\\{char}"
        else:
            escaped += char
    return escaped


def html_to_text(html: str) -> str:
    """
    HTML을 일반 텍스트로 변환
    
    간단한 HTML 태그를 제거하고 텍스트만 추출
    """
    from bs4 import BeautifulSoup
    
    if not html:
        return ""
    
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    
    # 불필요한 공백 제거
    text = ' '.join(text.split())
    
    return text


def truncate_message(message: str, max_length: int = MAX_MESSAGE_LENGTH - 200) -> str:
    """
    메시지 길이 제한 처리
    
    Telegram API 제한과 Markdown 이스케이프 여유 공간을 고려
    """
    if len(message) <= max_length:
        return message
    
    # 길이 제한으로 자르고 "..." 추가
    truncated = message[:max_length - 3] + "..."
    
    logger.warning(f"Message truncated: {len(message)} -> {len(truncated)}")
    return truncated


def format_message(title: str, content: str, url: str, source_name: str, hashtag: Optional[str] = None) -> str:
    """
    포맷팅된 메시지 생성
    
    포맷:
    📰 [번역된 제목]
    
    [번역된 내용 요약]
    
    🔗 [원문 링크](url)
    
    출처: [source_name] | #{hashtag}
    """
    # MarkdownV2 이스케이프 처리
    escaped_title = escape_markdown_v2(title)
    escaped_url = escape_markdown_v2(url)
    escaped_source = escape_markdown_v2(source_name)
    escaped_hashtag = escape_markdown_v2(hashtag if hashtag else "news")
    
    # 내용은 HTML이 포함될 수 있으므로 텍스트로 변환 후 이스케이프
    text_content = html_to_text(content)
    escaped_content = escape_markdown_v2(text_content)
    
    # 내용이 너무 길면 자르기
    escaped_content = truncate_message(escaped_content, max_length=1000)
    
    message = f"📰 {escaped_title}\n\n"
    message += f"{escaped_content}\n\n"
    message += f"🔗 [원문 링크]({escaped_url})\n\n"
    message += f"출처: {escaped_source} \\| \\#{escaped_hashtag}"
    
    return message


async def send_message_async(
    bot: Bot,
    channel_id: str,
    title: str,
    content: str,
    url: str,
    source_name: str,
    hashtag: Optional[str] = None,
    max_retries: int = 3
) -> bool:
    """
    비동기적으로 메시지 전송 (재시도 로직 포함)
    
    Args:
        bot: Telegram Bot 인스턴스
        channel_id: 대상 채널 ID
        title: 뉴스 제목
        content: 뉴스 내용 (HTML 포함 가능)
        url: 원문 링크
        source_name: 출처 이름
        hashtag: 해시태그 (선택사항)
        max_retries: 최대 재시도 횟수
    
    Returns:
        bool: 전송 성공 여부
    """
    # 메시지 포맷팅
    message = format_message(title, content, url, source_name, hashtag)
    
    # 메시지 길이 체크
    if len(message) > MAX_MESSAGE_LENGTH:
        logger.error(f"Message too long: {len(message)} > {MAX_MESSAGE_LENGTH}")
        message = truncate_message(message, MAX_MESSAGE_LENGTH)
    
    for attempt in range(max_retries):
        try:
            await bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode='MarkdownV2',
                disable_web_page_preview=False
            )
            
            logger.info(f"Message sent successfully to channel {channel_id}")
            return True
            
        except NetworkError as e:
            logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                # 지수 백오프 대기
                wait_time = 2 ** attempt
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to send message after {max_retries} attempts: {e}")
                return False
                
        except TimedOut as e:
            logger.warning(f"Timeout (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to send message after {max_retries} attempts: {e}")
                return False
                
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            return False
            
    return False


def send_translated_news(
    channel_id: str,
    title: str,
    content: str,
    url: str,
    source_name: str,
    hashtag: Optional[str] = None
) -> bool:
    """
    번역된 뉴스 전송 (동기식 래퍼)
    
    Args:
        channel_id: 대상 채널 ID
        title: 뉴스 제목
        content: 뉴스 내용 (HTML 포함 가능)
        url: 원문 링크
        source_name: 출처 이름
        hashtag: 해시태그 (선택사항)
    
    Returns:
        bool: 전송 성공 여부
    """
    # 환경 변수에서 Bot Token 로드
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
        return False
    
    # Bot 인스턴스 생성 (프록시 설정 지원)
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=10.0,
        read_timeout=10.0,
        write_timeout=10.0
    )
    
    bot = Bot(token=bot_token, request=request)
    
    # 비동기 함수 실행
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    success = loop.run_until_complete(
        send_message_async(bot, channel_id, title, content, url, source_name, hashtag)
    )
    
    return success


def send_to_default_channel(
    title: str,
    content: str,
    url: str,
    source_name: str,
    hashtag: Optional[str] = None
) -> bool:
    """
    기본 채널로 뉴스 전송 (환경 변수에서 채널 ID 로드)
    
    Args:
        title: 뉴스 제목
        content: 뉴스 내용
        url: 원문 링크
        source_name: 출처 이름
        hashtag: 해시태그 (선택사항)
    
    Returns:
        bool: 전송 성공 여부
    """
    channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not channel_id:
        logger.error("TELEGRAM_CHANNEL_ID environment variable not set")
        return False
    
    return send_translated_news(channel_id, title, content, url, source_name, hashtag)


if __name__ == "__main__":
    # 테스트 코드
    print("Telegram Bot 모듈 테스트")
    print(f"MESSAGE_LENGTH_LIMIT: {MAX_MESSAGE_LENGTH}")