import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import difflib

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================

st.set_page_config(page_title="Yetips Champions", layout="wide", page_icon="🏆")

st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    .stMetric {background-color: #262730; padding: 10px; border-radius: 10px; border: 1px solid #41444b;}
    h1 {color: #ffd700;}
    </style>
    """, unsafe_allow_html=True)

# TUS CLAVES
API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f"
TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
TG_CHAT_ID = "1197028422"

LIGAS = {
    "🇪🇺 UEFA Champions League": {"api": "CL", "csv": "MULTI"},
    "🇪🇸 La Liga": {"api": "PD", "csv": "SP1"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"api": "PL", "csv": "E0"},
    "🇩🇪 Bundesliga": {"api": "BL1", "csv": "D1"},
    "🇮🇹 Serie A": {"api": "SA", "csv": "I1"},
    "🇫🇷 Ligue 1": {"api": "FL1", "csv": "F1"},
    "🇳🇱 Eredivisie": {"api": "DED", "csv": "N1"},
    "🇵🇹 Primeira Liga": {"api": "PPL", "csv": "P1"}
}

# ==========================================
# 2. CARGA DE DATOS
# ==========================================

@st.cache_data(ttl=3600)
def cargar_datos_liga(codigo_csv):
    # MODO CHAMPIONS: Carga TODAS las ligas
    if codigo_csv == "MULTI":
        todos_codigos = ["SP1", "E0", "D1", "I1", "F1", "N1", "P1"]
        mega_stats = {}
        for c in todos_codigos:
            s = cargar_datos_liga(c)
            if s: mega_stats.update(s)
        return mega_stats

    # MODO NORMAL
    url = f"https://www.football-data.co.uk/mmz4281/2526/{codigo_csv}.csv"
    try:
        df = pd.read_csv(url)
        stats = {}
        for idx, row in df.iterrows():
            for tipo in ['Home', 'Away']:
                team = row[f'{tipo}Team']
                if team not in stats: 
                    stats[team] = {'pj': 0, 'gf': 0, 'gc': 0, 'corn': 0, 'sot': 0, 'cards': 0}
                
                es_local = (tipo == 'Home')
                stats[team]['pj'] += 1
                stats[team]['gf'] += row['FTHG'] if es_local else row['FTAG']
                stats[team]['gc'] += row['FTAG'] if es_local else row['FTHG']
                
                if 'HC' in row and pd.notna(row['HC']): 
                    stats[team]['corn'] += row['HC'] if es_local else row['AC']
                if 'HST' in row and pd.notna(row['HST']):
                    stats[team]['sot'] += row['HST'] if es_local else row['AST']
                if 'HY' in row and pd.notna(row['HY']):
                    stats[team]['cards'] += (row['HY'] if es_local else row['AY'])
        return stats
    except: return None

def cargar_offsides_manual(uploaded_file):
    if uploaded_file is None: return None
    try:
        try: df = pd.read_csv(uploaded_file, header=1)
        except: df = pd.read_csv(uploaded_file, header=0)
        off_stats = {}
        cols = df.columns.tolist()
        col_squad = next((c for c in cols if 'Squad' in c), None)
        col_off = next((c for c in cols if 'Off' in c), None)
        if col_squad and col_off:
            for _, row in df.iterrows():
                try:
                    squad = row[col_squad]
                    div = 1.0
                    if '90s' in cols: div = float(row['90s'])
                    val = float(row[col_off])
                    if div > 0: off_stats[squad] = val / div
                except: continue
            return off_stats
        return None
    except: return None

# ==========================================
# 3. LÓGICA DE NOMBRES Y CÁLCULOS
# ==========================================

def encontrar_equipo(nombre_api, lista_nombres):
    manual = {
        "Sport Lisboa e Benfica": "Benfica",
        "Real Madrid CF": "Real Madrid",
        "Sporting Clube de Portugal": "Sp Portugal",
        "PSV Eindhoven": "PSV Eindhoven",
        "Athletic Club": "Ath Bilbao", 
        "Club Atlético de Madrid": "Ath Madrid",
        "Manchester United FC": "Man United", 
        "Wolverhampton Wanderers FC": "Wolves",
        "Paris Saint-Germain FC": "Paris SG", 
        "Bayer 04 Leverkusen": "Leverkusen",
        "Real Betis Balompié": "Betis", 
        "Rayo Vallecano de Madrid": "Rayo Vallecano",
        "Girona FC": "Girona", 
        "Real Sociedad de Fútbol": "Sociedad",
        "RCD Mallorca": "Mallorca", 
        "CA Osasuna": "Osasuna", 
        "Sevilla FC": "Sevilla",
        "Inter Milan": "Inter", 
        "AC Milan": "Milan", 
        "FC Barcelona": "Barcelona", 
        "FC Bayern München": "Bayern Munich",
        "Lille OSC": "Lille", 
        "Aston Villa FC": "Aston Villa",
        "Bologna FC 1909": "Bologna", 
        "VfB Stuttgart": "Stuttgart", 
        "RB Leipzig": "Leipzig"
    }
    
    if nombre_api in manual:
        nombre_csv = manual[nombre_api]
        if nombre_csv in lista_nombres: return nombre_csv
        match_manual = difflib.get_close_matches(nombre_csv, lista_nombres, n=1, cutoff=0.6)
        if match_manual: return match_manual[0]

    match = difflib.get_close_matches(nombre_api, lista_nombres, n=1, cutoff=0.5)
    return match[0] if match else None

def calcular_pronostico(local, visita, stats_auto, stats_off=None):
    nom_L = encontrar_equipo(local, list(stats_auto.keys()))
    nom_V = encontrar_equipo(visita, list(stats_auto.keys()))
    
    if not nom_L or not nom_V: return None

    L = stats_auto[nom_L]
    V = stats_auto[nom_V]

    # Stats
    xg_h = (L['gf']/L['pj'] + V['gc']/V['pj']) / 2
    xg_a = (V['gf']/V['pj'] + L['gc']/L['pj']) / 2
    total_goals = xg_h + xg_a
    pick_gol = "MÁS 2.5" if total_goals > 2.5 else "MENOS 2.5"
    
    diff = xg_h - xg_a
    if diff > 0.3: ganador = f"{local}"
    elif diff < -0.3: ganador = f"{visita}"
    else: ganador = "Empate / X"

    ah_raw = round(diff * 2) / 2
    if ah_raw > 0: ah_line = f"{local} -{abs(ah_raw)}"
    elif ah_raw < 0: ah_line = f"{visita} -{abs(ah_raw)}"
    else: ah_line = "DNB 0.0"

    corn_val = (L['corn']/L['pj'] + V['corn']/V['pj'])
    pick_corn = "MÁS 9.5" if corn_val > 9.5 else "MENOS 9.5"
    
    sot_val = (L['sot']/L['pj'] + V['sot']/V['pj'])
    pick_sot = "MÁS 8.5" if sot_val > 8.5 else "MENOS 8.5"
    
    cards_val = (L['cards']/L['pj'] + V['cards']/V['pj'])
    pick_cards = "MÁS 4.5" if cards_val > 4.5 else "MENOS 4.5"

    off_val = 0
    pick_off = "N/A"
    if stats_off:
        nL = encontrar_equipo(local, list(stats_off.keys()))
        nV = encontrar_equipo(visita, list(stats_off.keys()))
        if nL and nV:
            off_val = stats_off[nL] + stats_off[nV]
            pick_off = f"{'MÁS' if off_val > 3.5 else 'MENOS'} 3.5"

    return {
        "ganador": ganador, "ah": ah_line,
        "goles_val": total_goals, "goles_pick": pick_gol,
        "corn_val": corn_val, "corn_pick": pick_corn,
        "sot_val": sot_val, "sot_pick": pick_sot,
        "cards_val": cards_val, "cards_pick": pick_cards,
        "off_val": off_val, "off_pick": pick_off,
        "score_est": f"{round(xg_h)}-{round(xg_a)}"
    }

# ==========================================
# 4. DASHBOARD
# ==========================================

st.title("🦁 YETIPS: CHAMPIONS LEAGUE EDITION 🏆")
st.markdown("---")

with st.sidebar:
    st.header("🎛️ Panel de Mando")
    liga_sel = st.selectbox("Selecciona Competición", list(LIGAS.keys()))
    st.markdown("---")
    st.info("📂 Cargar Offsides (FBref)")
    off_file = st.file_uploader("CSV Offsides", type=['csv'])

codigos = LIGAS[liga_sel]
if codigos['csv'] == "MULTI":
    st.info("🌍 Cargando datos de Europa (Champions Mode)...")

stats_auto = cargar_datos_liga(codigos['csv'])
stats_off = cargar_offsides_manual(off_file)

if not stats_auto:
    st.error("Error cargando datos.")
    st.stop()

tab1, tab2 = st.tabs(["⚽ PRONÓSTICOS", "📊 AUDITORÍA"])

with tab1:
    if st.button(f"ANALIZAR {liga_sel}", type="primary", use_container_width=True):
        with st.spinner("🧠 Procesando Inteligencia Artificial..."):
            url = f"https://api.football-data.org/v4/competitions/{codigos['api']}/matches?status=SCHEDULED"
            headers = {'X-Auth-Token': API_KEY}
            r = requests.get(url, headers=headers)
            
            if r.status_code == 200:
                matches = r.json()['matches']
                if matches:
                    # HEMOS CAMBIADO EL FORMATO A HTML PARA EVITAR ERRORES
                    tg_msg = f"🦁 <b>YETIPS - {liga_sel.upper()}</b>\n"
                    tg_msg += f"📅 {datetime.now().strftime('%d/%m')}\n\n"
                    data_display = []
                    
                    prox_matches = []
                    for m in matches:
                        match_date = datetime.strptime(m['utcDate'][:10], "%Y-%m-%d")
                        if match_date <= datetime.now() + timedelta(days=14):
                            prox_matches.append(m)

                    if not prox_matches: st.warning("No hay partidos próximos (14 días).")

                    for m in prox_matches:
                        local, visita = m['homeTeam']['name'], m['awayTeam']['name']
                        d = calcular_pronostico(local, visita, stats_auto, stats_off)
                        
                        if d:
                            tg_msg += f"🏆 <b>{local} vs {visita}</b>\n"
                            tg_msg += f"💎 Pick: {d['ganador']}\n"
                            tg_msg += f"⚖️ AH: {d['ah']}\n"
                            
                            i_gol = "🟢" if "MÁS" in d['goles_pick'] else "🔴"
                            tg_msg += f"⚽ Goles: {i_gol} {d['goles_pick']} ({d['goles_val']:.2f})\n"
                            
                            i_corn = "⛳" if "MÁS" in d['corn_pick'] else "📉"
                            tg_msg += f"⛳ Corners: {i_corn} {d['corn_pick']} ({d['corn_val']:.2f})\n"
                            
                            if d['off_pick'] != "N/A":
                                tg_msg += f"🚩 Offsides: {d['off_pick']}\n"
                                
                            tg_msg += "➖➖➖➖➖➖➖➖\n"

                            data_display.append({
                                "Partido": f"{local} vs {visita}",
                                "Ganador": d['ganador'],
                                "Hándicap": d['ah'],
                                "Goles": f"{d['goles_pick']} ({d['goles_val']:.1f})",
                                "Corners": f"{d['corn_pick']} ({d['corn_val']:.1f})",
                                "Tiros": f"{d['sot_pick']}",
                                "Tarjetas": f"{d['cards_pick']}",
                                "Offsides": d['off_pick']
                            })

                    if data_display:
                        st.dataframe(pd.DataFrame(data_display), use_container_width=True)
                        
                        # --- BOTÓN DE TELEGRAM CORREGIDO ---
                        if st.button("📲 ENVIAR REPORTE A TELEGRAM"):
                            payload = {
                                "chat_id": TG_CHAT_ID, 
                                "text": tg_msg, 
                                "parse_mode": "HTML" # CAMBIADO A HTML (MÁS SEGURO)
                            }
                            try:
                                req = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=payload)
                                if req.status_code == 200:
                                    st.success("✅ ¡Mensaje enviado con éxito a Telegram!")
                                    st.balloons()
                                else:
                                    st.error(f"❌ Error enviando mensaje: {req.text}")
                            except Exception as e:
                                st.error(f"⚠️ Error de conexión: {e}")

                else:
                    st.warning("No hay partidos programados.")

with tab2:
    st.write("📊 Auditoría de resultados pasados.")
