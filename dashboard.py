import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime, timedelta
import difflib

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Yetips IA Ultimate", layout="wide", page_icon="🧠")

# Estilos CSS Dark Mode Pro
st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    .stMetric {background-color: #1f2937; padding: 15px; border-radius: 10px; border: 1px solid #374151;}
    h1, h2, h3 {color: #ffd700;}
    .stDataFrame {border: 1px solid #374151;}
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZAR MEMORIA (Session State) ---
if 'datos_ia' not in st.session_state: st.session_state.datos_ia = None
if 'datos_clasico' not in st.session_state: st.session_state.datos_clasico = None
if 'mensaje_telegram' not in st.session_state: st.session_state.mensaje_telegram = ""

# --- TUS CLAVES (NO BORRAR) ---
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
# 2. MOTOR MATEMÁTICO (IA POISSON) 🧠
# ==========================================

def calcular_poisson(esperado, k):
    """Probabilidad de ocurrencia de k eventos dado un promedio esperado"""
    return (math.exp(-esperado) * (esperado ** k)) / math.factorial(k)

def simular_probabilidad_over(xg_total, linea):
    """Calcula % REAL de superar una línea usando Poisson"""
    prob_under = 0
    # Sumamos prob de 0, 1... hasta linea (inclusivo para el under)
    # Ej: Para Over 2.5, sumamos 0, 1, 2. La inversa es la probabilidad de > 2.5
    for k in range(int(math.floor(linea)) + 1): 
        prob_under += calcular_poisson(xg_total, k)
    return max(0, min(100, (1 - prob_under) * 100))

def determinar_linea_gol_inteligente(xg):
    """Lógica difusa para determinar el tipo de partido"""
    if xg >= 3.60: return "MÁS 3.0/3.5", "🔥 PARTIDO DE GOLPES", 3.5
    elif xg >= 2.90: return "MÁS 2.5/3.0", "✅ TENDENCIA OVER", 2.5
    elif xg >= 2.55: return "MÁS 2.5 (Justo)", "⚠️ OVER AJUSTADO", 2.5
    elif xg <= 1.90: return "MENOS 2.5", "🧊 PARTIDO CERRADO", 2.5
    elif xg <= 2.30: return "MENOS 3.0", "🛡️ DEFENSA FUERTE", 3.0
    else: return "NO BET (Rango 2-3)", "⚖️ EQUILIBRADO", 2.5

def determinar_ganador_handicap(xg_h, xg_a, local, visita):
    """Calcula AH basado en diferencia de poder (xG diff)"""
    diff = xg_h - xg_a
    abs_diff = abs(diff)
    lado = local if diff > 0 else visita
    
    if abs_diff >= 1.5: return f"GANA {lado} (-1.5 AH)", 5
    elif abs_diff >= 1.0: return f"GANA {lado} (-1.0 AH)", 4
    elif abs_diff >= 0.6: return f"GANA {lado} (-0.5 Directo)", 3
    elif abs_diff >= 0.2: return f"{lado} (DNB / Sin Empate)", 2
    else: return "EMPATE / DOBLE OPORTUNIDAD", 1

# ==========================================
# 3. CARGA DE DATOS Y UTILIDADES
# ==========================================

@st.cache_data(ttl=3600)
def cargar_datos_liga(codigo_csv):
    if codigo_csv == "MULTI":
        todos_codigos = ["SP1", "E0", "D1", "I1", "F1", "N1", "P1"]
        mega_stats = {}
        for c in todos_codigos:
            s = cargar_datos_liga(c)
            if s: mega_stats.update(s)
        return mega_stats

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

def encontrar_equipo(nombre_api, lista_nombres):
    manual = {
        "Sport Lisboa e Benfica": "Benfica", "Real Madrid CF": "Real Madrid",
        "Sporting Clube de Portugal": "Sp Portugal", "PSV Eindhoven": "PSV Eindhoven",
        "Athletic Club": "Ath Bilbao", "Club Atlético de Madrid": "Ath Madrid",
        "Manchester United FC": "Man United", "Paris Saint-Germain FC": "Paris SG", 
        "Bayer 04 Leverkusen": "Leverkusen", "Real Betis Balompié": "Betis", 
        "Inter Milan": "Inter", "AC Milan": "Milan", "FC Barcelona": "Barcelona", 
        "FC Bayern München": "Bayern Munich", "Lille OSC": "Lille", 
        "Aston Villa FC": "Aston Villa", "RB Leipzig": "Leipzig",
        "Arsenal FC": "Arsenal", "Liverpool FC": "Liverpool", "Manchester City FC": "Man City"
    }
    if nombre_api in manual:
        nombre_csv = manual[nombre_api]
        if nombre_csv in lista_nombres: return nombre_csv
        match_manual = difflib.get_close_matches(nombre_csv, lista_nombres, n=1, cutoff=0.6)
        if match_manual: return match_manual[0]
    match = difflib.get_close_matches(nombre_api, lista_nombres, n=1, cutoff=0.5)
    return match[0] if match else None

# ==========================================
# 4. LÓGICA DE PRONÓSTICO (HÍBRIDA)
# ==========================================

def analizar_partido(local, visita, stats_auto, stats_off, manual_data):
    # Recuperar datos base
    nom_L = encontrar_equipo(local, list(stats_auto.keys()))
    nom_V = encontrar_equipo(visita, list(stats_auto.keys()))
    if not nom_L or not nom_V: return None

    L, V = stats_auto[nom_L], stats_auto[nom_V]
    
    # --- MÉTRICAS PER 90 (BASE PARA IA) ---
    gf_90_L = L['gf']/L['pj']
    ga_90_L = L['gc']/L['pj']
    gf_90_V = V['gf']/V['pj']
    ga_90_V = V['gc']/V['pj']
    
    # 1. CÁLCULO xG (PROMEDIO CRUZADO)
    xg_h = (gf_90_L + ga_90_V) / 2 * 1.05 # +5% Factor Local
    xg_a = (gf_90_V + ga_90_L) / 2
    
    # 2. LABORATORIO MANUAL (Sobrescritura)
    if manual_data and manual_data['usar']:
        xg_h = (xg_h + manual_data['g_h']) / 2
        xg_a = (xg_a + manual_data['g_a']) / 2

    xg_total = xg_h + xg_a
    
    # --- CÁLCULOS IA POISSON ---
    pick_gol_txt, etiqueta_gol, linea_ref = determinar_linea_gol_inteligente(xg_total)
    prob_exito = simular_probabilidad_over(xg_total, 2.5) # Prob base Over 2.5
    
    ganador_ia, stake_ia = determinar_ganador_handicap(xg_h, xg_a, local, visita)
    
    # --- CÁLCULOS CLÁSICOS (PARA COMPARAR) ---
    corn_val = (L['corn']/L['pj'] + V['corn']/V['pj'])
    if manual_data and manual_data['usar']: corn_val = manual_data['corn']
    
    off_val = 0
    pick_off = "N/A"
    if stats_off:
        nL_off = encontrar_equipo(local, list(stats_off.keys()))
        nV_off = encontrar_equipo(visita, list(stats_off.keys()))
        if nL_off and nV_off:
            off_val = stats_off[nL_off] + stats_off[nV_off]
            pick_off = f"{'MÁS' if off_val > 3.5 else 'MENOS'} 3.5"

    return {
        "equipo_L": local, "equipo_V": visita,
        "xg_h": xg_h, "xg_a": xg_a, "xg_total": xg_total,
        # IA Output
        "ia_pick_gol": pick_gol_txt, "ia_tag": etiqueta_gol,
        "ia_prob": prob_exito, "ia_ganador": ganador_ia,
        # Clásico Output
        "corn_val": corn_val, "off_pick": pick_off
    }

# ==========================================
# 5. INTERFAZ Y DASHBOARD
# ==========================================

st.title("🧠 YETIPS: IA + MATEMÁTICAS 🦁")
st.markdown("---")

# --- SIDEBAR ---
with st.sidebar:
    st.header("🎛️ Configuración")
    liga_sel = st.selectbox("Competición", list(LIGAS.keys()))
    off_file = st.file_uploader("CSV Offsides (FBref)", type=['csv'])
    
    with st.expander("🧪 LABORATORIO (Ajuste Manual)"):
        st.caption("Sobrescribe los datos del algoritmo")
        man_h_g = st.number_input("Goles Local", 1.5, step=0.1)
        man_a_g = st.number_input("Goles Visita", 1.0, step=0.1)
        man_corn = st.slider("Corners Esperados", 5.0, 15.0, 9.5)
        usar_manual = st.checkbox("✅ ACTIVAR DATOS MANUALES")
        
    manual_data = {'usar': usar_manual, 'g_h': man_h_g, 'g_a': man_a_g, 'corn': man_corn}

codigos = LIGAS[liga_sel]
stats_auto = cargar_datos_liga(codigos['csv'])
stats_off = cargar_offsides_manual(off_file)

if not stats_auto:
    st.error("⚠️ Error cargando base de datos. Intenta más tarde.")
    st.stop()

# --- BOTÓN DE ANÁLISIS ---
if st.button(f"🚀 ANALIZAR {liga_sel} CON IA", type="primary", use_container_width=True):
    with st.spinner("🤖 La IA está simulando los partidos con Poisson..."):
        url = f"https://api.football-data.org/v4/competitions/{codigos['api']}/matches?status=SCHEDULED"
        headers = {'X-Auth-Token': API_KEY}
        r = requests.get(url, headers=headers)
        
        if r.status_code == 200:
            matches = r.json()['matches']
            prox_matches = [m for m in matches if datetime.strptime(m['utcDate'][:10], "%Y-%m-%d") <= datetime.now() + timedelta(days=14)]
            
            if prox_matches:
                data_ia = []
                data_clasico = []
                tg_msg = f"🦁 <b>YETIPS IA PRO - {liga_sel}</b>\n📅 {datetime.now().strftime('%d/%m')}\n\n"
                
                for m in prox_matches:
                    loc, vis = m['homeTeam']['name'], m['awayTeam']['name']
                    res = analizar_partido(loc, vis, stats_auto, stats_off, manual_data)
                    
                    if res:
                        # LOGICA TELEGRAM (Usamos la IA porque es mejor)
                        icon_prob = "🟢" if res['ia_prob'] > 58 else ("🟡" if res['ia_prob'] > 50 else "🔴")
                        tg_msg += f"🏆 <b>{loc} vs {vis}</b>\n"
                        tg_msg += f"🧠 IA: {res['ia_pick_gol']} ({res['ia_prob']:.1f}%)\n"
                        tg_msg += f"🏷️ Tipo: {res['ia_tag']} {icon_prob}\n"
                        tg_msg += f"💎 Pick: {res['ia_ganador']}\n"
                        tg_msg += f"⛳ Corners: {'MÁS' if res['corn_val']>9.5 else 'MENOS'} 9.5 ({res['corn_val']:.1f})\n"
                        if res['off_pick'] != "N/A": tg_msg += f"🚩 Offsides: {res['off_pick']}\n"
                        tg_msg += "➖➖➖➖➖➖➖➖\n"

                        # DATA IA
                        data_ia.append({
                            "Partido": f"{loc} vs {vis}",
                            "xG Total": f"{res['xg_total']:.2f}",
                            "Pronóstico Gol": res['ia_pick_gol'],
                            "Probabilidad": f"{res['ia_prob']:.1f}%",
                            "Etiqueta": res['ia_tag'],
                            "Ganador/AH": res['ia_ganador']
                        })
                        
                        # DATA CLASICA
                        data_clasico.append({
                            "Partido": f"{loc} vs {vis}",
                            "Goles Esperados": f"{res['xg_total']:.2f}",
                            "Corners Esp": f"{res['corn_val']:.1f}",
                            "Offsides": res['off_pick']
                        })

                st.session_state.datos_ia = pd.DataFrame(data_ia)
                st.session_state.datos_clasico = pd.DataFrame(data_clasico)
                st.session_state.mensaje_telegram = tg_msg
            else:
                st.warning("No hay partidos próximos programados.")
        else:
            st.error(f"Error API: {r.status_code}")

# --- VISUALIZACIÓN DE RESULTADOS ---
if st.session_state.datos_ia is not None:
    
    tab_ia, tab_clasico, tab_audit = st.tabs(["🤖 PREDICCIONES IA (POISSON)", "📊 MÉTODO CLÁSICO", "📝 AUDITORÍA"])
    
    with tab_ia:
        st.subheader("Resultados del Motor Matemático")
        st.caption("Este modelo utiliza la distribución de Poisson para calcular probabilidades reales.")
        st.dataframe(st.session_state.datos_ia, use_container_width=True, hide_index=True)
        
    with tab_clasico:
        st.subheader("Estadísticas Promedio Simple")
        st.dataframe(st.session_state.datos_clasico, use_container_width=True, hide_index=True)
        
    with tab_audit:
        st.subheader("📁 Auditoría y Exportación")
        st.write("Historial de análisis generado en esta sesión.")
        if st.session_state.datos_ia is not None:
            # Convertir a CSV para descargar
            csv = st.session_state.datos_ia.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Pronósticos en Excel/CSV",
                data=csv,
                file_name='pronosticos_ia.csv',
                mime='text/csv',
            )
            st.info("Guarda este archivo para verificar los aciertos mañana.")

    # --- BOTÓN TELEGRAM (FUERA DE LAS TABS) ---
    st.markdown("---")
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("📲 ENVIAR REPORTE IA A TELEGRAM"):
            payload = {
                "chat_id": TG_CHAT_ID, 
                "text": st.session_state.mensaje_telegram, 
                "parse_mode": "HTML"
            }
            try:
                req = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=payload)
                if req.status_code == 200:
                    st.success("✅ ¡Reporte enviado!")
                    st.balloons()
                else:
                    st.error(f"❌ Error Telegram: {req.text}")
            except Exception as e:
                st.error(f"⚠️ Error Conexión: {e}")
