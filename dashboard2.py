#nohup /home/pi/tesis_env/bin/streamlit run /home/pi/DATALOGGER/dashboard2.py &

import streamlit as st
import pandas as pd
import time

# Configuración de la página
st.set_page_config(page_title="Dashboard Red Mesh", layout="wide")
st.title("🌱 Dashboard de Monitoreo - Visión Simultánea")

# --- Panel de Configuración ---
st.sidebar.header("⚙️ Configuración")
auto_refresh = st.sidebar.checkbox("Activar Auto-Actualización (5s)", value=True)

# 1. Cargar y limpiar los datos
@st.cache_data(ttl=1) 
def load_data():
    try:
        df = pd.read_csv("datos_tesis_v5_metricas_completas.csv", na_values=["N/A", " N/A", "NaN", "nan"])
        df['Fecha_Hora'] = pd.to_datetime(df['Fecha_Hora'])
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

# Optimización de memoria: solo las últimas 500 filas
if not df.empty:
    df = df.tail(500)  

if df.empty:
    st.warning("⏳ Esperando datos... El archivo CSV aún no se ha creado o está vacío.")
    time.sleep(2)
    st.rerun()

# 2. Separar datos
df_nodos = df[df['Tipo_Mensaje'] == 'consenso'].copy()

# Si no hay datos de clima, usar consenso como fuente global
if "clima" in df['Tipo_Mensaje'].values:
    df_clima = df[df['Tipo_Mensaje'] == 'clima'].copy()
else:
    df_clima = df[df['Tipo_Mensaje'] == 'consenso'].copy()

# ==========================================
# ESCUDO PROTECTOR PARA GRÁFICAS (Evita Crash de Streamlit)
# ==========================================
cols_numericas = ['Temp_C', 'Luz_%', 'Estres_Evap', 'Nivel_Tanque_%']
for col in cols_numericas:
    if col in df_clima.columns:
        df_clima[col] = pd.to_numeric(df_clima[col], errors='coerce')

# ==========================================
# TRADUCTOR DE IDs (AHORA CON NÚMERO Y ID ORIGINAL)
# ==========================================
ids_gigantes = sorted(df_nodos['ID_Nodo'].dropna().unique())
# Aquí hacemos que el alias sea "Nodo 1 (ID)"
mapeo_nodos = {id_real: f"Nodo {i+1} ({int(id_real)})" for i, id_real in enumerate(ids_gigantes)}
df_nodos['Alias_Nodo'] = df_nodos['ID_Nodo'].map(mapeo_nodos)

# ==========================================
# SECCIÓN 1: DATOS GLOBALES (CLIMA Y TANQUE)
# ==========================================
st.header("🌍 Estado Global de la Red")
if not df_clima.empty:
    # Asegurarse de agarrar el último dato válido
    ultimo_clima = df_clima.dropna(subset=['Temp_C', 'Luz_%', 'Estres_Evap']).iloc[-1] if not df_clima.dropna(subset=['Temp_C']).empty else df_clima.iloc[-1]
    
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("🌡️ Temperatura Global", f"{ultimo_clima['Temp_C']} °C")
    c2.metric("☀️ Luz Global", f"{ultimo_clima['Luz_%']} %")
    c3.metric("💨 Estrés Evaporativo", f"{ultimo_clima['Estres_Evap']} %")

    nivel_tanque = float(ultimo_clima['Nivel_Tanque_%'])
    if nivel_tanque < 20.0:
        c4.error(f"💧 Nivel Tanque: {nivel_tanque} % (¡CRÍTICO!)")
    else:
        c4.metric("💧 Nivel Tanque", f"{nivel_tanque} %")
else:
    st.info("Aún no hay datos de clima en el archivo CSV.")

st.divider()

# ==========================================
# SECCIÓN 2: NODOS A LA PAR (COLUMNAS)
# ==========================================
st.header("🌿 Estado de los Nodos en Tiempo Real")
nodos_disponibles = sorted(df_nodos['Alias_Nodo'].dropna().unique())

