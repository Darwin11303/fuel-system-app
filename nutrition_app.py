import streamlit as st
import pandas as pd
import gspread
import uuid
import time
import os
from datetime import datetime, date, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. CONFIGURACIÓN Y MOTOR DE NUBE
# ==========================================
st.set_page_config(page_title="Fuel System Architect", page_icon="🧬", layout="wide")

@st.cache_resource
def conectar_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # ESTRATEGIA 1: Buscar archivo local (Prioridad en tu PC)
    if os.path.exists("credentials.json"):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            client = gspread.authorize(creds)
            return client.open("nutrition_db")
        except Exception as e:
            st.error(f"❌ Error leyendo credentials.json: {e}")
            st.stop()

    # ESTRATEGIA 2: Buscar secretos en la Nube
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            return client.open("nutrition_db")
    except Exception:
        pass 

    st.error("❌ ERROR CRÍTICO DE CONEXIÓN")
    st.stop()

def inicializar_pestanas(sheet):
    try:
        ws_log = sheet.worksheet("Registros")
    except:
        ws_log = sheet.add_worksheet(title="Registros", rows=2000, cols=15)
        headers_log = ["Log_ID", "Fecha", "Hora", "Alimento", "Cantidad_Input", "Unidad", 
                       "Kcal", "Prot", "Carb", "Gras", "Es_Entreno", 
                       "Meta_Kcal", "Meta_Prot", "Meta_Carb", "Meta_Gras"]
        ws_log.append_row(headers_log)

    llenar_bd = False
    try:
        ws_food = sheet.worksheet("Alimentos")
        if len(ws_food.col_values(1)) < 2: llenar_bd = True
    except:
        ws_food = sheet.add_worksheet(title="Alimentos", rows=1000, cols=8)
        llenar_bd = True
        
    if llenar_bd:
        ws_food.clear()
        ws_food.append_row(["Alimento", "Kcal", "Prot", "Carb", "Gras", "Tipo_Unidad", "Peso_Standard"])
        base_foods = [
            ["Arroz Blanco (Cocido)", 130, 2.7, 28.0, 0.3, "g", 1],
            ["Avena en Hojuelas", 389, 16.9, 66.3, 6.9, "g", 1],
            ["Verde (Cocido)", 122, 1.3, 30.0, 0.2, "g", 1],
            ["Maduro (Cocido)", 120, 1.3, 29.0, 0.3, "g", 1],
            ["Menestra Lenteja", 116, 9.0, 20.0, 0.4, "g", 1],
            ["Pechuga Pollo (Cocida)", 165, 31.0, 0.0, 3.6, "g", 1],
            ["Pechuga Pollo (Cruda)", 110, 23.0, 0.0, 1.2, "g", 1],
            ["Huevo Entero", 155, 13.0, 1.1, 11.0, "unidad", 55],
            ["Claras de Huevo", 52, 11.0, 0.7, 0.2, "g", 1],
            ["Whey Protein", 370, 75.0, 4.0, 2.0, "scoop (30g)", 30],
            ["Aceite de Oliva", 884, 0.0, 0.0, 100.0, "cucharada (15ml)", 14],
            ["Atún en Agua", 116, 26.0, 0.0, 0.8, "lata (160g)", 160],
            ["Pan Integral", 265, 9.0, 49.0, 4.2, "rebanada", 28],
            ["Papa Cocida", 87, 1.9, 20.1, 0.1, "g", 1],
            ["Yogur Griego", 59, 10.0, 3.6, 0.4, "g", 1]
        ]
        for food in base_foods: ws_food.append_row(food)
            
    return ws_log, ws_food

# ==========================================
# 2. CAPA DE LÓGICA (CORE LOGIC)
# ==========================================

def calcular_macros_core(qty, unidad, peso_std, k_base, p_base, c_base, g_base):
    """Calcula macros normalizados."""
    if unidad == 'g':
        factor = qty / 100
    else:
        factor = (qty * peso_std) / 100
    
    return {
        "kcal": round(k_base * factor),
        "prot": round(p_base * factor, 1),
        "carb": round(c_base * factor, 1),
        "gras": round(g_base * factor, 1)
    }

