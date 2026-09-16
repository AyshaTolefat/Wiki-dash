from __future__ import annotations

import argparse
import bz2
import gzip
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
DATA_DIR = BASE_DIR / "data"
DUMPS_DIR = DATA_DIR / "dumps"
DUMP_OUTPUTS_DIR = DATA_DIR / "dump_outputs"
DEFAULT_DUMP_URL = "https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.gz"

ALLOWED_COUNTRIES_PATH = DATA_DIR / "allowed_countries_qids.csv"
MISSING_QIDS_PATH = DATA_DIR / "missing_iso3_to_qid.csv"
SPECIAL_TERRITORY_QIDS = {"Q1246", "Q23681", "Q34754"} 

GEO_DB_PATH = DUMP_OUTPUTS_DIR / "geo_edges.sqlite"
PEOPLE_CACHE_PATH = DUMP_OUTPUTS_DIR / "people_raw.jsonl.gz"
NEEDED_OCCUPATIONS_PATH = DUMP_OUTPUTS_DIR / "needed_occupation_qids.txt"
OCCUPATION_LABEL_CACHE_PATH = DATA_DIR / "occupation_labels_cache.csv"
RAW_OUTPUT_PATH = DATA_DIR / "gender_occupation_raw_long.csv"
FINAL_OUTPUT_PATH = DATA_DIR / "gender_occupation_with_isco_refined.csv"

REFINE_SCRIPTS = ["refine_occupations.py", "refine_map_to_isco.py"]

REFINED_SCHEMA = [
    "country_qid", "country",
    "occupation_qid", "occupation",
    "genderCategory", "count",
    "occupationLabel",
    "sector", "sector_source",
    "isco_major_code", "isco_major_title",
    "isco_sub_major_code", "isco_sub_major_title",
    "isco_mapping_method", "isco_mapping_notes",
]

GENDER_MALE_QIDS = {"Q6581097", "Q2449503"}
GENDER_FEMALE_QIDS = {"Q6581072", "Q1052281"}

MIN_BIRTH_YEAR_DEFAULT = 1900
HTTP_HEADERS = {
    "User-Agent": "Wiki-dashboard/1.0 (occupation refresh; research project)"
}

QID_IN_LINE_RE = re.compile(r'"id"\s*:\s*"(Q\d+)"')
TIME_YEAR_RE = re.compile(r"^([+-]\d+)-\d{2}-\d{2}T")

def qid_from_uri(uri: str) -> str:
    return str(uri).rsplit("/", 1)[-1].strip()


def load_allowed_country_qids() -> set[str]:
    qids: set[str] = set(SPECIAL_TERRITORY_QIDS)

    if ALLOWED_COUNTRIES_PATH.exists():
        df = pd.read_csv(ALLOWED_COUNTRIES_PATH)
        if "country" in df.columns:
            qids.update(qid_from_uri(v) for v in df["country"].dropna())

    if MISSING_QIDS_PATH.exists():
        df = pd.read_csv(MISSING_QIDS_PATH)
        if "qid" in df.columns:
            qids.update(str(v).strip() for v in df["qid"].dropna())

    qids = {q for q in qids if re.fullmatch(r"Q\d+", q or "")}
    return qids

def download_dump(url: str, dest_path: Path, chunk_size: int = 1 << 20) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    resume_from = dest_path.stat().st_size if dest_path.exists() else 0
    headers = dict(HTTP_HEADERS)
    mode = "wb"

    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
        mode = "ab"
        print(f"Resuming download from byte {resume_from:,}")

    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        if resume_from and r.status_code == 200:
            print("Server did not honour resume request; restarting download.")
            resume_from = 0
            mode = "wb"
        elif r.status_code not in (200, 206):
            r.raise_for_status()

        total = r.headers.get("Content-Length")
        total = int(total) + resume_from if total else None

        written = resume_from
        last_report = time.time()
        start = time.time()

        with open(dest_path, mode) as fh:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                written += len(chunk)

                now = time.time()
                if now - last_report >= 5:
                    elapsed = now - start
                    rate = (written - resume_from) / elapsed if elapsed > 0 else 0
                    pct = f"{written / total * 100:5.1f}%" if total else "?"
                    print(
                        f"  downloaded {written / (1 << 30):.2f} GiB "
                        f"({pct}) at {rate / (1 << 20):.1f} MiB/s"
                    )
                    last_report = now

    print(f"Download complete: {dest_path} ({dest_path.stat().st_size / (1 << 30):.2f} GiB)")

