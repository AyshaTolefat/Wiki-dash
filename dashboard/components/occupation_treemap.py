import numpy as np
import pandas as pd
import plotly.express as px


def _safe_series(df: pd.DataFrame, col: str, default="") -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def _prep_occ_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    df["count"] = pd.to_numeric(_safe_series(df, "count", 0), errors="coerce").fillna(0).astype(int)

    df["genderCategory"] = (
        _safe_series(df, "genderCategory", "")
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .replace({
            "": "Unknown / not stated",
            "nan": "Unknown / not stated",
            "None": "Unknown / not stated",
            "null": "Unknown / not stated",
        })
    )

    df["occupationLabel"] = (
        _safe_series(df, "occupationLabel", "")
        .fillna("")
        .astype(str)
        .str.strip()
        .replace({
            "": "Unknown occupation",
            "nan": "Unknown occupation",
            "None": "Unknown occupation",
            "null": "Unknown occupation",
        })
    )

    df["sector"] = (
        _safe_series(df, "sector", "")
        .fillna("")
        .astype(str)
        .str.strip()
        .replace({
            "": "Other / Unclassified",
            "nan": "Other / Unclassified",
            "None": "Other / Unclassified",
            "null": "Other / Unclassified",
        })
    )

    if "isco_major_title" in df.columns:
        df["isco_major_title"] = _safe_series(df, "isco_major_title", "")
    elif "isco_major_label" in df.columns:
        df["isco_major_title"] = _safe_series(df, "isco_major_label", "")
    else:
        df["isco_major_title"] = "Unmapped ISCO major"

    df["isco_major_title"] = (
        df["isco_major_title"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace({
            "": "Unmapped ISCO major",
            "nan": "Unmapped ISCO major",
            "None": "Unmapped ISCO major",
            "null": "Unmapped ISCO major",
        })
    )

    if "country_qid" in df.columns:
        df["country_qid"] = df["country_qid"].astype(str).str.strip()

    if "country" in df.columns:
        df["country"] = df["country"].astype(str).str.strip()

    df = df[df["count"] > 0].copy()

    return df


def clean_occupation_df(df: pd.DataFrame) -> pd.DataFrame:
    return _prep_occ_df(df)


def filter_country_occ(df_all: pd.DataFrame, qid: str) -> pd.DataFrame:
    df = _prep_occ_df(df_all)
    if df.empty:
        return df

    qid = str(qid).strip()
    url_http = f"http://www.wikidata.org/entity/{qid}"
    url_https = f"https://www.wikidata.org/entity/{qid}"

    if "country_qid" in df.columns and "country" in df.columns:
        mask = (
            (df["country_qid"] == qid)
            | (df["country"] == url_http)
            | (df["country"] == url_https)
            | (df["country"] == qid)
        )
    elif "country_qid" in df.columns:
        mask = df["country_qid"] == qid
    elif "country" in df.columns:
        mask = (
            (df["country"] == url_http)
            | (df["country"] == url_https)
            | (df["country"] == qid)
        )
    else:
        return pd.DataFrame(columns=df.columns)

    out = df.loc[mask].copy()
    return out


def _group_small_leaves_within_parent(
    agg: pd.DataFrame,
    parent_col: str,
    leaf_col: str,
    value_col: str,
    min_share_within_parent: float,
) -> pd.DataFrame:
    out_parts = []

    for parent_value, g in agg.groupby(parent_col, sort=False):
        g = g.copy().sort_values(value_col, ascending=False)
        parent_total = float(g[value_col].sum())

        if parent_total <= 0:
            continue

        g["share_in_parent"] = g[value_col] / parent_total
        small = g[g["share_in_parent"] < min_share_within_parent].copy()
        big = g[g["share_in_parent"] >= min_share_within_parent].copy()

        if not small.empty:
            other_sum = int(small[value_col].sum())
            other_row = pd.DataFrame([{
                parent_col: parent_value,
                leaf_col: "Other (small occupations)",
                value_col: other_sum,
            }])
            big = pd.concat(
                [big[[parent_col, leaf_col, value_col]], other_row],
                ignore_index=True
            )
        else:
            big = big[[parent_col, leaf_col, value_col]]

        out_parts.append(big)

    if not out_parts:
        return pd.DataFrame(columns=[parent_col, leaf_col, value_col])

    return pd.concat(out_parts, ignore_index=True)


def make_occupation_treemap(
    df_country: pd.DataFrame,
    *,
    country_label: str,
    gender_filter: str = "All",
    group_mode: str = "Sector → Occupation",
    min_share_within_parent: float = 0.005,
):
    df = _prep_occ_df(df_country)

    if gender_filter and gender_filter != "All":
        df = df[df["genderCategory"] == gender_filter].copy()

    if df.empty:
        fig = px.treemap(
            names=["No occupation data"],
            parents=[""],
            values=[1],
            title=f"Occupations — {country_label}",
        )
        fig.update_traces(textinfo="label")
        fig.update_layout(template="simple_white", height=700)
        return fig

    agg = (
        df.groupby(["sector", "isco_major_title", "occupationLabel"], as_index=False)["count"]
        .sum()
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )

    if agg.empty or int(agg["count"].sum()) <= 0:
        fig = px.treemap(
            names=["No occupation data"],
            parents=[""],
            values=[1],
            title=f"Occupations — {country_label}",
        )
        fig.update_traces(textinfo="label")
        fig.update_layout(template="simple_white", height=700)
        return fig

    if group_mode == "ISCO Major → Occupation":
        parent_col = "isco_major_title"
        title = f"Occupations by ISCO major — {country_label}"
    else:
        parent_col = "sector"
        title = f"Occupations by sector — {country_label}"

    agg2 = agg[[parent_col, "occupationLabel", "count"]].copy()
    agg2 = _group_small_leaves_within_parent(
        agg2,
        parent_col=parent_col,
        leaf_col="occupationLabel",
        value_col="count",
        min_share_within_parent=min_share_within_parent,
    )

    if agg2.empty or int(agg2["count"].sum()) <= 0:
        fig = px.treemap(
            names=["No occupation data"],
            parents=[""],
            values=[1],
            title=title,
        )
        fig.update_traces(textinfo="label")
        fig.update_layout(template="simple_white", height=700)
        return fig

    plot_df = agg2.rename(columns={"occupationLabel": "Occupation"})

    fig = px.treemap(
        plot_df,
        path=[parent_col, "Occupation"],
        values="count",
        title=title,
    )

    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>Count: %{value:,}<extra></extra>",
        marker=dict(line=dict(width=1, color="white"), pad=dict(t=1, l=1, r=1, b=1),),
        textinfo="label",
        root_color="rgba(0,0,0,0)",
    )
    fig.update_layout(
        template="simple_white",
        height=700,
        margin=dict(l=10, r=10, t=60, b=10),
        paper_bgcolor="White",
        plot_bgcolor="White",
    )
    return fig


def make_occupation_details_table(
    df_country: pd.DataFrame,
    *,
    gender_filter: str = "All",
) -> pd.DataFrame:
    df = _prep_occ_df(df_country)
    if df.empty:
        return pd.DataFrame(columns=["Occupation", "Count", "Share (%)", "Sector", "ISCO major", "Gender"])

    if gender_filter and gender_filter != "All":
        df = df[df["genderCategory"] == gender_filter].copy()

    if df.empty:
        return pd.DataFrame(columns=["Occupation", "Count", "Share (%)", "Sector", "ISCO major", "Gender"])

    agg = (
        df.groupby(["occupationLabel", "sector", "isco_major_title", "genderCategory"], as_index=False)["count"]
        .sum()
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )

    total = float(agg["count"].sum())
    agg["Share (%)"] = np.where(total > 0, (agg["count"] / total) * 100.0, 0.0)

    out = agg.rename(columns={
        "occupationLabel": "Occupation",
        "count": "Count",
        "sector": "Sector",
        "isco_major_title": "ISCO major",
        "genderCategory": "Gender",
    })

    out = out[["Occupation", "Count", "Share (%)", "Sector", "ISCO major", "Gender"]]
    return out

