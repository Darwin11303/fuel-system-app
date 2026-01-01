import streamlit as st
import pandas as pd
import gspread
import uuid
import time
import os
import plotly.express as px
from datetime import datetime, date
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. CONFIGURACIÓN Y MOTOR DE NUBE
# ==========================================
st.set_page_config(page_title="Fuel System Architect", page_icon="🧬", layout="wide")

st.markdown("""
    <style>
    .stButton>button {
        height: 3.2rem;
        width: 100%;
        font-weight: 700;
        border-radius: 8px;
    }
    /* Estilo para las tarjetas de previsualización */
    div[data-testid="stMetricValue"] {
        font-size: 1.2rem;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def conectar_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    try:
        if os.path.exists("credentials.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        elif "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            st.error("❌ Error Fatal: No se encontraron credenciales (ni locales ni en Secrets).")
            st.stop()
            
        client = gspread.authorize(creds)
        return client.open("nutrition_db")
    except Exception as e:
        st.error(f"❌ Error de Conexión: {e}")
        st.stop()

def inicializar_pestanas(sheet):
    # Intentamos conectar de forma segura
    ws_log = None
    for n in ["Log_ID", "Registros", "Diario"]:
        try: ws_log = sheet.worksheet(n); break
        except: pass
    
    if not ws_log:
        ws_log = sheet.add_worksheet(title="Registros", rows=2000, cols=20)
        # Headers oficiales V4
        ws_log.append_row(["Log_ID", "Fecha", "Hora", "Alimento", "Cantidad_Input", "Unidad", 
                           "Kcal", "Prot", "Carb", "Gras", "Es_Entreno", 
                           "Meta_Kcal", "Meta_Prot", "Meta_Carb", "Meta_Gras", "Momento"])

    ws_food = None
    for n in ["Alimento", "Alimentos", "BD"]:
        try: ws_food = sheet.worksheet(n); break
        except: pass
        
    if not ws_food:
        ws_food = sheet.add_worksheet(title="Alimentos", rows=1000, cols=10)
        ws_food.append_row(["Alimento", "Kcal", "Prot", "Carb", "Gras", "Tipo_Unidad", "Peso_Standard"])
            
    return ws_log, ws_food

def calcular_macros(qty, unidad, peso_std, k, p, c, g):
    # Lógica de conversión
    if unidad == 'g': 
        factor = qty / 100
    else: 
        # Si es unidad/scoop, asumimos que los macros BD son por 100g de producto
        # y usamos el peso standard para convertir.
        peso_real = qty * peso_std
        factor = peso_real / 100
    
    return {
        "kcal": round(k * factor), 
        "prot": round(p * factor, 1),
        "carb": round(c * factor, 1), 
        "gras": round(g * factor, 1)
    }

@st.cache_data(ttl=60)
def get_data_frame(_ws):
    try:
        data = _ws.get_all_records()
        df = pd.DataFrame(data)
        
        # --- BLINDAJE DE COLUMNAS (Fix solicitado por Chat) ---
        # Definimos qué columnas DEBEN existir sí o sí para que el código no rompa
        required_cols = ["Log_ID", "Fecha", "Hora", "Alimento", "Cantidad_Input", "Unidad", 
                         "Kcal", "Prot", "Carb", "Gras", "Es_Entreno", 
                         "Meta_Kcal", "Meta_Prot", "Meta_Carb", "Meta_Gras", "Momento"]
        
        if df.empty:
            return pd.DataFrame(columns=required_cols)
        
        # Si falta alguna columna crítica (por ejemplo, Cantidad_Input), la creamos rellena de 0 o ""
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0 if "Meta" in col or "Kcal" in col or "Prot" in col else ""

        # Forzar tipos de datos para evitar errores de graficado
        # Fechas siempre string al leer
        if "Fecha" in df.columns:
            df["Fecha"] = df["Fecha"].astype(str)
            
        return df
    except Exception as e:
        # Si falla la lectura, devolvemos DF vacío seguro
        return pd.DataFrame()

# Carga Inicial
sheet = conectar_google()
ws_log, ws_food = inicializar_pestanas(sheet)
df_foods = get_data_frame(ws_food)
df_logs = get_data_frame(ws_log)

# ==========================================
# 2. PANEL LATERAL (METAS)
# ==========================================
with st.sidebar:
    st.title("🎛️ Panel de Control")
    modo = st.radio("Modo del Día", ["🏋️‍♂️ Entrenamiento", "🔥 Descanso"], index=0)
    es_entreno = True if "Entrenamiento" in modo else False
    st.divider()
    
    if es_entreno:
        st.caption("🚀 METAS GYM (1850 kcal)")
        c1, c2 = st.columns(2)
        m_kcal = c1.number_input("Kcal", value=1850, step=50)
        m_prot = c2.number_input("Prot", value=150, step=5)
        m_carb = c1.number_input("Carb", value=180, step=10)
        m_gras = c2.number_input("Gras", value=60, step=5)
    else:
        st.caption("🔥 METAS DESCANSO (1650 kcal)")
        c1, c2 = st.columns(2)
        m_kcal = c1.number_input("Kcal", value=1650, step=50)
        m_prot = c2.number_input("Prot", value=145, step=5)
        m_carb = c1.number_input("Carb", value=130, step=10)
        m_gras = c2.number_input("Gras", value=65, step=5)

    if st.button("🔄 Recargar Datos"):
        get_data_frame.clear()
        st.rerun()

# ==========================================
# 3. INTERFAZ PRINCIPAL
# ==========================================
st.title("🧬 Fuel System Architect")

t1, t2, t3 = st.tabs(["📅 Diario", "📊 Analítica", "🍎 Alimentos"])

# --- TAB 1: DIARIO ---
with t1:
    with st.container():
        st.markdown("### 🍽️ Registrar Comida")
        
        # Fila 1: Selección básica
        c1, c2 = st.columns([2, 1])
        
        lista_alimentos = []
        if not df_foods.empty and 'Alimento' in df_foods.columns:
            lista_alimentos = sorted(df_foods['Alimento'].astype(str).unique())
            
        if not lista_alimentos:
            food_sel = c1.selectbox("Alimento", ["Sin datos..."], disabled=True)
            st.warning("⚠️ Base de datos vacía o no leída.")
        else:
            food_sel = c1.selectbox("Alimento", lista_alimentos)
            
        momento = c2.selectbox("Momento", ["Desayuno", "Almuerzo", "Cena", "Snack 1", "Snack 2", "Pre-Entreno", "Post-Entreno"])

        # Fila 2: Cantidad y PREVISUALIZACIÓN (Tu petición)
        c_qty, c_prev = st.columns([1, 3])
        
        qty = 0
        unidad_txt = "g"
        macros = {"kcal": 0, "prot": 0, "carb": 0, "gras": 0}
        
        if food_sel and food_sel != "Sin datos..." and not df_foods.empty:
            row_food = df_foods[df_foods['Alimento'] == food_sel]
            if not row_food.empty:
                info = row_food.iloc[0]
                unidad_txt = info.get('Tipo_Unidad', 'g')
                
                # Input de Cantidad
                val_default = 100.0 if unidad_txt == 'g' else 1.0
                step_val = 10.0 if unidad_txt == 'g' else 0.5
                qty = c_qty.number_input(f"Cant. ({unidad_txt})", value=val_default, step=step_val)
                
                # CÁLCULO EN VIVO
                try:
                    macros = calcular_macros(
                        qty, unidad_txt, 
                        float(info.get('Peso_Standard', 1)), 
                        float(info.get('Kcal', 0)), 
                        float(info.get('Prot', 0)), 
                        float(info.get('Carb', 0)), 
                        float(info.get('Gras', 0))
                    )
                    
                    # --- AQUÍ ESTÁ LA PREVISUALIZACIÓN QUE PEDISTE ---
                    with c_prev:
                        # Usamos un container para que se vea bonito
                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("🔥 Kcal", macros['kcal'])
                        k2.metric("🥩 Prot", macros['prot'])
                        k3.metric("🍚 Carb", macros['carb'])
                        k4.metric("🥑 Gras", macros['gras'])
                        
                except Exception as e:
                    st.error("Error calculando macros.")

        # Botón de añadir (Debajo de la previsualización)
        if st.button("Añadir al Diario", type="primary", disabled=(not lista_alimentos)):
            if food_sel and qty > 0:
                new_row = [
                    str(uuid.uuid4()),                  # Log_ID
                    str(date.today()),                  # Fecha
                    datetime.now().strftime("%H:%M"),   # Hora
                    food_sel,                           # Alimento
                    qty,                                # Cantidad_Input (Ya existe en la BD gracias al blindaje)
                    unidad_txt,                         # Unidad
                    macros['kcal'], macros['prot'], macros['carb'], macros['gras'], 
                    str(es_entreno), m_kcal, m_prot, m_carb, m_gras, momento
                ]
                try:
                    ws_log.append_row(new_row)
                    st.toast(f"✅ {food_sel} añadido exitosamente")
                    get_data_frame.clear()
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error escribiendo en Google Sheets: {e}")

    st.divider()

    # --- RESUMEN DEL DÍA ---
    fecha_hoy = str(date.today())
    
    if not df_logs.empty and "Fecha" in df_logs.columns:
        # Asegurar numéricos para sumas
        for col in ['Kcal', 'Prot', 'Carb', 'Gras']:
            if col in df_logs.columns:
                df_logs[col] = pd.to_numeric(df_logs[col], errors='coerce').fillna(0)
        
        df_hoy = df_logs[df_logs['Fecha'] == fecha_hoy].copy()
        
        if not df_hoy.empty:
            # Totales
            tot = df_hoy[['Kcal', 'Prot', 'Carb', 'Gras']].sum()
            
            # Tarjetas de Resumen
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Kcal", int(tot['Kcal']), int(tot['Kcal'] - m_kcal), delta_color="inverse")
            k2.metric("Prot", f"{int(tot['Prot'])}g", f"{int(tot['Prot'] - m_prot)}g")
            k3.metric("Carb", f"{int(tot['Carb'])}g", f"{int(tot['Carb'] - m_carb)}g", delta_color="off")
            k4.metric("Gras", f"{int(tot['Gras'])}g", f"{int(tot['Gras'] - m_gras)}g", delta_color="off")
            
            # Barras
            st.caption("Progreso Diario")
            st.progress(min(tot['Kcal'] / m_kcal, 1.0), text=f"Calorías: {int((tot['Kcal']/m_kcal)*100)}%")
            st.progress(min(tot['Prot'] / m_prot, 1.0), text=f"Proteína: {int((tot['Prot']/m_prot)*100)}%")

            # Tabla Detalle (Columnas seguras)
            st.markdown("##### 📋 Detalle de hoy")
            safe_cols = [c for c in ['Momento', 'Hora', 'Alimento', 'Cantidad_Input', 'Unidad', 'Kcal', 'Prot', 'Carb', 'Gras'] if c in df_hoy.columns]
            st.dataframe(df_hoy[safe_cols], use_container_width=True, hide_index=True)
            
            # Borrado Seguro
            with st.expander("🗑️ Borrar registro"):
                # Crear etiqueta legible
                df_hoy['Display'] = df_hoy.apply(lambda x: f"{x.get('Hora','?')} - {x.get('Alimento','?')} ({x.get('Kcal',0)} kcal)", axis=1)
                
                opciones = df_hoy['Display'].tolist()
                ids = df_hoy['Log_ID'].tolist()
                
                if opciones:
                    idx = st.selectbox("Seleccionar item:", range(len(opciones)), format_func=lambda x: opciones[x])
                    if st.button("Eliminar Registro Seleccionado"):
                        id_target = ids[idx]
                        try:
                            # Buscamos la celda exacta del ID para borrar ESA fila y no otra
                            cell = ws_log.find(id_target)
                            ws_log.delete_rows(cell.row)
                            st.success("Registro eliminado.")
                            get_data_frame.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al borrar: {e}. (Puede que el ID no se encuentre)")
        else:
            st.info("Aún no has registrado comidas hoy.")

# --- TAB 2: ANALÍTICA ---
with t2:
    if not df_logs.empty and "Fecha" in df_logs.columns:
        st.subheader("Tendencias")
        # Copia para no romper original
        df_stats = df_logs.copy()
        
        # Conversión segura de fechas
        df_stats['Fecha_DT'] = pd.to_datetime(df_stats['Fecha'], errors='coerce')
        df_stats = df_stats.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT")
        
        if not df_stats.empty:
            # Agrupación segura
            cols_agg = {k: "sum" for k in ["Kcal", "Prot"] if k in df_stats.columns}
            cols_mean = {k: "mean" for k in ["Meta_Kcal", "Meta_Prot"] if k in df_stats.columns}
            # Unir diccionarios
            agg_dict = {**cols_agg, **cols_mean}
            
            daily = df_stats.groupby("Fecha_DT").agg(agg_dict).reset_index()
            last_7 = daily.tail(7)
            
            c1, c2 = st.columns(2)
            with c1:
                if "Kcal" in last_7.columns and "Meta_Kcal" in last_7.columns:
                    fig_cal = px.bar(last_7, x="Fecha_DT", y=["Kcal", "Meta_Kcal"], barmode="group", 
                                     title="Calorías", color_discrete_map={"Kcal": "#4CAF50", "Meta_Kcal": "#E0E0E0"})
                    st.plotly_chart(fig_cal, use_container_width=True)
            with c2:
                if "Prot" in last_7.columns and "Meta_Prot" in last_7.columns:
                    fig_prot = px.line(last_7, x="Fecha_DT", y=["Prot", "Meta_Prot"], markers=True, 
                                       title="Proteína", color_discrete_map={"Prot": "#2196F3", "Meta_Prot": "#FF5252"})
                    st.plotly_chart(fig_prot, use_container_width=True)
        else:
            st.info("No hay datos históricos válidos.")

# --- TAB 3: BASE DE DATOS ---
with t3:
    st.markdown("### 🍎 Gestión de Alimentos")
    col_crud, col_view = st.columns([1, 2])
    with col_crud:
        st.info("Añadir Nuevo")
        with st.form("add_food"):
            n_name = st.text_input("Nombre")
            n_unit = st.selectbox("Unidad", ["g", "unidad", "scoop"])
            n_std = st.number_input("Peso (g) por unidad", value=100.0)
            nk = st.number_input("Kcal (por 100g/unidad)", 0)
            np_ = st.number_input("Prot", 0.0)
            nc = st.number_input("Carb", 0.0)
            ng = st.number_input("Gras", 0.0)
            
            if st.form_submit_button("Guardar"):
                ws_food.append_row([n_name, nk, np_, nc, ng, n_unit, n_std])
                st.success("Guardado")
                get_data_frame.clear()
                time.sleep(1)
                st.rerun()
    with col_view:
        if not df_foods.empty:
            st.dataframe(df_foods, use_container_width=True)