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
    .stAlert {background-color: #1e1e1e; color: #00ff00; border: 1px solid #00ff00;}
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA ---
if 'reporte_premium' not in st.session_state: st.session_state.reporte_premium = ""
if 'data_audit' not in st.session_state: st.session_state.data_audit = None
if 'ai_engine' not in st.session_state: st.session_state.ai_engine = None

# --- CLAVES ---
API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f" # Football-Data
ODDS_API_KEY = "0be5c934e5b9dd3025a98f641e31dd41" # The-Odds-API (TU CLAVE)
TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
TG_CHAT_ID = "1197028422"
TEMPORADA_URL = "2526"

LIGAS = {
    "🇪🇺 Champions League": {"api": "CL", "csv": "MULTI", "odds": "soccer_uefa_champs_league"},
    "🇪🇸 La Liga": {"api": "PD", "csv": "SP1", "odds": "soccer_spain_la_liga"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"api": "PL", "csv": "E0", "odds": "soccer_epl"},
    "🇩🇪 Bundesliga": {"api": "BL1", "csv": "D1", "odds": "soccer_germany_bundesliga"},
    "🇮🇹 Serie A": {"api": "SA", "csv": "I1", "odds": "soccer_italy_serie_a"},
    "🇫🇷 Ligue 1": {"api": "FL1", "csv": "F1", "odds": "soccer_france_ligue_one"},
    "🇳🇱 Eredivisie": {"api": "DED", "csv": "N1", "odds": "soccer_netherlands_eredivisie"},
    "🇵🇹 Primeira Liga": {"api": "PPL", "csv": "P1", "odds": "soccer_portugal_primeira_liga"},
    "🇧🇪 Jupiler Pro League": {"api": "BJL", "csv": "B1", "odds": "soccer_belgium_first_div"},
    "🇬🇷 Super League": {"api": "G1", "csv": "G1", "odds": "soccer_greece_super_league"},
    "🇹🇷 Süper Lig": {"api": "T1", "csv": "T1", "odds": "soccer_turkey_super_league"},
    "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Premiership": {"api": "SC0", "csv": "SC0", "odds": "soccer_spl"}
}

# ==========================================
# 2. MOTOR MATEMÁTICO (MODO CLÁSICO / MANUAL)
# ==========================================

def poisson(k, lamb):
    return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)

def calcular_probabilidades_exactas(xg_h, xg_a):
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
    
    prob_under_25 = 0
    for h in range(3):
        for a in range(3):
            if h + a < 2.5:
                prob_under_25 += prob_matrix[h][a]
    prob_over_25 = 1 - prob_under_25

    prob_btts_no = 0
    for h in range(max_goals):
        for a in range(max_goals):
            if h == 0 or a == 0:
                prob_btts_no += prob_matrix[h][a]
    prob_btts_si = 1 - prob_btts_no

    return {
        "1": prob_home * 100, "X": prob_draw * 100, "2": prob_away * 100,
        "1X": (prob_home + prob_draw) * 100, "X2": (prob_away + prob_draw) * 100,
        "Over25": prob_over_25 * 100, "Under25": prob_under_25 * 100,
        "BTTS_Si": prob_btts_si * 100, "BTTS_No": prob_btts_no * 100
    }

def determinar_estrategia(probs, diff_xg, local, visita):
    p1, p2 = probs['1'], probs['2']
    if p1 > 70: return "🪜 RETO/PARLAY", f"Gana {local}"
    elif p2 > 70: return "🪜 RETO/PARLAY", f"Gana {visita}"
    elif p1 > 45: return "🛡️ SIMPLE", f"Gana {local}"
    elif p2 > 45: return "🛡️ SIMPLE", f"Gana {visita}"
    elif probs['BTTS_Si'] > 65: return "🛡️ SIMPLE", "Ambos Marcan: SÍ"
    elif probs['Under25'] > 65: return "🛡️ SIMPLE", "Menos de 2.5 Goles"
    else: return "🤡 FUNBET", "Empate"

