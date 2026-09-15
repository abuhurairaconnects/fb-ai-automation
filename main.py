import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from routes.webhook import router as webhook_router
from services.gemini_service import gemini_service
from services.youtube_service import youtube_service
from services.telegram_service import telegram_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

scheduler = AsyncIOScheduler()

async def check_youtube_channel_job():
    """
    Periodic job that checks the configured YouTube channel for new video uploads.
    Extracts transcript and sends post draft to Telegram for approval.
    """
    channel_id = settings.YOUTUBE_CHANNEL_ID.strip()
    if not channel_id or channel_id == "your_youtube_channel_id_here":
        logger.info("YOUTUBE_CHANNEL_ID is not configured yet. Skipping auto-check.")
        return

    logger.info(f"Checking YouTube channel {channel_id} for new videos...")
    try:
        videos = await youtube_service.get_latest_videos_from_channel(channel_id, max_results=3)
        new_videos = [v for v in videos if v.get("is_new")]

        if not new_videos:
            logger.info("No new videos found on the channel.")
            return

        logger.info(f"Found {len(new_videos)} new video(s)!")
        for vid in new_videos:
            video_id = vid["video_id"]
            title = vid["title"]
            logger.info(f"Processing new video: {title} ({video_id})")

            # Extract transcript
            transcript = youtube_service.get_video_transcript(video_id)

            # Generate Facebook post draft using Gemini
            draft = await gemini_service.generate_post_from_video(
                video_title=title,
                video_description=vid["description"],
                transcript=transcript,
                video_url=vid["url"]
            )
            draft["thumbnail_url"] = vid["thumbnail_url"]
            draft["description"] = vid["description"]
            draft["transcript"] = transcript

            # Send to Telegram for approval
            sent = await telegram_service.send_draft_for_approval(draft)
            if sent:
                # Mark as processed so it won't be sent again
                youtube_service.mark_video_processed(video_id)
                logger.info(f"Draft sent to Telegram for video: {video_id}")
            else:
                logger.warning(f"Could not send draft to Telegram for {video_id}. Will retry next cycle.")

    except Exception as e:
        logger.error(f"Error during YouTube check job: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Start Telegram Bot polling
    tg_app = await telegram_service.init_app()
    if tg_app:
        try:
            await tg_app.initialize()
            await tg_app.start()
            if tg_app.updater:
                await tg_app.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram Bot started polling successfully.")
        except Exception as e:
            logger.error(f"Failed to start Telegram polling: {e}")

    # 2. Start YouTube monitoring background scheduler
    interval = max(settings.YOUTUBE_CHECK_INTERVAL_MINUTES, 5)
    scheduler.add_job(check_youtube_channel_job, 'interval', minutes=interval, id='yt_checker')
    scheduler.start()
    logger.info(f"YouTube channel monitor scheduler started (Every {interval} mins).")

    # Run one initial check shortly after startup in background
    asyncio.create_task(check_youtube_channel_job())

    yield

    # Shutdown
    logger.info("Shutting down services...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if tg_app and tg_app.updater:
        try:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        except Exception as e:
            logger.warning(f"Error closing Telegram bot: {e}")

app = FastAPI(
    title="Facebook Page AI Automation",
    description="24/7 Facebook Page Content, Auto-Reply, and Approval Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Include Webhook Router
app.include_router(webhook_router)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "facebook-page-ai-automation",
        "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_TOKEN != "your_telegram_bot_token_here"),
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here"),
        "facebook_configured": bool(settings.FB_PAGE_ACCESS_TOKEN and settings.FB_PAGE_ACCESS_TOKEN != "your_long_lived_page_access_token_here")
    }

@app.get("/", response_class=HTMLResponse)
async def home():
    """Simple friendly web interface showing system status and webhook URL."""
    return """
    <!DOCTYPE html>
    <html lang="bn">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Facebook Page AI Automation</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; display: flex; justify-content: center; }
            .container { max-width: 700px; width: 100%; background: #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); border: 1px solid #334155; }
            h1 { color: #38bdf8; margin-top: 0; font-size: 26px; }
            .badge { display: inline-block; padding: 6px 14px; border-radius: 9999px; font-weight: bold; font-size: 13px; background: #22c55e20; color: #4ade80; border: 1px solid #22c55e; margin-bottom: 20px; }
            .card { background: #0f172a; border-radius: 10px; padding: 18px; margin-bottom: 16px; border: 1px solid #334155; }
            .card h3 { margin: 0 0 8px 0; font-size: 17px; color: #94a3b8; }
            .card p { margin: 0; font-size: 15px; color: #e2e8f0; line-height: 1.5; }
            code { background: #1e293b; padding: 3px 8px; border-radius: 6px; color: #38bdf8; font-size: 14px; }
            .features { list-style: none; padding: 0; margin: 16px 0; }
            .features li { margin-bottom: 10px; display: flex; align-items: center; gap: 10px; font-size: 15px; }
            .footer { margin-top: 24px; text-align: center; color: #64748b; font-size: 13px; }
        </style>
    </head>
    <body>
        <div class="container">
            <span class="badge">● ২৪/৭ সক্রিয় রয়েছে</span>
            <h1>🤖 ফেসবুক পেজ স্মার্ট অটোমেশন সিস্টেম</h1>
            <p style="color: #94a3b8; line-height: 1.6;">আপনার ফেসবুক পেজের কনটেন্ট তৈরি, টেলিগ্রাম অ্যাপ্রুভাল এবং এআই মেসেঞ্জার/কমেন্ট রিপ্লাই ব্যাকগ্রাউন্ডে স্বয়ংক্রিয়ভাবে চলছে।</p>
            
            <div class="card">
                <h3>🔗 ফেসবুক ওয়েব-হুক ইউআরএল (Webhook URL)</h3>
                <p>মেটা ডেভেলপার পোর্টালে এই ইউআরএলটি দিন:<br><code>/webhook/facebook</code></p>
            </div>

            <div class="card">
                <h3>⚡ মূল সুবিধাসমূহ:</h3>
                <ul class="features">
                    <li>🎬 <strong>ইউটিউব ভিডিও ট্র্যাকার:</strong> নতুন ভিডিওর ট্রান্সক্রিপ্ট বুঝে অটোমেটিক পোস্ট রাইটিং।</li>
                    <li>📱 <strong>টেলিগ্রাম অ্যাপ্রুভাল:</strong> ফোনে বাটন চেপে ১ ক্লিকে পেজে পোস্ট পাবলিশ।</li>
                    <li>💬 <strong>মেসেঞ্জার ও কমেন্ট এআই:</strong> নলেজ বেসের তথ্যের ভিত্তিতে সাবলীল বাংলায় ২৪/৭ রিপ্লাই।</li>
                    <li>⚠️ <strong>অ্যাডমিন অ্যালার্ট:</strong> বিশেষ ও জরুরি প্রশ্নে টেলিগ্রামে নোটিফিকেশন।</li>
                </ul>
            </div>

            <div class="footer">
                Facebook Page AI Automation • Powered by FastAPI & Google Gemini
            </div>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