# --- NUEVA FUNCIÓN PRO: RECÁLCULO DINÁMICO ---
def recalcular_logs_con_bd_actual(df_logs, df_foods):
    """
    Toma el historial (logs) y RECALCULA todos los macros usando 
    la información MÁS RECIENTE de la base de alimentos (foods).
    Si un alimento fue borrado de la BD, mantiene el valor histórico original.
    """
    if df_logs.empty or df_foods.empty:
        return df_logs

    # Convertir BD a un diccionario para búsqueda rápida O(1)
    bd_dict = df_foods.set_index('Alimento').to_dict('index')
    
    # Listas para almacenar columnas recalculadas
    new_k, new_p, new_c, new_g = [], [], [], []
    
    for index, row in df_logs.iterrows():
        food_name = row['Alimento']
        
        # Si el alimento existe en la BD actual, recalculamos
        if food_name in bd_dict:
            info = bd_dict[food_name]
            macros = calcular_macros_core(
                row['Cantidad_Input'], info['Tipo_Unidad'], info['Peso_Standard'],
                info['Kcal'], info['Prot'], info['Carb'], info['Gras']
            )
            new_k.append(macros['kcal'])
            new_p.append(macros['prot'])
            new_c.append(macros['carb'])
            new_g.append(macros['gras'])
        else:
            # Si el alimento fue borrado, usamos el histórico (Fallback)
            new_k.append(row['Kcal'])
            new_p.append(row['Prot'])
            new_c.append(row['Carb'])
            new_g.append(row['Gras'])
            
    # Asignamos las columnas recalculadas (esto no afecta el Google Sheet, solo la visualización)
    df_logs['Kcal'] = new_k
    df_logs['Prot'] = new_p
    df_logs['Carb'] = new_c
    df_logs['Gras'] = new_g
    
    return df_logs

# ==========================================
# 3. CARGA DE DATOS
# ==========================================
sheet = conectar_google()
ws_log, ws_food = inicializar_pestanas(sheet)

def get_data(ws): return pd.DataFrame(ws.get_all_records())
df_foods = get_data(ws_food)
df_logs_raw = get_data(ws_log)

# --- APLICAMOS LA MAGIA AQUÍ ---
# Ya no usamos los logs crudos, usamos los recalculados
df_logs = recalcular_logs_con_bd_actual(df_logs_raw, df_foods)

# ==========================================
# 4. INTERFAZ: SIDEBAR (CONFIGURACIÓN)
# ==========================================
with st.sidebar:
    st.title("🎛️ Centro de Mando")
    modo = st.radio("Modo del Día", ["🏋️‍♂️ Entrenamiento", "🔥 Descanso"], index=0)
    es_entreno = True if "Entrenamiento" in modo else False
    st.divider()
    
    if es_entreno:
        st.caption("🚀 METAS GYM (1850 kcal)")
        m_kcal = st.number_input("Kcal", value=1850)
        m_prot = st.number_input("Prot (g)", value=150)
        m_carb = st.number_input("Carb (g)", value=180)
        m_gras = st.number_input("Gras (g)", value=60)
    else:
        st.caption("🔥 METAS DESCANSO (1650 kcal)")
        m_kcal = st.number_input("Kcal", value=1650)
        m_prot = st.number_input("Prot (g)", value=145)
        m_carb = st.number_input("Carb (g)", value=130)
        m_gras = st.number_input("Gras (g)", value=65)

# ==========================================
# 5. INTERFAZ PRINCIPAL
# ==========================================
st.title("🧬 Fuel System Architect")

tab1, tab2, tab3 = st.tabs(["📅 Diario Inteligente", "🍎 Base de Datos", "📈 Analítica Viva"])

