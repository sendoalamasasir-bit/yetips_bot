import streamlit as st
import pandas as pd
import requests
import math
import numpy as np
from datetime import datetime, timedelta
import difflib

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Yetips Premium Analyst", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    .stMetric {background-color: #1f2937; border: 1px solid #374151;}
    h1, h2, h3 {color: #ffd700;}
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA ---
if 'reporte_premium' not in st.session_state: st.session_state.reporte_premium = ""
if 'data_audit' not in st.session_state: st.session_state.data_audit = None

# --- CLAVES ---
API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f"
TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
TG_CHAT_ID = "1197028422"

LIGAS = {
    "🇪🇺 Champions League": {"api": "CL", "csv": "MULTI"},
    "🇪🇸 La Liga": {"api": "PD", "csv": "SP1"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"api": "PL", "csv": "E0"},
    "🇩🇪 Bundesliga": {"api": "BL1", "csv": "D1"},
    "🇮🇹 Serie A": {"api": "SA", "csv": "I1"},
    "🇫🇷 Ligue 1": {"api": "FL1", "csv": "F1"},
    "🇳🇱 Eredivisie": {"api": "DED", "csv": "N1"},
    "🇵🇹 Primeira Liga": {"api": "PPL", "csv": "P1"}
}

# ==========================================
# 2. MOTOR MATEMÁTICO AVANZADO (IA)
# ==========================================

def poisson(k, lamb):
    """Probabilidad de que ocurran k eventos dado un promedio lambda"""
    return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)

def calcular_probabilidades_exactas(xg_h, xg_a):
    """Genera matriz de marcadores exactos hasta 9 goles para sacar % 1X2"""
    max_goals = 10
    prob_matrix = np.zeros((max_goals, max_goals))
    
    for h in range(max_goals):
        for a in range(max_goals):
            prob_h = poisson(h, xg_h)
            prob_a = poisson(a, xg_a)
            prob_matrix[h][a] = prob_h * prob_a
            
    prob_home = np.sum(np.tril(prob_matrix, -1))
    prob_draw = np.sum(np.diag(prob_matrix))
    prob_away = np.sum(np.triu(prob_matrix, 1))
    
    # Probabilidades Over/Under 2.5
    prob_under_25 = 0
    for h in range(3):
        for a in range(3):
            if h + a < 2.5:
                prob_under_25 += prob_matrix[h][a]
    prob_over_25 = 1 - prob_under_25

    # Probabilidad BTTS (Ambos marcan)
    # 1 - (Prob Local 0 + Prob Visita 0 - Prob 0-0)
    prob_h0 = sum(poisson(0, xg_h) * poisson(x, xg_a) for x in range(10)) # Esto es aprox
    # Mejor cálculo directo:
    prob_btts_no = 0
    for h in range(max_goals):
        for a in range(max_goals):
            if h == 0 or a == 0:
                prob_btts_no += prob_matrix[h][a]
    prob_btts_si = 1 - prob_btts_no

    return {
        "1": prob_home * 100, "X": prob_draw * 100, "2": prob_away * 100,
        "1X": (prob_home + prob_draw) * 100, "X2": (prob_away + prob_draw) * 100,
        "12": (prob_home + prob_away) * 100,
        "Over25": prob_over_25 * 100, "Under25": prob_under_25 * 100,
        "BTTS_Si": prob_btts_si * 100, "BTTS_No": prob_btts_no * 100
    }

def determinar_estrategia(probs, diff_xg, local, visita):
    p1, px, p2 = probs['1'], probs['X'], probs['2']
    
    if p1 > 70:
        return "🪜 RETO (Challenge) / PARLAY", f"Gana {local} (Cuota baja, alta seguridad)"
    elif p2 > 70:
        return "🪜 RETO (Challenge) / PARLAY", f"Gana {visita} (Cuota baja, alta seguridad)"
    elif p1 > 45:
        return "🛡️ SIMPLE (Single)", f"Gana {local} (Stake Medio)"
    elif p2 > 45:
        return "🛡️ SIMPLE (Single)", f"Gana {visita} (Stake Medio)"
    elif probs['BTTS_Si'] > 65:
        return "🛡️ SIMPLE (Estadística)", "Ambos Equipos Marcan: SÍ"
    elif probs['Under25'] > 65:
        return "🛡️ SIMPLE (Estadística)", "Menos de 2.5 Goles"
    else:
        return "🤡 FUNBET (Riesgo Alto)", "Empate o Marcador Exacto"

