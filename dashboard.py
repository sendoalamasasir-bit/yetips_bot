import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================

# --- TUS CLAVES (PÉGALAS AQUÍ) ---
API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f" 
TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
TG_CHAT_ID = "1197028422"

# Si usas Streamlit Cloud, el sistema intentará buscarlas en los "Secrets" primero
if "API_KEY" in st.secrets: API_KEY = st.secrets["API_KEY"]
if "TG_TOKEN" in st.secrets: TG_TOKEN = st.secrets["TG_TOKEN"]
if "TG_CHAT_ID" in st.secrets: TG_CHAT_ID = st.secrets["TG_CHAT_ID"]

# --- CONFIGURACIÓN DE LA LIGA ---
COMPETITION_ID = 'PD' # Primera División
URL_API = f"https://api.football-data.org/v4/competitions/{COMPETITION_ID}/matches"

# --- MAPA DE NOMBRES ---
mapa_nombres = {
    "Deportivo Alavés": ["Alavés", "Alaves"], "Girona FC": ["Girona", "Girona"],
    "Athletic Club": ["Athletic Club", "Ath Bilbao"], "Elche CF": ["Elche", "Elche"],
    "Club Atlético de Madrid": ["Atlético Madrid", "Ath Madrid"], "RCD Espanyol de Barcelona": ["Espanyol", "Espanyol"],
    "FC Barcelona": ["Barcelona", "Barcelona"], "Levante UD": ["Levante", "Levante"],
    "Real Betis Balompié": ["Real Betis", "Betis"], "Rayo Vallecano de Madrid": ["Rayo Vallecano", "Rayo Vallecano"],
    "RC Celta de Vigo": ["Celta Vigo", "Celta"], "RCD Mallorca": ["Mallorca", "Mallorca"],
    "Getafe CF": ["Getafe", "Getafe"], "Sevilla FC": ["Sevilla", "Sevilla"],
    "CA Osasuna": ["Osasuna", "Osasuna"], "Real Madrid CF": ["Real Madrid", "Real Madrid"],
    "Villarreal CF": ["Villarreal", "Villarreal"], "Valencia CF": ["Valencia", "Valencia"],
    "Real Sociedad de Fútbol": ["Real Sociedad", "Sociedad"], "Real Oviedo": ["Oviedo", "Oviedo"],
    "Real Valladolid CF": ["Valladolid", "Valladolid"], "UD Las Palmas": ["Las Palmas", "Las Palmas"],
    "CD Leganés": ["Leganés", "Leganes"]
}

# ==========================================
# 2. FUNCIONES
# ==========================================

def clean_num(val):
    if isinstance(val, str): return float(val.replace(',', '.'))
    return float(val) if val else 0.0

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data)
        return r.status_code == 200
    except:
        return False

@st.cache_data
def cargar_bases_datos():
    try:
        # A) FBref (Goles y Amarillas)
        df_goals = pd.read_csv('liga_stand_25 - Hoja 1.csv', header=1)[['Squad', '90s', 'Gls']]
        df_misc = pd.read_csv('misc25sp - Hoja 1.csv', header=1)[['Squad', 'Off', 'CrdY']]
        df_fbref = df_goals.merge(df_misc, on='Squad', how='inner')
        
        df_fbref['90s'] = df_fbref['90s'].apply(clean_num)
        df_fbref['G_p'] = df_fbref['Gls'].apply(clean_num) / df_fbref['90s']
        df_fbref['O_p'] = df_fbref['Off'].apply(clean_num) / df_fbref['90s']
        df_fbref['Y_p'] = df_fbref['CrdY'].apply(clean_num) / df_fbref['90s'] # Amarillas promedio

        # B) SP1 (Corners y Tiros)
        df_sp1 = pd.read_csv('SP1 (1).csv')
        sp1_stats = {}
        for idx, row in df_sp1.iterrows():
            for tipo in ['Home', 'Away']:
                team = row[f'{tipo}Team']
                if team not in sp1_stats: sp1_stats[team] = {'pj':0, 'corn':0, 'sot':0}
                sp1_stats[team]['pj'] += 1
                sp1_stats[team]['corn'] += row['HC'] if tipo == 'Home' else row['AC']
                sp1_stats[team]['sot'] += row['HST'] if tipo == 'Home' else row['AST']
        
        return df_fbref, sp1_stats
    except:
        return None, None

def calcular_predicciones(local_api, visita_api, df_fbref, sp1_stats):
    names_L = mapa_nombres.get(local_api)
    names_V = mapa_nombres.get(visita_api)
    if not names_L or not names_V: return None

    nom_fb_L, nom_sp1_L = names_L
    nom_fb_V, nom_sp1_V = names_V
    
    try:
        h_fb = df_fbref[df_fbref['Squad'] == nom_fb_L].iloc[0]
        a_fb = df_fbref[df_fbref['Squad'] == nom_fb_V].iloc[0]
        h_sp = sp1_stats.get(nom_sp1_L, {'pj':1, 'corn':0, 'sot':0})
        a_sp = sp1_stats.get(nom_sp1_V, {'pj':1, 'corn':0, 'sot':0})
        
        return {
            "goles": h_fb['G_p'] + a_fb['G_p'],
            "off": h_fb['O_p'] + a_fb['O_p'],
            "yellows": h_fb['Y_p'] + a_fb['Y_p'],
            "corn": (h_sp['corn']/h_sp['pj']) + (a_sp['corn']/a_sp['pj']),
            "sot": (h_sp['sot']/h_sp['pj']) + (a_sp['sot']/a_sp['pj'])
        }
    except:
        return None