# ==========================================
# 3. MOTOR INTELIGENCIA ARTIFICIAL
# ==========================================
class BettingAI:
    def __init__(self, league_code, csv_code):
        self.csv_url = f"https://www.football-data.co.uk/mmz4281/{TEMPORADA_URL}/{csv_code}.csv"
        # Si es multi, usamos E0 como base para entrenamiento genérico si falla la carga específica
        if "MULTI" in csv_code: 
             self.csv_url = f"https://www.football-data.co.uk/mmz4281/{TEMPORADA_URL}/E0.csv"
        self.models = {}
        self.team_stats = {}
        self.train_success = False

    def entrenar(self):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(self.csv_url, headers=headers)
            if r.status_code != 200: return False
            
            df = pd.read_csv(StringIO(r.text))
            df = df.dropna(subset=['HomeTeam', 'AwayTeam', 'FTR']).fillna(0)
            
            # AÑADIDO: HS y AS para Tiros Totales
            cols = ['FTHG','FTAG', 'HST','AST', 'HS', 'AS', 'HC','AC', 'HY','AY','HR','AR']
            actual_cols = [c for c in cols if c in df.columns]
            
            self.team_stats['home'] = df.groupby('HomeTeam')[actual_cols].mean()
            self.team_stats['away'] = df.groupby('AwayTeam')[actual_cols].mean()
            
            features, y_win, y_gh, y_ga, y_corn, y_card = [],[],[],[],[],[]
            y_sot_h, y_sot_a, y_shot_h, y_shot_a = [],[],[],[] # Arrays para tiros

            for i, row in df.iterrows():
                if row['HomeTeam'] in self.team_stats['home'].index and row['AwayTeam'] in self.team_stats['away'].index:
                    fv = np.concatenate([self.team_stats['home'].loc[row['HomeTeam']].values, self.team_stats['away'].loc[row['AwayTeam']].values])
                    features.append(fv)
                    y_win.append(0 if row['FTR']=='H' else (1 if row['FTR']=='D' else 2))
                    y_gh.append(row['FTHG']); y_ga.append(row['FTAG'])
                    y_corn.append(row['HC']+row['AC'])
                    y_card.append(row['HY']+row['AY']+row['HR']+row['AR'])
                    
                    # Tiros Puerta
                    y_sot_h.append(row.get('HST',0)); y_sot_a.append(row.get('AST',0))
                    # Tiros Totales (NUEVO)
                    y_shot_h.append(row.get('HS',0)); y_shot_a.append(row.get('AS',0))

            if not features: return False
            X = np.array(features)
            rf = {'n_estimators': 100, 'random_state': 42, 'n_jobs': -1}
            
            self.models['win'] = RandomForestClassifier(**rf).fit(X, y_win)
            self.models['gh'] = RandomForestRegressor(**rf).fit(X, y_gh)
            self.models['ga'] = RandomForestRegressor(**rf).fit(X, y_ga)
            self.models['corn'] = RandomForestRegressor(**rf).fit(X, y_corn)
            self.models['card'] = RandomForestRegressor(**rf).fit(X, y_card)
            self.models['soth'] = RandomForestRegressor(**rf).fit(X, y_sot_h)
            self.models['sota'] = RandomForestRegressor(**rf).fit(X, y_sot_a)
            # Modelos Tiros Totales
            self.models['shoth'] = RandomForestRegressor(**rf).fit(X, y_shot_h)
            self.models['shota'] = RandomForestRegressor(**rf).fit(X, y_shot_a)
            
            self.train_success = True
            return True
        except Exception as e:
            return False

    def predecir(self, home, away):
        if not self.train_success: return None
        h_n = encontrar_equipo(home, list(self.team_stats['home'].index))
        a_n = encontrar_equipo(away, list(self.team_stats['away'].index))
        if not h_n or not a_n: return None
        
        fv = np.concatenate([self.team_stats['home'].loc[h_n].values, self.team_stats['away'].loc[a_n].values]).reshape(1,-1)
        return {
            'probs': self.models['win'].predict_proba(fv)[0],
            'gh': self.models['gh'].predict(fv)[0], 'ga': self.models['ga'].predict(fv)[0],
            'corn': self.models['corn'].predict(fv)[0], 'card': self.models['card'].predict(fv)[0],
            'soth': self.models['soth'].predict(fv)[0], 'sota': self.models['sota'].predict(fv)[0],
            'shoth': self.models['shoth'].predict(fv)[0], 'shota': self.models['shota'].predict(fv)[0]
        }

