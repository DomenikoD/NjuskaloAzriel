"""
Njuskalo.hr Laptop Scraper & Analyzer

Scrapes laptop listings from njuskalo.hr, extracts specs and prices,
then performs best-buy and price-drop analysis to find the best deals.

Usage:
    python scraper.py [--pages N] [--output FILE] [--min-price N] [--max-price N]

Requirements:
    pip install -r requirements.txt
    Chrome/Chromium browser installed
    ChromeDriver available in PATH
"""

import argparse
import logging
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.njuskalo.hr"

# Brand subcategory URLs (actual laptops only, excludes parts/accessories/broken)
BRAND_CATEGORIES = {
    "Acer": "/acer-prijenosnici",
    "Asus": "/asus-prijenosnici",
    "Apple": "/apple-macbook",
    "Dell": "/dell-prijenosnici",
    "Fujitsu": "/fujitsu-siemens-prijenosnici",
    "HP": "/hp-prijenosnici",
    "Lenovo": "/ibm-lenovo-prijenosnici",
    "Sony": "/sony-prijenosnici",
    "Toshiba": "/toshiba-prijenosnici",
    "Other": "/ostale-marke-laptopa",
}

# Known CPU generations with approximate release years and performance tiers
# tier: 1=low, 2=mid, 3=high, 4=ultra
CPU_DATABASE = {
    # Intel 14th/15th Gen (2024-2025)
    r"i9[-\s]?1[45]\d{3}": {"gen": "Intel 14/15th", "tier": 4, "year": 2024},
    r"i7[-\s]?1[45]\d{3}": {"gen": "Intel 14/15th", "tier": 3, "year": 2024},
    r"i5[-\s]?1[45]\d{3}": {"gen": "Intel 14/15th", "tier": 2, "year": 2024},
    r"i3[-\s]?1[45]\d{3}": {"gen": "Intel 14/15th", "tier": 1, "year": 2024},
    # Intel 13th Gen (2023)
    r"i9[-\s]?13\d{3}": {"gen": "Intel 13th", "tier": 4, "year": 2023},
    r"i7[-\s]?13\d{3}": {"gen": "Intel 13th", "tier": 3, "year": 2023},
    r"i5[-\s]?13\d{3}": {"gen": "Intel 13th", "tier": 2, "year": 2023},
    r"i3[-\s]?13\d{3}": {"gen": "Intel 13th", "tier": 1, "year": 2023},
    # Intel 12th Gen (2022)
    r"i9[-\s]?12\d{3}": {"gen": "Intel 12th", "tier": 4, "year": 2022},
    r"i7[-\s]?12\d{3}": {"gen": "Intel 12th", "tier": 3, "year": 2022},
    r"i5[-\s]?12\d{3}": {"gen": "Intel 12th", "tier": 2, "year": 2022},
    r"i3[-\s]?12\d{3}": {"gen": "Intel 12th", "tier": 1, "year": 2022},
    # Intel 11th Gen (2021)
    r"i9[-\s]?11\d{3}": {"gen": "Intel 11th", "tier": 4, "year": 2021},
    r"i7[-\s]?11\d{3}": {"gen": "Intel 11th", "tier": 3, "year": 2021},
    r"i5[-\s]?11\d{3}": {"gen": "Intel 11th", "tier": 2, "year": 2021},
    r"i3[-\s]?11\d{3}": {"gen": "Intel 11th", "tier": 1, "year": 2021},
    # Intel 10th Gen (2020)
    r"i9[-\s]?10\d{3}": {"gen": "Intel 10th", "tier": 4, "year": 2020},
    r"i7[-\s]?10\d{3}": {"gen": "Intel 10th", "tier": 3, "year": 2020},
    r"i5[-\s]?10\d{3}": {"gen": "Intel 10th", "tier": 2, "year": 2020},
    r"i3[-\s]?10\d{3}": {"gen": "Intel 10th", "tier": 1, "year": 2020},
    # Intel 8th Gen (2018)
    r"i7[-\s]?8\d{3}": {"gen": "Intel 8th", "tier": 3, "year": 2018},
    r"i5[-\s]?8\d{3}": {"gen": "Intel 8th", "tier": 2, "year": 2018},
    r"i3[-\s]?8\d{3}": {"gen": "Intel 8th", "tier": 1, "year": 2018},
    # AMD Ryzen 7000/8000 (2024-2025)
    r"ryzen\s*9\s*[78]\d{3}": {"gen": "AMD Zen4/5", "tier": 4, "year": 2024},
    r"ryzen\s*7\s*[78]\d{3}": {"gen": "AMD Zen4/5", "tier": 3, "year": 2024},
    r"ryzen\s*5\s*[78]\d{3}": {"gen": "AMD Zen4/5", "tier": 2, "year": 2024},
    r"ryzen\s*3\s*[78]\d{3}": {"gen": "AMD Zen4/5", "tier": 1, "year": 2024},
    # AMD Ryzen 5000/6000 (2022-2023)
    r"ryzen\s*9\s*[56]\d{3}": {"gen": "AMD Zen3/4", "tier": 4, "year": 2022},
    r"ryzen\s*7\s*[56]\d{3}": {"gen": "AMD Zen3/4", "tier": 3, "year": 2022},
    r"ryzen\s*5\s*[56]\d{3}": {"gen": "AMD Zen3/4", "tier": 2, "year": 2022},
    r"ryzen\s*3\s*[56]\d{3}": {"gen": "AMD Zen3/4", "tier": 1, "year": 2022},
    # Apple Silicon (word-boundary anchored to avoid false positives)
    r"\bm[45]\s*max\b": {"gen": "Apple M4/M5", "tier": 4, "year": 2024},
    r"\bm[45]\s*pro\b": {"gen": "Apple M4/M5", "tier": 3, "year": 2024},
    r"\bm[45]\b(?!\s*(?:ssd|hdd|\.2))": {"gen": "Apple M4/M5", "tier": 2, "year": 2024},
    r"\bm3\s*max\b": {"gen": "Apple M3", "tier": 4, "year": 2023},
    r"\bm3\s*pro\b": {"gen": "Apple M3", "tier": 3, "year": 2023},
    r"\bm3\b(?!\s*(?:ssd|hdd|\.2))": {"gen": "Apple M3", "tier": 2, "year": 2023},
    r"\bm2\s*max\b": {"gen": "Apple M2", "tier": 4, "year": 2022},
    r"\bm2\s*pro\b": {"gen": "Apple M2", "tier": 3, "year": 2022},
    r"\bm2\b(?!\s*(?:ssd|hdd|\.2))": {"gen": "Apple M2", "tier": 2, "year": 2022},
    r"\bm1\s*max\b": {"gen": "Apple M1", "tier": 3, "year": 2021},
    r"\bm1\s*pro\b": {"gen": "Apple M1", "tier": 3, "year": 2021},
    r"\bm1\b(?!\s*(?:ssd|hdd|\.2))": {"gen": "Apple M1", "tier": 2, "year": 2020},
}


