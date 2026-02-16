import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import difflib

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================

API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f"
TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
TG_CHAT_ID = "1197028422"

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
# 2. FUNCIONES DE DATOS
# ==========================================

@st.cache_data(ttl=3600)
def cargar_datos_liga(codigo_csv):
    """Descarga stats 25/26"""
    url = f"https://www.football-data.co.uk/mmz4281/2526/{codigo_csv}.csv"
    try:
        df = pd.read_csv(url)
        stats = {}
        for idx, row in df.iterrows():
            for tipo in ['Home', 'Away']:
                team = row[f'{tipo}Team']
                if team not in stats: 
                    stats[team] = {'pj': 0, 'gf': 0, 'gc': 0, 'corn': 0, 'sot': 0}
                
                es_local = (tipo == 'Home')
                stats[team]['pj'] += 1
                stats[team]['gf'] += row['FTHG'] if es_local else row['FTAG']
                stats[team]['gc'] += row['FTAG'] if es_local else row['FTHG']
                
                if 'HC' in row and pd.notna(row['HC']): 
                    c = row['HC'] if es_local else row['AC']
                    stats[team]['corn'] += c
                if 'HST' in row and pd.notna(row['HST']):
                    s = row['HST'] if es_local else row['AST']
                    stats[team]['sot'] += s
        return stats
    except: return None

def cargar_offsides_manual(uploaded_file):
    if uploaded_file is None: return None
    try:
        try: df = pd.read_csv(uploaded_file, header=1)
        except: df = pd.read_csv(uploaded_file, header=0)
        
        off_stats = {}
        if 'Squad' in df.columns and 'Off' in df.columns:
            for _, row in df.iterrows():
                try:
                    squad = row['Squad']
                    # Si '90s' no existe, usamos pj=1 para normalizar (o buscar columna MP)
                    pj = float(row['90s']) if '90s' in df.columns else 1
                    off = float(row['Off'])
                    if pj > 0: off_stats[squad] = off / pj
                except: continue
            return off_stats
        return None
    except: return None

# ==========================================
# 3. MOTORES DE CÁLCULO
# ==========================================

def encontrar_equipo(nombre_api, lista_nombres):
    match = difflib.get_close_matches(nombre_api, lista_nombres, n=1, cutoff=0.5)
    manual = {
        "Athletic Club": "Ath Bilbao", "Club Atlético de Madrid": "Ath Madrid",
        "Manchester United FC": "Man United", "Wolverhampton Wanderers FC": "Wolves",
        "Paris Saint-Germain FC": "Paris SG", "Bayer 04 Leverkusen": "Leverkusen",
        "Real Betis Balompié": "Betis", "Rayo Vallecano de Madrid": "Rayo Vallecano",
        "Girona FC": "Girona", "Real Sociedad de Fútbol": "Sociedad",
        "RCD Mallorca": "Mallorca", "CA Osasuna": "Osasuna",
        "Sevilla FC": "Sevilla", "Valencia CF": "Valencia", "Villarreal CF": "Villarreal",
        "Inter Milan": "Inter", "AC Milan": "Milan"
    }
    if nombre_api in manual:
        if manual[nombre_api] in lista_nombres: return manual[nombre_api]
        match_manual = difflib.get_close_matches(manual[nombre_api], lista_nombres, n=1, cutoff=0.6)
        if match_manual: return match_manual[0]
    return match[0] if match else None

def calcular_pronostico(local, visita, stats_auto, stats_off=None):
    nom_L = encontrar_equipo(local, list(stats_auto.keys()))
    nom_V = encontrar_equipo(visita, list(stats_auto.keys()))
    
    if not nom_L or not nom_V: return None

    L = stats_auto[nom_L]
    V = stats_auto[nom_V]

    # --- xG y Ganador ---
    xg_h = (L['gf']/L['pj'] + V['gc']/V['pj']) / 2
    xg_a = (V['gf']/V['pj'] + L['gc']/L['pj']) / 2
    total_goals = xg_h + xg_a
    
    diff = xg_h - xg_a
    if diff > 0.4: ganador = f"Local ({local})"
    elif diff < -0.4: ganador = f"Visita ({visita})"
    else: ganador = "Empate"

    # --- Strings Más/Menos ---
    pick_gol = "MÁS 2.5" if total_goals > 2.5 else "MENOS 2.5"
    
    corn_val = (L['corn']/L['pj'] + V['corn']/V['pj'])
    pick_corn = "MÁS 9.5" if corn_val > 9.5 else "MENOS 9.5"

    # --- Offsides ---
    off_val = 0
    pick_off = "N/A"
    if stats_off:
        nL = encontrar_equipo(local, list(stats_off.keys()))
        nV = encontrar_equipo(visita, list(stats_off.keys()))
        if nL and nV:
            off_val = stats_off[nL] + stats_off[nV]
            pick_off = f"{'MÁS' if off_val > 3.5 else 'MENOS'} 3.5 ({off_val:.2f})"

    return {
        "ganador": ganador,
        "goles_val": total_goals,
        "goles_pick": pick_gol,
        "corn_val": corn_val,
        "corn_pick": pick_corn,
        "off_pick": pick_off,
        "score_est": f"{round(xg_h)}-{round(xg_a)}"
    }

# ==========================================
# 4. AUDITORÍA (BACKTESTING)
# ==========================================

