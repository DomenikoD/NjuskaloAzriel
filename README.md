# Njuskalo Laptop Scraper & Deal Analyzer

Scrapes laptop listings from [njuskalo.hr](https://www.njuskalo.hr) (Croatia's largest classifieds site) and performs **best-buy** and **price-drop analysis** to help you find great laptops at the best prices.

## Features

- **Multi-brand scraping**: Crawls all major laptop brand categories (Acer, Asus, Apple, Dell, Fujitsu, HP, Lenovo, Sony, Toshiba, and others)
- **Smart spec extraction**: Automatically detects CPU model/generation, RAM, storage (SSD/HDD), screen size, and resolution from listing titles and descriptions
- **Value scoring**: Rates each listing based on specs-per-euro ratio
- **Market price estimation**: Estimates fair market value based on detected specs
- **Price drop analysis**: Identifies listings priced below estimated market value
- **Deal rating**: Labels each listing as STEAL / GREAT / GOOD / FAIR / OVERPRICED
- **Budget recommendations**: Best picks organized by price bracket
- **Export**: CSV, JSON, and text report output formats

## Requirements

- Python 3.10+
- Chrome/Chromium browser
- ChromeDriver (matching your Chrome version)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Quick scan (3 pages per brand, ~200-400 listings)
```bash
python scraper.py
```

### Deep scan (10 pages per brand)
```bash
python scraper.py --pages 10
```

### Budget laptops only
```bash
python scraper.py --max-price 500
```

### Specific brands
```bash
python scraper.py --brands Apple Dell HP
```

### Scrape detail pages for more specs
```bash
python scraper.py --details
```

### Filter to recent CPUs only (last 2 years)
```bash
python scraper.py --recent-only
```

### Save output
```bash
python scraper.py --output results.csv --json results.json --report report.txt
```

## How It Works

### 1. Scraping
The scraper uses Selenium (headless Chrome) to navigate njuskalo.hr laptop categories. It extracts:
- Title, price, URL, posting date, and location from listing pages
- Optionally visits individual listing pages for detailed specs (`--details` flag)

### 2. Spec Extraction
A regex-based engine detects hardware specs from listing text:
- **CPU**: Intel Core i3-i9 (8th-15th gen), AMD Ryzen 3-9, Apple M1-M5
- **RAM**: 4GB to 128GB
- **Storage**: SSD/NVMe/HDD with capacity
- **Screen**: Size in inches and resolution (FHD/QHD/4K)

### 3. Value Analysis
Each listing gets a **value score** based on:
- CPU performance tier (0-40 points)
- RAM capacity (0-20 points)
- Storage capacity and type (0-15 points)
- Screen size and resolution (0-15 points)
- All divided by price for a specs-per-euro ratio

### 4. Price Drop Detection
The analyzer estimates fair market price based on specs and compares it to the asking price. Listings priced significantly below market value are flagged as deals.

## Output

The tool generates:
1. **Console report** with summary stats, top 20 best buys, biggest price drops, and budget picks
2. **CSV file** (`njuskalo_laptops.csv` by default) with all data for further analysis
3. Optional **JSON** and **text report** files

## Legacy

This repo was originally a Telegram bot project (see `bot.py`).

## Disclaimer

This tool is for personal use only. Respect njuskalo.hr's terms of service and rate limits. The scraper includes polite delays between requests.
