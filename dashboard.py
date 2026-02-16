import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- CONFIGURACIÓN ---
# Si lo ejecutas en local, pon tu clave aquí abajo. 
# Si está en Streamlit Cloud, usa st.secrets["API_KEY"]
try:
    API_KEY = st.secrets["API_KEY"]
except:
    API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f" # <--- ¡PON TU TOKEN AQUI SI ESTAS EN LOCAL!

COMPETITION_ID = 'PD' # La Liga
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

# --- FUNCIONES DE CÁLCULO ---
def clean_num(val):
    if isinstance(val, str): return float(val.replace(',', '.'))
    return float(val) if val else 0.0

@st.cache_data
def cargar_bases_datos():
    """Carga y procesa los CSVs una sola vez para que sea rápido"""
    try:
        # A) FBref (Goles, Offsides, Tarjetas)
        df_goals = pd.read_csv('liga_stand_25 - Hoja 1.csv', header=1)[['Squad', '90s', 'Gls']]
        df_misc = pd.read_csv('misc25sp - Hoja 1.csv', header=1)[['Squad', 'Off', 'CrdY', 'CrdR']]
        df_fbref = df_goals.merge(df_misc, on='Squad', how='inner')
        
        df_fbref['90s'] = df_fbref['90s'].apply(clean_num)
        df_fbref['G_p'] = df_fbref['Gls'].apply(clean_num) / df_fbref['90s']
        df_fbref['O_p'] = df_fbref['Off'].apply(clean_num) / df_fbref['90s']
        y = df_fbref['CrdY'].apply(clean_num)
        r = df_fbref['CrdR'].apply(clean_num)
        df_fbref['C_p'] = ((y * 10) + (r * 25)) / df_fbref['90s']

        # B) SP1 (Corners, Tiros)
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
    """Calcula los números basado en los nombres de la API"""
    names_L = mapa_nombres.get(local_api)
    names_V = mapa_nombres.get(visita_api)
    
    if not names_L or not names_V: return None

    nom_fb_L, nom_sp1_L = names_L
    nom_fb_V, nom_sp1_V = names_V
    
    try:
        # FBref Data
        h_fb = df_fbref[df_fbref['Squad'] == nom_fb_L].iloc[0]
        a_fb = df_fbref[df_fbref['Squad'] == nom_fb_V].iloc[0]
        
        # SP1 Data
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

# --- CONEXIÓN API ---
def get_matches(status='SCHEDULED'):
    headers = {'X-Auth-Token': API_KEY}
    # Pedimos partidos programados o finalizados
    # Si pedimos finished, necesitamos un rango de fechas (últimos 30 días)
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

# --- INTERFAZ ---
st.set_page_config(page_title="Yetips Dashboard 2.0", layout="wide", page_icon="🦁")

# Cargar datos una sola vez
df_fbref, sp1_stats = cargar_bases_datos()

if df_fbref is None:
    st.error("❌ Error cargando CSVs. Verifica que están en la carpeta.")
    st.stop()

st.title("🦁 Yetips Dashboard 2.0")
st.markdown("**Sistema de Inteligencia Deportiva: Predicción & Validación**")

# Pestañas
tab1, tab2 = st.tabs(["🔮 Próximos Partidos", "✅ Historial y Aciertos"])

# --- PESTAÑA 1: FUTURO ---
with tab1:
    if st.button("🔄 Analizar Jornada Actual"):
        with st.spinner("Conectando con La Liga..."):
            matches = get_matches('SCHEDULED')
            if matches:
                reporte = []
                for m in matches[:10]: # Solo mostramos los 10 primeros
                    local = m['homeTeam']['name']
                    visita = m['awayTeam']['name']
                    fecha = m['utcDate'][:10]
                    
                    preds = calcular_predicciones(local, visita, df_fbref, sp1_stats)
                    if preds:
                        reporte.append({
                            "Fecha": fecha,
                            "Partido": f"{local} vs {visita}",
                            "⚽ Goles": f"{preds['goles']:.2f} ({'MÁS 2.5' if preds['goles']>2.55 else 'Menos'})",
                            "🚩 Offsides": f"{preds['off']:.2f} ({'MÁS 3.5' if preds['off']>3.6 else 'Menos'})",
                            "⛳ Corners": f"{preds['corn']:.2f} ({'MÁS 9.5' if preds['corn']>9.5 else 'Menos'})",
                            "🟨 Tarjetas": f"{preds['cards']:.0f} pts"
                        })
                st.dataframe(pd.DataFrame(reporte), use_container_width=True)
            else:
                st.warning("No hay partidos programados pronto.")

# --- PESTAÑA 2: PASADO (VERIFICACIÓN) ---
with tab2:
    st.info("ℹ️ Validando automáticamente Goles (La API gratuita no da datos históricos de Córners/Tarjetas).")
    
    if st.button("📊 Verificar Aciertos (Últimos 30 días)"):
        with st.spinner("Auditando resultados..."):
            matches = get_matches('FINISHED')
            if matches:
                audit_data = []
                aciertos = 0
                total_audit = 0
                
                for m in matches:
                    local = m['homeTeam']['name']
                    visita = m['awayTeam']['name']
                    
                    # Resultado REAL
                    try:
                        g_real_h = m['score']['fullTime']['home']
                        g_real_a = m['score']['fullTime']['away']
                        if g_real_h is None: continue # Partido cancelado o sin datos
                        total_goles_real = g_real_h + g_real_a
                    except:
                        continue

                    # Nuestra Predicción
                    preds = calcular_predicciones(local, visita, df_fbref, sp1_stats)
                    
                    if preds:
                        pred_val = preds['goles']
                        pick = "MÁS 2.5" if pred_val > 2.55 else "MENOS 2.5"
                        
                        # VEREDICTO
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
                
                # MOSTRAR METRICAS
                if total_audit > 0:
                    win_rate = (aciertos / total_audit) * 100
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Partidos Analizados", total_audit)
                    col_m2.metric("Aciertos", aciertos)
                    col_m3.metric("Win Rate", f"{win_rate:.1f}%")
                    
                    # Colorear tabla
                    df_audit = pd.DataFrame(audit_data)
                    st.dataframe(df_audit.style.applymap(
                        lambda x: 'color: green' if 'ACIERTO' in str(x) else ('color: red' if 'FALLO' in str(x) else ''), 
                        subset=['Estado']
                    ), use_container_width=True)
                else:
                    st.warning("No se encontraron partidos finalizados con datos.")
