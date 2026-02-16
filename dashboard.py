import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import difflib

# ==========================================
# 1. CONFIGURACIÓN (TUS CLAVES)
# ==========================================

API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f"
TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
TG_CHAT_ID = "1197028422"

# --- LIGAS SOPORTADAS ---
LIGAS = {
    "🇪🇸 La Liga": {"api": "PD", "csv": "SP1"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"api": "PL", "csv": "E0"},
    "🇩🇪 Bundesliga": {"api": "BL1", "csv": "D1"},
    "🇮🇹 Serie A": {"api": "SA", "csv": "I1"},
    "🇫🇷 Ligue 1": {"api": "FL1", "csv": "F1"},
    "🇳🇱 Eredivisie": {"api": "DED", "csv": "N1"},
    "🇵🇹 Primeira Liga": {"api": "PPL", "csv": "P1"}
}

# ==========================================
# 2. FUNCIONES DE CARGA DE DATOS
# ==========================================

@st.cache_data(ttl=3600)
def cargar_datos_liga(codigo_csv):
    """
    Descarga stats automáticas (Goles, Corners, Tarjetas, Tiros)
    TEMPORADA 25/26
    """
    # CAMBIO AQUÍ: 2526 para la temporada 2025/2026
    url = f"https://www.football-data.co.uk/mmz4281/2526/{codigo_csv}.csv"
    
    try:
        df = pd.read_csv(url)
        stats = {}
        for idx, row in df.iterrows():
            # Acumulamos datos Local y Visitante
            for tipo in ['Home', 'Away']:
                team = row[f'{tipo}Team']
                if team not in stats: 
                    stats[team] = {'pj': 0, 'gf': 0, 'gc': 0, 'corn': 0, 'sot': 0}
                
                es_local = (tipo == 'Home')
                stats[team]['pj'] += 1
                stats[team]['gf'] += row['FTHG'] if es_local else row['FTAG']
                stats[team]['gc'] += row['FTAG'] if es_local else row['FTHG']
                
                # Corners y Tiros (verificamos que la columna exista)
                if 'HC' in row and pd.notna(row['HC']): 
                    c = row['HC'] if es_local else row['AC']
                    stats[team]['corn'] += c
                if 'HST' in row and pd.notna(row['HST']):
                    s = row['HST'] if es_local else row['AST']
                    stats[team]['sot'] += s
        return stats
    except Exception as e:
        st.error(f"No se pudieron descargar los datos de la 25/26 ({url}). Asegúrate de que la liga ya haya empezado. Error: {e}")
        return None

def cargar_offsides_manual(uploaded_file):
    """Procesa el CSV manual de FBref para fueras de juego"""
    if uploaded_file is None: return None
    try:
        try:
            df = pd.read_csv(uploaded_file, header=1)
            if 'Squad' not in df.columns: 
                df = pd.read_csv(uploaded_file, header=0)
        except:
            return None

        off_stats = {}
        required = ['Squad', '90s', 'Off']
        
        if all(col in df.columns for col in required):
            for _, row in df.iterrows():
                try:
                    squad = row['Squad']
                    partidos = float(row['90s'])
                    total_off = float(row['Off'])
                    if partidos > 0:
                        off_stats[squad] = total_off / partidos
                except: continue
            return off_stats
        else:
            st.warning("El CSV manual no tiene las columnas 'Squad', '90s' y 'Off'.")
            return None
    except Exception as e:
        st.error(f"Error leyendo CSV manual: {e}")
        return None

# ==========================================
# 3. LÓGICA DE CÁLCULO
# ==========================================

def encontrar_equipo(nombre_api, lista_nombres):
    """Busca el nombre más parecido en una lista"""
    match = difflib.get_close_matches(nombre_api, lista_nombres, n=1, cutoff=0.5)
    
    manual = {
        "Athletic Club": "Ath Bilbao", "Club Atlético de Madrid": "Ath Madrid",
        "Manchester United FC": "Man United", "Wolverhampton Wanderers FC": "Wolves",
        "Paris Saint-Germain FC": "Paris SG", "Bayer 04 Leverkusen": "Leverkusen",
        "Real Betis Balompié": "Betis", "Rayo Vallecano de Madrid": "Rayo Vallecano",
        "Girona FC": "Girona", "Real Sociedad de Fútbol": "Sociedad",
        "RCD Mallorca": "Mallorca", "CA Osasuna": "Osasuna",
        "Sevilla FC": "Sevilla", "Valencia CF": "Valencia",
        "Villarreal CF": "Villarreal"
    }
    
    if nombre_api in manual:
        if manual[nombre_api] in lista_nombres: return manual[nombre_api]
        match_manual = difflib.get_close_matches(manual[nombre_api], lista_nombres, n=1, cutoff=0.6)
        if match_manual: return match_manual[0]

    return match[0] if match else None

