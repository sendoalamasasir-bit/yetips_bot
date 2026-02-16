import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURACIÓN ---
API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f"  # <--- ¡PEGA TU API KEY AQUÍ!
COMPETITION_ID = 'PD' # Primera División (La Liga)
URL_API = f"https://api.football-data.org/v4/competitions/{COMPETITION_ID}/matches"

# --- MAPA DE NOMBRES (TRADUCTOR API -> TUS CSVs) ---
# La API devuelve nombres oficiales (ej: "Real Betis Balompié")
# Tus CSVs usan nombres cortos (ej: "Betis" o "Real Betis")
mapa_nombres = {
    # Nombre API : [Nombre Statsbomb, Nombre SP1]
    "Deportivo Alavés": ["Alavés", "Alaves"],
    "Girona FC": ["Girona", "Girona"],
    "Athletic Club": ["Athletic Club", "Ath Bilbao"],
    "Elche CF": ["Elche", "Elche"],
    "Club Atlético de Madrid": ["Atlético Madrid", "Ath Madrid"],
    "RCD Espanyol de Barcelona": ["Espanyol", "Espanyol"],
    "FC Barcelona": ["Barcelona", "Barcelona"],
    "Levante UD": ["Levante", "Levante"],
    "Real Betis Balompié": ["Real Betis", "Betis"],
    "Rayo Vallecano de Madrid": ["Rayo Vallecano", "Rayo Vallecano"],
    "RC Celta de Vigo": ["Celta Vigo", "Celta"],
    "RCD Mallorca": ["Mallorca", "Mallorca"],
    "Getafe CF": ["Getafe", "Getafe"],
    "Sevilla FC": ["Sevilla", "Sevilla"],
    "CA Osasuna": ["Osasuna", "Osasuna"],
    "Real Madrid CF": ["Real Madrid", "Real Madrid"],
    "Villarreal CF": ["Villarreal", "Villarreal"],
    "Valencia CF": ["Valencia", "Valencia"],
    "Real Sociedad de Fútbol": ["Real Sociedad", "Sociedad"],
    "Real Oviedo": ["Oviedo", "Oviedo"],
    "Real Valladolid CF": ["Valladolid", "Valladolid"],
    "UD Las Palmas": ["Las Palmas", "Las Palmas"],
    "CD Leganés": ["Leganés", "Leganes"]
}

# --- FUNCIONES ---
def clean_num(val):
    if isinstance(val, str): return float(val.replace(',', '.'))
    return float(val) if val else 0.0