# ==========================================
# 4. CARGA DE DATOS Y UTILIDADES
# ==========================================
@st.cache_data(ttl=3600)
def cargar_datos_liga_manual(codigo_csv):
    if codigo_csv == "MULTI":
        todos = ["SP1", "E0", "D1", "I1", "F1", "N1", "P1", "B1", "G1", "T1", "SC0"]
        mega = {}
        for c in todos:
            s = cargar_datos_liga_manual(c)
            if s: mega.update(s)
        return mega

    url = f"https://www.football-data.co.uk/mmz4281/{TEMPORADA_URL}/{codigo_csv}.csv"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return None
        df = pd.read_csv(StringIO(r.text))
        stats = {}
        for _, row in df.iterrows():
            for t in ['Home', 'Away']:
                team = row[f'{t}Team']
                if pd.isna(team): continue
                if team not in stats: 
                    stats[team] = {'pj':0,'gf':0,'gc':0,'corn':0,'sot':0,'shots':0,'cards':0}
                
                is_h = (t == 'Home')
                stats[team]['pj']+=1
                stats[team]['gf']+=row['FTHG'] if is_h else row['FTAG']
                stats[team]['gc']+=row['FTAG'] if is_h else row['FTHG']
                if 'HC' in row and pd.notna(row['HC']): stats[team]['corn']+=row['HC'] if is_h else row['AC']
                if 'HST' in row and pd.notna(row['HST']): stats[team]['sot']+=row['HST'] if is_h else row['AST']
                if 'HS' in row and pd.notna(row['HS']): stats[team]['shots']+=row['HS'] if is_h else row['AS'] # Tiros Totales
                if 'HY' in row and pd.notna(row['HY']): stats[team]['cards']+=row['HY'] if is_h else row['AY']
        return stats
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
        "RCD Mallorca": "Mallorca", "CA Osasuna": "Osasuna", "Rayo Vallecano de Madrid": "Vallecano",
        "Real Sociedad de Fútbol": "Sociedad", "PSV Eindhoven": "PSV Eindhoven",
        "Club Brugge KV": "Club Brugge", "Olympiacos FC": "Olympiakos", 
        "Galatasaray SK": "Galatasaray", "Fenerbahçe SK": "Fenerbahce"
    }
    if nombre_api in manual:
        target = manual[nombre_api]
        if target in lista_nombres: return target
        match = difflib.get_close_matches(target, lista_nombres, n=1, cutoff=0.6)
        if match: return match[0]
    match = difflib.get_close_matches(nombre_api, lista_nombres, n=1, cutoff=0.5)
    return match[0] if match else None

# ==========================================
# 5. SISTEMA DE CUOTAS Y VALUE (NUEVO)
# ==========================================

def obtener_cuotas_api(league_key):
    """Consulta la API de The-Odds-API para obtener cuotas en vivo"""
    url = f"https://api.the-odds-api.com/v4/sports/{league_key}/odds"
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': 'eu', # Europa
        'markets': 'h2h', # Ganador del partido
        'oddsFormat': 'decimal'
    }
    try:
        r = requests.get(url, params=params)
        if r.status_code != 200: return {}
        
        data = r.json()
        cuotas_dict = {}
        
        for event in data:
            h_team = event['home_team']
            a_team = event['away_team']
            
            # Buscar mejores cuotas
            best_h, best_x, best_a = 0, 0, 0
            bookie_h, bookie_x, bookie_a = "N/A", "N/A", "N/A"
            
            for bookmaker in event['bookmakers']:
                for market in bookmaker['markets']:
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            price = outcome['price']
                            name = outcome['name']
                            if name == h_team and price > best_h:
                                best_h, bookie_h = price, bookmaker['title']
                            elif name == a_team and price > best_a:
                                best_a, bookie_a = price, bookmaker['title']
                            elif name == 'Draw' and price > best_x:
                                best_x, bookie_x = price, bookmaker['title']
            
            # Guardamos con una clave combinada para buscar luego
            key = f"{h_team}|{a_team}"
            cuotas_dict[key] = {
                "1": best_h, "X": best_x, "2": best_a,
                "B1": bookie_h, "BX": bookie_x, "B2": bookie_a,
                "home_api": h_team, "away_api": a_team
            }
        return cuotas_dict
    except Exception as e:
        return {}

