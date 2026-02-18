import streamlit as st
import pandas as pd
import requests
import math
import numpy as np
from datetime import datetime, timedelta
import difflib
import time
from io import StringIO
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
    "🇵🇹 Primeira Liga": {"api": "PPL", "csv": "P1"},
    "🇧🇪 Jupiler Pro League": {"api": "BJL", "csv": "B1"} # Añadida para soporte CL
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
            p_h = poisson(h, xg_h)
            p_a = poisson(a, xg_a)
            prob_matrix[h][a] = p_h * p_a
            
    p1 = np.sum(np.tril(prob_matrix, -1)) * 100
    pX = np.sum(np.diag(prob_matrix)) * 100
    p2 = np.sum(np.triu(prob_matrix, 1)) * 100
    
    under25 = sum(prob_matrix[h][a] for h in range(3) for a in range(3) if h+a < 2.5) * 100
    btts_no = sum(prob_matrix[h][0] for h in range(max_goals)) + sum(prob_matrix[0][a] for a in range(1, max_goals))
    
    return {
        "1": p1, "X": pX, "2": p2,
        "1X": p1+pX, "X2": p2+pX,
        "Over25": 100-under25, "Under25": under25,
        "BTTS_Si": (1-(btts_no/100))*100, "BTTS_No": btts_no
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
        self.models = {}
        self.team_stats = {}
        self.train_success = False

    def entrenar(self):
        try:
            # Si es MULTI en IA, intentamos cargar un dataset combinado o el principal (E0) por defecto
            # Para CL real, lo ideal es cargar múltiples, pero por simplicidad en IA usamos E0 como base si es MULTI
            url = self.csv_url if "MULTI" not in self.csv_url else f"https://www.football-data.co.uk/mmz4281/{TEMPORADA_URL}/E0.csv"
            
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers)
            if r.status_code != 200: return False
            
            df = pd.read_csv(StringIO(r.text))
            df = df.dropna(subset=['HomeTeam', 'AwayTeam', 'FTR']).fillna(0)
            
            cols = ['FTHG','FTAG', 'HST','AST', 'HS', 'AS', 'HC','AC', 'HY','AY','HR','AR']
            actual_cols = [c for c in cols if c in df.columns]
            if len(actual_cols) < 6: return False

            self.team_stats['home'] = df.groupby('HomeTeam')[actual_cols].mean()
            self.team_stats['away'] = df.groupby('AwayTeam')[actual_cols].mean()
            
            # Entrenamiento
            features, y_win, y_gh, y_ga, y_corn, y_card, y_shot_h, y_shot_a, y_sot_h, y_sot_a = [],[],[],[],[],[],[],[],[],[]
            for i, row in df.iterrows():
                if row['HomeTeam'] in self.team_stats['home'].index and row['AwayTeam'] in self.team_stats['away'].index:
                    fv = np.concatenate([self.team_stats['home'].loc[row['HomeTeam']].values, self.team_stats['away'].loc[row['AwayTeam']].values])
                    features.append(fv)
                    y_win.append(0 if row['FTR']=='H' else (1 if row['FTR']=='D' else 2))
                    y_gh.append(row['FTHG']); y_ga.append(row['FTAG'])
                    y_corn.append(row['HC']+row['AC']); y_card.append(row['HY']+row['AY']+row['HR']+row['AR'])
                    y_shot_h.append(row.get('HS',0)); y_shot_a.append(row.get('AS',0))
                    y_sot_h.append(row.get('HST',0)); y_sot_a.append(row.get('AST',0))

            if not features: return False
            X = np.array(features)
            rf = {'n_estimators': 100, 'random_state': 42, 'n_jobs': -1}
            
            self.models['win'] = RandomForestClassifier(**rf).fit(X, y_win)
            self.models['gh'] = RandomForestRegressor(**rf).fit(X, y_gh)
            self.models['ga'] = RandomForestRegressor(**rf).fit(X, y_ga)
            self.models['corn'] = RandomForestRegressor(**rf).fit(X, y_corn)
            self.models['card'] = RandomForestRegressor(**rf).fit(X, y_card)
            self.models['shoth'] = RandomForestRegressor(**rf).fit(X, y_shot_h)
            self.models['shota'] = RandomForestRegressor(**rf).fit(X, y_shot_a)
            self.models['soth'] = RandomForestRegressor(**rf).fit(X, y_sot_h)
            self.models['sota'] = RandomForestRegressor(**rf).fit(X, y_sot_a)
            
            self.train_success = True
            return True
        except: return False

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
            'shoth': self.models['shoth'].predict(fv)[0], 'shota': self.models['shota'].predict(fv)[0],
            'soth': self.models['soth'].predict(fv)[0], 'sota': self.models['sota'].predict(fv)[0]
        }

