import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

logger = logging.getLogger("youtube_service")

PROCESSED_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "processed_videos.json")

class YouTubeService:
    def __init__(self):
        self._processed_video_ids = self._load_processed_videos()

    def _load_processed_videos(self) -> set:
        if os.path.exists(PROCESSED_FILE):
            try:
                with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data)
            except Exception as e:
                logger.error(f"Error loading processed videos: {e}")
        return set()

    def mark_video_processed(self, video_id: str):
        self._processed_video_ids.add(video_id)
        try:
            with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self._processed_video_ids), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving processed videos: {e}")

    @staticmethod
    def extract_video_id(url_or_id: str) -> Optional[str]:
        """Extracts 11-char YouTube video ID from various URL formats or raw ID."""
        if not url_or_id:
            return None
        cleaned = url_or_id.strip()
        if len(cleaned) == 11 and re.match(r'^[A-Za-z0-9_-]{11}$', cleaned):
            return cleaned

        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'youtu\.be\/([0-9A-Za-z_-]{11})',
            r'embed\/([0-9A-Za-z_-]{11})',
            r'shorts\/([0-9A-Za-z_-]{11})',
        ]
        for p in patterns:
            match = re.search(p, cleaned)
            if match:
                return match.group(1)
        return None

    async def get_latest_videos_from_channel(self, channel_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches latest videos from YouTube channel via RSS feed (Zero API key required, 100% free & fast).
        """
        if not channel_id:
            return []

        # If user provides @handle, resolve or fetch
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        
        videos = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch YouTube RSS feed for {channel_id}: status {resp.status_code}")
                    return []

                root = ET.fromstring(resp.content)
                # XML Namespaces in YouTube RSS
                ns = {
                    "atom": "http://www.w3.org/2005/Atom",
                    "yt": "http://www.youtube.com/xml/schemas/2015",
                    "media": "http://search.yahoo.com/mrss/"
                }

                entries = root.findall("atom:entry", ns)
                for entry in entries[:max_results]:
                    vid_elem = entry.find("yt:videoId", ns)
                    title_elem = entry.find("atom:title", ns)
                    media_group = entry.find("media:group", ns)
                    desc_elem = media_group.find("media:description", ns) if media_group is not None else None
                    thumbnail_elem = media_group.find("media:thumbnail", ns) if media_group is not None else None

                    vid_id = vid_elem.text if vid_elem is not None else None
                    if not vid_id:
                        continue

                    title = title_elem.text if title_elem is not None else "Untitled Video"
                    desc = desc_elem.text if desc_elem is not None else ""
                    thumbnail_url = thumbnail_elem.attrib.get("url") if thumbnail_elem is not None else f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"

                    videos.append({
                        "video_id": vid_id,
                        "title": title,
                        "description": desc,
                        "url": f"https://www.youtube.com/watch?v=/{vid_id}",
                        "thumbnail_url": thumbnail_url,
                        "is_new": vid_id not in self._processed_video_ids
                    })
        except Exception as e:
            logger.error(f"Error reading channel RSS feed: {e}")

        return videos

    def get_video_transcript(self, video_id: str) -> str:
        """
        Extracts transcript/subtitles for the video using youtube_transcript_api.
        Prefers Bengali ('bn', 'bn-BD', 'bn-IN'), then English ('en', 'en-US'), or any available.
        """
        try:
            # Check available transcript languages
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # 1. Look for manually created Bengali
            try:
                transcript = transcript_list.find_transcript(['bn', 'bn-BD', 'bn-IN', 'en', 'en-US'])
                items = transcript.fetch()
                return " ".join([i['text'] for i in items])
            except Exception:
                pass

            # 2. Look for auto-generated transcript and translate or take it directly
            for t in transcript_list:
                try:
                    items = t.fetch()
                    return " ".join([i['text'] for i in items])
                except Exception:
                    continue

        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.info(f"No transcript found for video {video_id}: {e}")
        except Exception as e:
            logger.warning(f"Could not retrieve transcript for {video_id}: {e}")

        return ""

    async def get_video_details_by_id(self, video_id: str) -> Dict[str, Any]:
        """
        Fetches title, description, thumbnail and transcript for a single video ID on demand.
        Uses oEmbed and public metadata.
        """
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        title = "YouTube Video"
        description = ""

        # Fetch oEmbed for accurate title & author
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
                resp = await client.get(oembed_url)
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", title)
        except Exception as e:
            logger.warning(f"oEmbed fetch error for {video_id}: {e}")

        transcript = self.get_video_transcript(video_id)

        return {
            "video_id": video_id,
            "title": title,
            "description": description,
            "url": video_url,
            "thumbnail_url": thumbnail_url,
            "transcript": transcript
        }

youtube_service = YouTubeService()