@dataclass
class LaptopListing:
    """Represents a single laptop listing from njuskalo.hr."""

    title: str
    price_eur: Optional[float]
    url: str
    date_posted: Optional[str]
    location: str = ""
    brand: str = ""
    # Extracted specs
    cpu: str = ""
    cpu_gen: str = ""
    cpu_tier: int = 0
    cpu_year: int = 0
    ram_gb: int = 0
    storage_gb: int = 0
    storage_type: str = ""
    screen_size: float = 0.0
    resolution: str = ""
    condition: str = ""
    # Analysis fields
    value_score: float = 0.0
    estimated_market_price: float = 0.0
    price_drop_pct: float = 0.0
    deal_rating: str = ""


def create_driver(proxy: str = "") -> webdriver.Chrome:
    """Create a headless Chrome WebDriver instance with anti-detection measures.

    Args:
        proxy: Optional proxy URL (e.g., 'http://user:pass@host:port' or
               'socks5://host:port'). Residential proxies are recommended
               to avoid IP-based bot detection.
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # Additional anti-detection flags
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
        logger.info("Using proxy: %s", proxy.split("@")[-1] if "@" in proxy else proxy)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)

    # Remove webdriver flag from navigator
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['hr-HR', 'hr', 'en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            """
        },
    )

    return driver


def accept_cookies(driver: webdriver.Chrome) -> None:
    """Dismiss cookie consent dialog if present."""
    try:
        cookie_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.ID, "didomi-notice-agree-button")
            )
        )
        cookie_btn.click()
        time.sleep(1)
        logger.info("Cookie consent accepted")
    except Exception:
        logger.debug("No cookie consent dialog found")


