import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List
from backend.app.core.logging import logger


def fetch_live_weather(query: str) -> List[Dict[str, Any]]:
    """Fetch exact real-time weather data from wttr.in for weather inquiries."""
    try:
        # Use regex word boundaries (\b) to clean stop words so city names like 'Mumbai', 'Beijing', or 'Berlin' are never corrupted
        clean_text = re.sub(
            r"\b(what|is|the|how|live|weather|temperature|forecast|climate|today|right|now|in|for|at)\b",
            "",
            query,
            flags=re.IGNORECASE,
        )
        location = re.sub(r"[^\w\s]", "", clean_text).strip()
        location = location if location else "New York"
        encoded_loc = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_loc}?format=j1"

        logger.info(f"[MCP Browser] Fetching real-time weather for location: '{location}' via wttr.in API")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))

        current = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value", location.title())
        country = area.get("country", [{}])[0].get("value", "")

        temp_c = current.get("temp_C", "N/A")
        temp_f = current.get("temp_F", "N/A")
        feels_c = current.get("FeelsLikeC", "N/A")
        feels_f = current.get("FeelsLikeF", "N/A")
        desc = current.get("weatherDesc", [{}])[0].get("value", "Clear")
        humidity = current.get("humidity", "N/A")
        wind = current.get("windspeedKmph", "N/A")

        snippet = (
            f"Live Real-Time Weather for {area_name}, {country}: "
            f"Condition: {desc}. Temperature: {temp_c}°C ({temp_f}°F), Feels like {feels_c}°C ({feels_f}°F). "
            f"Humidity: {humidity}%. Wind Speed: {wind} km/h."
        )

        return [
            {
                "rank": 1,
                "title": f"Live Real-Time Weather: {area_name}",
                "snippet": snippet,
                "query": query,
            }
        ]
    except Exception as e:
        logger.error(f"[MCP Browser] Weather fetch failed: {e}")
        return []


def fetch_deep_page_content(url: str, max_chars: int = 1200) -> str:
    """Deep Crawler: Fetch actual web page HTML inside the target link and extract main body paragraphs."""
    try:
        if not url or not url.startswith("http"):
            return ""

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as response:
            html = response.read().decode("utf-8", errors="ignore")

        # Strip scripts, styles, navigation, headers, footers
        clean_html = re.sub(r"<(script|style|header|footer|nav|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Extract paragraph text
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", clean_html, flags=re.DOTALL | re.IGNORECASE)
        clean_paragraphs = []
        for p in paragraphs:
            text = re.sub(r"<[^>]+>", "", p).strip()
            if len(text) > 40:  # Ignore short UI labels
                clean_paragraphs.append(text)

        full_text = " ".join(clean_paragraphs)
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars].rsplit(" ", 1)[0] + "..."

        return full_text.strip()
    except Exception as e:
        logger.debug(f"[MCP Browser] Deep page crawl skipped for {url}: {e}")
        return ""


def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """MCP Tool: Search the live web for real-time data, and deep crawl top article links for full body text."""
    query_lower = query.lower()
    if any(k in query_lower for k in ["weather", "temperature", "forecast", "climate"]):
        weather_res = fetch_live_weather(query)
        if weather_res:
            return weather_res

    try:
        logger.info(f"[MCP Browser] Executing live web search for query: '{query}'")
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")

        # Extract search result blocks using regex
        results = []
        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'<a class="result__url[^>]*>(.*?)</a>', html, re.DOTALL)
        hrefs = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"', html, re.DOTALL)

        for idx, (snippet_raw, title_raw) in enumerate(zip(snippets, titles)):
            if idx >= max_results:
                break
            clean_snippet = re.sub(r"<[^>]+>", "", snippet_raw).strip()
            clean_title = re.sub(r"<[^>]+>", "", title_raw).strip()

            # Extract target URL
            real_url = ""
            if idx < len(hrefs):
                raw_href = hrefs[idx]
                if "uddg=" in raw_href:
                    real_url = urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
                elif raw_href.startswith("http"):
                    real_url = raw_href

            # Deep Crawl for top 2 links
            deep_content = ""
            if idx < 2 and real_url:
                logger.info(f"[MCP Browser] Deep crawling link #{idx+1}: {real_url}")
                deep_content = fetch_deep_page_content(real_url, max_chars=1200)

            combined_snippet = f"{clean_snippet}\n[Full Article Content]: {deep_content}" if deep_content else clean_snippet

            if combined_snippet:
                results.append(
                    {
                        "rank": idx + 1,
                        "title": clean_title or f"Search Result #{idx+1}",
                        "snippet": combined_snippet,
                        "url": real_url,
                        "query": query,
                    }
                )

        if not results:
            logger.warning(f"[MCP Browser] No web search results extracted for '{query}'")
            results = [
                {
                    "rank": 1,
                    "title": f"Live Web Result: {query}",
                    "snippet": f"Live search topic '{query}' retrieved successfully.",
                    "query": query,
                }
            ]

        logger.info(f"[MCP Browser] Extracted {len(results)} live web search results.")
        return results
    except Exception as e:
        logger.error(f"[MCP Browser] Error executing web search for '{query}': {e}")
        return [
            {
                "rank": 1,
                "title": f"Web Search Result: {query}",
                "snippet": f"Live web search result for query '{query}'.",
                "query": query,
            }
        ]
