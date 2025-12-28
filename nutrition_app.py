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
    
    # ESTRATEGIA 1: Buscar archivo local (Prioridad para tu PC)
    if os.path.exists("credentials.json"):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            client = gspread.authorize(creds)
            return client.open("nutrition_db")
        except Exception as e:
            st.error(f"❌ Error leyendo archivo local: {e}")
            st.stop()
            
    # ESTRATEGIA 2: Buscar Secretos (Prioridad para la Nube)
    elif "gcp_service_account" in st.secrets:
        try:
            # Convertimos el objeto de secretos a diccionario normal
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # Arreglo crítico para la llave privada (reemplaza los \\n por saltos reales)
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            return client.open("nutrition_db")
        except Exception as e:
            st.error(f"❌ Error leyendo Secretos de Nube: {e}")
            st.stop()

    # Si llegamos aquí, no funcionó nada
    else:
        st.error("❌ ERROR CRÍTICO DE CONEXIÓN")
        st.warning("Diagnóstico:")
        st.write("1. En PC: No encuentro 'credentials.json'. Revisa que no se llame 'credentials.json.json'.")
        st.write("2. En Nube: No encuentro los Secretos configurados en 'Manage App'.")
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

def calcular_macros_core(qty, unidad, peso_std, k_base, p_base, c_base, g_base):
    if unidad == 'g': factor = qty / 100
    else: factor = (qty * peso_std) / 100
    return {
        "kcal": round(k_base * factor), "prot": round(p_base * factor, 1),
        "carb": round(c_base * factor, 1), "gras": round(g_base * factor, 1)
    }

def recalcular_logs_con_bd_actual(df_logs, df_foods):
    if df_logs.empty or df_foods.empty: return df_logs
    bd_dict = df_foods.set_index('Alimento').to_dict('index')
    new_k, new_p, new_c, new_g = [], [], [], []
    for index, row in df_logs.iterrows():
        food_name = row['Alimento']
        if food_name in bd_dict:
            info = bd_dict[food_name]
            macros = calcular_macros_core(row['Cantidad_Input'], info['Tipo_Unidad'], info['Peso_Standard'], info['Kcal'], info['Prot'], info['Carb'], info['Gras'])
            new_k.append(macros['kcal']); new_p.append(macros['prot']); new_c.append(macros['carb']); new_g.append(macros['gras'])
        else:
            new_k.append(row['Kcal']); new_p.append(row['Prot']); new_c.append(row['Carb']); new_g.append(row['Gras'])
    df_logs['Kcal'] = new_k; df_logs['Prot'] = new_p; df_logs['Carb'] = new_c; df_logs['Gras'] = new_g
    return df_logs

# CARGA DE DATOS
sheet = conectar_google()
ws_log, ws_food = inicializar_pestanas(sheet)
def get_data(ws): return pd.DataFrame(ws.get_all_records())
df_foods = get_data(ws_food)
df_logs_raw = get_data(ws_log)
df_logs = recalcular_logs_con_bd_actual(df_logs_raw, df_foods)

# INTERFAZ
with st.sidebar:
    st.title("🎛️ Centro de Mando")
    modo = st.radio("Modo del Día", ["🏋️‍♂️ Entrenamiento", "🔥 Descanso"], index=0)
    es_entreno = True if "Entrenamiento" in modo else False
    st.divider()
    if es_entreno:
        st.caption("🚀 METAS GYM (1850 kcal)")
        m_kcal = st.number_input("Kcal", value=1850); m_prot = st.number_input("Prot (g)", value=150)
        m_carb = st.number_input("Carb (g)", value=180); m_gras = st.number_input("Gras (g)", value=60)
    else:
        st.caption("🔥 METAS DESCANSO (1650 kcal)")
        m_kcal = st.number_input("Kcal", value=1650); m_prot = st.number_input("Prot (g)", value=145)
        m_carb = st.number_input("Carb (g)", value=130); m_gras = st.number_input("Gras (g)", value=65)

st.title("🧬 Fuel System Architect")
tab1, tab2, tab3 = st.tabs(["📅 Diario Inteligente", "🍎 Base de Datos", "📈 Analítica Viva"])

