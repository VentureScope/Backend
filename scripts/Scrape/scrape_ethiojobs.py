import csv
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

from playwright.sync_api import sync_playwright

INPUT_FILE = os.path.join(os.path.dirname(__file__), "telegram_scrape_20260427213807.json")
OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__),
    f"jobs_{datetime.utcnow().isoformat().replace(':', '-').replace('.', '-')}.csv",
)

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger(__name__)


def extract_job_id(button_links: Any) -> Optional[str]:
    if not isinstance(button_links, list):
        return None
    for link in button_links:
        if not isinstance(link, dict):
            continue
        url = link.get("url")
        if not isinstance(url, str):
            continue
        match = re.search(r"job_id_(\d+)", url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def scrape_job_page(page) -> Dict[str, str]:
    return page.evaluate(
        """
        () => {
          const title = document.title || "";
          const h1 = document.querySelector("h1")?.innerText?.trim() || "";
          const metaDescription = document.querySelector('meta[name="description"]')?.content || "";
          const canonicalUrl = document.querySelector('link[rel="canonical"]')?.href || "";
          const bodyText = document.body?.innerText?.replace(/\s+/g, " ").trim() || "";

          return { title, h1, metaDescription, canonicalUrl, bodyText };
        }
        """
    )


def main() -> None:
    with open(INPUT_FILE, "r", encoding="utf-8") as handle:
        items = json.load(handle)

    headers = [
        "job_id",
        "source_channel",
        "source_id",
        "source_date",
        "source_text",
        "source_views",
        "source_forwards",
        "source_button_links",
        "redirect_location",
        "final_url",
        "page_title",
        "page_h1",
        "page_meta_description",
        "page_canonical_url",
        "page_body_text",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        handle.flush()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            current_redirect = {"value": ""}

            def capture_redirect(response) -> None:
                if current_redirect["value"]:
                    return
                try:
                    status = response.status
                    response_headers = response.headers
                    if status in REDIRECT_STATUSES and "location" in response_headers:
                        current_redirect["value"] = response_headers["location"]
                except Exception:
                    return

            page.on("response", capture_redirect)

            try:
                for item in items:
                    job_id = extract_job_id(item.get("button_links"))
                    if not job_id:
                        LOGGER.debug("Skipping item without job_id: %s", item.get("id"))
                        continue

                    base_url = f"https://ethiojobs.net/job/{job_id}"
                    current_redirect["value"] = ""
                    final_url = ""
                    scraped = {
                        "title": "",
                        "h1": "",
                        "metaDescription": "",
                        "canonicalUrl": "",
                        "bodyText": "",
                    }

                    try:
                        page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
                        final_url = page.url
                        scraped = scrape_job_page(page)
                    except Exception as exc:
                        LOGGER.warning("Failed to scrape %s: %s", base_url, exc)

                    writer.writerow(
                        {
                            "job_id": job_id,
                            "source_channel": item.get("channel", ""),
                            "source_id": item.get("id", ""),
                            "source_date": item.get("date", ""),
                            "source_text": item.get("text", ""),
                            "source_views": item.get("views", ""),
                            "source_forwards": item.get("forwards", ""),
                            "source_button_links": json.dumps(item.get("button_links", [])),
                            "redirect_location": current_redirect["value"],
                            "final_url": final_url,
                            "page_title": scraped.get("title", ""),
                            "page_h1": scraped.get("h1", ""),
                            "page_meta_description": scraped.get("metaDescription", ""),
                            "page_canonical_url": scraped.get("canonicalUrl", ""),
                            "page_body_text": scraped.get("bodyText", ""),
                        }
                    )
                    handle.flush()
                    LOGGER.info("Scraped job_id %s", job_id)
            except KeyboardInterrupt:
                LOGGER.warning("Interrupted. Partial CSV is saved.")
            finally:
                browser.close()

    LOGGER.info("CSV written to %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