def calcular_valor_ev(datos_analisis, cuotas_api):
    """Calcula si hay Value Bet comparando Probabilidad vs Cuota"""
    if not cuotas_api: return None
    
    local_script = datos_analisis['local']
    visita_script = datos_analisis['visita']
    
    # 1. Encontrar el partido en el diccionario de cuotas (Fuzzy matching complejo)
    keys = list(cuotas_api.keys())
    # Intentamos buscar el local
    match_h = difflib.get_close_matches(local_script, [k.split("|")[0] for k in keys], n=1, cutoff=0.5)
    # Intentamos buscar la visita
    match_a = difflib.get_close_matches(visita_script, [k.split("|")[1] for k in keys], n=1, cutoff=0.5)
    
    odds = None
    if match_h and match_a:
        # Reconstruir la clave
        for k in keys:
            if match_h[0] in k and match_a[0] in k:
                odds = cuotas_api[k]
                break
    
    if not odds: return None

    # 2. Calcular EV
    probs = datos_analisis['probs'] # Ej: 60.5
    
    # EV = (Probabilidad(%) * Cuota) - 100
    ev_1 = (probs['1'] * odds['1']) / 100 - 1
    ev_x = (probs['X'] * odds['X']) / 100 - 1
    ev_2 = (probs['2'] * odds['2']) / 100 - 1
    
    ev_list = []
    
    # Umbral de valor: Solo mostrar si EV > 0 (Rentable)
    if ev_1 > 0: ev_list.append({"pick": "1 (Local)", "ev": ev_1*100, "cuota": odds['1'], "bookie": odds['B1']})
    if ev_x > 0: ev_list.append({"pick": "X (Empate)", "ev": ev_x*100, "cuota": odds['X'], "bookie": odds['BX']})
    if ev_2 > 0: ev_list.append({"pick": "2 (Visita)", "ev": ev_2*100, "cuota": odds['2'], "bookie": odds['B2']})
    
    # Retornar la mejor opción de valor si existe
    if ev_list:
        # Ordenar por mayor EV
        ev_list.sort(key=lambda x: x['ev'], reverse=True)
        return ev_list[0] # Retorna la mejor
    return None

# ==========================================
# 6. ANÁLISIS
# ==========================================
def analizar_partido_manual(local, visita, stats, manual_data):
    nL = encontrar_equipo(local, list(stats.keys()))
    nV = encontrar_equipo(visita, list(stats.keys()))
    
    if not nL or not nV:
        return {"error": True, "local": local, "visita": visita, "metodo": "SIN DATOS"}

    L, V = stats[nL], stats[nV]
    
    xg_h = (L['gf']/L['pj'] + V['gc']/V['pj']) / 2 * 1.05
    xg_a = (V['gf']/V['pj'] + L['gc']/L['pj']) / 2
    
    if manual_data['usar']:
        xg_h, xg_a = (xg_h + manual_data['g_h'])/2, (xg_a + manual_data['g_a'])/2
        
    xg_total = xg_h + xg_a
    probs = calcular_probabilidades_exactas(xg_h, xg_a)
    
    # Props
    corn = (L['corn']/L['pj'] + V['corn']/V['pj']) if not manual_data['usar'] else manual_data['corn']
    sot_L, sot_V = (L['sot']/L['pj']*1.1 + V['sot']/V['pj'])/2, (V['sot']/V['pj']*1.1 + L['sot']/L['pj'])/2
    # Calculo Tiros Totales
    shots_L = (L['shots']/L['pj']*1.05 + V['shots']/V['pj'])/2
    shots_V = (V['shots']/V['pj']*1.05 + L['shots']/L['pj'])/2
    cards = L['cards']/L['pj'] + V['cards']/V['pj']
    
    diff = xg_h - xg_a
    ah = f"{local} -0.5" if diff > 0.5 else (f"{visita} -0.5" if diff < -0.5 else "Igualdad")
    fmt, sel = determinar_estrategia(probs, diff, local, visita)
    
    return {
        "error": False, "local": local, "visita": visita,
        "probs": probs, "xg_total": xg_total, "diff": diff, "ah": ah,
        "dnb_team": local if probs['1']>probs['2'] else visita, 
        "dnb_prob": probs['1']/(probs['1']+probs['2'])*100,
        "sot_L": sot_L, "sot_V": sot_V, 
        "shots_L": shots_L, "shots_V": shots_V,
        "corn": corn, "cards": cards, "fmt": fmt, "sel": sel, "metodo": "MANUAL/POISSON",
        "value_data": None # Placeholder
    }