def parse_price(text: str) -> Optional[float]:
    """Extract price in EUR from text like '1.200 EUR' or '650 €'."""
    if not text:
        return None
    # Remove common noise
    text = text.replace("\xa0", " ").strip()
    # Match patterns like "1.200 €", "650€", "1,200 EUR", "350.00 €"
    match = re.search(r"([\d.,]+)\s*(?:€|EUR|eur)", text)
    if match:
        price_str = match.group(1)
        # Croatian format: 1.200,50 -> 1200.50
        if "." in price_str and "," in price_str:
            price_str = price_str.replace(".", "").replace(",", ".")
        elif "." in price_str:
            # Could be 1.200 (thousands separator) or 1.50 (decimal)
            parts = price_str.split(".")
            if len(parts[-1]) == 3:
                # Thousands separator
                price_str = price_str.replace(".", "")
            # else it's a decimal
        elif "," in price_str:
            price_str = price_str.replace(",", ".")
        try:
            return float(price_str)
        except ValueError:
            return None
    return None


def extract_specs_from_text(text: str) -> dict:
    """Extract laptop specifications from title and description text."""
    text_lower = text.lower()
    specs = {}

    # CPU detection
    for pattern, info in CPU_DATABASE.items():
        if re.search(pattern, text_lower):
            match = re.search(pattern, text_lower)
            specs["cpu"] = match.group(0).strip()
            specs["cpu_gen"] = info["gen"]
            specs["cpu_tier"] = info["tier"]
            specs["cpu_year"] = info["year"]
            break

    # RAM detection (e.g., "16GB RAM", "8 GB", "32gb")
    ram_match = re.search(
        r"(\d{1,3})\s*gb\s*(?:ram|ddr|memory)", text_lower
    )
    if not ram_match:
        ram_match = re.search(r"(\d{1,3})\s*gb(?!\s*(?:ssd|hdd|nvme|storage|disk))", text_lower)
    if ram_match:
        ram_val = int(ram_match.group(1))
        if ram_val in (2, 4, 8, 12, 16, 24, 32, 48, 64, 128):
            specs["ram_gb"] = ram_val

    # Storage detection
    ssd_match = re.search(
        r"(\d{1,4})\s*(?:gb|tb)\s*(?:ssd|nvme|m\.?2|pcie)", text_lower
    )
    hdd_match = re.search(r"(\d{1,4})\s*(?:gb|tb)\s*(?:hdd|hard)", text_lower)
    storage_match = re.search(
        r"(\d{1,4})\s*(gb|tb)\s*(?:ssd|nvme|m\.?2|hdd|storage|disk)", text_lower
    )
    if ssd_match:
        val = int(ssd_match.group(1))
        unit = "tb" if "tb" in ssd_match.group(0).lower() else "gb"
        specs["storage_gb"] = val * 1000 if unit == "tb" else val
        specs["storage_type"] = "SSD"
    elif hdd_match:
        val = int(hdd_match.group(1))
        unit = "tb" if "tb" in hdd_match.group(0).lower() else "gb"
        specs["storage_gb"] = val * 1000 if unit == "tb" else val
        specs["storage_type"] = "HDD"
    elif storage_match:
        val = int(storage_match.group(1))
        unit = storage_match.group(2).lower()
        specs["storage_gb"] = val * 1000 if unit == "tb" else val
        specs["storage_type"] = "SSD"

    # Screen size (e.g., "15.6\"", "14 inch", "13.3")
    screen_match = re.search(
        r'(\d{2}(?:\.\d)?)\s*(?:"|\'|inch|incha|col|")', text_lower
    )
    if screen_match:
        specs["screen_size"] = float(screen_match.group(1))

    # Resolution
    res_match = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", text_lower)
    if res_match:
        w, h = int(res_match.group(1)), int(res_match.group(2))
        if w >= 1920 or h >= 1080:
            specs["resolution"] = f"{w}x{h}"
    if "fhd" in text_lower or "full hd" in text_lower:
        specs.setdefault("resolution", "1920x1080")
    elif "qhd" in text_lower or "2k" in text_lower:
        specs.setdefault("resolution", "2560x1440")
    elif "4k" in text_lower or "uhd" in text_lower:
        specs.setdefault("resolution", "3840x2160")

    return specs


