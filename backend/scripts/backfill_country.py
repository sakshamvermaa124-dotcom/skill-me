"""
Fill students.country for applications made before the apply form asked for it.

  python scripts/backfill_country.py            # dry run: prints every guess, writes nothing
  python scripts/backfill_country.py --apply    # writes country + country_source

Only rows with no country are touched, so a country an applicant picked themselves is never
overwritten and re-running is safe. Each guess records where it came from in country_source:
'phone' (dialling code, or a bare Indian mobile number) or 'college' (a city, region or
institution in the college name). Rows that give no clear signal stay NULL and are listed.
"""
import argparse
import asyncio
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import db  # noqa: E402
from services.countries import country_name, infer_country  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        rows = await db.fetch_all(
            "SELECT id, phone, college FROM students WHERE country IS NULL OR country = '' ORDER BY id"
        )
    except Exception as e:
        if "country" not in str(e).lower():
            raise
        # The column arrives with the next deploy's migration. A dry run stays read-only;
        # --apply adds just these two columns (the same statements the migration runs).
        if args.apply:
            for stmt in ("ALTER TABLE students ADD COLUMN country TEXT",
                         "ALTER TABLE students ADD COLUMN country_source TEXT"):
                await db.execute(stmt)
            print("Added students.country / country_source.")
        rows = await db.fetch_all("SELECT id, phone, college FROM students ORDER BY id")
    if not rows:
        print("Every application already has a country.")
        return

    guesses, unknown = [], []
    for r in rows:
        iso, source = infer_country(r["phone"], r["college"])
        (guesses if iso else unknown).append((r, iso, source))

    by_country = collections.Counter(iso for _, iso, _ in guesses)
    by_source = collections.Counter(src for _, _, src in guesses)
    print(f"{'APPLYING' if args.apply else 'DRY RUN'}: {len(rows)} application(s) without a country")
    print(f"  resolved {len(guesses)} ({by_source['phone']} from phone, {by_source['college']} from college), "
          f"unresolved {len(unknown)}\n")
    for iso, n in by_country.most_common():
        print(f"  {n:>4}  {iso}  {country_name(iso)}")

    college_guesses = [g for g in guesses if g[2] == "college"]
    if college_guesses:
        print("\nFrom college name (check these):")
        for r, iso, _ in college_guesses:
            print(f"  #{r['id']:<5} {iso}  phone={r['phone']!r:<22} college={r['college']!r}")
    if unknown:
        print("\nNo clear signal (left empty):")
        for r, _, _ in unknown:
            print(f"  #{r['id']:<5} phone={r['phone']!r:<22} college={r['college']!r}")

    if not args.apply:
        print("\nRe-run with --apply to write.")
        return

    for r, iso, source in guesses:
        await db.execute(
            "UPDATE students SET country = ?, country_source = ? WHERE id = ? AND (country IS NULL OR country = '')",
            (iso, source, r["id"]),
        )
    print(f"\nDone: {len(guesses)} row(s) updated.")


if __name__ == "__main__":
    asyncio.run(main())
