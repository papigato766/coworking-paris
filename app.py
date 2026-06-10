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
from folium.plugins import MarkerCluster

from geopy.geocoders import Nominatim


# ============================================================
# CONFIG STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Coworking Paris",
    layout="wide"
)

st.title("🧑‍💻 Espaces de coworking à Paris")
st.markdown("Application de visualisation des espaces de coworking à Paris.")


# ============================================================
# VARIABLES
# ============================================================

BASE_URL = "https://www.leportagesalarial.com/coworking/"
DOMAIN = "https://www.leportagesalarial.com"

locator = Nominatim(user_agent="student_project_coworking")


# ============================================================
# SCRAPING
# ============================================================

def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.text


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


def is_paris(adresse):
    if not adresse:
        return False
    return "Paris" in adresse or bool(re.search(r"75\d{3}", adresse))


def extract_data(name, url):
    html = fetch(url)
    doc = pq(html)

    titre = doc("h1").text().strip()

    image = ""
    img_tag = doc("article img").eq(0)
    if img_tag:
        image = img_tag.attr("src")
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

        link = li("a").attr("href") or ""
        if "http" in link and DOMAIN not in link:
            site = link

    time.sleep(0.5)

    return {
        "Nom": name,
        "Titre": titre,
        "Adresse": adresse,
        "Téléphone": telephone,
        "Description": description,
        "Image": image,
        "Site": site,
        "URL": url
    }


# ============================================================
# DATAFRAME
# ============================================================

@st.cache_data
def build_dataframe():
    links = get_coworking_links()
    data = []

    progress = st.progress(0)

    for i, (name, url) in enumerate(links):
        try:
            d = extract_data(name, url)
            if is_paris(d["Adresse"]):
                data.append(d)
        except:
            pass

        progress.progress((i + 1) / len(links))

    return pd.DataFrame(data)


df = build_dataframe()


# ============================================================
# GEOCODING
# ============================================================

@st.cache_data
def geocode_dataframe(df):

    geocodes = []

    for i, adresse in enumerate(df["Adresse"]):

        if pd.isna(adresse):
            geocodes.append([np.nan, np.nan])
            continue

        try:
            location = locator.geocode(
                f"{adresse}, Paris, France",
                timeout=10
            )

            if location:
                geocodes.append([location.latitude, location.longitude])
            else:
                geocodes.append([np.nan, np.nan])

            time.sleep(1)

        except:
            geocodes.append([np.nan, np.nan])

    df["GEOCODE"] = geocodes
    return df


df = geocode_dataframe(df)


# ============================================================
# ARRONDISSEMENT
# ============================================================

def extract_arrondissement(adresse):
    if not isinstance(adresse, str):
        return "Inconnu"

    match = re.search(r"75(\d{3})", adresse)
    if match:
        return match.group(1)[-2:]

    return "Inconnu"


df["Arrondissement"] = df["Adresse"].apply(extract_arrondissement)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🔎 Filtres")

search = st.sidebar.text_input("Recherche")

arr = st.sidebar.selectbox(
    "Arrondissement",
    ["Tous"] + sorted(df["Arrondissement"].unique())
)

site_only = st.sidebar.checkbox("Avec site web uniquement")
with_tel = st.sidebar.checkbox("Avec téléphone uniquement")

font_size = st.sidebar.slider("Taille texte", 12, 24, 16)



st.markdown(
    f"""
    <style>
    html, body {{
        font-size: {font_size}px;
    }}
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# FILTRES
# ============================================================

filtered_df = df.copy()

if search:
    filtered_df = filtered_df[
        filtered_df["Titre"].str.contains(search, case=False, na=False)
    ]

if arr != "Tous":
    filtered_df = filtered_df[filtered_df["Arrondissement"] == arr]

if site_only:
    filtered_df = filtered_df[filtered_df["Site"].str.len() > 0]

if with_tel:
    filtered_df = filtered_df[filtered_df["Téléphone"].str.len() > 0]


# ============================================================
# KPI
# ============================================================

col1, col2 = st.columns(2)

col1.metric("Résultats", len(filtered_df))
col2.metric("Total", len(df))


# ============================================================
# TABLEAU
# ============================================================

st.subheader("📋 Données")

st.dataframe(
    filtered_df[["Titre", "Adresse", "Téléphone", "Site"]],
    width="stretch"
)


# ============================================================
# CARTE
# ============================================================

st.subheader("🗺️ Carte")

m = folium.Map(location=[48.8566, 2.3522], zoom_start=12)

marker_cluster = MarkerCluster().add_to(m)

for _, row in filtered_df.iterrows():

    geo = row["GEOCODE"]

    if (
        isinstance(geo, list)
        and len(geo) == 2
        and not pd.isna(geo[0])
    ):

        popup = f"""
        <b>{row['Titre']}</b><br>
        {row['Adresse']}<br><br>
        {row['Téléphone']}<br><br>
        <a href="{row['Site']}" target="_blank">Site</a>
        """

        folium.Marker(
            location=geo,
            popup=folium.Popup(popup, max_width=300),
            tooltip=row["Titre"],

            icon=folium.Icon(
                color="red",
                icon="briefcase",
                prefix="fa"
            )
        ).add_to(marker_cluster)


st_folium(m, width=1200, height=600)


# ============================================================
# FICHE DETAILLEE
# ============================================================

st.subheader("🏢 Détail")

if len(filtered_df) > 0:

    choice = st.selectbox("Choisir un coworking", filtered_df["Titre"])

    row = filtered_df[filtered_df["Titre"] == choice].iloc[0]

    col1, col2 = st.columns([1, 2])

    with col1:
        if row["Image"]:
            st.image(row["Image"])

    with col2:
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
st.markdown("Projet Python — Coworking Paris | Réalisé par Aurélia Chartier")