def get_matches_from_api():
    headers = {'X-Auth-Token': API_KEY}
    # Pedimos partidos programados (SCHEDULED) de los próximos 7 días
    params = {'status': 'SCHEDULED'} 
    response = requests.get(URL_API, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        matches = []
        # Filtramos para coger solo la jornada actual (o la próxima disponible)
        # Por simplicidad, cogemos los primeros 10 partidos que nos devuelva la API
        for match in data['matches'][:10]: 
            matches.append({
                'local': match['homeTeam']['name'],
                'visitante': match['awayTeam']['name'],
                'fecha': match['utcDate'][:10] # Solo la fecha YYYY-MM-DD
            })
        return matches
    else:
        st.error(f"Error conectando con la API: {response.status_code}")
        return []

def procesar_datos(jornada):
    try:
        # CARGAR CSVs (Deben estar en la misma carpeta)
        df_goals = pd.read_csv('liga_stand_25 - Hoja 1.csv', header=1)[['Squad', '90s', 'Gls']]
        df_misc = pd.read_csv('misc25sp - Hoja 1.csv', header=1)[['Squad', 'Off', 'CrdY', 'CrdR']]
        df_fbref = df_goals.merge(df_misc, on='Squad', how='inner')
        
        # Cálculos FBref
        df_fbref['90s'] = df_fbref['90s'].apply(clean_num)
        df_fbref['G_p'] = df_fbref['Gls'].apply(clean_num) / df_fbref['90s']
        df_fbref['O_p'] = df_fbref['Off'].apply(clean_num) / df_fbref['90s']
        y = df_fbref['CrdY'].apply(clean_num)
        r = df_fbref['CrdR'].apply(clean_num)
        df_fbref['C_p'] = ((y * 10) + (r * 25)) / df_fbref['90s']

        # Cargar SP1
        df_sp1 = pd.read_csv('SP1 (1).csv')
        sp1_stats = {}
        for idx, row in df_sp1.iterrows():
            for tipo in ['Home', 'Away']:
                team = row[f'{tipo}Team']
                if team not in sp1_stats: sp1_stats[team] = {'pj':0, 'corn':0, 'sot':0}
                sp1_stats[team]['pj'] += 1
                sp1_stats[team]['corn'] += row['HC'] if tipo == 'Home' else row['AC']
                sp1_stats[team]['sot'] += row['HST'] if tipo == 'Home' else row['AST']
                
        # Generar Reporte
        reporte = []
        for juego in jornada:
            local_api = juego['local']
            visita_api = juego['visitante']
            
            # Traducir nombres
            names_L = mapa_nombres.get(local_api)
            names_V = mapa_nombres.get(visita_api)
            
            if not names_L or not names_V:
                reporte.append({"Partido": f"{local_api} vs {visita_api}", "Estado": "⚠️ Error Nombres (Revisar Mapa)"})
                continue

            nom_fb_L, nom_sp1_L = names_L
            nom_fb_V, nom_sp1_V = names_V
            
            # Recuperar Datos
            try:
                # FBref
                h_fb = df_fbref[df_fbref['Squad'] == nom_fb_L].iloc[0]
                a_fb = df_fbref[df_fbref['Squad'] == nom_fb_V].iloc[0]
                
                # SP1
                h_sp = sp1_stats.get(nom_sp1_L, {'pj':1, 'corn':0, 'sot':0})
                a_sp = sp1_stats.get(nom_sp1_V, {'pj':1, 'corn':0, 'sot':0})
                
                # Totales
                tot_gls = h_fb['G_p'] + a_fb['G_p']
                tot_off = h_fb['O_p'] + a_fb['O_p']
                tot_crd = h_fb['C_p'] + a_fb['C_p']
                tot_corn = (h_sp['corn']/h_sp['pj']) + (a_sp['corn']/a_sp['pj'])
                tot_sot = (h_sp['sot']/h_sp['pj']) + (a_sp['sot']/a_sp['pj'])
                
                # Guardar fila
                reporte.append({
                    "Partido": f"{local_api} vs {visita_api}",
                    "Fecha": juego['fecha'],
                    "⚽ Goles": f"{tot_gls:.2f} ({'MÁS 2.5' if tot_gls > 2.5 else 'Menos'})",
                    "🚩 Offsides": f"{tot_off:.2f} ({'MÁS 3.5' if tot_off > 3.6 else 'Menos'})",
                    "⛳ Corners": f"{tot_corn:.2f} ({'MÁS 9.5' if tot_corn > 9.5 else 'Menos'})",
                    "🚀 Tiros P": f"{tot_sot:.2f} ({'MÁS 8.5' if tot_sot > 8.5 else 'Menos'})",
                    "🟨 Tarjetas": f"{tot_crd:.0f} pts ({'MÁS 55' if tot_crd > 55 else 'Menos'})"
                })

            except Exception as e:
                reporte.append({"Partido": f"{local_api} vs {visita_api}", "Estado": f"Error Datos: {e}"})

        return pd.DataFrame(reporte)

    except FileNotFoundError:
        st.error("❌ No encuentro los CSVs. Asegúrate de que están en la misma carpeta.")
        return None

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Yetips Dashboard", layout="wide")

st.title("🦁 Yetips Dashboard 2.0")
st.markdown("Sistema de análisis automático de La Liga.")

col1, col2 = st.columns([1, 3])

with col1:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/LaLiga_Santander_Logo_%282016-2023%29.svg/1200px-LaLiga_Santander_Logo_%282016-2023%29.svg.png", width=150)
    if st.button("🔄 Buscar Partidos y Analizar", type="primary"):
        with st.spinner('Contactando con La Liga y calculando probabilidades...'):
            matches = get_matches_from_api()
            if matches:
                df_resultado = procesar_datos(matches)
                st.session_state['data'] = df_resultado
            else:
                st.warning("No hay partidos programados pronto o falló la API.")

with col2:
    if 'data' in st.session_state and st.session_state['data'] is not None:
        st.success("✅ Análisis Completado")
        st.dataframe(st.session_state['data'], use_container_width=True)
    else:
        st.info("Pulsa el botón para cargar la jornada actual.")