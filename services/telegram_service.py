import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from config import settings
from services.facebook_service import facebook_service
from services.gemini_service import gemini_service
from services.youtube_service import youtube_service

logger = logging.getLogger("telegram_service")

class TelegramService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.admin_chat_id = str(settings.TELEGRAM_ADMIN_CHAT_ID).strip()
        self.app: Optional[Application] = None
        # In-memory storage for pending post drafts {draft_id: {...}}
        self.pending_drafts: Dict[str, Dict[str, Any]] = {}

    def is_admin(self, user_id: int) -> bool:
        if not self.admin_chat_id:
            return True
        return str(user_id) == self.admin_chat_id

    async def init_app(self):
        """Builds and initializes the Telegram Application."""
        if not self.bot_token or self.bot_token == "your_telegram_bot_token_here":
            logger.warning("TELEGRAM_BOT_TOKEN is not configured. Telegram bot won't start.")
            return None

        self.app = Application.builder().token(self.bot_token).build()

        # Command Handlers
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("help", self._cmd_help))

        # Callback query handler for inline buttons
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

        # Message handler for receiving YouTube links
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message))

        return self.app

    async def send_draft_for_approval(self, draft_data: Dict[str, Any]) -> bool:
        """
        Sends a post draft to the owner's Telegram with Approve, Regenerate, and Cancel buttons.
        """
        if not self.app or not self.admin_chat_id:
            logger.warning("Telegram Bot or TELEGRAM_ADMIN_CHAT_ID is not configured.")
            return False

        draft_id = str(uuid.uuid4())[:8]
        self.pending_drafts[draft_id] = draft_data

        caption = draft_data.get("caption", "")
        title = draft_data.get("title", "YouTube Video")
        video_url = draft_data.get("url", "")
        thumbnail_url = draft_data.get("thumbnail_url", "")

        keyboard = [
            [
                InlineKeyboardButton("✅ Approve & Publish", callback_data=f"appr:{draft_id}"),
                InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen:{draft_id}")
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data=f"canc:{draft_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        header = f"📢 *নতুন ফেসবুক পোস্ট ড্রাফট!*\n\n🎬 *ভিডিও:* {title}\n🔗 *লিংক:* {video_url}\n\n───────────────\n"
        full_text = f"{header}{caption}\n───────────────\n\n_আপনি কি এই পোস্টটি ফেসবুক পেজে প্রকাশ করতে চান?_"

        try:
            bot = self.app.bot
            # Telegram caption limit for send_photo is 1024 chars.
            # If text is longer, send photo first, then full post text with buttons.
            if thumbnail_url:
                try:
                    if len(full_text) <= 1024:
                        await bot.send_photo(
                            chat_id=self.admin_chat_id,
                            photo=thumbnail_url,
                            caption=full_text,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                        return True
                    else:
                        await bot.send_photo(
                            chat_id=self.admin_chat_id,
                            photo=thumbnail_url,
                            caption=f"🎬 *{title}*",
                            parse_mode="Markdown"
                        )
                except Exception as pe:
                    logger.warning(f"Could not send thumbnail photo ({pe}), sending as text.")

            # Fallback or long text
            # Split into chunks if > 4000
            if len(full_text) > 4000:
                await bot.send_message(chat_id=self.admin_chat_id, text=full_text[:3900])
                await bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=full_text[3900:],
                    reply_markup=reply_markup
                )
            else:
                await bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=full_text,
                    reply_markup=reply_markup
                )
            return True
        except Exception as e:
            logger.error(f"Error sending draft to Telegram: {e}")
            return False

    async def send_alert_to_admin(self, alert_text: str):
        """Sends urgent customer notification to owner's Telegram."""
        if not self.app or not self.admin_chat_id:
            return
        try:
            bot = self.app.bot
            msg = f"⚠️ *গ্রাহক সতর্কতা / এলার্ট!*\n\n{alert_text}"
            await bot.send_message(chat_id=self.admin_chat_id, text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error sending alert to Telegram: {e}")

    # ================= Telegram Command Handlers =================

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = update.effective_chat.id
        msg = (
            f"👋 আসসালামু আলাইকুম {user.first_name}!\n\n"
            f"🤖 *ফেসবুক পেজ স্মার্ট অটোমেশন বটে স্বাগতম!*\n\n"
            f"🆔 *আপনার Telegram Chat ID:* `{chat_id}`\n"
            f"_(এই আইডিটি আপনার `.env` ফাইলের `TELEGRAM_ADMIN_CHAT_ID` তে বসিয়ে রাখুন)_\n\n"
            f"🚀 *বট যেভাবে কাজ করবে:*\n"
            f"১. ইউটিউবে নতুন ভিডিও আসলে অটোমেটিক পোস্টের ড্রাফট তৈরি করে এখানে বাটন সহ পাঠানো হবে।\n"
            f"২. যেকোনো সময় আপনি এখানে একটি ইউটিউব ভিডিওর লিংক পাঠালে সাথে সাথে ফেসবুক পোস্ট বানিয়ে দেবে।\n"
            f"৩. পেজে কোনো কাস্টমার জরুরি বিষয়ে কথা বলতে চাইলে আপনাকে তৎক্ষণাৎ জানিয়ে দেবে।\n\n"
            f"কমান্ডসমূহ:\n"
            f"/status - সিস্টেমের সার্বিক অবস্থা দেখুন\n"
            f"/help - সাহায্য ও গাইড"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ আপনি এই বটের অ্যাডমিন নন।")
            return

        yt_id = settings.YOUTUBE_CHANNEL_ID or "সেট করা নেই"
        fb_id = settings.FB_PAGE_ID or "সেট করা নেই"
        gemini_status = "✅ কনফিগার করা আছে" if settings.GEMINI_API_KEY else "❌ মিসিং"
        fb_status = "✅ কনফিগার করা আছে" if settings.FB_PAGE_ACCESS_TOKEN else "❌ মিসিং"

        msg = (
            f"📊 *সিস্টেম স্ট্যাটাস:* \n\n"
            f"• *Google Gemini AI:* {gemini_status}\n"
            f"• *Facebook Page Token:* {fb_status}\n"
            f"• *Facebook Page ID:* `{fb_id}`\n"
            f"• *YouTube Channel ID:* `{yt_id}`\n"
            f"• *পেন্ডিং পোস্ট ড্রাফট:* {len(self.pending_drafts)} টি\n\n"
            f"সবকিছু ২৪/৭ সক্রিয় রয়েছে! ✅"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            f"💡 *সহায়িকা ও টিপস:*\n\n"
            f"১. যেকোনো ইউটিউব ভিডিওর লিংক (যেমন `https://youtu.be/...`) সরাসরি এই চ্যাটে সেন্ড করুন। এআই ভিডিওটি দেখে আকর্ষণীয় বাংলা ফেসবুক পোস্ট বানিয়ে অ্যাপ্রুভাল চাইবে।\n"
            f"২. ড্রাফট আসলে `[✅ Approve & Publish]` চাপলেই ১ সেকেন্ডে ফেসবুক পেজে চলে যাবে।\n"
            f"৩. লেখা পছন্দ না হলে `[🔄 Regenerate]` চাপলে ভিন্ন স্টাইলে নতুন করে লিখে দেবে।\n"
            f"৪. `[❌ Cancel]` চাপলে ড্রাফট বাতিল হবে।"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("⛔ অননুমোদিত অ্যাকশন।")
            return

        data = query.data
        action, draft_id = data.split(":", 1)
        draft = self.pending_drafts.get(draft_id)

        if not draft and action != "canc":
            await query.edit_message_text("⚠️ এই ড্রাফটটি আর পাওয়া যাচ্ছে না বা মেয়াদ উত্তীর্ণ হয়েছে।")
            return

        if action == "appr":
            # Approve and publish to Facebook
            await query.edit_message_text("⏳ ফেসবুক পেজে পাবলিশ হচ্ছে...")
            res = await facebook_service.publish_post(
                caption=draft.get("caption", ""),
                link=draft.get("url"),
                photo_url=draft.get("thumbnail_url")
            )
            if res.get("success"):
                post_id = res.get("post_id", "Success")
                await query.edit_message_text(
                    f"🎉 *সফলভাবে ফেসবুক পেজে পোস্ট করা হয়েছে!*\n\n"
                    f"📌 *Post ID:* `{post_id}`\n"
                    f"🎬 *ভিডিও:* {draft.get('title')}",
                    parse_mode="Markdown"
                )
                # Mark as processed so it's not re-done
                vid_id = youtube_service.extract_video_id(draft.get("url", ""))
                if vid_id:
                    youtube_service.mark_video_processed(vid_id)
                self.pending_drafts.pop(draft_id, None)
            else:
                err = res.get("error", "ত্রুটি ঘটেছে")
                await query.edit_message_text(
                    f"❌ পোস্ট পাবলিশ করতে সমস্যা হয়েছে:\n`{err}`\n\nদয়া করে আপনার ফেসবুক পেজ এক্সেস টোকেন চেক করুন।"
                )

        elif action == "regen":
            await query.edit_message_text("🔄 নতুন আঙ্গিকে পোস্ট পুনরায় লেখা হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...")
            new_draft = await gemini_service.generate_post_from_video(
                video_title=draft.get("title", ""),
                video_description=draft.get("description", ""),
                transcript=draft.get("transcript", ""),
                video_url=draft.get("url", ""),
                style="অত্যন্ত আকর্ষণীয় গল্প ও আকর্ষণীয় বুলেট পয়েন্ট স্টাইল"
            )
            new_draft["thumbnail_url"] = draft.get("thumbnail_url", "")
            new_draft["description"] = draft.get("description", "")
            new_draft["transcript"] = draft.get("transcript", "")
            await self.send_draft_for_approval(new_draft)

        elif action == "canc":
            self.pending_drafts.pop(draft_id, None)
            await query.edit_message_text("❌ পোস্ট ড্রাফট বাতিল করা হয়েছে।")

    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles manual YouTube link pasted by the admin in Telegram chat."""
        if not self.is_admin(update.effective_user.id):
            return

        text = update.message.text.strip()
        video_id = youtube_service.extract_video_id(text)
        if not video_id:
            await update.message.reply_text(
                "ℹ️ অনুগ্রহ করে একটি সঠিক ইউটিউব ভিডিওর লিঙ্ক দিন (অথবা কমান্ড দেখার জন্য /help লিখুন)।"
            )
            return

        status_msg = await update.message.reply_text(
            "⏳ ইউটিউব ভিডিওর তথ্য ও ট্রান্সক্রিপ্ট সংগ্রহ করা হচ্ছে..."
        )

        video_info = await youtube_service.get_video_details_by_id(video_id)
        await status_msg.edit_text("✍️ জেমিনি এআই দিয়ে ফেসবুক পোস্ট লেখা হচ্ছে...")

        draft = await gemini_service.generate_post_from_video(
            video_title=video_info["title"],
            video_description=video_info["description"],
            transcript=video_info["transcript"],
            video_url=video_info["url"]
        )
        draft["thumbnail_url"] = video_info["thumbnail_url"]
        draft["description"] = video_info["description"]
        draft["transcript"] = video_info["transcript"]

        await status_msg.delete()
        await self.send_draft_for_approval(draft)

telegram_service = TelegramService()