def open_dump_text(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    if suffix == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "rt", encoding="utf-8", errors="replace")


def iter_dump_lines(path: Path) -> Iterator[str]:
    with open_dump_text(path) as fh:
        it = iter(fh)
        while True:
            try:
                line = next(it)
            except StopIteration:
                return
            except (EOFError, OSError) as exc:
                print(f"  warning: dump stream ended unexpectedly, stopping early ({exc})")
                return

            line = line.strip()
            if not line or line in ("[", "]"):
                continue
            if line.endswith(","):
                line = line[:-1]
            if line:
                yield line


def iter_dump_entities(path: Path, limit: int | None = None) -> Iterator[dict]:
    count = 0
    for line in iter_dump_lines(path):
        try:
            entity = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield entity
        count += 1
        if limit is not None and count >= limit:
            return


def progress(prefix: str, count: int, start_time: float, every: int = 500_000) -> None:
    if count % every == 0:
        elapsed = time.time() - start_time
        rate = count / elapsed if elapsed > 0 else 0
        print(f"  [{prefix}] {count:,} entities scanned ({rate:,.0f}/s)")

def _truthy_claims(claims: dict, prop: str) -> list[dict]:
    prop_claims = claims.get(prop, [])
    preferred = [c for c in prop_claims if c.get("rank") == "preferred"]
    if preferred:
        return preferred
    return [c for c in prop_claims if c.get("rank", "normal") == "normal"]


def iter_claim_qids(claims: dict, prop: str) -> Iterator[str]:
    for claim in _truthy_claims(claims, prop):
        mainsnak = claim.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        datavalue = mainsnak.get("datavalue", {})
        if datavalue.get("type") != "wikibase-entityid":
            continue
        qid = datavalue.get("value", {}).get("id")
        if qid:
            yield qid


def first_claim_qid(claims: dict, prop: str) -> str | None:
    return next(iter_claim_qids(claims, prop), None)


def extract_birth_year(claims: dict) -> int | None:
    for claim in _truthy_claims(claims, "P569"):
        mainsnak = claim.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        datavalue = mainsnak.get("datavalue", {})
        if datavalue.get("type") != "time":
            continue
        value = datavalue.get("value", {})
        if value.get("precision", 0) < 9:
            continue
        m = TIME_YEAR_RE.match(value.get("time", ""))
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def gender_category(gender_qid: str | None) -> str:
    if gender_qid is None:
        return "Unknown / not stated"
    if gender_qid in GENDER_MALE_QIDS:
        return "Male"
    if gender_qid in GENDER_FEMALE_QIDS:
        return "Female"
    return "Non-binary or other"

