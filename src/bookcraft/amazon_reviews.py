"""Fetch Amazon customer reviews using a headless Playwright browser."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

REVIEWS_URL = "https://www.amazon.com/product-reviews/{asin}?sortBy=recent&reviewerType=all_reviews&pageNumber={page}"


@dataclass
class Review:
    stars: int
    title: str
    body: str
    date: str
    verified: bool


def fetch_reviews(asin: str, max_pages: int = 5) -> list[Review]:
    """Return up to max_pages * 10 reviews for the given Amazon ASIN."""
    from playwright.sync_api import sync_playwright

    reviews: list[Review] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        for page_num in range(1, max_pages + 1):
            url = REVIEWS_URL.format(asin=asin, page=page_num)
            logger.info("Fetching reviews page %d: %s", page_num, url)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(2_000)
            except Exception as e:
                logger.warning("Failed to load page %d: %s", page_num, e)
                break

            # Check for CAPTCHA / bot wall
            if "Type the characters" in page.content() or "robot" in page.content().lower():
                logger.warning("Bot detection triggered on page %d — stopping", page_num)
                break

            page_reviews = _parse_reviews(page.content())
            if not page_reviews:
                logger.info("No reviews found on page %d — stopping", page_num)
                break

            reviews.extend(page_reviews)
            logger.info("Page %d: found %d reviews (total %d)", page_num, len(page_reviews), len(reviews))

            if page_num < max_pages:
                time.sleep(1.5)

        browser.close()

    return reviews


def _parse_reviews(html: str) -> list[Review]:
    """Parse review blocks from Amazon HTML."""
    from playwright.sync_api import sync_playwright

    # Use regex on the raw HTML — avoids a second browser pass
    reviews: list[Review] = []

    # Each review block is wrapped in a data-hook="review" div
    blocks = re.findall(
        r'data-hook="review".*?(?=data-hook="review"|<div id="reviews-medley-footer")',
        html,
        re.DOTALL,
    )

    for block in blocks:
        stars = _extract_stars(block)
        title = _extract_text(block, r'data-hook="review-title"[^>]*>.*?<span[^>]*>(.*?)</span>', strip_html=True)
        body = _extract_text(block, r'data-hook="review-body"[^>]*>.*?<span[^>]*>(.*?)</span>', strip_html=True)
        date = _extract_text(block, r'data-hook="review-date"[^>]*>(.*?)</span>', strip_html=True)
        verified = "Verified Purchase" in block

        if body:
            reviews.append(Review(stars=stars, title=title, body=body, date=date, verified=verified))

    return reviews


def _extract_stars(block: str) -> int:
    m = re.search(r'(\d+)\.0 out of 5 stars', block)
    return int(m.group(1)) if m else 0


def _extract_text(block: str, pattern: str, strip_html: bool = False) -> str:
    m = re.search(pattern, block, re.DOTALL)
    if not m:
        return ""
    text = m.group(1)
    if strip_html:
        text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def format_reviews_report(reviews: list[Review], asin: str) -> str:
    """Format reviews as a plain-text report."""
    if not reviews:
        return f"No reviews fetched for ASIN {asin}.\n"

    lines: list[str] = []
    lines.append(f"Amazon Reviews — ASIN {asin}")
    lines.append(f"Total fetched: {len(reviews)}")
    lines.append("")

    by_stars: dict[int, list[Review]] = {}
    for r in reviews:
        by_stars.setdefault(r.stars, []).append(r)

    dist = "  ".join(f"{s}★: {len(by_stars.get(s, []))}" for s in range(5, 0, -1))
    lines.append(f"Distribution: {dist}")
    lines.append("")

    for stars in range(1, 6):
        group = by_stars.get(stars, [])
        if not group:
            continue
        lines.append(f"{'=' * 60}")
        lines.append(f"{stars} STAR REVIEWS ({len(group)})")
        lines.append(f"{'=' * 60}")
        for r in group:
            lines.append(f"\n[{r.stars}★] {r.title}")
            lines.append(f"Date: {r.date}{'  [Verified]' if r.verified else ''}")
            lines.append(r.body)
        lines.append("")

    return "\n".join(lines)
