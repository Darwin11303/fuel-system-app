import streamlit as st
import pandas as pd
import gspread
import uuid
import time
import os
import plotly.express as px
from datetime import datetime, date, timedelta
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
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def conectar_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
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
    return client.open("nutrition_db") 

def inicializar_pestanas(sheet):
    # 1. Conectar con REGISTROS (Tu diario)
    # Intentamos nombres probables para que no falle
    ws_log = None
    for nombre in ["Log_ID", "Registros", "Diario"]:
        try:
            ws_log = sheet.worksheet(nombre)
            break
        except: pass
        
    if not ws_log:
        # Si no existe ninguna, creamos "Registros"
        ws_log = sheet.add_worksheet(title="Registros", rows=2000, cols=20)
        ws_log.append_row(["Log_ID", "Fecha", "Hora", "Alimento", "Cantidad_Input", "Unidad", 
                           "Kcal", "Prot", "Carb", "Gras", "Es_Entreno", 
                           "Meta_Kcal", "Meta_Prot", "Meta_Carb", "Meta_Gras", "Momento"])

    # 2. Conectar con ALIMENTOS (Tu base de datos)
    # --- AQUÍ ESTABA EL ERROR ---
    ws_food = None
    # Buscamos "Alimento" (tu nombre real) primero
    for nombre in ["Alimento", "Alimentos", "Food", "BD"]:
        try:
            ws_food = sheet.worksheet(nombre)
            break
        except: pass
        
    if not ws_food:
        ws_food = sheet.add_worksheet(title="Alimentos", rows=1000, cols=10)
        ws_food.append_row(["Alimento", "Kcal", "Prot", "Carb", "Gras", "Tipo_Unidad", "Peso_Standard"])
            
    return ws_log, ws_food

def calcular_macros(qty, unidad, peso_std, k, p, c, g):
    if unidad == 'g': 
        factor = qty / 100
    else: 
        peso_real = qty * peso_std
        factor = peso_real / 100
    return {
        "kcal": round(k * factor), "prot": round(p * factor, 1),
        "carb": round(c * factor, 1), "gras": round(g * factor, 1)
    }

@st.cache_data(ttl=60)
def get_data_frame(_ws):
    try:
        data = _ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Si el DF está vacío, devolvemos estructura vacía segura
        if df.empty:
            return pd.DataFrame(columns=["Alimento", "Kcal", "Prot", "Carb", "Gras", "Tipo_Unidad", "Peso_Standard", "Fecha"])
        
        return df
    except Exception:
        return pd.DataFrame()

# Carga Inicial
sheet = conectar_google()
ws_log, ws_food = inicializar_pestanas(sheet)
df_foods = get_data_frame(ws_food)
df_logs = get_data_frame(ws_log)