def stage_extract(
    dump_path: Path,
    geo_db_path: Path,
    people_cache_path: Path,
    needed_occupations_path: Path,
    min_birth_year: int,
    limit: int | None,
    batch_size: int = 50_000,
) -> None:
    geo_db_path.parent.mkdir(parents=True, exist_ok=True)
    people_cache_path.parent.mkdir(parents=True, exist_ok=True)

    if geo_db_path.exists():
        geo_db_path.unlink()

    conn = sqlite3.connect(geo_db_path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(
        "CREATE TABLE geo_edges (qid TEXT PRIMARY KEY, p131 TEXT, p17 TEXT)"
    )
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")

    needed_occupations: set[str] = set()
    geo_batch: list[tuple[str, str | None, str | None]] = []
    people_written = 0
    start = time.time()

    with gzip.open(people_cache_path, "wt", encoding="utf-8") as people_out:
        for count, entity in enumerate(iter_dump_entities(dump_path, limit=limit), start=1):
            progress("extract", count, start)

            if entity.get("type") != "item":
                continue

            claims = entity.get("claims", {})
            if not claims:
                continue

            p131 = first_claim_qid(claims, "P131")
            p17 = first_claim_qid(claims, "P17")
            if p131 or p17:
                geo_batch.append((entity.get("id"), p131, p17))
                if len(geo_batch) >= batch_size:
                    conn.executemany(
                        "INSERT OR REPLACE INTO geo_edges (qid, p131, p17) VALUES (?, ?, ?)",
                        geo_batch,
                    )
                    geo_batch.clear()

            p31 = set(iter_claim_qids(claims, "P31"))
            if "Q5" not in p31:
                continue

            birthplace = first_claim_qid(claims, "P19")
            if birthplace is None:
                continue

            occ_qids = list(dict.fromkeys(iter_claim_qids(claims, "P106")))
            if not occ_qids:
                continue

            birth_year = extract_birth_year(claims)
            if birth_year is not None and birth_year < min_birth_year:
                continue

            gender_qid = first_claim_qid(claims, "P21")
            record = {
                "b": birthplace,
                "o": occ_qids,
                "g": gender_category(gender_qid),
            }
            people_out.write(json.dumps(record, separators=(",", ":")) + "\n")
            people_written += 1
            needed_occupations.update(occ_qids)

        if geo_batch:
            conn.executemany(
                "INSERT OR REPLACE INTO geo_edges (qid, p131, p17) VALUES (?, ?, ?)",
                geo_batch,
            )

    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('status', 'complete')"
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('source_dump', ?)",
        (str(dump_path),),
    )
    conn.commit()
    conn.close()

    needed_occupations_path.parent.mkdir(parents=True, exist_ok=True)
    needed_occupations_path.write_text(
        "\n".join(sorted(needed_occupations)), encoding="utf-8"
    )

    elapsed = time.time() - start
    print(
        f"Extract stage complete in {elapsed / 60:.1f} min: "
        f"{people_written:,} people written, "
        f"{len(needed_occupations):,} distinct occupation QIDs, "
        f"geo edges db at {geo_db_path}"
    )


def geo_pass_is_complete(geo_db_path: Path) -> bool:
    if not geo_db_path.exists():
        return False
    try:
        conn = sqlite3.connect(geo_db_path)
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'status'"
        ).fetchone()
        conn.close()
        return bool(row and row[0] == "complete")
    except sqlite3.Error:
        return False

def load_label_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    return dict(zip(df["qid"], df["label"]))