def scrape_listing_page(
    soup: BeautifulSoup, brand: str
) -> list[LaptopListing]:
    """Parse all laptop listings from a single page."""
    listings = []
    items = soup.select(".EntityList-item")

    for item in items:
        try:
            # Title and URL
            title_el = item.select_one(".entity-title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            url = BASE_URL + href if href.startswith("/") else href

            # Skip non-laptop items (parts, chargers, bags, etc.)
            skip_keywords = [
                "punjač", "adapter", "baterija", "torba", "ruksak",
                "tipkovnica", "ekran", "display", "panel", "kućište",
                "ventilator", "hladnjak", "kabel", "konektor", "matična",
                "ploča", "wi-fi", "bluetooth", "procesor", "optički",
                "zvučnik", "mikrofon", "web kamer", "tipk", "prekidač",
                "dijelov", "dock", "stalak", "miš", "mouse", "hub",
                "memorija ram", "stick", "modul ram",
            ]
            title_lower = title.lower()
            if any(kw in title_lower for kw in skip_keywords):
                continue

            # Price
            price_el = item.select_one(".price--hrk, .price--eur, .price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = parse_price(price_text)

            # Skip listings with no price or unrealistically low price
            if price is None or price < 30:
                continue

            # Date posted
            date_el = item.select_one("time[datetime]")
            date_posted = date_el.get("datetime", "") if date_el else ""

            # Location
            desc_el = item.select_one(".entity-description")
            location = ""
            if desc_el:
                loc_text = desc_el.get_text(strip=True)
                loc_match = re.search(r"Lokacija:\s*(.+?)(?:$|\n)", loc_text)
                if loc_match:
                    location = loc_match.group(1).strip()

            # Extract specs from title
            specs = extract_specs_from_text(title)

            listing = LaptopListing(
                title=title,
                price_eur=price,
                url=url,
                date_posted=date_posted,
                location=location,
                brand=brand,
                cpu=specs.get("cpu", ""),
                cpu_gen=specs.get("cpu_gen", ""),
                cpu_tier=specs.get("cpu_tier", 0),
                cpu_year=specs.get("cpu_year", 0),
                ram_gb=specs.get("ram_gb", 0),
                storage_gb=specs.get("storage_gb", 0),
                storage_type=specs.get("storage_type", ""),
                screen_size=specs.get("screen_size", 0.0),
                resolution=specs.get("resolution", ""),
            )
            listings.append(listing)

        except Exception as e:
            logger.warning("Error parsing listing: %s", e)
            continue

    return listings


def scrape_detail_page(
    driver: webdriver.Chrome, listing: LaptopListing
) -> LaptopListing:
    """Visit individual listing page to extract additional specs."""
    try:
        driver.get(listing.url)
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Get description text for additional spec extraction
        desc = soup.select_one(
            ".ClassifiedDetailDescription, "
            "[class*='Description-text'], "
            ".classified-detail__description"
        )
        if desc:
            desc_text = desc.get_text(strip=True)
            combined_text = listing.title + " " + desc_text
            specs = extract_specs_from_text(combined_text)

            # Only fill in specs we don't already have
            if not listing.cpu and specs.get("cpu"):
                listing.cpu = specs["cpu"]
                listing.cpu_gen = specs.get("cpu_gen", "")
                listing.cpu_tier = specs.get("cpu_tier", 0)
                listing.cpu_year = specs.get("cpu_year", 0)
            if not listing.ram_gb and specs.get("ram_gb"):
                listing.ram_gb = specs["ram_gb"]
            if not listing.storage_gb and specs.get("storage_gb"):
                listing.storage_gb = specs["storage_gb"]
                listing.storage_type = specs.get("storage_type", "")
            if not listing.screen_size and specs.get("screen_size"):
                listing.screen_size = specs["screen_size"]
            if not listing.resolution and specs.get("resolution"):
                listing.resolution = specs["resolution"]

        # Check condition from detail page
        condition_el = soup.find(
            string=re.compile(r"Stanje", re.IGNORECASE)
        )
        if condition_el:
            parent = condition_el.find_parent()
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    condition_text = sibling.get_text(strip=True).lower()
                    if "novo" in condition_text:
                        listing.condition = "new"
                    elif "rabljeno" in condition_text or "korišteno" in condition_text:
                        listing.condition = "used"
                    elif "oštećeno" in condition_text:
                        listing.condition = "damaged"

    except Exception as e:
        logger.debug("Could not scrape detail page %s: %s", listing.url, e)

    return listing


def _is_bot_blocked(driver: webdriver.Chrome) -> bool:
    """Check if the current page is a bot-detection challenge (perfdrive)."""
    current_url = driver.current_url
    if "validate.perfdrive.com" in current_url:
        return True
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        h1 = soup.select_one("h1")
        if h1 and "ispričavam" in h1.get_text(strip=True).lower():
            return True
    except Exception:
        pass
    return False


def _wait_for_page_or_detect_block(
    driver: webdriver.Chrome, max_wait: int = 10
) -> bool:
    """Wait for the page to load and check for bot blocking.

    Returns True if the page loaded normally, False if blocked.
    """
    for _ in range(max_wait):
        if _is_bot_blocked(driver):
            return False
        # Check if listing content is present
        try:
            soup = BeautifulSoup(driver.page_source, "html.parser")
            if soup.select(".EntityList-item") or soup.select(".entity-title"):
                return True
        except Exception:
            pass
        time.sleep(1)
    # Final check
    return not _is_bot_blocked(driver)


def scrape_all_laptops(
    pages_per_category: int = 3,
    min_price: float = 0,
    max_price: float = float("inf"),
    scrape_details: bool = False,
    categories: Optional[list[str]] = None,
    proxy: str = "",
) -> list[LaptopListing]:
    """
    Scrape laptop listings from all brand categories on njuskalo.hr.

    Args:
        pages_per_category: Number of pages to scrape per brand category.
        min_price: Minimum price filter in EUR.
        max_price: Maximum price filter in EUR.
        scrape_details: Whether to visit each listing's detail page.
        categories: List of brand names to scrape (None = all).
        proxy: Optional proxy URL for anti-bot-detection bypass.

    Returns:
        List of LaptopListing objects.
    """
    driver = create_driver(proxy=proxy)
    all_listings: list[LaptopListing] = []
    seen_urls: set[str] = set()
    bot_blocked = False

    cats = categories or list(BRAND_CATEGORIES.keys())

    try:
        # Accept cookies on first page load
        driver.get(BASE_URL + "/prijenosna-racunala")
        time.sleep(3)

        if _is_bot_blocked(driver):
            logger.error(
                "Bot detection triggered on initial page load. "
                "njuskalo.hr uses perfdrive anti-bot protection that may "
                "block datacenter IPs. Try using a residential proxy with "
                "--proxy http://user:pass@host:port"
            )
            bot_blocked = True
            return all_listings

        accept_cookies(driver)

        for brand in cats:
            if brand not in BRAND_CATEGORIES:
                logger.warning("Unknown brand category: %s", brand)
                continue

            cat_path = BRAND_CATEGORIES[brand]
            logger.info("Scraping %s laptops (%s)...", brand, cat_path)

            for page in range(1, pages_per_category + 1):
                url = f"{BASE_URL}{cat_path}?page={page}"
                logger.info("  Page %d: %s", page, url)

                try:
                    driver.get(url)
                    time.sleep(3)

                    # Check for bot blocking with retry
                    if _is_bot_blocked(driver):
                        logger.warning(
                            "Bot detection triggered on %s. "
                            "Waiting 30s before retry...", url
                        )
                        time.sleep(30)
                        driver.get(url)
                        time.sleep(5)
                        if _is_bot_blocked(driver):
                            logger.error(
                                "Still blocked after retry. "
                                "Skipping remaining pages for %s. "
                                "Consider using --proxy.", brand
                            )
                            bot_blocked = True
                            break

                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    page_listings = scrape_listing_page(soup, brand)

                    if not page_listings:
                        logger.info(
                            "  No more listings found on page %d", page
                        )
                        break

                    for listing in page_listings:
                        if listing.url not in seen_urls:
                            # Apply price filters
                            if listing.price_eur is not None:
                                if (
                                    min_price
                                    <= listing.price_eur
                                    <= max_price
                                ):
                                    seen_urls.add(listing.url)
                                    all_listings.append(listing)

                    logger.info(
                        "  Found %d listings on page %d",
                        len(page_listings),
                        page,
                    )

                except Exception as e:
                    logger.error("Error scraping page %s: %s", url, e)
                    continue

            if bot_blocked:
                break

        # Optionally scrape detail pages for additional specs
        if scrape_details and all_listings:
            logger.info(
                "Scraping detail pages for %d listings...",
                len(all_listings),
            )
            for i, listing in enumerate(all_listings):
                if i % 10 == 0:
                    logger.info(
                        "  Detail progress: %d/%d", i, len(all_listings)
                    )
                scrape_detail_page(driver, listing)
                time.sleep(1)  # Be polite

    finally:
        driver.quit()

    if bot_blocked and not all_listings:
        logger.error(
            "No listings could be scraped due to bot detection. "
            "njuskalo.hr blocks datacenter/cloud IPs. Solutions:\n"
            "  1. Use a residential proxy: --proxy http://user:pass@host:port\n"
            "  2. Use a SOCKS proxy: --proxy socks5://host:port\n"
            "  3. Run from a residential IP (home network, VPN)"
        )

    logger.info("Total listings scraped: %d", len(all_listings))
    return all_listings


# ---------------------------------------------------------------------------
# Analysis Functions
# ---------------------------------------------------------------------------


def compute_value_score(listing: LaptopListing) -> float:
    """
    Compute a value score (higher = better deal).

    The score considers:
    - CPU tier and generation (performance level)
    - RAM amount
    - Storage capacity and type
    - Screen size and resolution
    - Price (lower is better for same specs)
    """
    if listing.price_eur is None or listing.price_eur <= 0:
        return 0.0

    score = 0.0

    # CPU contribution (0-40 points)
    cpu_points = listing.cpu_tier * 10
    score += cpu_points

    # RAM contribution (0-20 points)
    ram_map = {4: 4, 8: 8, 12: 12, 16: 16, 24: 18, 32: 20, 48: 20, 64: 20}
    score += ram_map.get(listing.ram_gb, 0)

    # Storage contribution (0-15 points)
    if listing.storage_gb > 0:
        storage_score = min(listing.storage_gb / 100, 10)
        if listing.storage_type == "SSD":
            storage_score *= 1.5
        score += min(storage_score, 15)

    # Screen contribution (0-10 points)
    if listing.screen_size >= 15:
        score += 6
    elif listing.screen_size >= 14:
        score += 8  # Sweet spot for portability
    elif listing.screen_size >= 13:
        score += 7

    # Resolution bonus
    if listing.resolution in ("2560x1440", "2560x1600"):
        score += 5
    elif listing.resolution in ("3840x2160", "3840x2400"):
        score += 4  # 4K (slightly less because of battery)
    elif listing.resolution in ("1920x1080", "1920x1200"):
        score += 3

    # Price efficiency: score per euro
    # Higher total spec score at lower price = better value
    if score > 0:
        value = (score * 100) / listing.price_eur
    else:
        # Even without detected specs, give a base score
        value = 10 / listing.price_eur

    return round(value, 2)


def estimate_market_price(listing: LaptopListing) -> float:
    """
    Estimate the fair market price based on specs.

    This uses rough price brackets based on CPU generation and specs.
    """
    base = 0.0

    # Base price by CPU tier
    tier_base = {0: 150, 1: 250, 2: 400, 3: 600, 4: 900}
    base = tier_base.get(listing.cpu_tier, 200)

    # RAM premium
    if listing.ram_gb >= 32:
        base += 150
    elif listing.ram_gb >= 16:
        base += 80
    elif listing.ram_gb >= 8:
        base += 30

    # Storage premium
    if listing.storage_gb >= 1000:
        base += 80
    elif listing.storage_gb >= 512:
        base += 40
    elif listing.storage_gb >= 256:
        base += 20

    # SSD premium
    if listing.storage_type == "SSD":
        base += 30

    # Screen size adjustment
    if listing.screen_size >= 16:
        base += 50
    elif listing.screen_size >= 15:
        base += 30

    # Resolution premium
    if "2560" in listing.resolution or "3840" in listing.resolution:
        base += 60

    # Brand premium
    if listing.brand in ("Apple",):
        base *= 1.4
    elif listing.brand in ("Dell", "Lenovo"):
        base *= 1.1

    # Condition adjustment
    if listing.condition == "new":
        base *= 1.2
    elif listing.condition == "damaged":
        base *= 0.5

    return round(base, 2)


def analyze_best_buys(listings: list[LaptopListing]) -> pd.DataFrame:
    """
    Analyze listings and return a DataFrame sorted by value score.

    Adds value_score, estimated_market_price, price_drop_pct, and deal_rating.
    """
    for listing in listings:
        listing.value_score = compute_value_score(listing)
        listing.estimated_market_price = estimate_market_price(listing)

        # Price drop analysis: how much below estimated market price
        if listing.estimated_market_price > 0 and listing.price_eur:
            drop = (
                (listing.estimated_market_price - listing.price_eur)
                / listing.estimated_market_price
                * 100
            )
            listing.price_drop_pct = round(drop, 1)
        else:
            listing.price_drop_pct = 0.0

        # Deal rating
        if listing.price_drop_pct >= 30:
            listing.deal_rating = "STEAL"
        elif listing.price_drop_pct >= 15:
            listing.deal_rating = "GREAT"
        elif listing.price_drop_pct >= 5:
            listing.deal_rating = "GOOD"
        elif listing.price_drop_pct >= -5:
            listing.deal_rating = "FAIR"
        else:
            listing.deal_rating = "OVERPRICED"

    # Convert to DataFrame
    data = [asdict(listing) for listing in listings]
    df = pd.DataFrame(data)

    if df.empty:
        return df

    # Sort by value score descending
    df = df.sort_values("value_score", ascending=False)

    return df


def filter_recent_laptops(
    df: pd.DataFrame, max_age_years: int = 2
) -> pd.DataFrame:
    """Filter to only laptops with CPUs from the last N years."""
    if df.empty:
        return df

    # Filter by CPU generation year if available
    current_year = datetime.now().year
    cutoff_year = current_year - max_age_years

    # Keep listings with recent CPUs based on cpu_year field
    recent_mask = df["cpu_year"].apply(
        lambda year: year >= cutoff_year if year > 0 else False
    )

    # Also check listing date
    if "date_posted" in df.columns:
        date_mask = df["date_posted"].apply(
            lambda d: _is_recent_date(d, max_age_years)
        )
        combined_mask = recent_mask | date_mask
    else:
        combined_mask = recent_mask

    return df[combined_mask].copy()


def _is_recent_date(date_str: str, max_years: int) -> bool:
    """Check if a date string is within the last max_years."""
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff_days = (now - dt).days
        return diff_days <= max_years * 365
    except (ValueError, TypeError):
        return False


def generate_report(df: pd.DataFrame, output_path: str = "") -> str:
    """Generate a comprehensive analysis report."""
    lines = []
    lines.append("=" * 80)
    lines.append("  NJUSKALO.HR LAPTOP DEALS REPORT")
    lines.append(
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    lines.append("=" * 80)
    lines.append("")

    if df.empty:
        lines.append("No listings found matching the criteria.")
        report = "\n".join(lines)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
        return report

    # Summary statistics
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total listings analyzed: {len(df)}")
    lines.append(
        f"Price range: {df['price_eur'].min():.0f} - "
        f"{df['price_eur'].max():.0f} EUR"
    )
    lines.append(f"Average price: {df['price_eur'].mean():.0f} EUR")
    lines.append(f"Median price: {df['price_eur'].median():.0f} EUR")
    lines.append("")

    # Brand distribution
    lines.append("BRAND DISTRIBUTION")
    lines.append("-" * 40)
    brand_counts = df["brand"].value_counts()
    for brand, count in brand_counts.items():
        avg_price = df[df["brand"] == brand]["price_eur"].mean()
        lines.append(f"  {brand:15s}: {count:4d} listings, avg {avg_price:,.0f} EUR")
    lines.append("")

    # Deal rating distribution
    lines.append("DEAL RATINGS")
    lines.append("-" * 40)
    deal_counts = df["deal_rating"].value_counts()
    for rating in ["STEAL", "GREAT", "GOOD", "FAIR", "OVERPRICED"]:
        count = deal_counts.get(rating, 0)
        lines.append(f"  {rating:12s}: {count:4d} listings")
    lines.append("")

    # Top 20 Best Buys
    lines.append("TOP 20 BEST BUYS (highest value score)")
    lines.append("-" * 80)
    top = df.head(20)
    for idx, row in top.iterrows():
        lines.append(
            f"  [{row['deal_rating']:>10s}] {row['title'][:60]:<60s}"
        )
        specs_parts = []
        if row["cpu"]:
            specs_parts.append(f"CPU: {row['cpu']}")
        if row["ram_gb"]:
            specs_parts.append(f"RAM: {row['ram_gb']}GB")
        if row["storage_gb"]:
            specs_parts.append(
                f"Storage: {row['storage_gb']}GB {row['storage_type']}"
            )
        specs_str = " | ".join(specs_parts) if specs_parts else "Specs not detected"
        lines.append(f"    {specs_str}")
        lines.append(
            f"    Price: {row['price_eur']:,.0f} EUR | "
            f"Est. Market: {row['estimated_market_price']:,.0f} EUR | "
            f"Drop: {row['price_drop_pct']:.1f}% | "
            f"Value Score: {row['value_score']:.2f}"
        )
        lines.append(f"    URL: {row['url']}")
        lines.append("")

    # Top Steals (biggest price drops)
    steals = df[df["price_drop_pct"] > 0].sort_values(
        "price_drop_pct", ascending=False
    )
    if not steals.empty:
        lines.append("TOP 10 BIGGEST PRICE DROPS (below estimated market value)")
        lines.append("-" * 80)
        for idx, row in steals.head(10).iterrows():
            lines.append(
                f"  [{row['deal_rating']:>10s}] {row['title'][:60]:<60s}"
            )
            lines.append(
                f"    Price: {row['price_eur']:,.0f} EUR | "
                f"Est. Market: {row['estimated_market_price']:,.0f} EUR | "
                f"Savings: {row['price_drop_pct']:.1f}%"
            )
            lines.append(f"    URL: {row['url']}")
            lines.append("")

    # Budget categories
    lines.append("BEST PICKS BY BUDGET")
    lines.append("-" * 80)
    budgets = [
        ("Under 200 EUR", 0, 200),
        ("200-400 EUR", 200, 400),
        ("400-700 EUR", 400, 700),
        ("700-1000 EUR", 700, 1000),
        ("Over 1000 EUR", 1000, float("inf")),
    ]
    for label, low, high in budgets:
        budget_df = df[
            (df["price_eur"] >= low) & (df["price_eur"] < high)
        ].head(3)
        if not budget_df.empty:
            lines.append(f"\n  {label}:")
            for idx, row in budget_df.iterrows():
                lines.append(
                    f"    - {row['title'][:55]} | "
                    f"{row['price_eur']:,.0f} EUR | "
                    f"Score: {row['value_score']:.2f} | "
                    f"{row['deal_rating']}"
                )
                lines.append(f"      {row['url']}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    report = "\n".join(lines)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info("Report saved to %s", output_path)

    return report


def save_to_csv(df: pd.DataFrame, filepath: str) -> None:
    """Save the analyzed listings to CSV."""
    columns = [
        "title",
        "price_eur",
        "brand",
        "cpu",
        "cpu_gen",
        "cpu_tier",
        "cpu_year",
        "ram_gb",
        "storage_gb",
        "storage_type",
        "screen_size",
        "resolution",
        "condition",
        "value_score",
        "estimated_market_price",
        "price_drop_pct",
        "deal_rating",
        "location",
        "date_posted",
        "url",
    ]
    existing_cols = [c for c in columns if c in df.columns]
    df[existing_cols].to_csv(filepath, index=False, encoding="utf-8-sig")
    logger.info("Data saved to %s (%d rows)", filepath, len(df))


def save_to_json(df: pd.DataFrame, filepath: str) -> None:
    """Save the analyzed listings to JSON."""
    df.to_json(filepath, orient="records", indent=2, force_ascii=False)
    logger.info("Data saved to %s (%d rows)", filepath, len(df))


def main():
    parser = argparse.ArgumentParser(
        description="Njuskalo.hr Laptop Scraper & Deal Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py                          # Quick scan (3 pages/brand)
  python scraper.py --pages 10               # Deep scan
  python scraper.py --max-price 500          # Budget laptops only
  python scraper.py --brands Apple Dell      # Specific brands only
  python scraper.py --details                # Also scrape detail pages
  python scraper.py --output results.csv     # Save to CSV
  python scraper.py --json results.json      # Save to JSON
        """,
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Pages to scrape per brand category (default: 3)",
    )
    parser.add_argument(
        "--min-price",
        type=float,
        default=50,
        help="Minimum price in EUR (default: 50)",
    )
    parser.add_argument(
        "--max-price",
        type=float,
        default=5000,
        help="Maximum price in EUR (default: 5000)",
    )
    parser.add_argument(
        "--brands",
        nargs="+",
        default=None,
        help="Specific brands to scrape (e.g., --brands Apple Dell HP)",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Also scrape individual listing pages for more specs",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output CSV file path",
    )
    parser.add_argument(
        "--json",
        type=str,
        default="",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="",
        help="Output report file path (text)",
    )
    parser.add_argument(
        "--recent-only",
        action="store_true",
        help="Only show laptops with CPUs from the last 2 years",
    )

    parser.add_argument(
        "--proxy",
        type=str,
        default="",
        help="Proxy URL to bypass bot detection (e.g., http://user:pass@host:port)",
    )

    args = parser.parse_args()

    logger.info("Starting Njuskalo.hr Laptop Scraper")
    logger.info(
        "Config: pages=%d, price=%d-%d EUR, brands=%s, details=%s",
        args.pages,
        args.min_price,
        args.max_price,
        args.brands or "all",
        args.details,
    )

    # Scrape listings
    listings = scrape_all_laptops(
        pages_per_category=args.pages,
        min_price=args.min_price,
        max_price=args.max_price,
        scrape_details=args.details,
        categories=args.brands,
        proxy=args.proxy,
    )

    if not listings:
        logger.warning("No listings found. Exiting.")
        return

    # Analyze
    df = analyze_best_buys(listings)

    # Filter to recent laptops if requested
    if args.recent_only:
        df = filter_recent_laptops(df)
        logger.info("After filtering to recent CPUs: %d listings", len(df))

    # Generate and print report
    report_path = args.report or ""
    report = generate_report(df, report_path)
    print(report)

    # Save data
    if args.output:
        save_to_csv(df, args.output)
    if args.json:
        save_to_json(df, args.json)

    # Default saves if no output specified
    if not args.output and not args.json:
        default_csv = "njuskalo_laptops.csv"
        save_to_csv(df, default_csv)
        logger.info("Default CSV saved to %s", default_csv)


if __name__ == "__main__":
    main()