def ejecutar_auditoria(api_code, stats_auto):
    headers = {'X-Auth-Token': API_KEY}
    
    # Rango: Últimos 30 días
    hoy = datetime.now()
    inicio = hoy - timedelta(days=30)
    
    url = f"https://api.football-data.org/v4/competitions/{api_code}/matches"
    params = {
        'status': 'FINISHED',
        'dateFrom': inicio.strftime('%Y-%m-%d'),
        'dateTo': hoy.strftime('%Y-%m-%d')
    }
    
    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200: return []
    
    matches = r.json()['matches']
    resultados = []
    
    aciertos = 0
    total = 0
    
    for m in matches:
        local = m['homeTeam']['name']
        visita = m['awayTeam']['name']
        
        # Resultado Real
        goles_real = m['score']['fullTime']['home'] + m['score']['fullTime']['away']
        
        # Predicción
        pred = calcular_pronostico(local, visita, stats_auto)
        
        if pred:
            pick = pred['goles_pick'] # "MÁS 2.5" o "MENOS 2.5"
            
            # Verificar si acertamos
            gano = False
            if "MÁS" in pick and goles_real > 2.5: gano = True
            elif "MENOS" in pick and goles_real < 2.5: gano = True
            
            if gano: aciertos += 1
            total += 1
            
            resultados.append({
                "Partido": f"{local} vs {visita}",
                "Predicción": f"{pick} (Est: {pred['goles_val']:.1f})",
                "Realidad": f"{goles_real} Goles",
                "Resultado": "✅ ACIERTO" if gano else "❌ FALLO"
            })
            
    return pd.DataFrame(resultados), aciertos, total

# ==========================================
# 5. INTERFAZ GRÁFICA
# ==========================================

st.set_page_config(page_title="Yetips Ultimate", layout="wide", page_icon="🦁")
st.title("🦁 Yetips Ultimate: Predicción + Auditoría")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configuración")
liga_sel = st.sidebar.selectbox("Liga", list(LIGAS.keys()))
codigos = LIGAS[liga_sel]

st.sidebar.markdown("---")
off_file = st.sidebar.file_uploader("📂 Offsides (FBref CSV)", type=['csv'])

# Carga de datos
stats_auto = cargar_datos_liga(codigos['csv'])
stats_off = cargar_offsides_manual(off_file)

if not stats_auto:
    st.error("Error cargando datos. Verifica conexión.")
    st.stop()

# --- PESTAÑAS PRINCIPALES ---
tab1, tab2 = st.tabs(["🔮 PRONÓSTICOS FUTUROS", "✅ AUDITORÍA (30 DÍAS)"])

# --- TAB 1: PRONÓSTICOS ---
with tab1:
    if st.button("🔄 Analizar Próximos Partidos", type="primary"):
        url = f"https://api.football-data.org/v4/competitions/{codigos['api']}/matches?status=SCHEDULED"
        headers = {'X-Auth-Token': API_KEY}
        r = requests.get(url, headers=headers)
        
        if r.status_code == 200:
            matches = r.json()['matches']
            if matches:
                tg_msg = f"🦁 *YETIPS - {liga_sel.upper()}*\n\n"
                table_data = []
                
                for m in matches[:12]:
                    local, visita = m['homeTeam']['name'], m['awayTeam']['name']
                    d = calcular_pronostico(local, visita, stats_auto, stats_off)
                    
                    if d:
                        # Iconos
                        ig = "🟢" if "MÁS" in d['goles_pick'] else "🔴"
                        ic = "🟢" if "MÁS" in d['corn_pick'] else "🔴"
                        
                        tg_msg += f"⚔️ *{local} vs {visita}*\n"
                        tg_msg += f"🏆 {d['ganador']} | 🔢 {d['score_est']}\n"
                        tg_msg += f"⚽ {ig} {d['goles_pick']} ({d['goles_val']:.2f})\n"
                        tg_msg += f"⛳ {ic} {d['corn_pick']} ({d['corn_val']:.2f})\n"
                        if d['off_pick'] != "N/A":
                            tg_msg += f"🚩 Offsides: {d['off_pick']}\n"
                        tg_msg += "---\n"
                        
                        table_data.append({
                            "Partido": f"{local} vs {visita}",
                            "Ganador": d['ganador'],
                            "Goles": f"{d['goles_pick']} ({d['goles_val']:.1f})",
                            "Corners": f"{d['corn_pick']} ({d['corn_val']:.1f})",
                            "Offsides": d['off_pick']
                        })
                
                st.dataframe(pd.DataFrame(table_data), use_container_width=True)
                if st.button("Enviar a Telegram"):
                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                  data={"chat_id": TG_CHAT_ID, "text": tg_msg, "parse_mode": "Markdown"})
                    st.success("Enviado.")
            else:
                st.info("No hay partidos programados pronto.")

# --- TAB 2: AUDITORÍA ---
with tab2:
    st.write("Verifica cómo habría funcionado el bot en los últimos 30 días.")
    if st.button("📊 Ejecutar Auditoría"):
        with st.spinner("Descargando resultados pasados y verificando..."):
            df_audit, wins, total = ejecutar_auditoria(codigos['api'], stats_auto)
            
            if total > 0:
                rate = (wins / total) * 100
                col1, col2, col3 = st.columns(3)
                col1.metric("Partidos Analizados", total)
                col2.metric("Aciertos (Goles 2.5)", wins)
                col3.metric("Win Rate", f"{rate:.1f}%")
                
                # Colorear la tabla
                def color_row(row):
                    color = '#d4edda' if row['Resultado'] == "✅ ACIERTO" else '#f8d7da'
                    return [f'background-color: {color}'] * len(row)

                st.dataframe(df_audit.style.apply(color_row, axis=1), use_container_width=True)
            else:
                st.warning("No se encontraron partidos finalizados en los últimos 30 días o hubo un error de conexión.")
