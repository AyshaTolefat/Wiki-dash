# Wiki-dash
Interactive visual analytics dashboard for exploring demographic representation gaps in Wikidata biographies.

It visualises country-level patterns in biography data derived from Wikidata, including:

- overall gender distribution
- gender distribution over decades
- languages associated with biographies
- ethnic-group labels associated with biographies
- occupation patterns
- age-group distributions

The repository also includes the data-processing scripts used to collect, update, clean, and prepare the datasets used by the dashboard.

---

## Features

- interactive globe overview for country selection
- detailed country dashboard for individual countries
- gender breakdown and gender gap summaries
- decade-based gender trends
- language, ethnicity, occupation, and age visualisations
- supporting scripts for reproducing the prepared data files

---

## Repository Structure

```test
dashboard/   Streamlit dashboard application
data/        Prepared datasets used by the dashboard
scripts/     Data extraction, update, and preprocessing scripts
```
---

## Installation

Clone the repository and move into the project directory:

```bash
git clone https://github.com/AyshaTolefat/Wiki-dash.git
cd Wiki-dash
```

Create a virtual environment:

```bash
python -m venv .venv
```
Activate the virtual environment.

**Windows:**

```bash
.venv\Scripts\activate
```

**macOS/Linux:**

```bash
source .venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

The main required libraries include:

- streamlit
- pandas
- numpy
- plotly
- requests
- SPARQLWrapper
- pycountry
- geopandas
- shapely

---

## How to Run the App

From the project root directory, run:

```bash
streamlit run dashboard/0_Globe_Overview.py
```

This will open the Streamlit application in your browser.

The dashboard reads the prepared datasets in the `data/` directory, so no live Wikidata queries are required while using the application.

---

## Dashboard Pages

The app contains:

- **Globe overview**: a world globe for selecting countries
- **Country dashboard**: a detailed page showing charts and summary statistics for the selected country

---

## Data Files

The dashboard reads prepared CSV and GeoJSON files from the `data/` folder.

These files include the processed outputs used directly by the application, such as:

- gender totals by country
- gender totals over decades
- languages by country
- ethnic groups by country
- occupation data
- age-group data
- allowed country lists
- map geometry and country centroids
- QID label mappings

---

## Reproducing and updating the Data

The repository contains the extraction and preprocessing scripts used to prepare the wikidata datasets consumed by the dashboard.

A single update script is provided to run the main data-refresh pipeline:

```bash
python scripts/update_all.py
```

This regenerates and updates the datatsets for:
- Overall gender distribution
- Gender distribution by decade
- Age groups
- Native and spoken languages
- Ethnic-group representation
- Supporting country and Wikidata label mappings

The update pipeline also runs the existing handling for missing and special territories where required.

---

## Notes

- The dashboard uses preprocessed datatsets rather than issuing live Wikidata queries during user interaction.
- Wikidata changes made after the latest preprocessing run will not appear until the datasets are regenerated.
- If a required data file is missing, the corresponding dashboard visualisation may not load correctly.
- The demographic distributions shown by the dashboard describe representation within Wikidata and should not be interpreted directly as real-world population distributions.

---

## Author

Aysha Tolefat