# ==========================================
# 2. INTERFAZ LATERAL
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
        c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1])
        
        # LISTA DE ALIMENTOS: Verificación robusta
        lista_alimentos = []
        if not df_foods.empty and 'Alimento' in df_foods.columns:
            lista_alimentos = sorted(df_foods['Alimento'].astype(str).unique())
        
        # Selectbox con aviso si está vacío
        if not lista_alimentos:
            food_sel = c1.selectbox("Alimento", ["Cargando o Sin Datos..."], disabled=True)
            st.warning("⚠️ No se leyeron alimentos. Verifica que la pestaña en Google Sheets se llame 'Alimento' o 'Alimentos'.")
        else:
            food_sel = c1.selectbox("Alimento", lista_alimentos)
        
        momento = c2.selectbox("Momento", ["Desayuno", "Almuerzo", "Cena", "Snack 1", "Snack 2", "Pre-Entreno", "Post-Entreno"])
        
        qty = 0
        unidad_txt = "g"
        macros = {"kcal": 0, "prot": 0, "carb": 0, "gras": 0}
        
        if food_sel and food_sel != "Cargando o Sin Datos..." and not df_foods.empty:
            # Buscar info del alimento seleccionado
            row_food = df_foods[df_foods['Alimento'] == food_sel]
            if not row_food.empty:
                info = row_food.iloc[0]
                unidad_txt = info.get('Tipo_Unidad', 'g')
                val_default = 100.0 if unidad_txt == 'g' else 1.0
                step_val = 10.0 if unidad_txt == 'g' else 0.5
                
                qty = c3.number_input(f"Cant. ({unidad_txt})", value=val_default, step=step_val)
                
                # Calcular macros safely
                try:
                    macros = calcular_macros(
                        qty, unidad_txt, 
                        float(info.get('Peso_Standard', 1)), 
                        float(info.get('Kcal', 0)), 
                        float(info.get('Prot', 0)), 
                        float(info.get('Carb', 0)), 
                        float(info.get('Gras', 0))
                    )
                    c4.metric("Kcal", macros['kcal'])
                except:
                    c4.metric("Error Datos", 0)

        if st.button("Añadir", type="primary", disabled=(not lista_alimentos)):
            if food_sel and qty > 0:
                new_row = [
                    str(uuid.uuid4()), str(date.today()), datetime.now().strftime("%H:%M"), 
                    food_sel, qty, unidad_txt,
                    macros['kcal'], macros['prot'], macros['carb'], macros['gras'], 
                    str(es_entreno), m_kcal, m_prot, m_carb, m_gras, momento
                ]
                ws_log.append_row(new_row)
                st.toast(f"✅ {food_sel} añadido")
                get_data_frame.clear()
                time.sleep(0.5)
                st.rerun()

    st.divider()

    fecha_hoy = str(date.today())
    if not df_logs.empty and "Fecha" in df_logs.columns:
        # Limpieza de datos numéricos
        for col in ['Kcal', 'Prot', 'Carb', 'Gras']:
            if col in df_logs.columns:
                df_logs[col] = pd.to_numeric(df_logs[col], errors='coerce').fillna(0)
        
        df_hoy = df_logs[df_logs['Fecha'] == fecha_hoy].copy()
        
        if not df_hoy.empty:
            total_k = df_hoy['Kcal'].sum()
            total_p = df_hoy['Prot'].sum()
            total_c = df_hoy['Carb'].sum()
            total_g = df_hoy['Gras'].sum()
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Kcal", f"{int(total_k)}", f"{int(total_k - m_kcal)}", delta_color="inverse")
            k2.metric("Prot", f"{int(total_p)}g", f"{int(total_p - m_prot)}g")
            k3.metric("Carb", f"{int(total_c)}g", f"{int(total_c - m_carb)}g", delta_color="off")
            k4.metric("Gras", f"{int(total_g)}g", f"{int(total_g - m_gras)}g", delta_color="off")
            
            st.caption("Progreso Diario")
            st.progress(min(total_k / m_kcal, 1.0), text=f"Calorías: {int((total_k/m_kcal)*100)}%")
            st.progress(min(total_p / m_prot, 1.0), text=f"Proteína: {int((total_p/m_prot)*100)}%")

            st.markdown("##### 📋 Detalle de hoy")
            cols_show = ['Hora', 'Alimento', 'Cantidad_Input', 'Unidad', 'Kcal', 'Prot']
            if 'Momento' in df_hoy.columns: cols_show.insert(0, 'Momento')
            
            st.dataframe(df_hoy[cols_show], use_container_width=True, hide_index=True)
            
            with st.expander("🗑️ Borrar registro"):
                # Crear etiquetas únicas para borrar
                df_hoy['Label'] = df_hoy.apply(lambda x: f"{x['Hora']} - {x['Alimento']} ({x['Kcal']} kcal)", axis=1)
                opts = df_hoy['Label'].tolist()
                ids = df_hoy['Log_ID'].tolist()
                
                if opts:
                    del_idx = st.selectbox("Seleccionar:", range(len(opts)), format_func=lambda x: opts[x])
                    if st.button("Eliminar Registro"):
                        id_del = ids[del_idx]
                        try:
                            cell = ws_log.find(id_del)
                            ws_log.delete_rows(cell.row)
                            st.success("Eliminado")
                            get_data_frame.clear()
                            st.rerun()
                        except:
                            st.error("No se pudo encontrar el registro en Excel.")
        else:
            st.info("Aún no has comido nada hoy.")

# --- TAB 2: ANALÍTICA ---
with t2:
    if not df_logs.empty and "Fecha" in df_logs.columns:
        st.subheader("Tendencias")
        df_stats = df_logs.copy()
        df_stats['Fecha'] = pd.to_datetime(df_stats['Fecha'], errors='coerce')
        df_stats = df_stats.dropna(subset=['Fecha']).sort_values("Fecha")
        
        if not df_stats.empty:
            daily = df_stats.groupby("Fecha").agg({
                "Kcal": "sum", "Prot": "sum", "Meta_Kcal": "mean", "Meta_Prot": "mean"
            }).reset_index()
            
            last_7 = daily.tail(7)
            
            c1, c2 = st.columns(2)
            with c1:
                fig_cal = px.bar(last_7, x="Fecha", y=["Kcal", "Meta_Kcal"], barmode="group", 
                                 title="Calorías", color_discrete_map={"Kcal": "#4CAF50", "Meta_Kcal": "#E0E0E0"})
                st.plotly_chart(fig_cal, use_container_width=True)
            with c2:
                fig_prot = px.line(last_7, x="Fecha", y=["Prot", "Meta_Prot"], markers=True, 
                                   title="Proteína", color_discrete_map={"Prot": "#2196F3", "Meta_Prot": "#FF5252"})
                st.plotly_chart(fig_prot, use_container_width=True)

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