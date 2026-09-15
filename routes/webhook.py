import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, Response, Query, BackgroundTasks
from config import settings
from services.facebook_service import facebook_service
from services.gemini_service import gemini_service
from services.telegram_service import telegram_service

logger = logging.getLogger("facebook_webhook")
router = APIRouter(prefix="/webhook/facebook", tags=["Facebook Webhook"])

@router.get("")
async def verify_facebook_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Handles Meta's Webhook verification challenge.
    When you add this Webhook URL in Meta Developer Dashboard, Facebook calls this GET endpoint.
    """
    logger.info(f"Webhook verification request: mode={hub_mode}, token={hub_verify_token}")
    if hub_mode == "subscribe" and hub_verify_token == settings.FB_VERIFY_TOKEN:
        logger.info("Facebook Webhook verification successful!")
        return Response(content=hub_challenge, media_type="text/plain")
    
    logger.warning("Facebook Webhook verification failed: tokens do not match.")
    return Response(content="Verification failed", status_code=403)

async def process_facebook_event(payload: Dict[str, Any]):
    """Background processor for incoming Facebook messages and feed comments."""
    try:
        obj = payload.get("object")
        if obj != "page":
            return

        entries = payload.get("entry", [])
        for entry in entries:
            # 1. Handle Messenger DMs
            messaging_events = entry.get("messaging", [])
            for event in messaging_events:
                sender_id = event.get("sender", {}).get("id")
                message = event.get("message", {})

                # Ignore echo messages (messages sent by page/bot itself) or delivery reports
                if message.get("is_echo") or not message.get("text"):
                    continue

                user_text = message.get("text", "").strip()
                logger.info(f"Received Messenger message from {sender_id}: '{user_text}'")

                # Generate AI response using Gemini + Knowledge Base
                ai_resp = await gemini_service.generate_auto_reply(
                    incoming_text=user_text,
                    sender_name="গ্রাহক",
                    context_type="messenger_dm"
                )

                # Send reply to customer on Messenger
                await facebook_service.send_messenger_message(
                    recipient_id=sender_id,
                    message_text=ai_resp.get("reply_text")
                )

                # Alert owner on Telegram if query is complex or needs human attention
                if ai_resp.get("needs_human_alert"):
                    alert_msg = (
                        f"📩 *নতুন জটিল মেসেজ (Messenger):*\n"
                        f"👤 *Sender ID:* `{sender_id}`\n"
                        f"💬 *বার্তা:* {user_text}\n"
                        f"🤖 *এআই উত্তর:* {ai_resp.get('reply_text')}\n"
                        f"📌 *কারণ:* {ai_resp.get('alert_reason')}"
                    )
                    await telegram_service.send_alert_to_admin(alert_msg)

            # 2. Handle Feed Comments
            changes = entry.get("changes", [])
            for change in changes:
                if change.get("field") == "feed":
                    val = change.get("value", {})
                    item = val.get("item")
                    verb = val.get("verb")

                    # We are interested in new comments
                    if item == "comment" and verb == "add":
                        comment_id = val.get("comment_id")
                        sender_id = val.get("from", {}).get("id")
                        sender_name = val.get("from", {}).get("name", "গ্রাহক")
                        comment_text = val.get("message", "").strip()

                        # Prevent replying to page's own comments
                        if str(sender_id) == str(settings.FB_PAGE_ID):
                            continue

                        if not comment_text or not comment_id:
                            continue

                        logger.info(f"New comment from {sender_name} ({comment_id}): '{comment_text}'")

                        # Generate AI reply
                        ai_resp = await gemini_service.generate_auto_reply(
                            incoming_text=comment_text,
                            sender_name=sender_name,
                            context_type="public_comment"
                        )

                        # A. Public comment reply
                        public_reply = ai_resp.get("reply_text")
                        if public_reply:
                            await facebook_service.reply_to_comment(
                                comment_id=comment_id,
                                message_text=public_reply
                            )

                        # B. Private DM reply (if asking for price/order/details)
                        if ai_resp.get("is_asking_price_or_details") and ai_resp.get("private_dm_text"):
                            logger.info(f"Sending private reply to comment {comment_id}")
                            await facebook_service.send_private_reply_to_comment(
                                comment_id=comment_id,
                                message_text=ai_resp.get("private_dm_text")
                            )

                        # C. Alert admin if needed
                        if ai_resp.get("needs_human_alert"):
                            alert_msg = (
                                f"💬 *নতুন জটিল কমেন্ট (Post Comment):*\n"
                                f"👤 *ইউজার:* {sender_name}\n"
                                f"💬 *কমেন্ট:* {comment_text}\n"
                                f"🤖 *রিপ্লাই:* {public_reply}\n"
                                f"📌 *কারণ:* {ai_resp.get('alert_reason')}"
                            )
                            await telegram_service.send_alert_to_admin(alert_msg)

    except Exception as e:
        logger.error(f"Error handling Facebook event: {e}", exc_info=True)

@router.post("")
async def handle_facebook_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Receives real-time events from Meta and processes them asynchronously in background.
    """
    try:
        body = await request.json()
        # Meta expects HTTP 200 immediately to avoid resending the webhook
        background_tasks.add_task(process_facebook_event, body)
        return {"status": "EVENT_RECEIVED"}
    except Exception as e:
        logger.error(f"Error parsing incoming webhook body: {e}")
        return {"status": "ERROR", "message": str(e)}
