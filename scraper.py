#!/usr/bin/env python3
"""
MBVK Property Auction Data Pipeline & Scraper (Magyar Bírósági Végrehajtói Kar)
Site: https://arveres.mbvk.hu/
Author: Antigravity Assistant for Ruben (University Project)
"""

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import requests
from ownership_parser import parse_ownership_share

BASE_LIST_URL = "https://arveres.mbvk.hu/publicapi/auction/list"
BASE_DETAIL_URL = "https://arveres.mbvk.hu/publicapi/auction/detail/{auction_id}/{item_id}"
BASE_LICIT_URL = "https://arveres.mbvk.hu/publicapi/auction/licit/{auction_id}/{item_id}?page=1"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
}

PHASE_CODES = {
    "normal_ingatlan": "normal_ingatlan_2021",
    "folyamatos_ingatlan": "folyamatos_ingatlan",
    "foldarveres": "folyamatos_foldarveres",
    "online_ingo": "online_ingo_2021",
    "offline_ingo": "offline_ingo",
}

# CSV Columns definition
CSV_FIELDNAMES = [
    "id",
    "auction_id",
    "case_number",
    "city",
    "zip_code",
    "location",
    "parcel_number",               # Helyrajzi szám (Hrsz)
    "ownership_share_raw",         # Nyers tulajdoni hányad (pl. 1/2+1/2=1/1, 2/2, 1/1)
    "ownership_fraction",          # Numerikus arány float-ban (pl. 1.0, 0.5, 0.25)
    "ownership_percent",           # Százalékos arány szövegként (pl. 100.0%, 50.0%)
    "is_full_ownership",           # Teljes (1/1 vagy azzal egyenértékű 100%) tulajdon-e (True/False)
    "ownership_parse_type",        # Értelmezési kategória
    "put_up_price_huf",            # Kikiáltási ár
    "min_price_huf",               # Minimálár
    "highest_bid_huf",             # Legmagasabb érvényes licit
    "bid_count",                   # Licitek száma
    "down_payment_huf",            # Árverési előleg
    "bid_step_huf",                # Licitlépcső
    "move_in_ready",               # Beköltözhető (igen/nem)
    "occupant_stay_rule",          # Lakó kötelezettség (pl. "nincs ilyen személy")
    "zoning",                      # Fekvés (belterület / külterület / zártkert)
    "building_type",               # Épület típus (lakóház / lakás / egyéb)
    "legal_nature",                # Jogi jelleg (társasház, stb.)
    "encumbrances",                # Tehermentesség / terhek
    "auction_start_date",          # Kezdet dátuma
    "auction_end_date",            # Lejárat dátuma
    "executor_name",               # Végrehajtó neve
    "executor_office",             # Végrehajtói iroda
    "executor_phone",              # Végrehajtó telefonszáma
    "executor_email",              # Végrehajtó email
    "viewing_info",                # Megtekintés információk
    "image_url",                   # Elsődleges fénykép URL
    "detail_url",                  # Közvetlen link az árveréshez a weboldalon
    "description",                 # Részletes leírás szövege
    "scraped_at",                  # Letöltés időpontja
]


