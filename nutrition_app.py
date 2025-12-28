import streamlit as st
import pandas as pd
import gspread
import uuid
import time
from datetime import datetime, date
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. MOTOR DE NUBE (GOOGLE SHEETS)
# ==========================================
st.set_page_config(page_title="Fuel System Ultimate", page_icon="☁️", layout="wide")

# --- CONEXIÓN SEGURA ---
@st.cache_resource
def conectar_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("nutrition_db") 
        return spreadsheet
    except Exception as e:
        st.error(f"❌ Error de Conexión: {e}")
        st.stop()

# --- INICIALIZACIÓN DE PESTAÑAS (SETUP) ---
def inicializar_pestanas(sheet):
    # 1. Pestaña REGISTROS
    try:
        ws_log = sheet.worksheet("Registros")
    except:
        ws_log = sheet.add_worksheet(title="Registros", rows=2000, cols=15)
        # Cabeceras con Snapshot de Metas
        headers_log = ["Log_ID", "Fecha", "Hora", "Alimento", "Cantidad_Input", "Unidad", 
                       "Kcal", "Prot", "Carb", "Gras", "Es_Entreno", 
                       "Meta_Kcal", "Meta_Prot", "Meta_Carb", "Meta_Gras"]
        ws_log.append_row(headers_log)

    # 2. Pestaña ALIMENTOS (Base de Datos)
    try:
        ws_food = sheet.worksheet("Alimentos")
    except:
        ws_food = sheet.add_worksheet(title="Alimentos", rows=1000, cols=8)
        headers_food = ["Alimento", "Kcal", "Prot", "Carb", "Gras", "Tipo_Unidad", "Peso_Standard"]
        ws_food.append_row(headers_food)
        
        # --- BASE DE DATOS INICIAL AMPLIADA (ECUADOR + GYM) ---
        base_foods = [
            ["Arroz Blanco (Cocido)", 130, 2.7, 28.0, 0.3, "g", 1],
            ["Arroz Integral (Cocido)", 111, 2.6, 23.0, 0.9, "g", 1],
            ["Avena en Hojuelas", 389, 16.9, 66.3, 6.9, "g", 1],
            ["Verde (Cocido/Majado)", 122, 1.3, 30.0, 0.2, "g", 1],
            ["Maduro (Cocido)", 120, 1.3, 29.0, 0.3, "g", 1],
            ["Menestra Lenteja", 116, 9.0, 20.0, 0.4, "g", 1],
            ["Papa Cocida", 87, 1.9, 20.1, 0.1, "g", 1],
            ["Pan Integral", 265, 9.0, 49.0, 4.2, "rebanada", 28],
            ["Pechuga Pollo (Cruda)", 110, 23.0, 0.0, 1.2, "g", 1],
            ["Pechuga Pollo (Cocida)", 165, 31.0, 0.0, 3.6, "g", 1],
            ["Carne Res Magra (Cocida)", 250, 26.0, 0.0, 15.0, "g", 1],
            ["Atún en Agua (Drenado)", 116, 26.0, 0.0, 0.8, "lata (160g)", 160],
            ["Huevo Entero (Grande)", 155, 13.0, 1.1, 11.0, "unidad", 55],
            ["Claras de Huevo", 52, 11.0, 0.7, 0.2, "g", 1],
            ["Whey Protein", 370, 75.0, 4.0, 2.0, "scoop (30g)", 30],
            ["Yogur Griego Natural", 59, 10.0, 3.6, 0.4, "g", 1],
            ["Aceite de Oliva", 884, 0.0, 0.0, 100.0, "cucharada (15ml)", 14],
            ["Aguacate", 160, 2.0, 9.0, 15.0, "g", 1],
            ["Manzana", 52, 0.3, 14.0, 0.2, "unidad", 180],
            ["Plátano / Banano", 89, 1.1, 22.8, 0.3, "g", 1]
        ]
        for food in base_foods:
            ws_food.append_row(food)
            
    return ws_log, ws_food

# Carga inicial
sheet = conectar_google()
ws_log, ws_food = inicializar_pestanas(sheet)

# Funciones Helper para leer datos
def get_data(worksheet):
    return pd.DataFrame(worksheet.get_all_records())

df_foods = get_data(ws_food)
df_logs = get_data(ws_log)

