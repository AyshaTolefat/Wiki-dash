from __future__ import annotations

import re
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

INP = DATA_DIR / "gender_occupation_with_isco_refined.csv"
OUT = DATA_DIR / "gender_occupation_with_isco_refined.csv"

ISCO_MAJOR_TITLES = {
    0: "Armed forces occupations",
    1: "Managers",
    2: "Professionals",
    3: "Technicians and associate professionals",
    4: "Clerical support workers",
    5: "Service and sales workers",
    6: "Skilled agricultural, forestry and fishery workers",
    7: "Craft and related trades workers",
    8: "Plant and machine operators, and assemblers",
    9: "Elementary occupations",
}

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def set_isco(df: pd.DataFrame, idx, major: int | str, sub: int | str = "", method: str = "", note: str = ""):
    if major == "":
        df.loc[idx, "isco_major_code"] = ""
        df.loc[idx, "isco_major_title"] = ""
        df.loc[idx, "isco_sub_major_code"] = ""
        df.loc[idx, "isco_sub_major_title"] = ""
    else:
        major = int(major)
        df.loc[idx, "isco_major_code"] = major
        df.loc[idx, "isco_major_title"] = ISCO_MAJOR_TITLES[major]
        if sub != "":
            sub = int(sub)
            df.loc[idx, "isco_sub_major_code"] = sub
            df.loc[idx, "isco_sub_major_title"] = ""
        else:
            df.loc[idx, "isco_sub_major_code"] = ""
            df.loc[idx, "isco_sub_major_title"] = ""

    if method:
        df.loc[idx, "isco_mapping_method"] = method
    if note:
        existing = str(df.loc[idx, "isco_mapping_notes"] or "").strip()
        df.loc[idx, "isco_mapping_notes"] = (existing + "; " + note).strip("; ").strip()

def main():
    if not INP.exists():
        raise SystemExit(f"Missing input: {INP}")

    df = pd.read_csv(INP)

    for col in ["occupationLabel", "isco_major_code", "isco_major_title", "isco_sub_major_code",
                "isco_sub_major_title", "isco_mapping_method", "isco_mapping_notes"]:
        if col not in df.columns:
            df[col] = ""

    unmapped = df["isco_mapping_method"].fillna("") == "unmapped"

    non_occ_patterns = [
        r"\b(criminal|serial killer|murderer|drug trafficker|warlord)\b",
        r"\b(political prisoner|prisoner|pensioner|housewife|homemaker)\b",
        r"\b(aristocrat|royalty|noble|princess|prince|duke|count|baron)\b",
        r"\b(first lady)\b",
    ]

    for i in df[unmapped].index:
        label = norm(df.at[i, "occupationLabel"])
        if any(re.search(p, label) for p in non_occ_patterns):
            set_isco(df, i, "", "", method="non_occupation",
                     note="Not an occupation under ISCO (status/role/crime/rank)")
            continue

        if re.search(r"\b(fisher|fisherman|fisherwoman)\b", label):
            set_isco(df, i, 6, 62, method="label_rule_refined", note="fishery worker")
            continue

        if re.search(r"\b(ship captain|captain|skipper)\b", label):
            set_isco(df, i, 8, 83, method="label_rule_refined", note="water transport captain (heuristic)")
            continue


        if re.search(r"\bfounder\b", label):
            set_isco(df, i, 1, "", method="role_heuristic", note="Founder treated as managerial role (heuristic)")
            continue

        if re.search(r"\b(celebrity|public figure|wikimedian|expert|communicator|worker)\b", label):
            df.loc[i, "isco_mapping_method"] = "ambiguous_label"
            df.loc[i, "isco_mapping_notes"] = "Label too generic to map reliably to ISCO major group"
            continue

    df.to_csv(OUT, index=False)
    print(f"Wrote: {OUT}")

    print("\nUpdated mapping_method distribution:")
    print(df["isco_mapping_method"].value_counts(dropna=False).head(20))

    print("\nRemaining unmapped examples:")
    remaining = df[df["isco_mapping_method"].isin(["unmapped", "ambiguous_label"])]
    if not remaining.empty:
        print(remaining["occupationLabel"].value_counts().head(25))

if __name__ == "__main__":
    main()
