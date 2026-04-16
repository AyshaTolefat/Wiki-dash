from __future__ import annotations

import re
import pandas as pd

QID_RE = re.compile(r"^Q\d+$", re.IGNORECASE)

BAD_TEXT = {
    "",
    "nan",
    "none",
    "null",
    "not stated",
}

def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()

def is_qid(value) -> bool:
    s = clean_text(value)
    return bool(QID_RE.fullmatch(s))

def normalise_unknown(value: str, unknown_label: str) -> str:
    s = clean_text(value)
    if s.lower() in BAD_TEXT:
        return unknown_label
    return s

def load_qid_label_map(path: str) -> dict[str, str]:
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}

    if "qid" not in df.columns or "label" not in df.columns:
        return {}

    out = {}
    for _, row in df.iterrows():
        qid = clean_text(row["qid"])
        label = clean_text(row["label"])
        if qid and label:
            out[qid] = label
    return out

def resolve_label(value, label_map: dict[str, str], unknown_label: str) -> str:
    s = clean_text(value)

    if not s:
        return unknown_label

    if s in label_map and label_map[s].strip():
        return label_map[s].strip()

    if is_qid(s):
        return unknown_label

    return normalise_unknown(s, unknown_label)