def analizar_partido_ia(cerebro, local, visita):
    pred = cerebro.predecir(local, visita)
    if not pred:
        return {"error": True, "local": local, "visita": visita, "metodo": "IA (SIN DATOS)"}
        
    p1, p2 = pred['probs'][0]*100, pred['probs'][2]*100
    xg_tot = pred['gh'] + pred['ga']
    
    probs = {"1":p1, "X":pred['probs'][1]*100, "2":p2, "1X":p1+pred['probs'][1]*100, "X2":p2+pred['probs'][1]*100, "Over25": 100 if xg_tot>2.65 else 30, "Under25": 100 if xg_tot<2.35 else 30, "BTTS_Si":60, "BTTS_No":40}
    
    sel = f"Gana {local}" if p1>55 else (f"Gana {visita}" if p2>55 else "Empate/Baja")
    
    return {
        "error": False, "local": local, "visita": visita,
        "probs": probs, "xg_total": xg_tot, "diff": pred['gh']-pred['ga'], "ah": "---",
        "dnb_team": local if p1>p2 else visita, "dnb_prob": p1/(p1+p2)*100,
        "sot_L": pred['soth'], "sot_V": pred['sota'], 
        "shots_L": pred['shoth'], "shots_V": pred['shota'],
        "corn": pred['corn'], "cards": pred['card'],
        "fmt": "🤖 IA", "sel": sel, "metodo": "IA (RANDOM FOREST)",
        "value_data": None # Placeholder
    }

def generar_texto(d, fecha, liga):
    txt = f"⚽ <b>{d['local']} vs {d['visita']}</b>\n📅 {fecha} | {liga}\n"
    if d['error']:
        txt += f"⚠️ <b>DATOS INSUFICIENTES</b>\n"
        txt += "=================================================================\n\n"
        return txt

    ic_1x2 = f"1({int(d['probs']['1'])}%) X({int(d['probs']['X'])}%) 2({int(d['probs']['2'])}%)"
    pick_ou = "OVER" if d['probs']['Over25'] > 50 else "UNDER"
    
    txt += f"⚙️ {d['metodo']}\n"
    txt += "-----------------------------------------------------------------\n"
    txt += f"1️⃣ 1X2: {ic_1x2}\n"
    txt += f"2️⃣ Goles: {d['xg_total']:.2f} | {pick_ou} 2.5\n"
    txt += f"3️⃣ Props:\n"
    txt += f"   • Tiros Tot: {d['local']}({d['shots_L']:.1f}) {d['visita']}({d['shots_V']:.1f})\n"
    txt += f"   • Tiros Puerta: {d['local']}({d['sot_L']:.1f}) {d['visita']}({d['sot_V']:.1f})\n"
    txt += f"   • Corners: {d['corn']:.1f} | Tarjetas: {d['cards']:.1f}\n"
    
    # SECCIÓN DE VALUE BET
    if d['value_data']:
        vd = d['value_data']
        txt += f"\n💰 <b>VALUE DETECTADO:</b>\n"
        txt += f"   🎯 Apuesta: <b>Gana {vd['pick']}</b>\n"
        txt += f"   📈 Cuota: {vd['cuota']} ({vd['bookie']})\n"
        txt += f"   🔥 Rentabilidad (EV): +{vd['ev']:.1f}%\n"
    
    txt += f"\n💡 Pick Analista: <b>{d['sel']}</b>\n"
    txt += "=================================================================\n\n"
    return txt

