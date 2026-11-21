#!/usr/bin/env python3
"""
MBVK Property Analysis and Filtering Helper
Load mbvk_active_real_estate.csv and run custom queries or export filtered datasets.
"""

import csv
import argparse
from collections import Counter


def load_dataset(csv_path="mbvk_active_real_estate.csv"):
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def print_summary(rows):
    print("=" * 65)
    print(f"Dataset Summary: {len(rows)} properties loaded")
    print("=" * 65)

    cities = Counter(r["city"] for r in rows if r["city"])
    print("\nTop 10 Cities:")
    for city, count in cities.most_common(10):
        print(f"  - {city:20}: {count} properties")

    full_count = sum(1 for r in rows if str(r.get("is_full_ownership")).lower() in ("true", "1"))
    print(f"\nOwnership Distribution:")
    print(f"  - Full (100%) Ownership : {full_count} properties ({full_count/len(rows)*100:.1f}%)" if rows else 0)
    print(f"  - Fractional Ownership   : {len(rows) - full_count} properties ({(len(rows)-full_count)/len(rows)*100:.1f}%)" if rows else 0)

    pct_shares = Counter(r.get("ownership_percent", "") for r in rows if r.get("ownership_percent"))
    print("\nTop Ownership Percentages:")
    for pct, count in pct_shares.most_common(6):
        print(f"  - {pct:20}: {count}")

    move_in = Counter(r.get("move_in_ready", "") for r in rows if r.get("move_in_ready"))
    print("\nMove-In Ready (Beköltözhető):")
    for status, count in move_in.items():
        print(f"  - {status:20}: {count}")

    prices = [float(r["put_up_price_huf"]) for r in rows if r.get("put_up_price_huf")]
    if prices:
        prices.sort()
        median_price = prices[len(prices) // 2]
        avg_price = sum(prices) / len(prices)
        print(f"\nPrice Statistics (HUF):")
        print(f"  - Min Price:        {min(prices):>15,.0f} Ft")
        print(f"  - Median Price:     {median_price:>15,.0f} Ft")
        print(f"  - Average Price:    {avg_price:>15,.0f} Ft")
        print(f"  - Max Price:        {max(prices):>15,.0f} Ft")


def filter_dataset(rows, city=None, max_price=None, min_share=None, only_full_ownership=False,
                   only_move_in=False, only_unencumbered=False):
    filtered = []
    for r in rows:
        if city and city.lower() not in r["city"].lower() and city.lower() not in r["location"].lower():
            continue
        if max_price:
            price = float(r.get("put_up_price_huf") or 0)
            if price > max_price:
                continue
        if only_full_ownership:
            is_full = str(r.get("is_full_ownership", "")).lower() in ("true", "1")
            if not is_full:
                continue
        if min_share is not None:
            frac = float(r.get("ownership_fraction") or 0)
            if frac < min_share:
                continue
        if only_move_in and r.get("move_in_ready") != "igen":
            continue
        if only_unencumbered and "tehermentes" not in r.get("encumbrances", "").lower():
            continue
        filtered.append(r)
    return filtered


def export_csv(rows, output_path):
    if not rows:
        print("[!] No rows to export.")
        return
    with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[✓] Exported {len(rows)} rows to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze and filter MBVK scraped properties")
    parser.add_argument("--csv", default="mbvk_active_real_estate.csv", help="Input CSV path")
    parser.add_argument("--city", help="Filter by city/settlement (e.g. Budapest, Szeged, Debrecen)")
    parser.add_argument("--max-price", type=float, help="Max appraised price in HUF")
    parser.add_argument("--min-share", type=float, help="Minimum ownership share (e.g. 0.5 for >=50 percent, 1.0 for 100 percent)")
    parser.add_argument("--full-ownership", action="store_true", help="Only 100 percent full ownership (including 1/1, 2/2, 1/2+1/2, etc.)")
    parser.add_argument("--move-in", action="store_true", help="Only move-in ready (beköltözhető)")
    parser.add_argument("--tehermentes", action="store_true", help="Only unencumbered properties")
    parser.add_argument("--export", help="Export filtered rows to a new CSV file")
    args = parser.parse_args()

    rows = load_dataset(args.csv)

    if args.city or args.max_price or args.min_share or args.full_ownership or args.move_in or args.tehermentes:
        filtered = filter_dataset(
            rows,
            city=args.city,
            max_price=args.max_price,
            min_share=args.min_share,
            only_full_ownership=args.full_ownership,
            only_move_in=args.move_in,
            only_unencumbered=args.tehermentes
        )
        print_summary(filtered)
        if args.export:
            export_csv(filtered, args.export)
    else:
        print_summary(rows)


if __name__ == "__main__":
    main()
