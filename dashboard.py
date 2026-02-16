import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURACIÓN (LAS LLAVES DEL REINO)
# ==========================================

# --- API FOOTBALL DATA ---
# Si usas Streamlit Cloud, usa st.secrets. Si es local, pon tu clave directa.
try:
    API_KEY = st.secrets["API_KEY"]
except:
    API_KEY = "TU_API_KEY_DE_FOOTBALL_DATA" # <--- ¡PEGALA AQUÍ!

# --- TELEGRAM CONFIG ---
try:
    TG_TOKEN = st.secrets["TG_TOKEN"]
    TG_CHAT_ID = st.secrets["TG_CHAT_ID"]
except:
    TG_TOKEN = "TU_TOKEN_DEL_BOTFATHER"     # <--- ¡PEGALO AQUÍ!
    TG_CHAT_ID = "TU_ID_NUMERICO_DE_USER"   # <--- ¡PEGALO AQUÍ!

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
# 2. FUNCIONES (EL CEREBRO)
# ==========================================

def clean_num(val):
    if isinstance(val, str): return float(val.replace(',', '.'))
    return float(val) if val else 0.0

def enviar_telegram(mensaje):
    """Envía un mensaje de texto a tu bot"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data)
        if r.status_code == 200:
            return True
        else:
            st.error(f"Error Telegram: {r.text}")
            return False
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return False

@st.cache_data
def cargar_bases_datos():
    try:
        # A) FBref
        df_goals = pd.read_csv('liga_stand_25 - Hoja 1.csv', header=1)[['Squad', '90s', 'Gls']]
        df_misc = pd.read_csv('misc25sp - Hoja 1.csv', header=1)[['Squad', 'Off', 'CrdY', 'CrdR']]
        df_fbref = df_goals.merge(df_misc, on='Squad', how='inner')
        
        df_fbref['90s'] = df_fbref['90s'].apply(clean_num)
        df_fbref['G_p'] = df_fbref['Gls'].apply(clean_num) / df_fbref['90s']
        df_fbref['O_p'] = df_fbref['Off'].apply(clean_num) / df_fbref['90s']
        y = df_fbref['CrdY'].apply(clean_num)
        r = df_fbref['CrdR'].apply(clean_num)
        df_fbref['C_p'] = ((y * 10) + (r * 25)) / df_fbref['90s']

        # B) SP1
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
    except Exception as e:
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
            "cards": h_fb['C_p'] + a_fb['C_p'],
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
    if response.status_code == 200:
        return response.json()['matches']
    return []

# ==========================================
# 3. INTERFAZ GRÁFICA (LO QUE VES)
# ==========================================

st.set_page_config(page_title="Yetips Dashboard 2.0", layout="wide", page_icon="🦁")

df_fbref, sp1_stats = cargar_bases_datos()

if df_fbref is None:
    st.error("❌ Error: No encuentro los archivos CSV (liga_stand_25, misc25sp, SP1). Súbelos a la carpeta.")
    st.stop()

st.title("🦁 Yetips Dashboard 2.0")

tab1, tab2 = st.tabs(["🔮 Próximos Partidos & Telegram", "✅ Historial de Aciertos"])

# --- PESTAÑA 1: PREDICCIONES Y ENVÍO ---
with tab1:
    col_btn, col_info = st.columns([1, 4])
    
    # Botón principal de análisis
    if col_btn.button("🔄 Analizar Jornada", type="primary"):
        with st.spinner("Consultando API y calculando..."):
            matches = get_matches('SCHEDULED')
            if matches:
                reporte_data = []
                telegram_buffer = "🦁 *YETIPS - REPORTE JORNADA*\n\n"
                
                for m in matches[:10]:
                    local = m['homeTeam']['name']
                    visita = m['awayTeam']['name']
                    fecha = m['utcDate'][:10]
                    
                    preds = calcular_predicciones(local, visita, df_fbref, sp1_stats)
                    if preds:
                        # Datos para la tabla visual
                        reporte_data.append({
                            "Fecha": fecha,
                            "Partido": f"{local} vs {visita}",
                            "⚽ Goles": f"{preds['goles']:.2f} ({'MÁS 2.5' if preds['goles']>2.55 else 'Menos'})",
                            "🚩 Offsides": f"{preds['off']:.2f} ({'MÁS 3.5' if preds['off']>3.6 else 'Menos'})",
                            "⛳ Corners": f"{preds['corn']:.2f} ({'MÁS 9.5' if preds['corn']>9.5 else 'Menos'})",
                            "🟨 Tarjetas": f"{preds['cards']:.0f} pts"
                        })
                        
                        # Datos para el mensaje de Telegram
                        telegram_buffer += f"⚔️ *{local} vs {visita}*\n"
                        telegram_buffer += f"⚽ Goles: {preds['goles']:.2f}\n"
                        telegram_buffer += f"⛳ Corners: {preds['corn']:.2f}\n"
                        telegram_buffer += f"🚩 Offsides: {preds['off']:.2f}\n"
                        telegram_buffer += "------------------\n"

                # Guardamos en session_state para que no se borre al pulsar otro botón
                st.session_state['reporte_tabla'] = pd.DataFrame(reporte_data)
                st.session_state['reporte_telegram'] = telegram_buffer
            else:
                st.warning("No hay partidos programados en la API para los próximos días.")

    # Mostrar resultados si existen en memoria
    if 'reporte_tabla' in st.session_state:
        st.dataframe(st.session_state['reporte_tabla'], use_container_width=True)
        
        st.write("---")
        st.subheader("📱 Zona de Envío")
        
        # Botón para enviar a Telegram
        if st.button("✈️ Enviar Reporte a Telegram"):
            if 'reporte_telegram' in st.session_state:
                with st.spinner("Enviando mensaje..."):
                    exito = enviar_telegram(st.session_state['reporte_telegram'])
                    if exito:
                        st.success("✅ ¡Reporte enviado a tu móvil!")
                    else:
                        st.error("❌ Falló el envío. Revisa el TOKEN y el CHAT_ID.")
            else:
                st.error("Primero analiza la jornada.")

# --- PESTAÑA 2: AUDITORÍA ---
with tab2:
    st.info("ℹ️ Validación automática de GOLES (Últimos 30 días)")
    
    if st.button("📊 Verificar Aciertos"):
        with st.spinner("Auditando resultados..."):
            matches = get_matches('FINISHED')
            if matches:
                audit_data = []
                aciertos = 0
                total_audit = 0
                
                for m in matches:
                    local = m['homeTeam']['name']
                    visita = m['awayTeam']['name']
                    
                    try:
                        g_real_h = m['score']['fullTime']['home']
                        g_real_a = m['score']['fullTime']['away']
                        if g_real_h is None: continue 
                        total_goles_real = g_real_h + g_real_a
                    except:
                        continue

                    preds = calcular_predicciones(local, visita, df_fbref, sp1_stats)
                    
                    if preds:
                        pred_val = preds['goles']
                        pick = "MÁS 2.5" if pred_val > 2.55 else "MENOS 2.5"
                        
                        ganada = False
                        if pick == "MÁS 2.5" and total_goles_real > 2.5: ganada = True
                        elif pick == "MENOS 2.5" and total_goles_real < 2.5: ganada = True
                        
                        if ganada: aciertos += 1
                        total_audit += 1
                        
                        audit_data.append({
                            "Partido": f"{local} vs {visita}",
                            "Resultado": f"{g_real_h}-{g_real_a} ({total_goles_real})",
                            "Predicción": f"{pred_val:.2f} ({pick})",
                            "Estado": "✅ ACIERTO" if ganada else "❌ FALLO"
                        })
                
                if total_audit > 0:
                    win_rate = (aciertos / total_audit) * 100
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Partidos", total_audit)
                    c2.metric("Aciertos", aciertos)
                    c3.metric("Win Rate", f"{win_rate:.1f}%")
                    
                    df_audit = pd.DataFrame(audit_data)
                    st.dataframe(df_audit.style.applymap(
                        lambda x: 'color: green' if 'ACIERTO' in str(x) else ('color: red' if 'FALLO' in str(x) else ''), 
                        subset=['Estado']
                    ), use_container_width=True)
                else:
                    st.warning("No hay datos recientes para auditar.")