if len(nodos_disponibles) > 0:
    columnas_nodos = st.columns(len(nodos_disponibles))
    
    for i, alias in enumerate(nodos_disponibles):
        with columnas_nodos[i]:
            st.subheader(f"📌 {alias}")  # Aquí aparecerá el nombre con el ID gigante
            df_nodo_actual = df_nodos[df_nodos['Alias_Nodo'] == alias]
            ultimo_dato = df_nodo_actual.iloc[-1]
            
            # --- Métricas principales ---
            st.metric("Humedad Local", f"{ultimo_dato['Hum_Local_%']} %")
            st.metric("Humedad Global (Consenso)", f"{ultimo_dato['Hum_Global_%']:.2f} %")
            st.metric("Urgencia de Riego", f"{ultimo_dato['Urgencia_Riego']:.2f}")

            # --- Estado de válvula ---
            if ultimo_dato['Valvula'] == 1:
                st.success("Válvula: ABIERTA 💧")
            else:
                st.info("Válvula: CERRADA 🛑")
                
            # --- Lógica de alertas ---
            alerta_v = str(ultimo_dato['Alerta_Valvula']).strip().lower()
            alerta_s = str(ultimo_dato['Alerta_Sensor']).strip().lower()
            
            if alerta_v == "true" or alerta_s == "true":
                st.error("⚠️ ALERTA EN ESTE NODO")
                if alerta_v == "true": st.write("🚨 Electroválvula bloqueada")
                if alerta_s == "true": st.write("🚨 Sensor de humedad fallando")

st.divider()

# ==========================================
# SECCIÓN 3: GRÁFICAS COMPARATIVAS
# ==========================================
st.header("📊 Comparativa Histórica")

df_nodos_limpio = df_nodos.drop_duplicates(subset=['Fecha_Hora', 'Alias_Nodo'])

# Primera fila de gráficas (Humedades)
col_graf1, col_graf2 = st.columns(2)

with col_graf1:
    st.subheader("💧 Humedad Local por Nodo")
    if not df_nodos_limpio.empty:
        df_pivot_hum_loc = df_nodos_limpio.pivot(index='Fecha_Hora', columns='Alias_Nodo', values='Hum_Local_%')
        st.line_chart(df_pivot_hum_loc)

with col_graf2:
    st.subheader("🌐 Humedad Global (Consenso Mesh)")
    if not df_nodos_limpio.empty:
        df_pivot_hum_glob = df_nodos_limpio.pivot(index='Fecha_Hora', columns='Alias_Nodo', values='Hum_Global_%')
        st.line_chart(df_pivot_hum_glob)

# Segunda fila de gráficas (Urgencia)
col_graf3, col_graf4 = st.columns(2)

with col_graf3:
    st.subheader("📈 Urgencia de Riego")
    if not df_nodos_limpio.empty:
        df_pivot_urg = df_nodos_limpio.pivot(index='Fecha_Hora', columns='Alias_Nodo', values='Urgencia_Riego')
        st.line_chart(df_pivot_urg)

with col_graf4:
    st.subheader("🌤️ Clima vs Tanque")
    if not df_clima.empty:
        df_clima_idx = df_clima.set_index('Fecha_Hora')[['Nivel_Tanque_%', 'Estres_Evap']].dropna()
        st.line_chart(df_clima_idx)

# --- NUEVA FILA DE GRÁFICAS GLOBALES ---
col_graf5, col_graf6 = st.columns(2)

with col_graf5:
    st.subheader("🌡️ Temperatura Global en el Tiempo")
    if not df_clima.empty:
        df_temp = df_clima.set_index('Fecha_Hora')[['Temp_C']].dropna()
        st.line_chart(df_temp)

with col_graf6:
    st.subheader("☀️ Luz Global en el Tiempo")
    if not df_clima.empty:
        df_luz = df_clima.set_index('Fecha_Hora')[['Luz_%']].dropna()
        st.line_chart(df_luz)

col_graf7, col_graf8 = st.columns(2)

with col_graf7:
    st.subheader("💨 Estrés Evaporativo Global en el Tiempo")
    if not df_clima.empty:
        df_estres = df_clima.set_index('Fecha_Hora')[['Estres_Evap']].dropna()
        st.line_chart(df_estres)

with col_graf8:
    st.subheader("💧 Nivel del Tanque en el Tiempo")
    if not df_clima.empty:
        df_tanque = df_clima.set_index('Fecha_Hora')[['Nivel_Tanque_%']].dropna()
        st.line_chart(df_tanque)

# Bucle de actualización
if auto_refresh:
    time.sleep(5)
    st.rerun()