# ==========================================
# 4. CARGA DE DATOS
# ==========================================
@st.cache_data(ttl=3600)
def cargar_datos_liga_manual(codigo_csv):
    # ✅ ACTUALIZADO: Lista ampliada para incluir equipos de Champions (Bélgica, Grecia, Turquía, Escocia)
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
                if team not in stats: stats[team] = {'pj':0,'gf':0,'gc':0,'corn':0,'sot':0,'shots':0,'cards':0}
                
                is_h = (t == 'Home')
                stats[team]['pj']+=1
                stats[team]['gf']+=row['FTHG'] if is_h else row['FTAG']
                stats[team]['gc']+=row['FTAG'] if is_h else row['FTHG']
                if 'HC' in row and pd.notna(row['HC']): stats[team]['corn']+=row['HC'] if is_h else row['AC']
                if 'HST' in row and pd.notna(row['HST']): stats[team]['sot']+=row['HST'] if is_h else row['AST']
                if 'HS' in row and pd.notna(row['HS']): stats[team]['shots']+=row['HS'] if is_h else row['AS']
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
# 5. ANÁLISIS
# ==========================================
def analizar_partido_manual(local, visita, stats, manual_data):
    nL = encontrar_equipo(local, list(stats.keys()))
    nV = encontrar_equipo(visita, list(stats.keys()))
    
    # ✅ LÓGICA FALLBACK: Si no hay datos, devolvemos un objeto básico en lugar de None
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
    shots_L, shots_V = (L['shots']/L['pj']*1.05 + V['shots']/V['pj'])/2, (V['shots']/V['pj']*1.05 + L['shots']/L['pj'])/2
    cards = L['cards']/L['pj'] + V['cards']/V['pj']
    
    diff = xg_h - xg_a
    ah = f"{local} -0.5" if diff > 0.5 else (f"{visita} -0.5" if diff < -0.5 else "Igualdad")
    fmt, sel = determinar_estrategia(probs, diff, local, visita)
    
    return {
        "error": False, "local": local, "visita": visita,
        "probs": probs, "xg_total": xg_total, "diff": diff, "ah": ah,
        "dnb_team": local if probs['1']>probs['2'] else visita, 
        "dnb_prob": probs['1']/(probs['1']+probs['2'])*100,
        "sot_L": sot_L, "sot_V": sot_V, "shots_L": shots_L, "shots_V": shots_V,
        "corn": corn, "cards": cards, "fmt": fmt, "sel": sel, "metodo": "MANUAL/POISSON"
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
        "sot_L": pred['soth'], "sot_V": pred['sota'], "shots_L": pred['shoth'], "shots_V": pred['shota'],
        "corn": pred['corn'], "cards": pred['card'],
        "fmt": "🤖 IA", "sel": sel, "metodo": "IA (RANDOM FOREST)"
    }

def generar_texto(d, fecha, liga):
    txt = f"⚽ <b>{d['local']} vs {d['visita']}</b>\n📅 {fecha} | {liga}\n"
    if d['error']:
        txt += f"⚠️ <b>DATOS INSUFICIENTES</b>\n"
        txt += f"   El sistema no tiene estadísticas históricas de uno de los equipos (ej. Qarabağ, Bodø).\n"
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
    txt += f"💡 Pick: <b>{d['sel']}</b>\n"
    txt += "=================================================================\n\n"
    return txt

# ==========================================
# 6. INTERFAZ
# ==========================================
st.title("💎 YETIPS: PREMIUM ANALYST")

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
    
    # Cargar Motor
    stats_man = None
    cerebro = None
    if mode == "💎 Manual/Estadístico":
        stats_man = cargar_datos_liga_manual(codigos['csv'])
    else:
        cerebro = BettingAI(codigos['api'], codigos['csv'])
        cerebro.entrenar()

    # Obtener Partidos
    url = f"https://api.football-data.org/v4/competitions/{codigos['api']}/matches" # Quitamos status=SCHEDULED para asegurar playoffs
    r = requests.get(url, headers={'X-Auth-Token': API_KEY})
    
    if r.status_code == 200:
        matches = r.json()['matches']
        # Filtro fecha (próximos 10 días)
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
                
                # ✅ MOSTRAR SIEMPRE, AUNQUE HAYA ERROR DE DATOS
                reporte += generar_texto(res, fecha, liga_sel)
                audit.append({"Fecha": fecha, "Partido": f"{loc} vs {vis}", "Status": "OK" if not res['error'] else "SIN DATOS"})
            
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