# ==========================================
# 2. LÓGICA DE NEGOCIO (TUS METAS 70.8KG)
# ==========================================
with st.sidebar:
    st.title("🎛️ Configuración")
    modo = st.toggle("🏋️‍♂️ DÍA DE ENTRENO", value=True)
    st.divider()
    
    if modo:
        st.caption("🚀 MODO GYM (Superávit de Rendimiento)")
        m_kcal = st.number_input("Kcal", value=1850)
        m_prot = st.number_input("Prot (g)", value=150)
        m_carb = st.number_input("Carb (g)", value=180)
        m_gras = st.number_input("Gras (g)", value=60)
    else:
        st.caption("🔥 MODO DESCANSO (Quema de Grasa)")
        m_kcal = st.number_input("Kcal", value=1650)
        m_prot = st.number_input("Prot (g)", value=145)
        m_carb = st.number_input("Carb (g)", value=130)
        m_gras = st.number_input("Gras (g)", value=65)

# ==========================================
# 3. INTERFAZ MAESTRA
# ==========================================
st.title("🥗 Fuel System Ultimate")

tab1, tab2, tab3 = st.tabs(["🍽️ Diario & Dashboard", "🍎 Gestión Alimentos (BD)", "📊 Historial"])

# --- PESTAÑA 1: DIARIO ---
with tab1:
    # 1.A REGISTRO DE COMIDA
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 2, 1])
        
        # Lista ordenada
        lista = sorted(df_foods['Alimento'].unique()) if not df_foods.empty else []
        food_sel = c1.selectbox("¿Qué vas a comer?", lista)
        
        if food_sel:
            # Datos del alimento
            info = df_foods[df_foods['Alimento'] == food_sel].iloc[0]
            unidad = info['Tipo_Unidad']
            w_std = info['Peso_Standard']
            
            qty = c2.number_input(f"Cantidad ({unidad})", value=1.0 if unidad != 'g' else 100.0, step=0.5 if unidad != 'g' else 10.0)
            
            # Cálculo
            factor = qty / 100 if unidad == 'g' else (qty * w_std) / 100
            kc = round(info['Kcal'] * factor)
            pc = round(info['Prot'] * factor, 1)
            cc = round(info['Carb'] * factor, 1)
            gc = round(info['Gras'] * factor, 1)
            
            if c3.button("Añadir", type="primary", use_container_width=True):
                new_row = [
                    str(uuid.uuid4()), str(date.today()), datetime.now().strftime("%H:%M"),
                    food_sel, qty, unidad, kc, pc, cc, gc, str(modo),
                    m_kcal, m_prot, m_carb, m_gras # Snapshot de metas
                ]
                ws_log.append_row(new_row)
                st.success(f"✅ Registrado: {food_sel}")
                time.sleep(1)
                st.rerun()

    # 1.B DASHBOARD COMPLETO (4 MACROS)
    if not df_logs.empty:
        # Filtrar hoy
        hoy = str(date.today())
        # Convertir a string para asegurar match
        df_logs['Fecha'] = df_logs['Fecha'].astype(str)
        df_hoy = df_logs[df_logs['Fecha'] == hoy]
        
        sum_p = df_hoy['Prot'].sum()
        sum_k = df_hoy['Kcal'].sum()
        sum_c = df_hoy['Carb'].sum()
        sum_g = df_hoy['Gras'].sum()
        
        st.divider()
        st.subheader("📈 Métricas del Día")
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Proteína", f"{int(sum_p)}/{m_prot}g", int(sum_p - m_prot))
        k2.metric("Calorías", f"{int(sum_k)}/{m_kcal}", int(sum_k - m_kcal), delta_color="inverse")
        k3.metric("Carbos", f"{int(sum_c)}/{m_carb}g", int(sum_c - m_carb), delta_color="inverse")
        k4.metric("Grasas", f"{int(sum_g)}/{m_gras}g", int(sum_g - m_gras), delta_color="inverse")
        
        # Barras de Progreso
        st.caption("🏗️ Proteína")
        st.progress(min(sum_p/m_prot, 1.0))
        st.caption("🔋 Calorías")
        if sum_k > m_kcal: st.progress(1.0) 
        else: st.progress(sum_k/m_kcal)
        
        # 1.C LOG CON BORRADO
        with st.expander("📜 Ver Detalle / Borrar Registros"):
            st.dataframe(df_hoy[['Hora', 'Alimento', 'Cantidad_Input', 'Unidad', 'Prot', 'Kcal']], use_container_width=True)
            
            # Selector de borrado
            lista_borrar = df_hoy.apply(lambda x: f"{x['Hora']} - {x['Alimento']} ({x['Log_ID']})", axis=1).tolist()
            if lista_borrar:
                to_delete = st.selectbox("Seleccionar entrada para eliminar:", lista_borrar)
                if st.button("🗑️ Eliminar Entrada Seleccionada"):
                    id_del = to_delete.split("(")[-1].replace(")", "")
                    # Buscar celda y borrar fila
                    cell = ws_log.find(id_del)
                    ws_log.delete_rows(cell.row)
                    st.success("Entrada eliminada.")
                    time.sleep(1)
                    st.rerun()
    else:
        st.info("👋 ¡Bienvenido! Empieza registrando tu primera comida.")

