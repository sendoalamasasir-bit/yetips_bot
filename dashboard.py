import streamlit as st
import pandas as pd
import requests
import math
import numpy as np
from datetime import datetime, timedelta
import difflib
import time
from io import StringIO
# Importaciones para IA
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier

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
if 'ai_engine' not in st.session_state: st.session_state.ai_engine = None # Memoria para el modelo IA

# --- CLAVES ---
API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f"
TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
TG_CHAT_ID = "1197028422"
TEMPORADA_URL = "2526"

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
# 2. MOTOR MATEMÁTICO (MODO CLÁSICO / MANUAL)
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
# 3. MOTOR INTELIGENCIA ARTIFICIAL (NUEVO)
# ==========================================
class BettingAI:
    def __init__(self, league_code, csv_code):
        self.league_code = league_code
        self.csv_code = csv_code
        self.csv_url = f"https://www.football-data.co.uk/mmz4281/{TEMPORADA_URL}/{csv_code}.csv"
        self.models = {}
        self.team_stats = {}
        self.train_success = False

    def entrenar(self):
        try:
            # Headers para evitar bloqueos
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get(self.csv_url, headers=headers)
            if r.status_code != 200: return False
            
            df = pd.read_csv(StringIO(r.text))
            df = df.dropna(subset=['HomeTeam', 'AwayTeam', 'FTR'])
            df = df.fillna(0)
        except Exception as e:
            return False

        # --- A. Ingeniería de Datos ---
        cols_stats = ['FTHG','FTAG', 'HST','AST', 'HC','AC', 'HY','AY','HR','AR']
        
        try:
            # Comprobación de seguridad por si faltan columnas
            available_cols = [c for c in cols_stats if c in df.columns]
            if len(available_cols) < len(cols_stats): return False

            self.team_stats['home'] = df.groupby('HomeTeam')[available_cols].mean()
            self.team_stats['away'] = df.groupby('AwayTeam')[available_cols].mean()
        except:
            return False

        # --- B. Preparar Entrenamiento ---
        features, y_win, y_gh, y_ga, y_corn, y_card, y_sot_h, y_sot_a = [], [], [], [], [], [], [], []

        for i, row in df.iterrows():
            loc, vis = row['HomeTeam'], row['AwayTeam']
            
            if loc in self.team_stats['home'].index and vis in self.team_stats['away'].index:
                fv = np.concatenate([
                    self.team_stats['home'].loc[loc].values, 
                    self.team_stats['away'].loc[vis].values
                ])
                features.append(fv)
                
                res = 0 if row['FTR']=='H' else (1 if row['FTR']=='D' else 2)
                y_win.append(res)
                y_gh.append(row['FTHG']); y_ga.append(row['FTAG'])
                y_corn.append(row['HC'] + row['AC'])
                y_card.append(row['HY'] + row['AY'] + row['HR'] + row['AR'])
                y_sot_h.append(row['HST']); y_sot_a.append(row['AST'])

        if not features: return False

        X = np.array(features)
        rf_conf = {'n_estimators': 100, 'random_state': 42, 'n_jobs': -1}

        # --- C. Entrenamiento ---
        self.models['win'] = RandomForestClassifier(**rf_conf).fit(X, y_win)
        self.models['gh'] = RandomForestRegressor(**rf_conf).fit(X, y_gh)
        self.models['ga'] = RandomForestRegressor(**rf_conf).fit(X, y_ga)
        self.models['corn'] = RandomForestRegressor(**rf_conf).fit(X, y_corn)
        self.models['card'] = RandomForestRegressor(**rf_conf).fit(X, y_card)
        self.models['soth'] = RandomForestRegressor(**rf_conf).fit(X, y_sot_h)
        self.models['sota'] = RandomForestRegressor(**rf_conf).fit(X, y_sot_a)
        
        self.train_success = True
        return True

    def predecir(self, home, away):
        if not self.train_success: return None
        # Usamos la función global de encontrar equipo para mayor robustez
        h_norm = encontrar_equipo(home, list(self.team_stats['home'].index))
        a_norm = encontrar_equipo(away, list(self.team_stats['away'].index))
        
        if not h_norm or not a_norm: return None
            
        fv = np.concatenate([
            self.team_stats['home'].loc[h_norm].values, 
            self.team_stats['away'].loc[a_norm].values
        ]).reshape(1, -1)
        
        return {
            'local_norm': h_norm, 'visita_norm': a_norm,
            'probs': self.models['win'].predict_proba(fv)[0], # [Local, Empate, Visita]
            'gh': self.models['gh'].predict(fv)[0],
            'ga': self.models['ga'].predict(fv)[0],
            'corn': self.models['corn'].predict(fv)[0],
            'card': self.models['card'].predict(fv)[0],
            'soth': self.models['soth'].predict(fv)[0],
            'sota': self.models['sota'].predict(fv)[0]
        }