# ==========================================
# 3. CARGA DE DATOS
# ==========================================
@st.cache_data(ttl=3600)
def cargar_datos_liga(codigo_csv):
    if codigo_csv == "MULTI":
        todos = ["SP1", "E0", "D1", "I1", "F1", "N1", "P1"]
        mega = {}
        for c in todos:
            s = cargar_datos_liga(c)
            if s: mega.update(s)
        return mega

    url = f"https://www.football-data.co.uk/mmz4281/2526/{codigo_csv}.csv"
    try:
        df = pd.read_csv(url)
        stats = {}
        for idx, row in df.iterrows():
            for tipo in ['Home', 'Away']:
                team = row[f'{tipo}Team']
                if team not in stats: 
                    stats[team] = {'pj':0,'gf':0,'gc':0,'corn':0,'sot':0,'cards':0}
                
                es_local = (tipo == 'Home')
                stats[team]['pj'] += 1
                stats[team]['gf'] += row['FTHG'] if es_local else row['FTAG']
                stats[team]['gc'] += row['FTAG'] if es_local else row['FTHG']
                
                # Check columnas existen
                if 'HC' in row and pd.notna(row['HC']): stats[team]['corn'] += row['HC'] if es_local else row['AC']
                if 'HST' in row and pd.notna(row['HST']): stats[team]['sot'] += row['HST'] if es_local else row['AST']
                if 'HY' in row and pd.notna(row['HY']): stats[team]['cards'] += row['HY'] if es_local else row['AY']
        return stats
    except: return None

def cargar_offsides_manual(file):
    if not file: return None
    try:
        df = pd.read_csv(file, header=1) if 'Squad' not in pd.read_csv(file, header=0).columns else pd.read_csv(file)
        off = {}
        for _, row in df.iterrows():
            if 'Squad' in row and 'Off' in row:
                 div = float(row.get('90s', 1))
                 if div > 0: off[row['Squad']] = float(row['Off']) / div
        return off
    except: return None