# --- PESTAÑA 1: DIARIO ---
with tab1:
    with st.expander("➕ Registrar Alimento", expanded=True):
        c1, c2, c3 = st.columns([3, 2, 1])
        lista_ordenada = sorted(df_foods['Alimento'].unique()) if not df_foods.empty else []
        food_sel = c1.selectbox("Alimento", lista_ordenada)
        
        if food_sel:
            info = df_foods[df_foods['Alimento'] == food_sel].iloc[0]
            qty = c2.number_input(f"Cantidad ({info['Tipo_Unidad']})", 
                                  value=1.0 if info['Tipo_Unidad'] != 'g' else 100.0,
                                  step=0.5 if info['Tipo_Unidad'] != 'g' else 10.0)
            
            # Cálculo inicial para guardar snapshot
            macros = calcular_macros_core(
                qty, info['Tipo_Unidad'], info['Peso_Standard'],
                info['Kcal'], info['Prot'], info['Carb'], info['Gras']
            )
            
            if c3.button("Añadir", type="primary", use_container_width=True):
                new_row = [
                    str(uuid.uuid4()), str(date.today()), datetime.now().strftime("%H:%M"),
                    food_sel, qty, info['Tipo_Unidad'], 
                    macros['kcal'], macros['prot'], macros['carb'], macros['gras'], 
                    str(es_entreno), m_kcal, m_prot, m_carb, m_gras
                ]
                ws_log.append_row(new_row)
                st.toast(f"✅ {food_sel} registrado")
                time.sleep(1)
                st.rerun()

    st.divider()

    col_date, col_title = st.columns([1, 3])
    fecha_ver = col_date.date_input("📅 Ver fecha:", value=date.today())
    
    if not df_logs.empty:
        df_logs['Fecha'] = df_logs['Fecha'].astype(str)
        df_dia = df_logs[df_logs['Fecha'] == str(fecha_ver)]
        
        if not df_dia.empty:
            sum_p, sum_k = df_dia['Prot'].sum(), df_dia['Kcal'].sum()
            sum_c, sum_g = df_dia['Carb'].sum(), df_dia['Gras'].sum()
            
            try:
                meta_p_snap = df_dia.iloc[0]['Meta_Prot']
                meta_k_snap = df_dia.iloc[0]['Meta_Kcal']
            except:
                meta_p_snap, meta_k_snap = m_prot, m_kcal

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Proteína", f"{int(sum_p)}g", f"{int(sum_p - meta_p_snap)}g")
            k2.metric("Calorías", f"{int(sum_k)}", f"{int(sum_k - meta_k_snap)}", delta_color="inverse")
            k3.metric("Carbos", f"{int(sum_c)}g", f"Hoy: {int(sum_c)}")
            k4.metric("Grasas", f"{int(sum_g)}g", f"Hoy: {int(sum_g)}")
            
            st.caption(f"Progreso Proteína ({int(sum_p)}/{meta_p_snap}g)")
            st.progress(min(sum_p/meta_p_snap, 1.0))

            st.subheader(f"Diario del {fecha_ver}")
            # Mostramos la tabla CON LOS VALORES RECALCULADOS
            st.dataframe(df_dia[['Hora', 'Alimento', 'Cantidad_Input', 'Unidad', 'Prot', 'Kcal']], use_container_width=True)
            
            with st.expander("🗑️ Borrar registro de este día"):
                opts = df_dia.apply(lambda x: f"{x['Hora']} - {x['Alimento']} ({x['Log_ID']})", axis=1).tolist()
                if opts:
                    del_sel = st.selectbox("Seleccionar item:", opts)
                    if st.button("Eliminar definitivamente"):
                        id_del = del_sel.split("(")[-1].replace(")", "")
                        cell = ws_log.find(id_del)
                        ws_log.delete_rows(cell.row)
                        st.success("Eliminado")
                        time.sleep(1)
                        st.rerun()
        else:
            st.info(f"No hay registros para el {fecha_ver}.")

