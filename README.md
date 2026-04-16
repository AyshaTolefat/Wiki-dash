# Wiki-dash
Interactive visualization dashboard for analyzing demographic bias in Wikidata.

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

## Requirements

Install the required packages with:

pip install -r requirements.txt

The main required libraries are:

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

streamlit run dashboard/0_Globe_Overview.py

This will open the Streamlit application in your browser.

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

## Reproducing the Data

The repository also contains the scripts used to collect and process the data from Wikidata.

These scripts cover:

- country-level gender extraction
- decade-level gender extraction
- age-group extraction
- language extraction
- ethnic-group extraction
- occupation extraction and refinement
- label resolution for missing Wikidata QIDs
- country ISO and map preparation

---

## Notes

- the dashboard is designed to run from the prepared files in the `data/` folder
- if any required data file is missing, some pages or charts may not load correctly
- the repository includes both the dashboard application and the supporting data-processing scripts used in the project

---

## Author

Aysha Tolefat

---
