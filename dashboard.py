import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import difflib # Para coincidencia de nombres aproximada

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================

# --- TUS CLAVES ---
try:
    API_KEY = st.secrets["API_KEY"]
    TG_TOKEN = st.secrets["TG_TOKEN"]
    TG_CHAT_ID = st.secrets["TG_CHAT_ID"]
except:
    # CLAVES DE EJEMPLO (¡CÁMBIALAS!)
    API_KEY = "68e35b4ab2b340b98523f2d6ea512f9f" 
    TG_TOKEN = "8590341693:AAEtYenrAY1cWd3itleTsYQ7c222tKpmZbQ"
    TG_CHAT_ID = "1197028422"

# --- CONFIGURACIÓN DE LIGAS (Expandible) ---
# 'API': Código en football-data.org
# 'CSV': Código en football-data.co.uk
LIGAS = {
    "🇪🇸 La Liga": {"api": "PD", "csv": "SP1"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"api": "PL", "csv": "E0"},
    "🇩🇪 Bundesliga": {"api": "BL1", "csv": "D1"},
    "🇮🇹 Serie A": {"api": "SA", "csv": "I1"},
    "🇫🇷 Ligue 1": {"api": "FL1", "csv": "F1"},
    # Puedes añadir: "🇳🇱 Eredivisie": {"api": "DED", "csv": "N1"}
}

# ==========================================
# 2. FUNCIONES DE CARGA DE DATOS (AUTOMÁTICAS)
# ==========================================

@st.cache_data(ttl=3600) # Se actualiza cada hora
def cargar_datos_liga(codigo_csv):
    """Descarga el CSV directamente de la web oficial de estadísticas"""
    url = f"https://www.football-data.co.uk/mmz4281/2526/{codigo_csv}.csv"
    
    # Intento de descarga para la temporada 25/26 (si ya existe)
    # Si estamos a principios de temporada y falla, usa la 24/25 cambiando el link
    # Nota: Como estamos en 2026, asumo temporada 25/26. Si falla, probar 2425.
    try:
        df = pd.read_csv(url)
        # Limpieza básica
        stats = {}
        for idx, row in df.iterrows():
            try:
                # Acumulamos datos Local y Visitante
                teams = [row['HomeTeam'], row['AwayTeam']]
                for i, team in enumerate(teams):
                    if team not in stats: 
                        stats[team] = {'pj': 0, 'goles': 0, 'corn': 0, 'sot': 0, 'cards': 0}
                    
                    es_local = (i == 0)
                    stats[team]['pj'] += 1
                    
                    # Goles
                    stats[team]['goles'] += row['FTHG'] if es_local else row['FTAG']
                    # Corners (HC = Home Corners, AC = Away Corners)
                    if pd.notna(row['HC']): stats[team]['corn'] += row['HC'] if es_local else row['AC']
                    # Tiros Puerta (HST / AST)
                    if pd.notna(row['HST']): stats[team]['sot'] += row['HST'] if es_local else row['AST']
                    # Amarillas (HY / AY)
                    if pd.notna(row['HY']): stats[team]['cards'] += row['HY'] if es_local else row['AY']
            except:
                continue
        return stats
    except Exception as e:
        st.error(f"Error descargando datos de {url}: {e}")
        return None

def get_matches(api_code, status='SCHEDULED'):
    headers = {'X-Auth-Token': API_KEY}
    url = f"https://api.football-data.org/v4/competitions/{api_code}/matches"
    
    params = {'status': status}
    if status == 'FINISHED':
        hoy = datetime.now()
        hace_mes = hoy - timedelta(days=30)
        params['dateFrom'] = hace_mes.strftime('%Y-%m-%d')
        params['dateTo'] = hoy.strftime('%Y-%m-%d')

    response = requests.get(url, headers=headers, params=params)
    return response.json()['matches'] if response.status_code == 200 else []

def encontrar_equipo_stats(nombre_api, stats_dict):
    """
    Usa 'difflib' para encontrar el nombre más parecido en el CSV 
    dado el nombre que nos da la API. Magia pura.
    """
    nombres_csv = list(stats_dict.keys())
    # Busca la coincidencia más cercana (cutoff 0.6 significa 60% de similitud mínima)
    coincidencias = difflib.get_close_matches(nombre_api, nombres_csv, n=1, cutoff=0.5)
    
    if coincidencias:
        return coincidencias[0]
    
    # Correcciones manuales comunes si falla el automático
    mapa_manual = {
        "Brighton & Hove Albion FC": "Brighton",
        "West Ham United FC": "West Ham",
        "Tottenham Hotspur FC": "Tottenham",
        "Wolverhampton Wanderers FC": "Wolves",
        "Paris Saint-Germain FC": "Paris SG",
        "FC Bayern München": "Bayern Munich",
        "Bayer 04 Leverkusen": "Leverkusen",
        "Inter Milan": "Inter",
        "AC Milan": "Milan",
        "Club Atlético de Madrid": "Ath Madrid",
        "Athletic Club": "Ath Bilbao"
    }
    return mapa_manual.get(nombre_api, None)