# ==========================================
# 4. CARGA DE DATOS Y UTILIDADES
# ==========================================
@st.cache_data(ttl=3600)
def cargar_datos_liga_manual(codigo_csv):
    """Carga clásica para el modo manual/estadístico"""
    if codigo_csv == "MULTI":
        todos = ["SP1", "E0", "D1", "I1", "F1", "N1", "P1"]
        mega = {}
        for c in todos:
            s = cargar_datos_liga_manual(c)
            if s: mega.update(s)
        return mega

    url = f"https://www.football-data.co.uk/mmz4281/{TEMPORADA_URL}/{codigo_csv}.csv"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200: return None
        
        df = pd.read_csv(StringIO(r.text))
        stats = {}
        for idx, row in df.iterrows():
            for tipo in ['Home', 'Away']:
                team = row[f'{tipo}Team']
                if pd.isna(team): continue
                if team not in stats: 
                    stats[team] = {'pj':0,'gf':0,'gc':0,'corn':0,'sot':0,'cards':0}
                
                es_local = (tipo == 'Home')
                stats[team]['pj'] += 1
                stats[team]['gf'] += row['FTHG'] if es_local else row['FTAG']
                stats[team]['gc'] += row['FTAG'] if es_local else row['FTHG']
                
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
        "Arsenal FC": "Arsenal", "Liverpool FC": "Liverpool", "Manchester City FC": "Man City",
        "RCD Mallorca": "Mallorca", "CA Osasuna": "Osasuna", "Rayo Vallecano de Madrid": "Vallecano"
    }
    if nombre_api in manual:
        nombre_csv = manual[nombre_api]
        if nombre_csv in lista_nombres: return nombre_csv
        match = difflib.get_close_matches(nombre_csv, lista_nombres, n=1, cutoff=0.6)
        if match: return match[0]
    match = difflib.get_close_matches(nombre_api, lista_nombres, n=1, cutoff=0.5)
    return match[0] if match else None

# ==========================================
# 5. LÓGICA DE ANÁLISIS (CLASICA VS IA)
# ==========================================

# --- A. LÓGICA CLÁSICA / MANUAL ---
def analizar_partido_manual(local, visita, stats, manual_data):
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
    
    sot_L = (L['sot']/L['pj'] + V['sot']/V['pj'])/2 * 1.1
    sot_V = (V['sot']/V['pj'] + L['sot']/L['pj'])/2
    cards_avg = (L['cards']/L['pj'] + V['cards']/V['pj'])

    # 3. Probabilidades
    probs = calcular_probabilidades_exactas(xg_h, xg_a)
    
    # 4. Handicaps y Estrategia
    diff = xg_h - xg_a
    if diff > 1.5: ah = f"Local -1.5"
    elif diff > 0.5: ah = f"Local -0.5 (Gana)"
    elif diff > 0: ah = f"Local +0.5 (Doble Op)"
    elif diff > -0.5: ah = f"Visita +0.5 (Doble Op)"
    else: ah = f"Visita -0.5 (Gana)"

    dnb_team = local if probs['1'] > probs['2'] else visita
    dnb_prob = probs['1'] / (probs['1']+probs['2']) * 100 if dnb_team == local else probs['2'] / (probs['1']+probs['2']) * 100
    fmt, sel = determinar_estrategia(probs, diff, local, visita)

    return {
        "local": local, "visita": visita,
        "probs": probs, "xg_total": xg_total, "diff": diff,
        "ah": ah, "dnb_team": dnb_team, "dnb_prob": dnb_prob,
        "sot_L": sot_L, "sot_V": sot_V, "corn": corn_avg, "cards": cards_avg,
        "fmt": fmt, "sel": sel, "metodo": "MANUAL/POISSON"
    }