def get_matches(status='SCHEDULED'):
    headers = {'X-Auth-Token': API_KEY}
    params = {'status': status}
    if status == 'FINISHED':
        hoy = datetime.now()
        hace_mes = hoy - timedelta(days=30)
        params['dateFrom'] = hace_mes.strftime('%Y-%m-%d')
        params['dateTo'] = hoy.strftime('%Y-%m-%d')
    response = requests.get(URL_API, headers=headers, params=params)
    return response.json()['matches'] if response.status_code == 200 else []

def obtener_pick(valor, linea, tipo=""):
    """Devuelve el texto formateado de la apuesta"""
    emoji = "🟢" if valor > linea else "🔴"
    texto = "MÁS" if valor > linea else "MENOS"
    return f"{emoji} {texto} {linea} ({valor:.2f})"

# ==========================================
# 3. INTERFAZ GRÁFICA
# ==========================================

st.set_page_config(page_title="Yetips Dashboard 3.0", layout="wide", page_icon="🦁")
df_fbref, sp1_stats = cargar_bases_datos()

if df_fbref is None:
    st.error("❌ Error: Faltan los CSV. Súbelos.")
    st.stop()

st.title("🦁 Yetips - Panel de Apuestas")

tab1, tab2 = st.tabs(["🔮 Pronósticos & Telegram", "✅ Auditoría"])

# --- PESTAÑA 1 ---
with tab1:
    col_btn, _ = st.columns([1, 4])
    if col_btn.button("🔄 Generar Pronósticos", type="primary"):
        with st.spinner("Analizando mercado..."):
            matches = get_matches('SCHEDULED')
            if matches:
                reporte_data = []
                tg_msg = "🦁 *YETIPS - PRONÓSTICOS*\n"
                tg_msg += f"📅 {datetime.now().strftime('%d/%m')}\n\n"
                
                for m in matches[:10]:
                    local, visita = m['homeTeam']['name'], m['awayTeam']['name']
                    preds = calcular_predicciones(local, visita, df_fbref, sp1_stats)
                    
                    if preds:
                        # LÓGICA DE APUESTAS (PICKS)
                        pick_gol = obtener_pick(preds['goles'], 2.5)
                        pick_corn = obtener_pick(preds['corn'], 9.5)
                        pick_card = obtener_pick(preds['yellows'], 4.5)
                        pick_sot = obtener_pick(preds['sot'], 8.5)
                        
                        # Dataframe Web
                        reporte_data.append({
                            "Partido": f"{local} vs {visita}",
                            "⚽ Goles": pick_gol,
                            "⛳ Corners": pick_corn,
                            "🟨 Amarillas": pick_card,
                            "🎯 Tiros Puerta": pick_sot
                        })
                        
                        # Mensaje Telegram
                        tg_msg += f"⚔️ *{local} vs {visita}*\n"
                        tg_msg += f"⚽ Goles: {pick_gol}\n"
                        tg_msg += f"⛳ Corns: {pick_corn}\n"
                        tg_msg += f"🟨 Cards: {pick_card}\n"
                        tg_msg += f"🎯 Tiros: {pick_sot}\n"
                        tg_msg += "------------------\n"

                st.session_state['data'] = pd.DataFrame(reporte_data)
                st.session_state['tg'] = tg_msg
            else:
                st.warning("Sin partidos programados.")

    if 'data' in st.session_state:
        st.dataframe(st.session_state['data'], use_container_width=True)
        if st.button("✈️ Enviar a Telegram"):
            if enviar_telegram(st.session_state['tg']): st.success("Enviado ✅")
            else: st.error("Error envío ❌")

# --- PESTAÑA 2 ---
with tab2:
    if st.button("📊 Auditar Goles (30 días)"):
        matches = get_matches('FINISHED')
        if matches:
            audit = []
            aciertos = 0
            for m in matches:
                try:
                    goles_real = m['score']['fullTime']['home'] + m['score']['fullTime']['away']
                    local, visita = m['homeTeam']['name'], m['awayTeam']['name']
                    preds = calcular_predicciones(local, visita, df_fbref, sp1_stats)
                    
                    if preds:
                        estimado = preds['goles']
                        pick = "MÁS 2.5" if estimado > 2.5 else "MENOS 2.5"
                        ganada = (pick == "MÁS 2.5" and goles_real > 2.5) or (pick == "MENOS 2.5" and goles_real < 2.5)
                        if ganada: aciertos += 1
                        
                        audit.append({
                            "Partido": f"{local} vs {visita}",
                            "Real": goles_real,
                            "Pick": f"{pick} (Est: {estimado:.1f})",
                            "Res": "✅" if ganada else "❌"
                        })
                except: continue
            
            df = pd.DataFrame(audit)
            if len(df) > 0:
                st.metric("Win Rate", f"{(aciertos/len(df)*100):.1f}%")
                st.dataframe(df, use_container_width=True)
