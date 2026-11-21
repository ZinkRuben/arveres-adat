# MBVK Real Estate Auction Scraper & Pipeline

Data harvesting and analysis pipeline for electronic property auctions published by the Hungarian Court Bailiffs Chamber (**Magyar Bírósági Végrehajtói Kar - MBVK** - [arveres.mbvk.hu](https://arveres.mbvk.hu/)).

## 1. Overview

The scraper connects directly to the MBVK public REST API, fetching auction listings and detailed property records without requiring browser automation or HTML parsing.

### Features
- **Direct REST API Access**: Fetches JSON payloads directly from `/publicapi/auction/list` and `/publicapi/auction/detail`.
- **Property Enrichment**:
  - Cadastral Parcel Number (`parcel_number` / Helyrajzi szám)
  - Ownership Share (`ownership_share` pl. `1/1`, `1/2`)
  - Vacancy status (`move_in_ready` / Beköltözhető)
  - Eviction & tenant rights (`occupant_stay_rule`)
  - Zoning & Building Type (`zoning`, `building_type`)
  - Valuation & Bidding (`put_up_price_huf`, `min_price_huf`, `highest_bid_huf`, `down_payment_huf`)
  - Bailiff Office Contacts (`executor_name`, `executor_phone`, `executor_email`)
- **Excel-Compatible CSV**: Saved with `utf-8-sig` encoding, ensuring Hungarian characters (`á, é, ő, ű`) open properly in Excel, LibreOffice, and Pandas.
- **Multithreaded Enrichment**: Fast concurrent detail fetching with polite pacing.

---

## 2. File Structure

- `scraper.py`: Core harvesting pipeline script.
- `analyze.py`: CLI filtering and statistics exploration tool.
- `mbvk_active_real_estate.csv`: Full harvested dataset of live real estate auctions (~1,472 items).

---

## 3. Usage Examples

### A. Run the Harvester
```bash
# Scrape all active real estate auctions with full property enrichment
python3 scraper.py --enrich --workers 8 --output mbvk_active_real_estate.csv

# Harvest only the first 50 items (quick sample)
python3 scraper.py --limit 50 --enrich --output sample.csv

# Harvest continuous real estate auctions (folyamatos ingatlanok)
python3 scraper.py --type folyamatos_ingatlan --limit 200 --enrich --output folyamatos_ingatlan.csv
```

### B. Filter & Analyze the Data
```bash
# View general summary statistics
python3 analyze.py

# Filter for 1/1 ownership + move-in ready properties in Budapest
python3 analyze.py --city Budapest --full-ownership --move-in

# Filter properties under 30 million HUF and export to a new CSV
python3 analyze.py --max-price 30000000 --full-ownership --move-in --export affordable_move_in.csv
```
