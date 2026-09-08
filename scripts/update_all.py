from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
DATA_DIR = ROOT_DIR / "data"

EXPECTED_OUTPUTS = [
    DATA_DIR / "gender_country_1900_present_per_country.csv",
    DATA_DIR / "gender_decades_by_country.csv",
    DATA_DIR / "age_groups_by_country.csv",
    DATA_DIR / "languages_by_country.csv",
    DATA_DIR / "ethnic_group_by_country_gender.csv",
    DATA_DIR / "wikidata_qid_labels.csv",
]

def run_script(
    filename: str,
    description: str,
    step: int,
    total_steps: int,
    dry_run: bool = False,
) -> None:
    """
    Run one of the existing dissertation scripts.
    """

    script_path = SCRIPTS_DIR / filename

    if not script_path.exists():
        raise FileNotFoundError(
            f"Required script does not exist: {script_path}"
        )

    print("\n" + "=" * 70)
    print(f"[{step}/{total_steps}] {description}")
    print(f"Script: {filename}")
    print("=" * 70)

    if dry_run:
        print("DRY RUN - script not executed.")
        return

    start = time.time()

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT_DIR),
    )

    elapsed = time.time() - start

    if result.returncode != 0:
        raise RuntimeError(
            f"{filename} failed with exit code "
            f"{result.returncode}."
        )

    print(
        f"\nCompleted: {filename} "
        f"({elapsed / 60:.1f} minutes)"
    )