# ==========================================
# 7. INTERFAZ
# ==========================================
st.title("💎 YETIPS: PREMIUM ANALYST + VALUE BOT")

with st.sidebar:
    liga_sel = st.selectbox("Liga", list(LIGAS.keys()))
    mode = st.radio("Motor", ["💎 Manual/Estadístico", "🤖 Inteligencia Artificial"])
    manual_data = {'usar': False, 'g_h':0, 'g_a':0, 'corn':0}
    
    if mode == "💎 Manual/Estadístico":
        with st.expander("Laboratorio"):
            mg_h = st.number_input("Goles Loc", 1.5)
            mg_a = st.number_input("Goles Vis", 1.0)
            mc = st.slider("Corners", 5.0, 15.0, 9.5)
            chk = st.checkbox("Activar")
            manual_data = {'usar': chk, 'g_h': mg_h, 'g_a': mg_a, 'corn': mc}

if st.button(f"🚀 ANALIZAR {liga_sel}"):
    codigos = LIGAS[liga_sel]
    
    stats_man = None
    cerebro = None
    odds_data = {}
    
    # 1. CARGA DE MOTOR
    with st.spinner(f"Cargando motor {mode}..."):
        if mode == "💎 Manual/Estadístico":
            stats_man = cargar_datos_liga_manual(codigos['csv'])
        else:
            cerebro = BettingAI(codigos['api'], codigos['csv'])
            cerebro.entrenar()

    # 2. CARGA DE CUOTAS (NUEVO)
    with st.spinner("Buscando cuotas y calculando valor..."):
        if 'odds' in codigos:
            odds_data = obtener_cuotas_api(codigos['odds'])
        else:
            st.warning("⚠️ Sin datos de cuotas para esta liga.")

    # 3. OBTENER PARTIDOS
    url = f"https://api.football-data.org/v4/competitions/{codigos['api']}/matches" 
    r = requests.get(url, headers={'X-Auth-Token': API_KEY})
    
    if r.status_code == 200:
        matches = r.json()['matches']
        prox = [m for m in matches if datetime.strptime(m['utcDate'][:10], "%Y-%m-%d") <= datetime.now() + timedelta(days=10)]
        
        if prox:
            reporte = f"💎 REPORTE {mode.upper()} - {liga_sel}\n\n"
            audit = []
            
            for m in prox:
                loc, vis = m['homeTeam']['name'], m['awayTeam']['name']
                fecha = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m %H:%M")
                
                res = None
                if mode == "💎 Manual/Estadístico":
                    res = analizar_partido_manual(loc, vis, stats_man, manual_data)
                else:
                    res = analizar_partido_ia(cerebro, loc, vis)
                
                # INTEGRACIÓN DE VALUE
                if not res['error'] and odds_data:
                    res['value_data'] = calcular_valor_ev(res, odds_data)
                
                reporte += generar_texto(res, fecha, liga_sel)
                
                val_txt = f"{res['value_data']['ev']:.1f}% ({res['value_data']['pick']})" if res.get('value_data') else "-"
                audit.append({
                    "Fecha": fecha, 
                    "Partido": f"{loc} vs {vis}", 
                    "Tiros Tot": f"{res.get('shots_L',0):.1f} - {res.get('shots_V',0):.1f}" if not res['error'] else "-",
                    "Value EV": val_txt
                })
            
            st.session_state.reporte_premium = reporte
            st.session_state.data_audit = pd.DataFrame(audit)
        else:
            st.warning("No hay partidos próximos.")
    else:
        st.error(f"Error API: {r.status_code}")

t1, t2 = st.tabs(["📄 Reporte", "📊 Auditoría"])
with t1:
    if st.session_state.reporte_premium:
        st.markdown(st.session_state.reporte_premium.replace("\n", "  \n"), unsafe_allow_html=True)
        if st.button("📲 Telegram"):
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": st.session_state.reporte_premium[:4090], "parse_mode": "HTML"})
            st.success("Enviado")
with t2:
    if st.session_state.data_audit is not None:
        st.dataframe(st.session_state.data_audit, use_container_width=True)
