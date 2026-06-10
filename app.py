# ============================================================
# IMPORTS
# ============================================================

import requests
import pandas as pd
from pyquery import PyQuery as pq
from urllib.parse import urljoin
import re
import time
import numpy as np

import streamlit as st
import folium

from streamlit_folium import st_folium


# ============================================================
# CONFIG STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Coworking Paris",
    layout="wide"
)

st.title("🧑‍💻 Espaces de coworking à Paris")
st.markdown("Carte interactive des espaces de coworking à Paris.")


# ============================================================
# VARIABLES
# ============================================================

BASE_URL = "https://www.leportagesalarial.com/coworking/"
DOMAIN = "https://www.leportagesalarial.com"


# ============================================================
# FETCH HTML
# ============================================================

def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.text


# ============================================================
# LINKS SCRAPING
# ============================================================

def get_coworking_links():
    html = fetch(BASE_URL)
    doc = pq(html)

    links = []

    for h in doc("h2, h3").items():
        if "Île de France" in h.text():
            ul = h.next("ul")

            for a in ul("a").items():
                name = a.text().strip()
                url = urljoin(DOMAIN, a.attr("href"))
                links.append((name, url))
            break

    return links


# ============================================================
# FILTER PARIS
# ============================================================

def is_paris(adresse):
    if not adresse:
        return False
    return "Paris" in adresse or bool(re.search(r"75\d{3}", adresse))


# ============================================================
# EXTRACTION DATA (SITE FIXÉ + PROPRE)
# ============================================================

def extract_data(name, url):

    html = fetch(url)
    doc = pq(html)

    titre = doc("h1").text().strip()

    image = ""
    img = doc("article img").eq(0)
    if img:
        image = img.attr("src")
        if image:
            image = urljoin(DOMAIN, image)

    description = ""
    for h2 in doc("h2").items():
        if "Présentation" in h2.text():
            p = h2.next()
            while p and not p.is_("h2"):
                description += p.text().strip() + " "
                p = p.next()
            break

    adresse = ""
    telephone = ""
    site = ""

    for li in doc("li").items():
        txt = li.text()

        if "Adresse" in txt:
            adresse = txt.split(":", 1)[-1].strip()

        if "Téléphone" in txt:
            telephone = txt.split(":", 1)[-1].strip()

    # ============================================================
    # SITE WEB PROPRE (anti freeland / annuaires)
    # ============================================================

    candidates = []

    for a in doc("a").items():

        link = a.attr("href")

        if link:
            link = urljoin(DOMAIN, link)

            if (
                link.startswith("http")
                and "leportagesalarial" not in link
                and "freeland" not in link.lower()
                and "facebook" not in link.lower()
                and "linkedin" not in link.lower()
            ):
                candidates.append(link)

    if len(candidates) > 0:
        site = candidates[0]

    time.sleep(0.3)

    return {
        "Nom": name,
        "Titre": titre,
        "Adresse": adresse,
        "Téléphone": telephone,
        "Description": description,
        "Image": image,
        "Site": site,
        "Adresse_full": adresse
    }


# ============================================================
# DATAFRAME
# ============================================================

@st.cache_data
def build_dataframe():

    links = get_coworking_links()
    data = []

    for name, url in links:

        try:
            d = extract_data(name, url)

            if is_paris(d["Adresse"]):
                data.append(d)

        except:
            pass

    return pd.DataFrame(data)


df = build_dataframe()


# ============================================================
# 🚀 GEOCODING STABLE (PHOTON API - NO LIMITS STREAMLIT)
# ============================================================

@st.cache_data
def geocode_address(address):

    if not address:
        return [np.nan, np.nan]

    try:
        url = f"https://photon.komoot.io/api/?q={address}, Paris, France&limit=1"
        r = requests.get(url, timeout=10)
        data = r.json()

        if data["features"]:
            lon = data["features"][0]["geometry"]["coordinates"][0]
            lat = data["features"][0]["geometry"]["coordinates"][1]
            return [lat, lon]

    except:
        pass

    return [np.nan, np.nan]


def add_geocodes(df):

    coords = []

    for addr in df["Adresse"]:

        coords.append(geocode_address(addr))
        time.sleep(0.2)

    df["GEOCODE"] = coords
    return df


df = add_geocodes(df)


# ============================================================
# ARRONDISSEMENT
# ============================================================

def extract_arrondissement(addr):

    if not isinstance(addr, str):
        return "Inconnu"

    match = re.search(r"75(\d{3})", addr)

    if match:
        return match.group(1)[-2:]

    return "Inconnu"


df["Arrondissement"] = df["Adresse"].apply(extract_arrondissement)


# ============================================================
# SIDEBAR FILTERS
# ============================================================

st.sidebar.title("🔎 Filtres")

search = st.sidebar.text_input("Recherche")

arr = st.sidebar.selectbox(
    "Arrondissement",
    ["Tous"] + sorted(df["Arrondissement"].unique())
)


# ============================================================
# FILTERING
# ============================================================

filtered_df = df.copy()

if search:
    filtered_df = filtered_df[
        filtered_df["Titre"].str.contains(search, case=False, na=False)
    ]

if arr != "Tous":
    filtered_df = filtered_df[filtered_df["Arrondissement"] == arr]


# ============================================================
# KPI
# ============================================================

col1, col2 = st.columns(2)

col1.metric("Résultats", len(filtered_df))
col2.metric("Total", len(df))


# ============================================================
# TABLE
# ============================================================

st.subheader("📋 Liste")

st.dataframe(
    filtered_df[["Titre", "Adresse", "Téléphone", "Site"]],
    width="stretch"
)


# ============================================================
# MAP (100% STABLE STREAMLIT)
# ============================================================

st.subheader("🗺️ Carte")

m = folium.Map(location=[48.8566, 2.3522], zoom_start=12)

for _, row in filtered_df.iterrows():

    geo = row["GEOCODE"]

    if isinstance(geo, list) and len(geo) == 2 and not pd.isna(geo[0]):

        folium.CircleMarker(
            location=[float(geo[0]), float(geo[1])],
            radius=6,
            color="red",
            fill=True,
            fill_color="red",
            fill_opacity=0.9,
            tooltip=row["Titre"],
            popup=row["Adresse"]
        ).add_to(m)


st_folium(m, width=1200, height=650)


# ============================================================
# DETAIL VIEW
# ============================================================

st.subheader("🏢 Détail")

if len(filtered_df) > 0:

    choice = st.selectbox("Choisir un coworking", filtered_df["Titre"])

    row = filtered_df[filtered_df["Titre"] == choice].iloc[0]

    st.markdown(f"### {row['Titre']}")
    st.write("📍", row["Adresse"])
    st.write("📞", row["Téléphone"])
    st.write(row["Description"][:500])

    if row["Site"]:
        st.link_button("🌐 Site web", row["Site"])


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.markdown("Projet Python — Coworking Paris | Réalisé par")
