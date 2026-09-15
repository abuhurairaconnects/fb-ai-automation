import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.youtube_service import YouTubeService
from services.gemini_service import GeminiService
from fastapi.testclient import TestClient
from main import app
from config import settings

client = TestClient(app)

def test_youtube_video_id_extraction():
    """Tests that YouTube URL variations extract the exact 11-character video ID."""
    test_urls = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ]
    for url, expected_id in test_urls:
        extracted = YouTubeService.extract_video_id(url)
        assert extracted == expected_id, f"Failed for {url}: expected {expected_id}, got {extracted}"

def test_knowledge_base_loading():
    """Tests loading knowledge_base.json and extracting page tone and FAQs."""
    service = GeminiService()
    kb = service.load_knowledge_base()
    assert isinstance(kb, dict)
    assert "page_name" in kb
    assert "common_faqs" in kb

@pytest.mark.asyncio
async def test_gemini_post_generation_mock():
    """Tests that GeminiService formats prompt and returns structured draft."""
    service = GeminiService()
    mock_post_text = "🔥 অসাধারণ নতুন ভিডিও!\n\n১. টিপস ১\n২. টিপস ২\n\n#TechTips #Bangla"
    
    with patch.object(service, '_call_gemini_api', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_post_text
        result = await service.generate_post_from_video(
            video_title="How to automate Facebook",
            video_description="Video description here",
            transcript="This is a test transcript of the video.",
            video_url="https://youtu.be/test12345"
        )
        assert result["title"] == "How to automate Facebook"
        assert result["caption"] == mock_post_text
        assert result["status"] == "pending_approval"

@pytest.mark.asyncio
async def test_gemini_auto_reply_json_parsing():
    """Tests that GeminiService correctly parses structured JSON auto-reply."""
    service = GeminiService()
    mock_json = '{"reply_text": "ধন্যবাদ! আমাদের সার্ভিস চার্জ ফ্রি।", "is_asking_price_or_details": true, "private_dm_text": "ইনবক্সে বিস্তারিত পাঠানো হলো।", "needs_human_alert": false, "alert_reason": ""}'

    with patch.object(service, '_call_gemini_api', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_json
        reply = await service.generate_auto_reply(
            incoming_text="ভাইয়া প্রাইস কত?",
            sender_name="রাকিব",
            context_type="messenger_dm"
        )
        assert reply["reply_text"] == "ধন্যবাদ! আমাদের সার্ভিস চার্জ ফ্রি।"
        assert reply["is_asking_price_or_details"] is True
        assert reply["private_dm_text"] == "ইনবক্সে বিস্তারিত পাঠানো হলো।"
        assert reply["needs_human_alert"] is False

def test_facebook_webhook_verification_success():
    """Tests that GET /webhook/facebook responds with challenge when token matches."""
    settings.FB_VERIFY_TOKEN = "test_verify_token_xyz"
    response = client.get(
        "/webhook/facebook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "test_verify_token_xyz"
        }
    )
    assert response.status_code == 200
    assert response.text == "1158201444"

def test_facebook_webhook_verification_failure():
    """Tests that GET /webhook/facebook rejects invalid tokens."""
    settings.FB_VERIFY_TOKEN = "test_verify_token_xyz"
    response = client.get(
        "/webhook/facebook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "wrong_token"
        }
    )
    assert response.status_code == 403

def test_health_check():
    """Tests the /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