def encontrar_equipo(nombre_api, lista_nombres):
    manual = {
        "Sport Lisboa e Benfica": "Benfica", "Real Madrid CF": "Real Madrid",
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
        match = difflib.get_close_matches(nombre_csv, lista_nombres, n=1, cutoff=0.6)
        if match: return match[0]
    match = difflib.get_close_matches(nombre_api, lista_nombres, n=1, cutoff=0.5)
    return match[0] if match else None

# ==========================================
# 4. LÓGICA DE ANÁLISIS
# ==========================================
def analizar_partido(local, visita, stats, manual_data):
    nL = encontrar_equipo(local, list(stats.keys()))
    nV = encontrar_equipo(visita, list(stats.keys()))
    if not nL or not nV: return None

    L, V = stats[nL], stats[nV]
    
    # 1. xG Calc
    xg_h = (L['gf']/L['pj'] + V['gc']/V['pj']) / 2 * 1.05
    xg_a = (V['gf']/V['pj'] + L['gc']/L['pj']) / 2
    
    # Manual Override
    if manual_data['usar']:
        xg_h = (xg_h + manual_data['g_h']) / 2
        xg_a = (xg_a + manual_data['g_a']) / 2
    
    xg_total = xg_h + xg_a
    
    # 2. Props Calc
    corn_avg = (L['corn']/L['pj'] + V['corn']/V['pj'])
    if manual_data['usar']: corn_avg = manual_data['corn']
    
    sot_L = (L['sot']/L['pj'] + V['sot']/V['pj'])/2 * 1.1 # Ajuste leve
    sot_V = (V['sot']/V['pj'] + L['sot']/L['pj'])/2
    
    cards_avg = (L['cards']/L['pj'] + V['cards']/V['pj'])

    # 3. Probabilidades
    probs = calcular_probabilidades_exactas(xg_h, xg_a)
    
    # 4. Handicaps
    diff = xg_h - xg_a
    if diff > 1.5: ah = f"Local -1.5"
    elif diff > 0.5: ah = f"Local -0.5 (Gana)"
    elif diff > 0: ah = f"Local +0.5 (Doble Op)"
    elif diff > -0.5: ah = f"Visita +0.5 (Doble Op)"
    else: ah = f"Visita -0.5 (Gana)"

    # 5. DNB
    dnb_team = local if probs['1'] > probs['2'] else visita
    dnb_prob = probs['1'] / (probs['1']+probs['2']) * 100 if dnb_team == local else probs['2'] / (probs['1']+probs['2']) * 100

    # 6. Estrategia
    fmt, sel = determinar_estrategia(probs, diff, local, visita)

    return {
        "local": local, "visita": visita,
        "probs": probs, "xg_total": xg_total, "diff": diff,
        "ah": ah, "dnb_team": dnb_team, "dnb_prob": dnb_prob,
        "sot_L": sot_L, "sot_V": sot_V, "corn": corn_avg, "cards": cards_avg,
        "fmt": fmt, "sel": sel
    }

# ==========================================
# 5. GENERADOR DE TEXTO PREMIUM
# ==========================================
def generar_bloque_texto(d, fecha_hora, liga_nombre):
    # Iconos y formatos
    ic_1x2 = f"1({int(d['probs']['1'])}%) X({int(d['probs']['X'])}%) 2({int(d['probs']['2'])}%)"
    
    # Logica DO
    do_1x = int(d['probs']['1X'])
    do_x2 = int(d['probs']['X2'])
    
    # Pick Goles
    pick_ou = "OVER" if d['probs']['Over25'] > 50 else "UNDER"
    pick_ou_perc = int(d['probs']['Over25']) if pick_ou == "OVER" else int(d['probs']['Under25'])
    
    pick_btts = "SÍ" if d['probs']['BTTS_Si'] > 50 else "NO"
    pick_btts_perc = int(d['probs']['BTTS_Si']) if pick_btts == "SÍ" else int(d['probs']['BTTS_No'])

    txt = f"⚽ <b>{d['local'].upper()} vs {d['visita'].upper()}</b>\n"
    txt += f"📅 {fecha_hora} | 🏟️ {liga_nombre}\n"
    txt += "-----------------------------------------------------------------\n"
    txt += "1️⃣ <b>MERCADOS PRINCIPALES (Ganador):</b>\n"
    txt += f"   • 1X2: {ic_1x2}\n"
    txt += f"   • Doble Oportunidad: 1X ({do_1x}%) | X2 ({do_x2}%)\n"
    txt += f"   • Apuesta Sin Empate (DNB): {d['dnb_team']} ({int(d['dnb_prob'])}%)\n\n"
    
    txt += "2️⃣ <b>MERCADOS AVANZADOS:</b>\n"
    txt += f"   • Hándicap Asiático Sugerido: {d['ah']}\n"
    txt += f"     (Dif. Goles esperada: {d['diff']:+.2f})\n\n"
    
    txt += "3️⃣ <b>LÍNEAS DE GOL:</b>\n"
    txt += f"   • Total Goles Exactos: {d['xg_total']:.2f}\n"
    txt += f"   • Over/Under 2.5: <b>{pick_ou} ({pick_ou_perc}%)</b>\n"
    txt += f"   • Ambos Marcan (BTTS): {pick_btts} ({pick_btts_perc}%)\n\n"
    
    txt += "4️⃣ <b>ACTUACIÓN DE EQUIPO (Props):</b>\n"
    txt += f"   • Tiros a Puerta {d['local']}: {d['sot_L']:.2f} (Línea sug: {round(d['sot_L']-0.5)}.5)\n"
    txt += f"   • Tiros a Puerta {d['visita']}: {d['sot_V']:.2f} (Línea sug: {round(d['sot_V']-0.5)}.5)\n"
    txt += f"   • Córners Totales: {d['corn']:.2f}\n"
    txt += f"   • Tarjetas Totales: {d['cards']:.2f}\n\n"
    
    txt += "💡 <b>ESTRATEGIA DE APUESTA (FORMATOS):</b>\n"
    txt += f"   🎯 Formato Recomendado: <b>{d['fmt']}</b>\n"
    txt += f"   🔥 Selección: {d['sel']}\n"
    txt += "=================================================================\n\n"
    return txt

# ==========================================
# 6. INTERFAZ STREAMLIT
# ==========================================
st.title("💎 YETIPS: PREMIUM ANALYST")
st.markdown("---")

with st.sidebar:
    st.header("🎛️ Configuración")
    liga_sel = st.selectbox("Selecciona Competición", list(LIGAS.keys()))
    off_file = st.file_uploader("CSV Offsides (FBref)", type=['csv'])
    
    with st.expander("🧪 LABORATORIO MANUAL"):
        man_h_g = st.number_input("Goles Local (Exp)", 1.5, step=0.1)
        man_a_g = st.number_input("Goles Visita (Exp)", 1.0, step=0.1)
        man_corn = st.slider("Corners Esperados", 5.0, 15.0, 9.5)
        usar_manual = st.checkbox("✅ ACTIVAR DATOS MANUALES")
    
    manual_data = {'usar': usar_manual, 'g_h': man_h_g, 'g_a': man_a_g, 'corn': man_corn}

codigos = LIGAS[liga_sel]
stats = cargar_datos_liga(codigos['csv'])
stats_off = cargar_offsides_manual(off_file)

if not stats:
    st.error("⚠️ Error cargando base de datos.")
    st.stop()

# --- BOTÓN ANÁLISIS ---
if st.button(f"💎 GENERAR REPORTE PREMIUM - {liga_sel}", type="primary", use_container_width=True):
    with st.spinner("🧠 Calculando probabilidades, props y estrategias..."):
        url = f"https://api.football-data.org/v4/competitions/{codigos['api']}/matches?status=SCHEDULED"
        headers = {'X-Auth-Token': API_KEY}
        r = requests.get(url, headers=headers)
        
        if r.status_code == 200:
            matches = r.json()['matches']
            prox = [m for m in matches if datetime.strptime(m['utcDate'][:10], "%Y-%m-%d") <= datetime.now() + timedelta(days=14)]
            
            if prox:
                full_report = "💎 <b>REPORTE PREMIUM: TODOS LOS MERCADOS</b>\n"
                full_report += "   (1X2, Over/Under, Hándicaps, Props, Funbets)\n"
                full_report += "=================================================================\n\n"
                
                audit_list = []
                
                for m in prox:
                    loc = m['homeTeam']['name']
                    vis = m['awayTeam']['name']
                    dt = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
                    fecha_str = dt.strftime("%d/%m %H:%M")
                    
                    res = analizar_partido(loc, vis, stats, manual_data)
                    
                    if res:
                        # Generar bloque de texto
                        bloque = generar_bloque_texto(res, fecha_str, liga_sel)
                        full_report += bloque
                        
                        # Guardar para auditoria
                        audit_list.append({
                            "Partido": f"{loc} vs {vis}",
                            "Pick": res['sel'],
                            "Prob 1": f"{res['probs']['1']:.1f}%",
                            "Prob 2": f"{res['probs']['2']:.1f}%",
                            "xG Total": f"{res['xg_total']:.2f}",
                            "Estrategia": res['fmt']
                        })
                
                st.session_state.reporte_premium = full_report
                st.session_state.data_audit = pd.DataFrame(audit_list)
            else:
                st.warning("No hay partidos próximos.")

# --- VISUALIZACIÓN ---
tab1, tab2, tab3 = st.tabs(["📄 VISTA PREVIA REPORTE", "📝 AUDITORÍA", "🤖 DEBUG DATOS"])

with tab1:
    if st.session_state.reporte_premium:
        # Mostrar el texto tal cual se enviará, pero interpretando HTML básico para la vista
        st.markdown(st.session_state.reporte_premium.replace("\n", "  \n"), unsafe_allow_html=True)
        
        st.markdown("---")
        if st.button("📲 ENVIAR REPORTE A TELEGRAM"):
            payload = {
                "chat_id": TG_CHAT_ID, 
                "text": st.session_state.reporte_premium, 
                "parse_mode": "HTML"
            }
            try:
                # Telegram tiene límite de 4096 caracteres. Si es muy largo, lo partimos.
                if len(st.session_state.reporte_premium) > 4000:
                    parts = [st.session_state.reporte_premium[i:i+4000] for i in range(0, len(st.session_state.reporte_premium), 4000)]
                    for p in parts:
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": p, "parse_mode": "HTML"})
                    st.success("✅ Reporte largo enviado en partes.")
                else:
                    req = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=payload)
                    if req.status_code == 200:
                        st.success("✅ ¡Reporte enviado con éxito!")
                        st.balloons()
                    else:
                        st.error(f"❌ Error Telegram: {req.text}")
            except Exception as e:
                st.error(f"⚠️ Error Conexión: {e}")

with tab2:
    if st.session_state.data_audit is not None:
        st.dataframe(st.session_state.data_audit, use_container_width=True)
        csv = st.session_state.data_audit.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Excel", csv, "audit_premium.csv", "text/csv")

with tab3:
    st.write("Datos brutos cargados (Primeros 5 equipos):")
    if stats:
        st.json(list(stats.items())[:5])