def check_file(path: Path) -> None:
    """
    Make sure an expected output exists and is not empty.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Expected output was not created: {path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"Output file is empty: {path}"
        )


def run_gender_country(
    step: int,
    total_steps: int,
    dry_run: bool = False,
) -> None:
    """
    Run the existing fetch_gender_country.py logic.

    fetch_allowed_countries() writes the country CSV but does
    not return the dataframe, so this wrapper reads that output
    and then calls the script's existing country-level function.

    The original dissertation file itself is not modified.
    """

    filename = "fetch_gender_country.py"
    script_path = SCRIPTS_DIR / filename

    print("\n" + "=" * 70)
    print(
        f"[{step}/{total_steps}] "
        "Overall gender distribution"
    )
    print(f"Script: {filename}")
    print("=" * 70)

    if dry_run:
        print("DRY RUN - script not executed.")
        return

    if not script_path.exists():
        raise FileNotFoundError(
            f"Required script does not exist: {script_path}"
        )

    start = time.time()
    original_cwd = Path.cwd()

    try:
        os.chdir(SCRIPTS_DIR)

        spec = importlib.util.spec_from_file_location(
            "fetch_gender_country_module",
            script_path,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                "Could not load fetch_gender_country.py"
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module.fetch_allowed_countries()

        countries_path = (
            DATA_DIR / "allowed_countries_qids.csv"
        )

        check_file(countries_path)

        countries = pd.read_csv(countries_path)

        required = {"country", "countryLabel"}

        if not required.issubset(countries.columns):
            raise ValueError(
                "allowed_countries_qids.csv is missing "
                "the expected columns."
            )

        all_rows = []
        total = len(countries)

        print(
            f"\nRetrieving gender data for "
            f"{total} countries..."
        )

        for idx, row in countries.iterrows():

            country_uri = str(row["country"])
            country_label = str(row["countryLabel"])
            country_qid = country_uri.rsplit("/", 1)[-1]

            print(
                f"[{idx + 1}/{total}] "
                f"{country_label} ({country_qid})"
            )

            df_country = module.fetch_gender_for_country(
                country_qid,
                country_label,
            )

            if (
                df_country is not None
                and not df_country.empty
            ):
                all_rows.append(df_country)

            time.sleep(1.5)

        if not all_rows:
            raise RuntimeError(
                "No overall gender data was retrieved."
            )

        result = pd.concat(
            all_rows,
            ignore_index=True,
        )

        output_path = (
            DATA_DIR
            / "gender_country_1900_present_per_country.csv"
        )

        result.to_csv(
            output_path,
            index=False,
        )

        print(
            f"\nSaved {len(result):,} rows to:"
        )
        print(output_path)

    finally:
        os.chdir(original_cwd)

    elapsed = time.time() - start

    print(
        f"\nCompleted gender-country refresh "
        f"({elapsed / 60:.1f} minutes)"
    )


def main(dry_run: bool = False) -> None:

    start = time.time()

    print("\n" + "#" * 70)
    print("WIKI-DASH DATA REFRESH")
    print("Occupation refresh is currently excluded.")
    print("#" * 70)

    if dry_run:
        print("\nDRY RUN MODE")
        print("No Wikidata queries will be executed.")


    stages = [

        (
            "make_allowed_countries_iso3.py",
            "Generate ISO-3 country mapping",
        ),
        (
            "fetch_missing_qids.py",
            "Resolve missing territory QIDs",
        ),
        (
            "append_missing_iso.py",
            "Add missing ISO-3 mappings",
        ),

        (
            "fetch_gender_decades.py",
            "Gender distribution by decade",
        ),
        (
            "fetch_age_country.py",
            "Age groups by country",
        ),
        (
            "languages_by_country.py",
            "Languages by country",
        ),
        (
            "languages_us_germany.py",
            "Language retrieval for US and Germany",
        ),
        (
            "ethnic_group_query.py",
            "Ethnic groups by country and gender",
        ),

        (
            "update_gender_country_query.py",
            "Gender totals for missing territories",
        ),
        (
            "update_gender_totals.py",
            "Gender totals for special territories",
        ),

        (
            "update_gender_decades_query.py",
            "Gender decades for missing territories",
        ),
        (
            "update_gender_decade.py",
            "Gender decades for special territories",
        ),

        (
            "update_age_groups_query.py",
            "Age groups for missing territories",
        ),
        (
            "update_age.py",
            "Age groups for special territories",
        ),

        (
            "update_languages_query.py",
            "Languages for missing territories",
        ),
        (
            "update_lang.py",
            "Languages for special territories",
        ),

        (
            "update_ethnic_group_query.py",
            "Ethnic groups for missing territories",
        ),
        (
            "update_ethnic_group.py",
            "Ethnic groups for special territories",
        ),

        (
            "resolve_missing_qid_labels.py",
            "Resolve Wikidata QID labels",
        ),
    ]

    total_steps = len(stages) + 1

    run_gender_country(
        step=1,
        total_steps=total_steps,
        dry_run=dry_run,
    )


    for step_number, (
        filename,
        description,
    ) in enumerate(stages, start=2):

        run_script(
            filename=filename,
            description=description,
            step=step_number,
            total_steps=total_steps,
            dry_run=dry_run,
        )


    if not dry_run:

        print("\n" + "=" * 70)
        print("VALIDATING FINAL OUTPUTS")
        print("=" * 70)

        for output in EXPECTED_OUTPUTS:

            check_file(output)

            size_mb = (
                output.stat().st_size
                / (1024 * 1024)
            )

            print(
                f"OK  {output.name} "
                f"({size_mb:.2f} MB)"
            )


    elapsed = time.time() - start

    print("\n" + "#" * 70)

    if dry_run:
        print("DRY RUN COMPLETE")
    else:
        print("DATA REFRESH COMPLETE")

    print(
        f"Total time: "
        f"{elapsed / 60:.1f} minutes"
    )

    print()
    print(
        "NOTE: Occupation data was not regenerated."
    )

    print(
        "Existing file retained:"
    )

    print(
        "data/"
        "gender_occupation_with_isco_refined.csv"
    )

    print("#" * 70 + "\n")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Regenerate Wiki-dash analytical datasets "
            "except occupation data."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Show the pipeline without executing "
            "Wikidata queries."
        ),
    )

    args = parser.parse_args()

    try:

        main(
            dry_run=args.dry_run,
        )

    except KeyboardInterrupt:

        print("\nUpdate cancelled by user.")
        sys.exit(130)

    except Exception as exc:

        print("\n" + "!" * 70)
        print("DATA REFRESH FAILED")
        print(f"Reason: {exc}")
        print("!" * 70)

        sys.exit(1)