def calcular_todo(local_api, visita_api, stats_auto, stats_off):
    nom_auto_L = encontrar_equipo(local_api, list(stats_auto.keys()))
    nom_auto_V = encontrar_equipo(visita_api, list(stats_auto.keys()))
    
    if not nom_auto_L or not nom_auto_V: return None

    L = stats_auto[nom_auto_L]
    V = stats_auto[nom_auto_V]
    
    # Offsides
    off_avg = "N/A"
    if stats_off:
        nom_off_L = encontrar_equipo(local_api, list(stats_off.keys()))
        nom_off_V = encontrar_equipo(visita_api, list(stats_off.keys()))
        if nom_off_L and nom_off_V:
            off_val = stats_off[nom_off_L] + stats_off[nom_off_V]
            off_avg = round(off_val, 2)

    # xG Simplificado
    xg_h = (L['gf']/L['pj'] + V['gc']/V['pj']) / 2
    xg_a = (V['gf']/V['pj'] + L['gc']/L['pj']) / 2
    total_goals = xg_h + xg_a
    
    # Ganador
    diff = xg_h - xg_a
    if diff > 0.4: ganador = f"Gana {local_api}"
    elif diff < -0.4: ganador = f"Gana {visita_api}"
    else: ganador = "Empate / Reñido"
    
    # Handicap
    raw_h = round((diff * -1) * 2) / 2
    handicap = f"{'+' if raw_h > 0 else ''}{raw_h}"

    return {
        "ganador": ganador,
        "marcador": f"{round(xg_h)}-{round(xg_a)}",
        "handicap": handicap,
        "goles": total_goals,
        "corn": (L['corn']/L['pj'] + V['corn']/V['pj']),
        "sot": (L['sot']/L['pj'] + V['sot']/V['pj']),
        "offsides": off_avg
    }

def get_matches(api_code):
    headers = {'X-Auth-Token': API_KEY}
    url = f"https://api.football-data.org/v4/competitions/{api_code}/matches?status=SCHEDULED"
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()['matches']
        else:
            st.error(f"Error API ({r.status_code}): Verifica tu suscripción.")
            return []
    except:
        return []

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        return True
    except:
        return False

# ==========================================
# 4. INTERFAZ GRÁFICA
# ==========================================

st.set_page_config(page_title="Yetips Pro 25/26", layout="wide", page_icon="🦁")
st.title("🦁 Yetips Pro: Temporada 25/26")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configuración")
liga = st.sidebar.selectbox("Selecciona la Liga", list(LIGAS.keys()))

st.sidebar.markdown("---")
st.sidebar.write("📂 **Fueras de Juego (Opcional)**")
st.sidebar.info("Sube 'misc.csv' de FBref (Temporada 25/26) para Offsides.")
off_file = st.sidebar.file_uploader("Subir CSV de Offsides", type=['csv'])

# --- CARGA DE DATOS ---
codigos = LIGAS[liga]
with st.spinner(f"Descargando datos 25/26 de {liga}..."):
    stats_auto = cargar_datos_liga(codigos['csv'])
    stats_off = cargar_offsides_manual(off_file) if off_file else None

if stats_auto:
    st.sidebar.success(f"✅ Datos 25/26: OK")
else:
    st.sidebar.error("❌ Error descargando. Revisa si la liga tiene datos en football-data.co.uk para la 25/26.")

if stats_off: st.sidebar.success("✅ Offsides: OK")

# --- BOTÓN DE ANÁLISIS ---
st.divider()

if st.button(f"🔍 ANALIZAR PARTIDOS DE {liga.upper()}", type="primary"):
    if not stats_auto:
        st.error("Faltan datos automáticos.")
        st.stop()
        
    with st.spinner("Analizando..."):
        matches = get_matches(codigos['api'])
        
        if matches:
            res_table = []
            tg_msg = f"🦁 *YETIPS PRO - {liga.upper()} (25/26)*\n"
            tg_msg += f"📅 {datetime.now().strftime('%d/%m/%Y')}\n\n"
            
            count = 0
            for m in matches:
                if count >= 10: break # Limite 10 partidos
                
                local = m['homeTeam']['name']
                visita = m['awayTeam']['name']
                
                d = calcular_todo(local, visita, stats_auto, stats_off)
                
                if d:
                    count += 1
                    tg_msg += f"⚔️ *{local} vs {visita}*\n"
                    tg_msg += f"🏆 {d['ganador']} (AH {d['handicap']})\n"
                    tg_msg += f"🔢 Marcador: {d['marcador']}\n"
                    
                    icon_gol = "🟢" if d['goles'] > 2.5 else "🔴"
                    tg_msg += f"⚽ Goles: {icon_gol} {d['goles']:.2f}\n"
                    
                    icon_corn = "🟢" if d['corn'] > 9.5 else "🔴"
                    tg_msg += f"⛳ Corners: {icon_corn} {d['corn']:.2f}\n"
                    
                    tg_msg += f"🎯 Tiros: {d['sot']:.2f}\n"
                    
                    if d['offsides'] != "N/A":
                        off_pick = "MÁS 3.5" if d['offsides'] > 3.5 else "MENOS 3.5"
                        tg_msg += f"🚩 Offsides: {d['offsides']} ({off_pick})\n"
                        # Actualizar para tabla
                        d['off_txt'] = f"{d['offsides']} ({off_pick})"
                    else:
                        d['off_txt'] = "N/A"
                    
                    tg_msg += "------------------\n"
                    
                    res_table.append({
                        "Partido": f"{local} vs {visita}",
                        "Ganador": d['ganador'],
                        "AH": d['handicap'],
                        "Marcador": d['marcador'],
                        "Goles": f"{d['goles']:.2f}",
                        "Corners": f"{d['corn']:.2f}",
                        "Tiros": f"{d['sot']:.2f}",
                        "Offsides": d['off_txt']
                    })

            # Mostrar Resultados
            st.dataframe(pd.DataFrame(res_table), use_container_width=True)
            
            if st.button("Enviar Telegram"):
                if enviar_telegram(tg_msg): st.success("Enviado ✈️")
                else: st.error("Error Telegram")
        else:
            st.warning("No hay partidos programados.")