# --- B. LÓGICA IA (RANDOM FOREST) ---
def analizar_partido_ia(cerebro_ai, local, visita):
    pred = cerebro_ai.predecir(local, visita)
    if not pred: return None
    
    p1, pX, p2 = pred['probs'][0]*100, pred['probs'][1]*100, pred['probs'][2]*100
    xg_h, xg_a = pred['gh'], pred['ga']
    xg_total = xg_h + xg_a
    diff = xg_h - xg_a
    
    # Reconstrucción de estructura compatible con el generador de texto
    probs = {
        "1": p1, "X": pX, "2": p2,
        "1X": p1+pX, "X2": p2+pX,
        "Over25": 100 if xg_total > 2.65 else 30, # Estimación basada en xG IA
        "Under25": 100 if xg_total < 2.35 else 30,
        "BTTS_Si": 100 if (xg_h > 0.8 and xg_a > 0.8) else 40,
        "BTTS_No": 100 if (xg_h < 0.8 or xg_a < 0.8) else 40
    }
    
    # Estrategia IA
    if p1 > 55: sel = f"Gana {local}"
    elif p2 > 55: sel = f"Gana {visita}"
    elif xg_total > 2.7: sel = "Over 2.5 Goles"
    else: sel = "Empate o Baja"
    
    ah = f"{local} -0.5" if diff > 0.5 else (f"{visita} -0.5" if diff < -0.5 else "Igualdad")
    dnb_team = local if p1 > p2 else visita
    dnb_prob = p1/(p1+p2)*100
    
    return {
        "local": local, "visita": visita,
        "probs": probs, "xg_total": xg_total, "diff": diff,
        "ah": ah, "dnb_team": dnb_team, "dnb_prob": dnb_prob,
        "sot_L": pred['soth'], "sot_V": pred['sota'], 
        "corn": pred['corn'], "cards": pred['card'],
        "fmt": "🤖 INTELIGENCIA ARTIFICIAL", "sel": sel, "metodo": "IA (RANDOM FOREST)"
    }

# ==========================================
# 6. GENERADOR DE TEXTO (UNIFICADO)
# ==========================================
def generar_bloque_texto(d, fecha_hora, liga_nombre):
    ic_1x2 = f"1({int(d['probs']['1'])}%) X({int(d['probs']['X'])}%) 2({int(d['probs']['2'])}%)"
    do_1x = int(d['probs']['1X'])
    do_x2 = int(d['probs']['X2'])
    
    pick_ou = "OVER" if d['probs']['Over25'] > 50 else "UNDER"
    pick_ou_perc = int(d['probs']['Over25']) if pick_ou == "OVER" else int(d['probs']['Under25'])
    pick_btts = "SÍ" if d['probs']['BTTS_Si'] > 50 else "NO"
    pick_btts_perc = int(d['probs']['BTTS_Si']) if pick_btts == "SÍ" else int(d['probs']['BTTS_No'])

    txt = f"⚽ <b>{d['local'].upper()} vs {d['visita'].upper()}</b>\n"
    txt += f"📅 {fecha_hora} | 🏟️ {liga_nombre} | ⚙️ {d['metodo']}\n"
    txt += "-----------------------------------------------------------------\n"
    txt += "1️⃣ <b>MERCADOS PRINCIPALES:</b>\n"
    txt += f"   • 1X2: {ic_1x2}\n"
    txt += f"   • Doble Op: 1X ({do_1x}%) | X2 ({do_x2}%)\n"
    txt += f"   • Sin Empate: {d['dnb_team']} ({int(d['dnb_prob'])}%)\n\n"
    
    txt += "2️⃣ <b>Goles y Hándicap:</b>\n"
    txt += f"   • Goles Esp: {d['xg_total']:.2f} (Dif: {d['diff']:+.2f})\n"
    txt += f"   • Over/Under 2.5: <b>{pick_ou} ({pick_ou_perc}%)</b>\n"
    txt += f"   • Hándicap: {d['ah']}\n\n"
    
    txt += "3️⃣ <b>PROPS (Estadísticas):</b>\n"
    txt += f"   • Tiros Puerta: {d['local']} ({d['sot_L']:.1f}) | {d['visita']} ({d['sot_V']:.1f})\n"
    txt += f"   • Córners Esp: {d['corn']:.1f}\n"
    txt += f"   • Tarjetas Esp: {d['cards']:.1f}\n\n"
    
    txt += "💡 <b>CONCLUSIÓN:</b>\n"
    txt += f"   🎯 Formato: <b>{d['fmt']}</b>\n"
    txt += f"   🔥 Selección: {d['sel']}\n"
    txt += "=================================================================\n\n"
    return txt

# ==========================================
# 7. INTERFAZ STREAMLIT
# ==========================================
st.title("💎 YETIPS: DUAL ENGINE ANALYST")
st.markdown("---")

with st.sidebar:
    st.header("🎛️ Configuración")
    liga_sel = st.selectbox("Selecciona Competición", list(LIGAS.keys()))
    
    # --- SELECTOR DE MODO ---
    mode = st.radio("Motor de Análisis", ["💎 Estadístico / Manual", "🤖 Inteligencia Artificial"], index=0)
    
    off_file = st.file_uploader("CSV Offsides (FBref) - Opcional", type=['csv'])
    
    # SOLO MOSTRAR LABORATORIO SI ESTÁ EN MODO MANUAL
    manual_data = {'usar': False, 'g_h': 0, 'g_a': 0, 'corn': 0}
    if mode == "💎 Estadístico / Manual":
        with st.expander("🧪 LABORATORIO MANUAL"):
            man_h_g = st.number_input("Goles Local (Exp)", 1.5, step=0.1)
            man_a_g = st.number_input("Goles Visita (Exp)", 1.0, step=0.1)
            man_corn = st.slider("Corners Esperados", 5.0, 15.0, 9.5)
            usar_manual = st.checkbox("✅ ACTIVAR DATOS MANUALES")
            manual_data = {'usar': usar_manual, 'g_h': man_h_g, 'g_a': man_a_g, 'corn': man_corn}
    else:
        st.info("ℹ️ El modo IA utiliza algoritmos de Random Forest y no admite modificaciones manuales de goles.")