with tab1:
    with st.expander("➕ Registrar Alimento", expanded=True):
        c1, c2, c3 = st.columns([3, 2, 1])
        lista_ordenada = sorted(df_foods['Alimento'].unique()) if not df_foods.empty else []
        food_sel = c1.selectbox("Alimento", lista_ordenada)
        if food_sel:
            info = df_foods[df_foods['Alimento'] == food_sel].iloc[0]
            qty = c2.number_input(f"Cantidad ({info['Tipo_Unidad']})", value=1.0 if info['Tipo_Unidad'] != 'g' else 100.0, step=0.5 if info['Tipo_Unidad'] != 'g' else 10.0)
            macros = calcular_macros_core(qty, info['Tipo_Unidad'], info['Peso_Standard'], info['Kcal'], info['Prot'], info['Carb'], info['Gras'])
            if c3.button("Añadir", type="primary", use_container_width=True):
                new_row = [str(uuid.uuid4()), str(date.today()), datetime.now().strftime("%H:%M"), food_sel, qty, info['Tipo_Unidad'], macros['kcal'], macros['prot'], macros['carb'], macros['gras'], str(es_entreno), m_kcal, m_prot, m_carb, m_gras]
                ws_log.append_row(new_row); st.toast(f"✅ {food_sel} registrado"); time.sleep(1); st.rerun()
    st.divider()
    col_date, col_title = st.columns([1, 3])
    fecha_ver = col_date.date_input("📅 Ver fecha:", value=date.today())
    if not df_logs.empty:
        df_logs['Fecha'] = df_logs['Fecha'].astype(str)
        df_dia = df_logs[df_logs['Fecha'] == str(fecha_ver)]
        if not df_dia.empty:
            sum_p, sum_k = df_dia['Prot'].sum(), df_dia['Kcal'].sum()
            sum_c, sum_g = df_dia['Carb'].sum(), df_dia['Gras'].sum()
            try: meta_p_snap = df_dia.iloc[0]['Meta_Prot']; meta_k_snap = df_dia.iloc[0]['Meta_Kcal']
            except: meta_p_snap, meta_k_snap = m_prot, m_kcal
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Proteína", f"{int(sum_p)}g", f"{int(sum_p - meta_p_snap)}g"); k2.metric("Calorías", f"{int(sum_k)}", f"{int(sum_k - meta_k_snap)}", delta_color="inverse")
            k3.metric("Carbos", f"{int(sum_c)}g", f"Hoy: {int(sum_c)}"); k4.metric("Grasas", f"{int(sum_g)}g", f"Hoy: {int(sum_g)}")
            st.progress(min(sum_p/meta_p_snap, 1.0))
            st.subheader(f"Diario del {fecha_ver}")
            st.dataframe(df_dia[['Hora', 'Alimento', 'Cantidad_Input', 'Unidad', 'Prot', 'Kcal']], use_container_width=True)
            with st.expander("🗑️ Borrar registro"):
                opts = df_dia.apply(lambda x: f"{x['Hora']} - {x['Alimento']} ({x['Log_ID']})", axis=1).tolist()
                if opts:
                    del_sel = st.selectbox("Seleccionar item:", opts)
                    if st.button("Eliminar"):
                        id_del = del_sel.split("(")[-1].replace(")", "")
                        cell = ws_log.find(id_del); ws_log.delete_rows(cell.row); st.success("Eliminado"); time.sleep(1); st.rerun()
        else: st.info(f"No hay registros para {fecha_ver}.")

with tab2:
    st.header("Gestión de Alimentos")
    accion = st.radio("Acción:", ["➕ Nuevo", "✏️ Editar", "❌ Borrar"], horizontal=True)
    lista = sorted(df_foods['Alimento'].unique()) if not df_foods.empty else []
    if accion == "➕ Nuevo":
        with st.form("new"):
            n_name = st.text_input("Nombre"); c1, c2 = st.columns(2); n_unit = c1.selectbox("Unidad", ["g", "unidad", "scoop"]); n_w = c2.number_input("Peso (g)", value=100.0)
            cc1, cc2, cc3, cc4 = st.columns(4); nk = cc1.number_input("Kcal", 0); np = cc2.number_input("Prot", 0.0); nc = cc3.number_input("Carb", 0.0); ng = cc4.number_input("Gras", 0.0)
            if st.form_submit_button("Guardar"): ws_food.append_row([n_name, nk, np, nc, ng, n_unit, n_w]); st.success("Guardado"); st.rerun()
    elif accion == "✏️ Editar" and lista:
        sel = st.selectbox("Editar:", lista); curr = df_foods[df_foods['Alimento'] == sel].iloc[0]
        with st.form("edit"):
            e_name = st.text_input("Nombre", value=curr['Alimento']); e_w = st.number_input("Peso", value=float(curr['Peso_Standard']))
            ek = st.number_input("Kcal", value=int(curr['Kcal'])); ep = st.number_input("Prot", value=float(curr['Prot']))
            if st.form_submit_button("Actualizar"): cell = ws_food.find(sel); ws_food.update(f"A{cell.row}:G{cell.row}", [[e_name, ek, ep, float(curr['Carb']), float(curr['Gras']), curr['Tipo_Unidad'], e_w]]); st.success("Listo"); st.rerun()
    elif accion == "❌ Borrar" and lista:
        del_sel = st.selectbox("Eliminar:", lista)
        if st.button("Borrar"): cell = ws_food.find(del_sel); ws_food.delete_rows(cell.row); st.success("Borrado"); st.rerun()

with tab3:
    st.header("📊 Rendimiento")
    if not df_logs.empty:
        df_logs['FechaDT'] = pd.to_datetime(df_logs['Fecha'])
        last_7 = df_logs[df_logs['FechaDT'] >= pd.to_datetime(date.today() - timedelta(days=7))]
        if not last_7.empty:
            c1, c2 = st.columns(2); c1.metric("Promedio Prot (7d)", f"{int(last_7.groupby('Fecha')['Prot'].sum().mean())}g"); c2.metric("Promedio Kcal (7d)", f"{int(last_7.groupby('Fecha')['Kcal'].sum().mean())}")
        st.divider(); daily = df_logs.groupby('Fecha')[['Prot','Kcal','Carb','Gras']].sum().sort_index(ascending=False)
        for f, r in daily.iterrows():
            icon = "🟢" if r['Prot']/150 >= 1 else "🟡"
            with st.expander(f"{icon} {f} | P: {int(r['Prot'])}g"): st.write(f"Kcal: {int(r['Kcal'])} | C: {int(r['Carb'])} | G: {int(r['Gras'])}")