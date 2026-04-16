from __future__ import annotations

import re
import time
import requests
import pandas as pd
from pathlib import Path

QID_RE = re.compile(r"^Q\d+$", re.IGNORECASE)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

LANG_PATH = DATA_DIR / "languages_by_country.csv"
ETHNIC_PATH = DATA_DIR / "ethnic_group_by_country_gender.csv"
OUT_PATH = DATA_DIR / "wikidata_qid_labels.csv"

HEADERS = {
    "User-Agent": "WikiDashboardLabelResolver/1.0 (research project; contact: aysha.tolefat@kcl.ac.uk)"
}


def is_qid(value) -> bool:
    if pd.isna(value):
        return False
    return bool(QID_RE.fullmatch(str(value).strip()))


def collect_qids() -> list[str]:
    qids = set()

    if LANG_PATH.exists():
        lang = pd.read_csv(LANG_PATH)

        if "languageLabel" in lang.columns:
            for v in lang["languageLabel"]:
                if is_qid(v):
                    qids.add(str(v).strip())

        if "language" in lang.columns:
            for v in lang["language"]:
                if pd.notna(v):
                    s = str(v).strip()
                    if "/Q" in s:
                        qid = s.rsplit("/", 1)[-1].strip()
                        if is_qid(qid):
                            qids.add(qid)

    if ETHNIC_PATH.exists():
        eth = pd.read_csv(ETHNIC_PATH)

        if "ethnicGroupLabel" in eth.columns:
            for v in eth["ethnicGroupLabel"]:
                if is_qid(v):
                    qids.add(str(v).strip())

        if "ethnicGroup" in eth.columns:
            for v in eth["ethnicGroup"]:
                if pd.notna(v):
                    s = str(v).strip()
                    if "/Q" in s:
                        qid = s.rsplit("/", 1)[-1].strip()
                        if is_qid(qid):
                            qids.add(qid)

    return sorted(qids)


def fetch_one_label(session: requests.Session, qid: str) -> str:
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

        entity = data.get("entities", {}).get(qid, {})
        labels = entity.get("labels", {})

        if "en" in labels and labels["en"].get("value"):
            return labels["en"]["value"].strip()

        for _, v in labels.items():
            if isinstance(v, dict) and v.get("value"):
                return str(v["value"]).strip()

        return ""

    except Exception as e:
        print(f"Failed for {qid}: {e}")
        return ""


def main():
    qids = collect_qids()
    print(f"Found {len(qids)} QIDs")

    session = requests.Session()
    session.headers.update(HEADERS)

    rows = []
    for i, qid in enumerate(qids, start=1):
        label = fetch_one_label(session, qid)
        rows.append({"qid": qid, "label": label})
        print(f"[{i}/{len(qids)}] {qid} -> {label if label else '(blank)'}")
        time.sleep(0.25)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_PATH, index=False)
    print(f"Saved label map to {OUT_PATH}")


if __name__ == "__main__":
    main()