codigos = LIGAS[liga_sel]

# --- BOTÓN ANÁLISIS ---
if st.button(f"🚀 GENERAR REPORTE ({mode})", type="primary", use_container_width=True):
    
    # 1. Preparar Motor
    stats_manual = None
    cerebro_ia = None
    
    with st.spinner(f"Cargando motor {mode}..."):
        if mode == "💎 Estadístico / Manual":
            stats_manual = cargar_datos_liga_manual(codigos['csv'])
            if not stats_manual:
                st.error("Error cargando base de datos CSV Manual.")
                st.stop()
        else:
            # Modo IA
            cerebro_ia = BettingAI(codigos['api'], codigos['csv'])
            if not cerebro_ia.entrenar():
                st.error("Error entrenando la IA. Revisa la conexión o la liga.")
                st.stop()

    # 2. Obtener Partidos
    with st.spinner("Analizando partidos..."):
        url = f"https://api.football-data.org/v4/competitions/{codigos['api']}/matches?status=SCHEDULED"
        headers = {'X-Auth-Token': API_KEY}
        r = requests.get(url, headers=headers)
        
        if r.status_code == 200:
            matches = r.json()['matches']
            prox = [m for m in matches if datetime.strptime(m['utcDate'][:10], "%Y-%m-%d") <= datetime.now() + timedelta(days=10)]
            
            if prox:
                full_report = f"💎 <b>REPORTE {mode.upper()}</b>\n"
                full_report += f"📅 {datetime.now().strftime('%d/%m %H:%M')}\n"
                full_report += "=================================================================\n\n"
                
                audit_list = []
                
                for m in prox:
                    loc = m['homeTeam']['name']
                    vis = m['awayTeam']['name']
                    dt = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
                    fecha_str = dt.strftime("%d/%m %H:%M")
                    
                    # --- BIFURCACIÓN DE LÓGICA ---
                    res = None
                    if mode == "💎 Estadístico / Manual":
                        res = analizar_partido_manual(loc, vis, stats_manual, manual_data)
                    else:
                        res = analizar_partido_ia(cerebro_ia, loc, vis)
                    
                    if res:
                        bloque = generar_bloque_texto(res, fecha_str, liga_sel)
                        full_report += bloque
                        
                        audit_list.append({
                            "Fecha": fecha_str,
                            "Partido": f"{loc} vs {vis}",
                            "Pick": res['sel'],
                            "1 %": f"{res['probs']['1']:.1f}",
                            "2 %": f"{res['probs']['2']:.1f}",
                            "xG": f"{res['xg_total']:.2f}",
                            "Metodo": res['metodo']
                        })
                
                st.session_state.reporte_premium = full_report
                st.session_state.data_audit = pd.DataFrame(audit_list)
            else:
                st.warning("No hay partidos próximos (7 días).")
        else:
            st.error(f"Error API: {r.status_code}")

# --- VISUALIZACIÓN ---
tab1, tab2, tab3 = st.tabs(["📄 VISTA PREVIA REPORTE", "📝 AUDITORÍA", "🤖 DEBUG"])

with tab1:
    if st.session_state.reporte_premium:
        st.markdown(st.session_state.reporte_premium.replace("\n", "  \n"), unsafe_allow_html=True)
        st.markdown("---")
        if st.button("📲 ENVIAR A TELEGRAM"):
            # Lógica envío (fragmentado si es largo)
            if len(st.session_state.reporte_premium) > 4000:
                parts = [st.session_state.reporte_premium[i:i+4000] for i in range(0, len(st.session_state.reporte_premium), 4000)]
                for p in parts:
                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": p, "parse_mode": "HTML"})
            else:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": st.session_state.reporte_premium, "parse_mode": "HTML"})
            st.success("Enviado.")

with tab2:
    if st.session_state.data_audit is not None:
        st.dataframe(st.session_state.data_audit, use_container_width=True)
        st.download_button("📥 Descargar Excel", st.session_state.data_audit.to_csv(index=False).encode('utf-8'), "audit.csv", "text/csv")

with tab3:
    st.info("Sistema funcionando.")
    if mode == "🤖 Inteligencia Artificial":
        st.write("El modelo IA usa RandomForest con 100 estimadores. Entrena en tiempo real con datos de la temporada actual.")
