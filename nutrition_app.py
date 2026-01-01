import streamlit as st
import pandas as pd
import gspread
import uuid
import time
import os
import plotly.express as px  # Nuevo: Para gráficas bonitas
from datetime import datetime, date, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. CONFIGURACIÓN Y MOTOR DE NUBE
# ==========================================
st.set_page_config(page_title="Fuel System Architect", page_icon="🧬", layout="wide")

# Estilos CSS para igualar al Gym Tracker
st.markdown("""
    <style>
    .stButton>button {
        height: 3.2rem;
        width: 100%;
        font-weight: 700;
        border-radius: 8px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #4CAF50;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def conectar_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # ESTRATEGIA HÍBRIDA (Igual que Gym Tracker)
    if os.path.exists("credentials.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    elif "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        st.error("❌ No se encontraron credenciales.")
        st.stop()
        
    client = gspread.authorize(creds)
    return client.open("nutrition_db") # Asegúrate que tu Sheet se llame así

def inicializar_pestanas(sheet):
    # Pestaña Registros (Añadí columna "Momento" ej: Desayuno)
    try:
        ws_log = sheet.worksheet("Registros")
    except:
        ws_log = sheet.add_worksheet(title="Registros", rows=2000, cols=16)
        headers_log = ["Log_ID", "Fecha", "Hora", "Momento", "Alimento", "Cantidad_Input", "Unidad", 
                       "Kcal", "Prot", "Carb", "Gras", "Es_Entreno", 
                       "Meta_Kcal", "Meta_Prot", "Meta_Carb", "Meta_Gras"]
        ws_log.append_row(headers_log)

    # Pestaña Alimentos (Base de Datos)
    try:
        ws_food = sheet.worksheet("Alimentos")
    except:
        ws_food = sheet.add_worksheet(title="Alimentos", rows=1000, cols=8)
        ws_food.append_row(["Alimento", "Kcal", "Prot", "Carb", "Gras", "Tipo_Unidad", "Peso_Standard"])
        # (Aquí iría tu lista base de alimentos si está vacía, la he omitido para ahorrar espacio visual)
            
    return ws_log, ws_food

# Cálculo de Macros
def calcular_macros(qty, unidad, peso_std, k, p, c, g):
    if unidad == 'g': 
        factor = qty / 100
    else: 
        # Si es unidad/scoop, multiplicamos por el peso estándar de esa unidad y dividimos por 100
        # Ojo: Tus datos base parecen estar por 100g O por unidad entera. 
        # Asumiremos que los macros en BD son por 100g o por la unidad completa.
        # Ajuste simple: Si la unidad NO es gramos, asumimos que los macros de la BD son POR ESA UNIDAD.
        factor = qty 
        
    # Corrección lógica: Si tus macros en BD son siempre por 100g:
    if unidad != 'g':
        peso_real = qty * peso_std
        factor = peso_real / 100

    return {
        "kcal": round(k * factor), 
        "prot": round(p * factor, 1),
        "carb": round(c * factor, 1), 
        "gras": round(g * factor, 1)
    }

# --- CARGA DE DATOS OPTIMIZADA (Sin recálculo masivo) ---
@st.cache_data(ttl=60)
def get_data_frame(_ws):
    return pd.DataFrame(_ws.get_all_records())

sheet = conectar_google()
ws_log, ws_food = inicializar_pestanas(sheet)
df_foods = get_data_frame(ws_food)
df_logs = get_data_frame(ws_log)

# ==========================================
# 2. INTERFAZ LATERAL (CONFIGURACIÓN DIARIA)
# ==========================================
with st.sidebar:
    st.title("🎛️ Configuración")
    modo = st.radio("Modo del Día", ["🏋️‍♂️ Entrenamiento", "🔥 Descanso"], index=0)
    es_entreno = True if "Entrenamiento" in modo else False
    
    st.divider()
    
    # Metas dinámicas
    if es_entreno:
        st.caption("🚀 OBJETIVO: SUPERÁVIT / MANTENIMIENTO")
        c1, c2 = st.columns(2)
        m_kcal = c1.number_input("Kcal Meta", value=2800, step=50)
        m_prot = c2.number_input("Prot Meta", value=180, step=5)
        m_carb = c1.number_input("Carb Meta", value=300, step=10)
        m_gras = c2.number_input("Gras Meta", value=80, step=5)
    else:
        st.caption("🔥 OBJETIVO: DÉFICIT / DESCANSO")
        c1, c2 = st.columns(2)
        m_kcal = c1.number_input("Kcal Meta", value=2400, step=50)
        m_prot = c2.number_input("Prot Meta", value=180, step=5)
        m_carb = c1.number_input("Carb Meta", value=200, step=10)
        m_gras = c2.number_input("Gras Meta", value=80, step=5)

    if st.button("🔄 Actualizar Datos"):
        get_data_frame.clear()
        st.rerun()

# ==========================================
# 3. INTERFAZ PRINCIPAL
# ==========================================
st.title("🧬 Fuel System Architect")

t1, t2, t3 = st.tabs(["📅 Diario de Comidas", "📊 Analítica Pro", "🍎 Base de Alimentos"])

# --- TAB 1: DIARIO ---
with t1:
    # 1. Formulario de Registro Rápido
    with st.container():
        st.markdown("### 🍽️ Registrar Comida")
        c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1])
        
        lista_alimentos = sorted(df_foods['Alimento'].unique()) if not df_foods.empty else []
        food_sel = c1.selectbox("Alimento", lista_alimentos)
        
        # Selección de Momento
        momento = c2.selectbox("Momento", ["Desayuno", "Almuerzo", "Cena", "Snack 1", "Snack 2", "Pre-Entreno", "Post-Entreno"])
        
        qty = 0
        unidad_txt = "g"
        
        if food_sel:
            info = df_foods[df_foods['Alimento'] == food_sel].iloc[0]
            unidad_txt = info['Tipo_Unidad']
            val_default = 100.0 if unidad_txt == 'g' else 1.0
            step_val = 10.0 if unidad_txt == 'g' else 0.5
            qty = c3.number_input(f"Cant. ({unidad_txt})", value=val_default, step=step_val)
            
            # Preview de Macros
            macros = calcular_macros(qty, unidad_txt, info['Peso_Standard'], info['Kcal'], info['Prot'], info['Carb'], info['Gras'])
            c4.metric("Kcal Est.", macros['kcal'])

        if st.button("Añadir al Diario", type="primary"):
            if food_sel and qty > 0:
                new_row = [
                    str(uuid.uuid4()), str(date.today()), datetime.now().strftime("%H:%M"), 
                    momento, food_sel, qty, unidad_txt,
                    macros['kcal'], macros['prot'], macros['carb'], macros['gras'], 
                    str(es_entreno), m_kcal, m_prot, m_carb, m_gras
                ]
                ws_log.append_row(new_row)
                st.toast(f"✅ {food_sel} añadido a {momento}")
                get_data_frame.clear()
                time.sleep(0.5)
                st.rerun()

    st.divider()

    # 2. Resumen del Día Actual
    fecha_hoy = str(date.today())
    if not df_logs.empty:
        # Asegurar tipos
        df_logs['Kcal'] = pd.to_numeric(df_logs['Kcal'], errors='coerce').fillna(0)
        df_logs['Prot'] = pd.to_numeric(df_logs['Prot'], errors='coerce').fillna(0)
        
        df_hoy = df_logs[df_logs['Fecha'] == fecha_hoy].copy()
        
        if not df_hoy.empty:
            total_k = df_hoy['Kcal'].sum()
            total_p = df_hoy['Prot'].sum()
            total_c = df_hoy['Carb'].sum()
            total_g = df_hoy['Gras'].sum()
            
            # Barras de Progreso
            col_met1, col_met2 = st.columns(2)
            with col_met1:
                st.markdown(f"**Calorías:** {int(total_k)} / {m_kcal}")
                prog_k = min(total_k / m_kcal, 1.0)
                st.progress(prog_k, text=f"{int(prog_k*100)}%")
                
            with col_met2:
                st.markdown(f"**Proteína:** {int(total_p)}g / {m_prot}g")
                prog_p = min(total_p / m_prot, 1.0)
                st.progress(prog_p, text=f"{int(prog_p*100)}%")

            # Tabla Detallada
            st.markdown("##### 📋 Detalle de hoy")
            st.dataframe(
                df_hoy[['Momento', 'Alimento', 'Cantidad_Input', 'Unidad', 'Kcal', 'Prot', 'Carb', 'Gras']],
                use_container_width=True,
                hide_index=True
            )
            
            # Botón Borrar
            with st.expander("🗑️ Corregir (Borrar último registro)"):
                logs_hoy = df_hoy['Alimento'].tolist()
                log_ids = df_hoy['Log_ID'].tolist()
                if logs_hoy:
                    del_idx = st.selectbox("Selecciona para borrar:", range(len(logs_hoy)), format_func=lambda x: logs_hoy[x])
                    if st.button("Borrar Registro Seleccionado"):
                        id_to_del = log_ids[del_idx]
                        cell = ws_log.find(id_to_del)
                        ws_log.delete_rows(cell.row)
                        st.success("Borrado.")
                        get_data_frame.clear()
                        st.rerun()
        else:
            st.info("Aún no has comido nada hoy. ¡A darle gasolina al cuerpo! 🦍")

# --- TAB 2: ANALÍTICA (VISUAL) ---
with t2:
    if not df_logs.empty:
        st.subheader("Tendencias Semanales")
        
        # Preparar datos
        df_stats = df_logs.copy()
        df_stats['Fecha'] = pd.to_datetime(df_stats['Fecha'])
        df_stats = df_stats.sort_values("Fecha")
        
        # Agrupar por día
        daily_stats = df_stats.groupby("Fecha").agg({
            "Kcal": "sum", "Prot": "sum", "Carb": "sum", "Gras": "sum",
            "Meta_Kcal": "mean", "Meta_Prot": "mean" # Tomamos el promedio de la meta del día
        }).reset_index()
        
        # Filtro última semana
        last_7_days = daily_stats.tail(7)
        
        c1, c2 = st.columns(2)
        with c1:
            # Gráfica Calorías vs Meta
            fig_cal = px.bar(last_7_days, x="Fecha", y=["Kcal", "Meta_Kcal"], barmode="group",
                             title="Calorías Consumidas vs Meta", color_discrete_map={"Kcal": "#4CAF50", "Meta_Kcal": "#BDBDBD"})
            st.plotly_chart(fig_cal, use_container_width=True)
            
        with c2:
            # Gráfica Proteína
            fig_prot = px.line(last_7_days, x="Fecha", y=["Prot", "Meta_Prot"], markers=True,
                               title="Proteína Diaria (g)", color_discrete_map={"Prot": "#2196F3", "Meta_Prot": "#FF5252"})
            st.plotly_chart(fig_prot, use_container_width=True)
            
        # Distribución de Macros (Promedio)
        st.subheader("Distribución de Macros (Promedio 7 días)")
        avg_macros = last_7_days[["Prot", "Carb", "Gras"]].mean().reset_index()
        avg_macros.columns = ["Macro", "Gramos"]
        fig_pie = px.pie(avg_macros, values="Gramos", names="Macro", color="Macro",
                         color_discrete_map={"Prot": "#2196F3", "Carb": "#FFC107", "Gras": "#FF5252"})
        st.plotly_chart(fig_pie, use_container_width=True)

# --- TAB 3: BASE DE DATOS ---
with t3:
    st.markdown("### 🍎 Gestión de Alimentos")
    
    col_crud, col_view = st.columns([1, 2])
    
    with col_crud:
        st.info("Añadir Nuevo Alimento a la BD")
        with st.form("add_food"):
            n_name = st.text_input("Nombre del Alimento")
            n_unit = st.selectbox("Tipo Unidad", ["g", "unidad", "scoop"])
            n_std = st.number_input("Peso por Unidad/Porción (g)", value=100.0, help="Si es 'g', pon 100. Si es unidad, lo que pese una unidad.")
            
            st.caption("Macros por cada 100g (o por unidad si seleccionaste unidad)")
            nk = st.number_input("Kcal", 0)
            np = st.number_input("Proteína", 0.0)
            nc = st.number_input("Carbos", 0.0)
            ng = st.number_input("Grasas", 0.0)
            
            if st.form_submit_button("Guardar en Base de Datos"):
                ws_food.append_row([n_name, nk, np, nc, ng, n_unit, n_std])
                st.success(f"{n_name} Guardado")
                get_data_frame.clear()
                time.sleep(1)
                st.rerun()

    with col_view:
        st.markdown("#### Listado Actual")
        st.dataframe(df_foods, use_container_width=True, height=500)