def fetch_list_page(session, phase_code, offset, limit=100, retries=3):
    params = {
        "phaseCode": phase_code,
        "offset": offset,
        "limit": limit,
        "sortMod": "feltolt",
        "sortDirection": "desc",
    }
    for attempt in range(retries):
        try:
            resp = session.get(BASE_LIST_URL, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                return {"data": []}
            else:
                time.sleep(1 + attempt)
        except Exception:
            time.sleep(1 + attempt)
    return {"data": []}


def fetch_detail(session, auction_id, item_id, retries=2):
    url = BASE_DETAIL_URL.format(auction_id=auction_id, item_id=item_id)
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("data", {})
            elif resp.status_code in (400, 404):
                return {}
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    return {}


def parse_attributes(attr_list):
    """Extract standard Hungarian property attributes from the attributes array."""
    res = {
        "move_in_ready": "",
        "occupant_stay_rule": "",
        "zoning": "",
        "building_type": "",
        "legal_nature": "",
        "encumbrances": "",
    }
    if not isinstance(attr_list, list):
        return res

    for a in attr_list:
        group = a.get("attributesGroup", "")
        name = a.get("attributeName", "")
        if group == "bekoltozheto":
            res["move_in_ready"] = name
        elif group == "lakotipus":
            res["occupant_stay_rule"] = name
        elif group == "fekvestipus":
            res["zoning"] = name
        elif group == "epulettipus":
            res["building_type"] = name
        elif group == "jogijellegtipus":
            res["legal_nature"] = name
        elif group == "bejegyzettjogtipus":
            res["encumbrances"] = name

    return res


def extract_record(item_summary, detail_data=None):
    """Normalize item summary and optional detail into a clean flat record."""
    item_id = item_summary.get("id")
    auction_id = item_summary.get("auctionId")

    record = {
        "id": item_id,
        "auction_id": auction_id,
        "case_number": item_summary.get("caseNumber", ""),
        "city": item_summary.get("city", ""),
        "zip_code": "",
        "location": item_summary.get("location", ""),
        "parcel_number": "",
        "ownership_share_raw": "",
        "ownership_fraction": "",
        "ownership_percent": "",
        "is_full_ownership": False,
        "ownership_parse_type": "",
        "put_up_price_huf": float(item_summary.get("putUpPrice") or 0),
        "min_price_huf": float(item_summary.get("minPrice") or 0),
        "highest_bid_huf": item_summary.get("highestBid"),
        "bid_count": item_summary.get("bidCount", 0),
        "down_payment_huf": "",
        "bid_step_huf": "",
        "move_in_ready": "",
        "occupant_stay_rule": "",
        "zoning": "",
        "building_type": "",
        "legal_nature": "",
        "encumbrances": "",
        "auction_start_date": "",
        "auction_end_date": item_summary.get("auctionEndDate", ""),
        "executor_name": "",
        "executor_office": "",
        "executor_phone": "",
        "executor_email": "",
        "viewing_info": "",
        "image_url": item_summary.get("imageUrl", ""),
        "detail_url": f"https://arveres.mbvk.hu/arveres-reszletek/{auction_id}/{item_id}",
        "description": item_summary.get("description", "").replace("\r", " ").strip(),
        "scraped_at": datetime.now().isoformat(),
    }

    view = item_summary.get("view")
    if isinstance(view, dict):
        parts = []
        if view.get("phone"):
            parts.append(f"Tel: {view['phone']}")
        if view.get("viewAddress"):
            parts.append(f"Cím: {view['viewAddress']}")
        if view.get("note"):
            parts.append(f"Megjegyzés: {view['note']}")
        record["viewing_info"] = " | ".join(parts)

    if detail_data:
        raw_share = detail_data.get("p_tulajdonihanyad", "")
        record["ownership_share_raw"] = raw_share
        frac, pct, is_full, ptype, _ = parse_ownership_share(raw_share)
        record["ownership_fraction"] = f"{frac:.6f}" if frac is not None else ""
        record["ownership_percent"] = pct or ""
        record["is_full_ownership"] = is_full
        record["ownership_parse_type"] = ptype

        record["auction_start_date"] = detail_data.get("auctionStartDate", "")
        if detail_data.get("downPay"):
            try:
                record["down_payment_huf"] = float(detail_data["downPay"])
            except (ValueError, TypeError):
                record["down_payment_huf"] = detail_data["downPay"]
        if detail_data.get("bidStep"):
            try:
                record["bid_step_huf"] = float(detail_data["bidStep"])
            except (ValueError, TypeError):
                record["bid_step_huf"] = detail_data["bidStep"]

        addresses = detail_data.get("propertyAddress", [])
        if addresses and isinstance(addresses, list):
            addr = addresses[0]
            record["zip_code"] = addr.get("zipCode", "")
            record["parcel_number"] = addr.get("parcelNumber", "")
            if not record["location"] and addr.get("formattedAddress"):
                record["location"] = addr.get("formattedAddress")

        attrs = parse_attributes(detail_data.get("propertyAttributes", []))
        for k, v in attrs.items():
            record[k] = v

        executors = detail_data.get("executor", [])
        if executors and isinstance(executors, list):
            ex = executors[0]
            record["executor_name"] = ex.get("name", "")
            record["executor_office"] = ex.get("officeName", "")
            phone = ex.get("phone", [])
            record["executor_phone"] = ", ".join(phone) if isinstance(phone, list) else str(phone)
            email = ex.get("email", [])
            record["executor_email"] = ", ".join(email) if isinstance(email, list) else str(email)

    return record


def run_pipeline(phase_code="normal_ingatlan_2021", output_csv="mbvk_properties.csv",
                 enrich=False, max_items=None, max_workers=5):
    """Main data harvesting pipeline."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    print("=" * 60)
    print(f"Starting MBVK Auction Harvester")
    print(f"Phase Code:     {phase_code}")
    print(f"Enrich Details: {enrich} (Hrsz, ownership share, move-in, executor)")
    print(f"Output File:    {output_csv}")
    print(f"Max Items:      {max_items or 'All available'}")
    print("=" * 60)

    first_page = fetch_list_page(session, phase_code, offset=0, limit=100)
    data = first_page.get("data", [])
    if not data:
        print("[!] No listings returned by API.")
        return

    total_available = data[0].get("itemNumber", len(data))
    target_count = min(total_available, max_items) if max_items else total_available
    print(f"[*] Total active auctions reported by server: {total_available}")
    print(f"[*] Target items to harvest: {target_count}")

    all_summaries = list(data)
    offset = 100

    while len(all_summaries) < target_count:
        batch_limit = min(100, target_count - len(all_summaries))
        sys.stdout.write(f"\r[*] Fetching listings summary: {len(all_summaries)} / {target_count} ({len(all_summaries)/target_count*100:.1f}%)")
        sys.stdout.flush()

        res = fetch_list_page(session, phase_code, offset=offset, limit=batch_limit)
        batch = res.get("data", [])
        if not batch:
            break
        all_summaries.extend(batch)
        offset += len(batch)
        time.sleep(0.3)

    all_summaries = all_summaries[:target_count]
    print(f"\r[*] Fetched all {len(all_summaries)} listing summaries successfully!                ")

    details_map = {}
    if enrich:
        print(f"[*] Enriching {len(all_summaries)} items with full details (Hrsz, ownership share, etc.)...")
        print(f"    Using {max_workers} concurrent threads...")
        
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(fetch_detail, session, it.get("auctionId"), it.get("id")): (it.get("auctionId"), it.get("id"))
                for it in all_summaries
            }

            for future in as_completed(future_to_item):
                auction_id, item_id = future_to_item[future]
                try:
                    det = future.result()
                    if det:
                        details_map[(auction_id, item_id)] = det
                except Exception:
                    pass

                completed += 1
                if completed % 25 == 0 or completed == len(all_summaries):
                    sys.stdout.write(f"\r[*] Enriched: {completed} / {len(all_summaries)} ({completed/len(all_summaries)*100:.1f}%)")
                    sys.stdout.flush()

        print(f"\n[*] Detail enrichment complete ({len(details_map)} records enriched).")

    print(f"[*] Writing data to {output_csv}...")
    with open(output_csv, mode="w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()

        for summary in all_summaries:
            key = (summary.get("auctionId"), summary.get("id"))
            detail = details_map.get(key)
            row = extract_record(summary, detail)
            writer.writerow(row)

    file_size_kb = os.path.getsize(output_csv) / 1024
    print("=" * 60)
    print(f"[✓] Pipeline finished successfully!")
    print(f"[✓] File: {output_csv} ({file_size_kb:.1f} KB, {len(all_summaries)} rows)")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="MBVK Property Auction Data Harvester (Hungarian Bailiff Auctions)"
    )
    parser.add_argument(
        "--type",
        choices=list(PHASE_CODES.keys()),
        default="normal_ingatlan",
        help="Type of auctions: normal_ingatlan (default, active property), folyamatos_ingatlan, foldarveres, online_ingo"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Fetch full individual property details (parcel number / Hrsz, ownership share, move-in status, executor info)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of items to harvest (default: all)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="mbvk_properties.csv",
        help="Output CSV file path (default: mbvk_properties.csv)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Worker threads for detail enrichment (default: 5)"
    )

    args = parser.parse_args()
    phase_code = PHASE_CODES[args.type]

    run_pipeline(
        phase_code=phase_code,
        output_csv=args.output,
        enrich=args.enrich,
        max_items=args.limit,
        max_workers=args.workers
    )


if __name__ == "__main__":
    main()
