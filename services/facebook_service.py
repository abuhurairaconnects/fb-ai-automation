import logging
from typing import Dict, Any, Optional
import httpx
from config import settings

logger = logging.getLogger("facebook_service")

GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

class FacebookService:
    def __init__(self):
        self.page_id = settings.FB_PAGE_ID
        self.access_token = settings.FB_PAGE_ACCESS_TOKEN

    def _get_headers(self) -> dict:
        return {
            "Content-Type": "application/json"
        }

    async def publish_post(
        self,
        caption: str,
        link: Optional[str] = None,
        photo_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Publishes a post to the Facebook Page feed or photo album.
        """
        if not self.access_token:
            logger.error("FB_PAGE_ACCESS_TOKEN is missing.")
            return {"success": False, "error": "FB_PAGE_ACCESS_TOKEN is not configured"}

        endpoint_target = self.page_id if self.page_id else "me"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if photo_url:
                    # Post with photo
                    url = f"{BASE_URL}/{endpoint_target}/photos"
                    params = {
                        "url": photo_url,
                        "caption": caption,
                        "access_token": self.access_token
                    }
                    resp = await client.post(url, params=params)
                else:
                    # Regular text / link post
                    url = f"{BASE_URL}/{endpoint_target}/feed"
                    payload: Dict[str, Any] = {
                        "message": caption,
                        "access_token": self.access_token
                    }
                    if link:
                        payload["link"] = link
                    resp = await client.post(url, json=payload)

                data = resp.json()
                if resp.status_code in [200, 201]:
                    post_id = data.get("id") or data.get("post_id")
                    logger.info(f"Successfully published post to Facebook Page: {post_id}")
                    return {"success": True, "post_id": post_id, "data": data}
                else:
                    logger.error(f"Facebook publish post failed: {data}")
                    return {"success": False, "error": data.get("error", {}).get("message", "Unknown error"), "data": data}

        except Exception as e:
            logger.error(f"Exception while publishing post to Facebook: {e}")
            return {"success": False, "error": str(e)}

    async def send_messenger_message(
        self,
        recipient_id: str,
        message_text: str
    ) -> Dict[str, Any]:
        """
        Sends a private message to a user on Facebook Messenger.
        """
        if not self.access_token:
            return {"success": False, "error": "FB_PAGE_ACCESS_TOKEN missing"}

        endpoint_target = self.page_id if self.page_id else "me"
        url = f"{BASE_URL}/{endpoint_target}/messages"

        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text},
            "messaging_type": "RESPONSE",
            "access_token": self.access_token
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if resp.status_code in [200, 201]:
                    logger.info(f"Messenger reply sent to {recipient_id}")
                    return {"success": True, "message_id": data.get("message_id")}
                else:
                    logger.error(f"Failed to send messenger message: {data}")
                    return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"Exception sending Messenger message: {e}")
            return {"success": False, "error": str(e)}

    async def reply_to_comment(
        self,
        comment_id: str,
        message_text: str
    ) -> Dict[str, Any]:
        """
        Replies publicly to a comment on a Facebook post.
        """
        if not self.access_token:
            return {"success": False, "error": "FB_PAGE_ACCESS_TOKEN missing"}

        url = f"{BASE_URL}/{comment_id}/comments"
        payload = {
            "message": message_text,
            "access_token": self.access_token
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if resp.status_code in [200, 201]:
                    logger.info(f"Comment reply posted to {comment_id}")
                    return {"success": True, "comment_id": data.get("id")}
                else:
                    logger.error(f"Failed to reply to comment {comment_id}: {data}")
                    return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"Exception replying to comment: {e}")
            return {"success": False, "error": str(e)}

    async def send_private_reply_to_comment(
        self,
        comment_id: str,
        message_text: str
    ) -> Dict[str, Any]:
        """
        Sends a 1-to-1 private Messenger message directly to someone who commented on a post.
        """
        if not self.access_token:
            return {"success": False, "error": "FB_PAGE_ACCESS_TOKEN missing"}

        endpoint_target = self.page_id if self.page_id else "me"
        url = f"{BASE_URL}/{endpoint_target}/messages"

        payload = {
            "recipient": {"comment_id": comment_id},
            "message": {"text": message_text},
            "messaging_type": "RESPONSE",
            "access_token": self.access_token
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if resp.status_code in [200, 201]:
                    logger.info(f"Private reply sent for comment {comment_id}")
                    return {"success": True, "message_id": data.get("message_id")}
                else:
                    logger.error(f"Failed to send private reply for comment {comment_id}: {data}")
                    return {"success": False, "error": data}
        except Exception as e:
            logger.error(f"Exception sending private reply for comment: {e}")
            return {"success": False, "error": str(e)}

facebook_service = FacebookService()