def calcular_predicciones(local_api, visita_api, stats_dict):
    # 1. Traducir nombres API -> CSV
    nom_L = encontrar_equipo_stats(local_api, stats_dict)
    nom_V = encontrar_equipo_stats(visita_api, stats_dict)
    
    if not nom_L or not nom_V: return None # No encontramos los datos

    try:
        sL = stats_dict[nom_L]
        sV = stats_dict[nom_V]
        
        # Promedios Simples (Total Global / Partidos Jugados)
        # Nota: Para hacerlo más preciso, podrías separar Local/Visita en el futuro
        def prom(k): return (sL[k]/sL['pj']) + (sV[k]/sV['pj'])

        return {
            "goles": prom('goles'), # Suma de promedios de gol (revisar lógica según necesidad)
            "corn": prom('corn'),
            "sot": prom('sot'),
            "cards": prom('cards')
        }
    except:
        return None

def obtener_pick(valor, linea):
    emoji = "🟢" if valor > linea else "🔴"
    texto = "MÁS" if valor > linea else "MENOS"
    return f"{emoji} {texto} {linea} ({valor:.2f})"

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
        return True
    except:
        return False

# ==========================================
# 3. INTERFAZ GRÁFICA MULTI-LIGA
# ==========================================

st.set_page_config(page_title="EuroTips Dashboard", layout="wide", page_icon="🌍")

st.title("🌍 EuroTips Pro Dashboard")

# --- SELECTOR DE LIGA (SIDEBAR) ---
st.sidebar.header("Configuración")
liga_seleccionada = st.sidebar.selectbox("Selecciona Liga", list(LIGAS.keys()))
codigos = LIGAS[liga_seleccionada]

# Cargamos stats AUTOMÁTICAMENTE desde la URL
with st.spinner(f"Descargando estadísticas de {liga_seleccionada}..."):
    stats_dict = cargar_datos_liga(codigos['csv'])

if stats_dict is None:
    st.error("No se pudieron descargar los datos. Verifica la temporada en la URL.")
    st.stop()

# --- PESTAÑAS PRINCIPALES ---
tab1, tab2 = st.tabs(["🔮 Pronósticos", "✅ Auditoría"])

# --- TAB 1: PRONÓSTICOS ---
with tab1:
    col_btn, _ = st.columns([1, 4])
    if col_btn.button("🔄 Analizar Partidos", type="primary"):
        with st.spinner("Consultando calendario y cruzando datos..."):
            matches = get_matches(codigos['api'], 'SCHEDULED')
            
            if matches:
                reporte_data = []
                tg_msg = f"🌍 *YETIPS - {liga_seleccionada.upper()}*\n\n"
                
                for m in matches[:10]: # Top 10 partidos próximos
                    local_api = m['homeTeam']['name']
                    visita_api = m['awayTeam']['name']
                    
                    preds = calcular_predicciones(local_api, visita_api, stats_dict)
                    
                    if preds:
                        # Ajustar lógica de Goles: En CSV 'FTHG' es goles totales del equipo.
                        # Aquí hacemos (Prom Gol L + Prom Gol V). Para Over 2.5 suele funcionar.
                        p_gol = obtener_pick(preds['goles'], 2.5)
                        p_corn = obtener_pick(preds['corn'], 9.5)
                        p_card = obtener_pick(preds['cards'], 4.5)
                        
                        reporte_data.append({
                            "Partido": f"{local_api} vs {visita_api}",
                            "⚽ Goles": p_gol,
                            "⛳ Corners": p_corn,
                            "🟨 Amarillas": p_card
                        })
                        
                        tg_msg += f"⚔️ *{local_api} vs {visita_api}*\n"
                        tg_msg += f"⚽ {p_gol}\n⛳ {p_corn}\n🟨 {p_card}\n---\n"
                
                if reporte_data:
                    st.session_state['data_multi'] = pd.DataFrame(reporte_data)
                    st.session_state['tg_multi'] = tg_msg
                else:
                    st.warning("No se pudieron calcular predicciones (posible error de nombres).")
            else:
                st.warning("No hay partidos programados pronto para esta liga.")

    if 'data_multi' in st.session_state:
        st.dataframe(st.session_state['data_multi'], use_container_width=True)
        if st.button("✈️ Enviar a Telegram"):
            enviar_telegram(st.session_state['tg_multi'])
            st.success("Enviado")

# --- TAB 2: AUDITORÍA ---
with tab2:
    if st.button("📊 Verificar Aciertos (30 días)"):
        matches = get_matches(codigos['api'], 'FINISHED')
        if matches:
            audit = []
            aciertos = 0
            for m in matches:
                try:
                    goles_real = m['score']['fullTime']['home'] + m['score']['fullTime']['away']
                    local, visita = m['homeTeam']['name'], m['awayTeam']['name']
                    
                    preds = calcular_predicciones(local, visita, stats_dict)
                    if preds:
                        est = preds['goles']
                        pick = "MÁS" if est > 2.5 else "MENOS"
                        # Lógica simple de verificación Over/Under 2.5
                        ganada = (pick == "MÁS" and goles_real > 2.5) or (pick == "MENOS" and goles_real < 2.5)
                        if ganada: aciertos += 1
                        
                        audit.append({
                            "Partido": f"{local} vs {visita}",
                            "Real": goles_real,
                            "Pred": f"{est:.2f} ({pick})",
                            "Res": "✅" if ganada else "❌"
                        })
                except: continue
            
            df = pd.DataFrame(audit)
            if not df.empty:
                st.metric("Win Rate Goles", f"{(aciertos/len(df)*100):.1f}%")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Sin datos suficientes.")
