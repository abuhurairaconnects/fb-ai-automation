import json
import logging
import os
from typing import Dict, Any, Optional
import httpx
from config import settings

logger = logging.getLogger("gemini_service")

class GeminiService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL or "gemini-2.5-flash"
        self._knowledge_base: Optional[Dict[str, Any]] = None

    def load_knowledge_base(self) -> Dict[str, Any]:
        """Loads business info and FAQs from knowledge_base.json"""
        kb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base.json")
        try:
            if os.path.exists(kb_path):
                with open(kb_path, "r", encoding="utf-8") as f:
                    self._knowledge_base = json.load(f)
                    return self._knowledge_base
        except Exception as e:
            logger.error(f"Error loading knowledge_base.json: {e}")
        
        self._knowledge_base = {
            "page_name": "Our Facebook Page",
            "tone_and_style": {"persona": "Friendly, polite, helpful in Bengali"},
            "services_and_products": [],
            "common_faqs": []
        }
        return self._knowledge_base

    async def _call_gemini_api(self, prompt: str, system_instruction: str = "") -> str:
        """Calls Google Gemini API via official endpoint using httpx (ultra-reliable)."""
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not configured.")
            return "দুঃখিত, বর্তমানে এআই সিস্টেম কনফিগার করা নেই।"

        # Fallback model list if 2.5-flash is not available in some regions
        models_to_try = [self.model, "gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        # Remove duplicates while preserving order
        seen = set()
        models = [m for m in models_to_try if not (m in seen or seen.add(m))]

        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 2048,
                }
            }
            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
                    else:
                        logger.warning(f"Model {model_name} failed with status {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Exception calling Gemini {model_name}: {e}")

        return "দুঃখিত, এআই রেসপন্স তৈরিতে কিছুটা সমস্যা হয়েছে।"

    async def generate_post_from_video(
        self,
        video_title: str,
        video_description: str,
        transcript: str,
        video_url: str = "",
        style: str = "engaging"
    ) -> Dict[str, Any]:
        """
        Analyzes video transcript & details, and creates a high-engagement Facebook post in Bengali.
        """
        system_instruction = (
            "তুমি একজন টপ-ক্লাস সোশ্যাল মিডিয়া কপিরাইটার এবং ফেসবুক মার্কেটিং এক্সপার্ট। "
            "তোমার কাজ হলো একটি ইউটিউব ভিডিওর বিস্তারিত, বিষয়বস্তু এবং ট্রান্সক্রিপ্ট (ভিডিওতে যা যা বলা হয়েছে) "
            "গভীরভাবে বিশ্লেষণ করে ফেসবুক পেজের জন্য অত্যন্ত আকর্ষণীয়, সাবলীল ও পাঠযোগ্য বাংলায় একটি ভাইরাল ফেসবুক পোস্ট তৈরি করা।"
        )

        prompt = f"""
নিচের ইউটিউব ভিডিওর তথ্য ও ট্রান্সক্রিপ্ট বিশ্লেষণ করো:
- ভিডিওর শিরোনাম: {video_title}
- ভিডিওর লিঙ্ক: {video_url}
- ভিডিওর বিবরণ (Description): {video_description[:1000]}
- ভিডিওর সাবটাইটেল/ট্রান্সক্রিপ্ট (যা যা বলা হয়েছে):
{transcript[:15000] if transcript else "ট্রান্সক্রিপ্ট পাওয়া যায়নি, শিরোনাম ও বিবরণের ওপর ভিত্তি করে লিখো।"}

কন্টেন্ট স্টাইল: {style}

পোস্টটি নিচের কাঠামোর ওপর ভিত্তি করে লিখবে:
১. একটি দুর্দান্ত ক্যাচি হুক/শিরোনাম (ইমোজি সহ, যা স্ক্রল থামিয়ে দেয়)।
২. ভিডিওতে মূল কোন সমস্যা বা টপিক নিয়ে আলোচনা করা হয়েছে তার বাস্তবসম্মত ভূমিকা।
৩. মূল শিক্ষণীয় বা গুরুত্বপূর্ণ বিষয়গুলো (৩-৫টি বুলেট পয়েন্ট আকারে সংক্ষেপে ও পরিষ্কারভাবে)।
৪. অডিয়েন্সের সাথে যুক্ত হওয়ার জন্য একটি প্রশ্ন বা মন্তব্য আহ্বান (Call to Action)।
৫. সম্পূর্ণ ভিডিওটি দেখতে আমন্ত্রণ ও ভিডিওর লিংক ({video_url if video_url else "চ্যানেলে গিয়ে ভিডিওটি দেখতে পারেন"})।
৬. ৫-৭টি প্রাসঙ্গিক জনপ্রিয় হ্যাশট্যাগ (যেমন: #TechTips #Tutorial #FacebookMarketing ইত্যাদি)।

আউটপুট শুধু মাত্র পোস্টের সম্পূর্ণ টেক্সট হিসেবে দিবে, কোনো অতিরিক্ত ভূমিকা বা 'নিচে পোস্ট দেওয়া হলো' টাইপ কথা বলবে না।
"""
        post_caption = await self._call_gemini_api(prompt, system_instruction)
        return {
            "title": video_title,
            "url": video_url,
            "caption": post_caption,
            "status": "pending_approval"
        }

    async def generate_auto_reply(
        self,
        incoming_text: str,
        sender_name: str = "গ্রাহক",
        context_type: str = "messenger_dm"  # 'messenger_dm', 'public_comment', 'private_reply_to_comment'
    ) -> Dict[str, Any]:
        """
        Generates smart reply for Messenger DM or Post Comment based on Knowledge Base.
        Returns dict with reply text, private inbox recommendation, and human alert flag.
        """
        kb = self.load_knowledge_base()
        kb_str = json.dumps(kb, ensure_ascii=False, indent=2)

        system_instruction = f"""
তুমি এই ফেসবুক পেজের অফিসিয়াল এআই সহকারী।
তোমার প্রধান দায়িত্ব গ্রাহকদের যেকোনো প্রশ্নের উত্তর অত্যন্ত বিনয়ী, সাবলীল ও প্রফেশনাল বাংলায় দেওয়া।

নিচে আমাদের পেজের অফিসিয়াল তথ্য ও নলেজ বেস (Knowledge Base) দেওয়া হলো:
{kb_str}

নির্দেশনা:
১. সর্বদা নলেজ বেসে থাকা তথ্যের ওপর ভিত্তি করে সঠিক উত্তর দেবে। বানিয়ে কিছু বলবে না।
২. সম্বোধনের ক্ষেত্রে 'আপনি' বা প্রয়োজনে 'ভাইয়া/আপু' ব্যবহার করবে।
৩. যদি কোনো প্রশ্নের উত্তর নলেজ বেসে না থাকে বা গ্রাহক খুব জটিল কোনো ব্যক্তিগত সমস্যার কথা বলে, তবে তাকে ভদ্রভাবে বলবে যে আমাদের একজন মানব প্রতিনিধি শীঘ্রই যোগাযোগ করবে। এবং "NEEDS_HUMAN_ALERT" সত্য করবে।
৪. উত্তরটি সর্বদা JSON ফরম্যাটে দেবে।
"""

        prompt = f"""
গ্রাহকের নাম: {sender_name}
প্ল্যাটফর্ম ধরন: {context_type}
গ্রাহকের মেসেজ বা কমেন্ট: "{incoming_text}"

অনুগ্রহ করে নিচের কাঠামোর বৈধ JSON অবজেক্ট আকারে উত্তর দাও (অন্য কোনো টেক্সট বা ব্যাকটিক ছাড়া):
{{
  "reply_text": "গ্রাহকের জন্য বাংলায় মূল রিপ্লাই",
  "is_asking_price_or_details": true/false (গ্রাহক কি দাম, অর্ডার বা স্পেসিফিক বিস্তারিত চেয়েছে?),
  "private_dm_text": "যদি কমেন্টে দাম/ডিটেইলস চায় তবে তার ইনবক্সে পাঠানোর উপযোগী বিস্তারিত মেসেজ, অন্যথায় খালি স্ট্রিং",
  "needs_human_alert": true/false (যদি এমন জটিল বা অচেনা প্রশ্ন হয় যা মানব অ্যাডমিনকে জানানো জরুরি),
  "alert_reason": "অ্যালার্ট করার কারণ (যদি needs_human_alert সত্য হয়)"
}}
"""
        raw_response = await self._call_gemini_api(prompt, system_instruction)
        
        # Clean JSON markdown if wrapped in ```json ... ```
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            return {
                "reply_text": data.get("reply_text", "ধন্যবাদ আপনার বার্তার জন্য! আমরা খুব শীঘ্রই যোগাযোগ করব।"),
                "is_asking_price_or_details": bool(data.get("is_asking_price_or_details", False)),
                "private_dm_text": data.get("private_dm_text", ""),
                "needs_human_alert": bool(data.get("needs_human_alert", False)),
                "alert_reason": data.get("alert_reason", "")
            }
        except Exception as e:
            logger.warning(f"Could not parse Gemini JSON response ({e}), raw text used: {raw_response}")
            return {
                "reply_text": raw_response if raw_response else "ধন্যবাদ আপনার বার্তার জন্য!",
                "is_asking_price_or_details": False,
                "private_dm_text": "",
                "needs_human_alert": False,
                "alert_reason": ""
            }

gemini_service = GeminiService()