def save_label_cache(path: Path, labels: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(sorted(labels.items()), columns=["qid", "label"])
    out.to_csv(path, index=False)


def entity_english_label(entity: dict) -> str:
    labels = entity.get("labels", {})
    if "en" in labels and labels["en"].get("value"):
        return str(labels["en"]["value"]).strip()
    for lang in ("en-gb", "en-ca", "en-us", "mul"):
        if lang in labels and labels[lang].get("value"):
            return str(labels[lang]["value"]).strip()
    for v in labels.values():
        if isinstance(v, dict) and v.get("value"):
            return str(v["value"]).strip()
    return ""


def stage_labels(
    dump_path: Path,
    needed_occupations_path: Path,
    cache_path: Path,
    limit: int | None,
) -> dict[str, str]:
    if not needed_occupations_path.exists():
        raise FileNotFoundError(
            f"{needed_occupations_path} not found; run the extract stage first."
        )

    needed = set(
        needed_occupations_path.read_text(encoding="utf-8").splitlines()
    )
    needed.discard("")

    cache = load_label_cache(cache_path)
    remaining = needed - set(cache.keys())

    print(f"Resolving labels for {len(remaining):,} occupation QIDs "
          f"({len(cache):,} already cached)")

    if remaining:
        start = time.time()
        found = 0

        for count, line in enumerate(iter_dump_lines(dump_path), start=1):
            progress("labels", count, start)

            m = QID_IN_LINE_RE.search(line[:120])
            if not m or m.group(1) not in remaining:
                continue

            try:
                entity = json.loads(line)
            except json.JSONDecodeError:
                continue

            qid = entity.get("id")
            if qid not in remaining:
                continue

            label = entity_english_label(entity)
            cache[qid] = label
            remaining.discard(qid)
            found += 1

            if not remaining:
                break

            if limit is not None and count >= limit:
                break

        print(f"Resolved {found:,} labels this pass; {len(remaining):,} still unresolved.")

    save_label_cache(cache_path, cache)
    return cache

def resolve_country(
    birthplace: str,
    conn: sqlite3.Connection,
    allowed: set[str],
    cache: dict[str, str | None],
    max_hops: int = 15,
) -> str | None:
    if birthplace in cache:
        return cache[birthplace]

    visited: list[str] = []
    current = birthplace
    result: str | None = None

    for _ in range(max_hops):
        if current in cache:
            result = cache[current]
            break

        if current in allowed:
            result = current
            break

        visited.append(current)
        row = conn.execute(
            "SELECT p131, p17 FROM geo_edges WHERE qid = ?", (current,)
        ).fetchone()

        if row is None:
            result = None
            break

        p131, p17 = row

        if p17 and p17 in allowed:
            result = p17
            break

        if p17 and p17 not in visited:
            current = p17
            continue

        if p131 and p131 not in visited:
            current = p131
            continue

        result = None
        break

    for qid in visited:
        cache[qid] = result
    cache[birthplace] = result
    return result


def stage_aggregate(
    people_cache_path: Path,
    geo_db_path: Path,
    labels: dict[str, str],
    allowed_countries: set[str],
    max_hops: int,
) -> pd.DataFrame:
    conn = sqlite3.connect(geo_db_path)
    country_cache: dict[str, str | None] = {}
    counts: Counter[tuple[str, str, str]] = Counter()

    start = time.time()
    people_total = 0
    unresolved = 0

    with gzip.open(people_cache_path, "rt", encoding="utf-8") as fh:
        for count, line in enumerate(fh, start=1):
            progress("aggregate", count, start, every=1_000_000)

            record = json.loads(line)
            country_qid = resolve_country(
                record["b"], conn, allowed_countries, country_cache, max_hops
            )
            people_total += 1

            if country_qid is None:
                unresolved += 1
                continue

            gender = record["g"]
            for occ_qid in record["o"]:
                counts[(country_qid, occ_qid, gender)] += 1

    conn.close()

    print(
        f"Aggregated {people_total:,} people "
        f"({unresolved:,} could not be resolved to an allowed country)"
    )

    rows = []
    for (country_qid, occ_qid, gender), n in counts.items():
        rows.append({
            "country_qid": country_qid,
            "country": f"http://www.wikidata.org/entity/{country_qid}",
            "occupation_qid": occ_qid,
            "occupation": f"http://www.wikidata.org/entity/{occ_qid}",
            "genderCategory": gender,
            "count": n,
            "occupationLabel": labels.get(occ_qid, occ_qid),
            "sector": "",
            "sector_source": "",
            "isco_major_code": "",
            "isco_major_title": "",
            "isco_sub_major_code": "",
            "isco_sub_major_title": "",
            "isco_mapping_method": "",
            "isco_mapping_notes": "",
        })

    df = pd.DataFrame(rows, columns=REFINED_SCHEMA)
    df = df.sort_values(["country_qid", "occupation_qid", "genderCategory"]).reset_index(drop=True)
    return df

def run_script(filename: str) -> None:
    script_path = SCRIPTS_DIR / filename
    if not script_path.exists():
        raise FileNotFoundError(f"Required script does not exist: {script_path}")

    print(f"\nRunning existing script: {filename}")
    result = subprocess.run([sys.executable, str(script_path)], cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise RuntimeError(f"{filename} failed with exit code {result.returncode}.")


def stage_apply(raw_output_path: Path, final_output_path: Path, run_refine: bool) -> None:
    if final_output_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = final_output_path.with_name(
            f"{final_output_path.stem}.backup-{stamp}{final_output_path.suffix}"
        )
        shutil.copy2(final_output_path, backup_path)
        print(f"Backed up existing dataset to {backup_path}")

    shutil.copy2(raw_output_path, final_output_path)
    print(f"Wrote raw aggregated data to {final_output_path}")

    if run_refine:
        for filename in REFINE_SCRIPTS:
            run_script(filename)

    df = pd.read_csv(final_output_path)
    missing_cols = [c for c in REFINED_SCHEMA if c not in df.columns]
    if missing_cols:
        raise RuntimeError(f"Final output is missing expected columns: {missing_cols}")

    print(f"\nFinal dataset: {len(df):,} rows, "
          f"{df['country_qid'].nunique():,} countries, "
          f"{df['occupation_qid'].nunique():,} occupations")
    print(df["isco_mapping_method"].value_counts(dropna=False).head(10))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconstructed first stage: rebuild the occupation dataset from a Wikidata JSON dump."
    )
    parser.add_argument("--dump-url", default=DEFAULT_DUMP_URL)
    parser.add_argument("--dump-path", default=str(DUMPS_DIR / "latest-all.json.gz"))
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-extract", action="store_true",
                         help="Reuse an existing geo-edges DB / people cache from a prior run.")
    parser.add_argument("--skip-labels", action="store_true",
                         help="Reuse the existing occupation label cache as-is.")
    parser.add_argument("--skip-aggregate", action="store_true",
                         help="Reuse an existing raw output CSV from a prior run.")
    parser.add_argument("--apply", action="store_true",
                         help="Back up and replace data/gender_occupation_with_isco_refined.csv, "
                              "then run the existing refinement scripts. Without this flag, "
                              "output is written to staging files only.")
    parser.add_argument("--skip-refine", action="store_true",
                         help="With --apply, replace the tracked file but don't run the refinement scripts.")
    parser.add_argument("--min-birth-year", type=int, default=MIN_BIRTH_YEAR_DEFAULT)
    parser.add_argument("--max-hops", type=int, default=15,
                         help="Max P131 hops when resolving a birthplace to a country.")
    parser.add_argument("--limit", type=int, default=None,
                         help="Only process the first N dump entities (for testing).")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print the resolved plan and exit without touching the network or dump.")
    args = parser.parse_args()

    dump_path = Path(args.dump_path)
    allowed_countries = load_allowed_country_qids()

    print("Occupation refresh plan:")
    print(f"  dump url        : {args.dump_url}")
    print(f"  dump path       : {dump_path}")
    print(f"  geo edges db    : {GEO_DB_PATH}")
    print(f"  people cache    : {PEOPLE_CACHE_PATH}")
    print(f"  label cache     : {OCCUPATION_LABEL_CACHE_PATH}")
    print(f"  raw output      : {RAW_OUTPUT_PATH}")
    print(f"  final output    : {FINAL_OUTPUT_PATH}")
    print(f"  allowed countries: {len(allowed_countries)}")
    print(f"  apply           : {args.apply}")

    if args.dry_run:
        print("\nDRY RUN - no network access or dump processing performed.")
        return

    if not args.skip_download:
        download_dump(args.dump_url, dump_path)
    elif not dump_path.exists():
        raise FileNotFoundError(
            f"--skip-download was passed but {dump_path} does not exist."
        )

    if not args.skip_extract:
        stage_extract(
            dump_path,
            GEO_DB_PATH,
            PEOPLE_CACHE_PATH,
            NEEDED_OCCUPATIONS_PATH,
            min_birth_year=args.min_birth_year,
            limit=args.limit,
        )
    elif not geo_pass_is_complete(GEO_DB_PATH):
        raise RuntimeError(
            "--skip-extract was passed but the geo-edges DB is missing or incomplete."
        )

    if not args.skip_labels:
        labels = stage_labels(
            dump_path, NEEDED_OCCUPATIONS_PATH, OCCUPATION_LABEL_CACHE_PATH, limit=args.limit
        )
    else:
        labels = load_label_cache(OCCUPATION_LABEL_CACHE_PATH)

    if not args.skip_aggregate:
        df = stage_aggregate(
            PEOPLE_CACHE_PATH, GEO_DB_PATH, labels, allowed_countries, args.max_hops
        )
        RAW_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(RAW_OUTPUT_PATH, index=False, encoding="utf-8")
        print(f"Wrote raw aggregated occupation data to {RAW_OUTPUT_PATH} ({len(df):,} rows)")
    elif not RAW_OUTPUT_PATH.exists():
        raise RuntimeError(
            "--skip-aggregate was passed but the raw output CSV is missing."
        )

    if args.apply:
        stage_apply(RAW_OUTPUT_PATH, FINAL_OUTPUT_PATH, run_refine=not args.skip_refine)
    else:
        print(
            "\n--apply not set: the tracked dataset was left untouched.\n"
            f"Review {RAW_OUTPUT_PATH} and re-run with --apply "
            "(add --skip-download --skip-extract --skip-labels --skip-aggregate "
            "to reuse everything already computed) to replace "
            f"{FINAL_OUTPUT_PATH} and run the existing refinement scripts."
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        sys.exit(130)