# --- PESTAÑA 2: GESTIÓN BD ---
with tab2:
    st.header("Gestión de Alimentos")
    accion = st.radio("¿Qué deseas hacer?", ["➕ Nuevo Alimento", "✏️ Editar Existente", "❌ Borrar Alimento"], horizontal=True)
    lista_bd_ordenada = sorted(df_foods['Alimento'].unique()) if not df_foods.empty else []

    if accion == "➕ Nuevo Alimento":
        with st.form("new_food"):
            n_name = st.text_input("Nombre del Alimento")
            c1, c2 = st.columns(2)
            n_unit = c1.selectbox("Tipo Unidad", ["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"])
            n_w = c2.number_input("Peso de 1 unidad (g)", value=100.0)
            
            st.write("Macros por 100g:")
            cc1, cc2, cc3, cc4 = st.columns(4)
            nk = cc1.number_input("Kcal", 0)
            np = cc2.number_input("Prot", 0.0)
            nc = cc3.number_input("Carb", 0.0)
            ng = cc4.number_input("Gras", 0.0)
            
            if st.form_submit_button("Guardar"):
                if n_name:
                    ws_food.append_row([n_name, nk, np, nc, ng, n_unit, n_w])
                    st.success("Guardado")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Ponle nombre.")

    elif accion == "✏️ Editar Existente":
        if lista_bd_ordenada:
            edit_sel = st.selectbox("Seleccionar Alimento:", lista_bd_ordenada)
            curr = df_foods[df_foods['Alimento'] == edit_sel].iloc[0]
            
            with st.form("edit_food"):
                e_name = st.text_input("Nombre", value=curr['Alimento'])
                e_unit = st.selectbox("Unidad", ["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"], index=["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"].index(curr['Tipo_Unidad']) if curr['Tipo_Unidad'] in ["g", "unidad", "scoop", "cucharada", "taza", "rebanada", "lata"] else 0)
                e_w = st.number_input("Peso Std (g)", value=float(curr['Peso_Standard']))
                ec1, ec2, ec3, ec4 = st.columns(4)
                ek = ec1.number_input("Kcal", value=int(curr['Kcal']))
                ep = ec2.number_input("Prot", value=float(curr['Prot']))
                ec = ec3.number_input("Carb", value=float(curr['Carb']))
                eg = ec4.number_input("Gras", value=float(curr['Gras']))
                
                if st.form_submit_button("Actualizar y Recalcular Historial"):
                    cell = ws_food.find(edit_sel)
                    ws_food.update(f"A{cell.row}:G{cell.row}", [[e_name, ek, ep, ec, eg, e_unit, e_w]])
                    st.success("✅ Alimento actualizado. El historial reflejará los nuevos valores.")
                    time.sleep(1)
                    st.rerun()

    elif accion == "❌ Borrar Alimento":
        if lista_bd_ordenada:
            del_sel = st.selectbox("Eliminar:", lista_bd_ordenada)
            if st.button("Borrar Definitivamente"):
                cell = ws_food.find(del_sel)
                ws_food.delete_rows(cell.row)
                st.success("Borrado")
                time.sleep(1)
                st.rerun()

# --- PESTAÑA 3: ANALÍTICA PRO ---
with tab3:
    st.header("📊 Rendimiento Vivo")
    
    if not df_logs.empty:
        # Aseguramos que estamos usando los datos RECALCULADOS
        cols = ['Prot', 'Kcal', 'Carb', 'Gras']
        
        df_logs['FechaDT'] = pd.to_datetime(df_logs['Fecha'])
        last_7 = df_logs[df_logs['FechaDT'] >= pd.to_datetime(date.today() - timedelta(days=7))]
        
        if not last_7.empty:
            avg_prot = last_7.groupby('Fecha')['Prot'].sum().mean()
            avg_kcal = last_7.groupby('Fecha')['Kcal'].sum().mean()
            
            c_avg1, c_avg2 = st.columns(2)
            c_avg1.metric("Promedio Proteína (7 días)", f"{int(avg_prot)}g")
            c_avg2.metric("Promedio Calorías (7 días)", f"{int(avg_kcal)}")
        
        st.divider()
        st.subheader("Historial Detallado")
        
        daily = df_logs.groupby('Fecha')[cols].sum().sort_index(ascending=False)
        
        for fecha, row in daily.iterrows():
            pct = row['Prot'] / 150 
            icon = "🟢" if pct >= 1.0 else "🟡" if pct > 0.8 else "🔴"
            
            with st.expander(f"{icon} {fecha} | P: {int(row['Prot'])}g | K: {int(row['Kcal'])}"):
                st.write(f"Carbos: {int(row['Carb'])}g | Grasas: {int(row['Gras'])}g")