# --- PESTAÑA 2: GESTIÓN BD (AGREGAR / EDITAR / BORRAR) ---
with tab2:
    mode_bd = st.radio("Acción:", ["➕ Agregar Nuevo", "✏️ Editar Existente", "❌ Borrar de Base de Datos"], horizontal=True)
    
    if mode_bd == "➕ Agregar Nuevo":
        with st.form("add_new"):
            st.subheader("Nuevo Alimento")
            n_name = st.text_input("Nombre")
            c1, c2 = st.columns(2)
            n_unit = c1.selectbox("Unidad", ["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"])
            n_w = c2.number_input("Peso Estándar (g)", value=100.0 if n_unit != 'g' else 1.0)
            
            st.markdown("**Información Nutricional (por 100g)**")
            cc1, cc2, cc3, cc4 = st.columns(4)
            nk = cc1.number_input("Kcal", 0)
            np = cc2.number_input("Prot", 0.0)
            nc = cc3.number_input("Carb", 0.0)
            ng = cc4.number_input("Gras", 0.0)
            
            if st.form_submit_button("Guardar en Nube"):
                if n_name:
                    ws_food.append_row([n_name, nk, np, nc, ng, n_unit, n_w])
                    st.success(f"{n_name} agregado.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Ponle un nombre.")

    elif mode_bd == "✏️ Editar Existente":
        if not df_foods.empty:
            edit_sel = st.selectbox("Editar:", sorted(df_foods['Alimento'].unique()))
            # Cargar datos actuales
            current = df_foods[df_foods['Alimento'] == edit_sel].iloc[0]
            
            with st.form("edit_food"):
                st.caption(f"Editando: {edit_sel}")
                # Inputs pre-cargados
                e_name = st.text_input("Nombre", value=current['Alimento'])
                e_unit = st.selectbox("Unidad", ["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"], index=["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"].index(current['Tipo_Unidad']) if current['Tipo_Unidad'] in ["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"] else 0)
                e_w = st.number_input("Peso Estándar (g)", value=float(current['Peso_Standard']))
                
                ec1, ec2, ec3, ec4 = st.columns(4)
                ek = ec1.number_input("Kcal (100g)", value=int(current['Kcal']))
                ep = ec2.number_input("Prot (100g)", value=float(current['Prot']))
                ec = ec3.number_input("Carb (100g)", value=float(current['Carb']))
                eg = ec4.number_input("Gras (100g)", value=float(current['Gras']))
                
                if st.form_submit_button("💾 Actualizar Datos"):
                    # Buscar la celda del nombre original
                    cell = ws_food.find(edit_sel)
                    # Actualizar fila (Row)
                    row_num = cell.row
                    # gspread range update
                    ws_food.update(f"A{row_num}:G{row_num}", [[e_name, ek, ep, ec, eg, e_unit, e_w]])
                    st.success("Datos actualizados.")
                    time.sleep(1)
                    st.rerun()

    elif mode_bd == "❌ Borrar de Base de Datos":
        if not df_foods.empty:
            del_sel = st.selectbox("Eliminar alimento para siempre:", sorted(df_foods['Alimento'].unique()))
            st.warning(f"¿Seguro que quieres borrar '{del_sel}' de la lista?")
            if st.button("Sí, borrar definitivamente"):
                cell = ws_food.find(del_sel)
                ws_food.delete_rows(cell.row)
                st.success(f"Adiós, {del_sel}.")
                time.sleep(1)
                st.rerun()

# --- PESTAÑA 3: HISTORIAL ---
with tab3:
    st.header("📊 Rendimiento Semanal")
    if not df_logs.empty:
        # Asegurar numéricos
        cols = ['Prot', 'Kcal', 'Carb', 'Gras']
        df_logs[cols] = df_logs[cols].apply(pd.to_numeric)
        
        # Agrupar por fecha
        resumen = df_logs.groupby('Fecha')[cols].sum().sort_index(ascending=False)
        
        for fecha, row in resumen.iterrows():
            # Intentar obtener meta del día (Snapshot)
            meta_snapshot = 150 # Default
            try:
                # Buscar primer registro de esa fecha
                meta_snapshot = df_logs[df_logs['Fecha'] == str(fecha)]['Meta_Prot'].iloc[0]
            except:
                pass
            
            pct = row['Prot'] / meta_snapshot
            icon = "🟢" if pct >= 1.0 else "🟡" if pct > 0.8 else "🔴"
            
            with st.expander(f"{icon} {fecha} | Prot: {int(row['Prot'])}g"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Kcal", int(row['Kcal']))
                c2.metric("Carbos", int(row['Carb']))
                c3.metric("Grasas", int(row['Gras']))