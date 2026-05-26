"""
Telegram Bot 모듈 테스트 스크립트

단위 테스트 및 통합 테스트 포함
"""

import os
import pytest
from telegram_bot import (
    escape_markdown_v2,
    html_to_text,
    truncate_message,
    format_message,
    MAX_MESSAGE_LENGTH
)


def test_escape_markdown_v2():
    """MarkdownV2 이스케이프 처리 테스트"""
    # 특수문자 포함 텍스트
    text = "테스트 *볼드* _이탤릭_ `코드` [링크](url)"
    escaped = escape_markdown_v2(text)
    
    # 특수문자가 이스케이프되었는지 확인
    assert "\\" in escaped
    assert "\\*" in escaped
    assert "\\_" in escaped
    print("✓ escape_markdown_v2 테스트 통과")


def test_html_to_text():
    """HTML → 텍스트 변환 테스트"""
    # HTML 포함 텍스트
    html = "<p>안녕하세요 <strong>테스트</strong>입니다.</p>"
    text = html_to_text(html)
    
    # HTML 태그가 제거되었는지 확인
    assert "<p>" not in text
    assert "<strong>" not in text
    assert "안녕하세요" in text
    assert "테스트" in text
    print("✓ html_to_text 테스트 통과")


def test_truncate_message():
    """메시지 길이 제한 테스트"""
    # 긴 메시지
    long_text = "A" * 5000
    truncated = truncate_message(long_text)
    
    # 길이 제한 확인
    assert len(truncated) <= MAX_MESSAGE_LENGTH - 200 + 3  # "..." 포함
    assert truncated.endswith("...")
    print("✓ truncate_message 테스트 통과")


def test_truncate_message_short():
    """짧은 메시지는 자르지 않음 테스트"""
    short_text = "짧은 메시지"
    truncated = truncate_message(short_text)
    
    assert truncated == short_text
    print("✓ truncate_message (짧은 메시지) 테스트 통과")


def test_format_message():
    """메시지 포맷팅 테스트"""
    title = "테스트 제목"
    content = "테스트 내용"
    url = "https://example.com/article"
    source_name = "테스트 출처"
    hashtag = "테스트뉴스"
    
    message = format_message(title, content, url, source_name, hashtag)
    
    # 모든 요소가 포함되었는지 확인
    assert "📰" in message
    assert "테스트 제목" in message
    assert "테스트 내용" in message
    assert "🔗" in message
    assert "원문 링크" in message
    assert "출처: 테스트 출처" in message
    assert "#테스트뉴스" in message
    print("✓ format_message 테스트 통과")


def test_format_message_content_length():
    """내용이 긴 경우 자르는지 테스트"""
    title = "테스트"
    content = "A" * 2000  # 긴 내용
    url = "https://example.com"
    source_name = "테스트"
    
    message = format_message(title, content, url, source_name)
    
    # 전체 메시지 길이 확인
    assert len(message) <= MAX_MESSAGE_LENGTH
    print("✓ format_message (긴 내용) 테스트 통과")


def test_message_length_limit():
    """Telegram 메시지 길이 제한 상수 테스트"""
    assert MAX_MESSAGE_LENGTH == 4096
    print(f"✓ MAX_MESSAGE_LENGTH: {MAX_MESSAGE_LENGTH}")


def run_integration_test():
    """통합 테스트 (실제 전송은 SKIP - 환경 변수 필요)"""
    print("\n--- 통합 테스트 ---")
    
    # 환경 변수 확인
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        print("⚠ TELEGRAM_BOT_TOKEN 환경 변수가 설정되지 않음")
        print("⚠ 실제 전송 테스트는 SKIP")
        return
    
    if not os.getenv('TELEGRAM_CHANNEL_ID'):
        print("⚠ TELEGRAM_CHANNEL_ID 환경 변수가 설정되지 않음")
        print("⚠ 실제 전송 테스트는 SKIP")
        return
    
    # 실제 전송 테스트는 주석 처리 (스스로 테스트 시 주해제)
    # from telegram_bot import send_to_default_channel
    # success = send_to_default_channel(
    #     title="통합 테스트",
    #     content="이것은 텔레그램 봇 통합 테스트입니다.",
    #     url="https://example.com/test",
    #     source_name="테스트",
    #     hashtag="test"
    # )
    # print(f"전송 결과: {'성공' if success else '실패'}")
    
    print("⚠ 실제 전송 테스트는 수동으로 실행해주세요")


if __name__ == "__main__":
    print("=== Telegram Bot 모듈 테스트 ===\n")
    
    # 단위 테스트 실행
    test_escape_markdown_v2()
    test_html_to_text()
    test_truncate_message()
    test_truncate_message_short()
    test_format_message()
    test_format_message_content_length()
    test_message_length_limit()
    
    # 통합 테스트
    run_integration_test()
    
    print("\n=== 모든 테스트 완료 ===")