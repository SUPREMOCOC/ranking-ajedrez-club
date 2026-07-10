import streamlit as st
import pandas as pd
import plotly.express as px

# Configuración de la página web
st.set_page_config(
    page_title="Club de Ajedrez Vallecas Villa",
    page_icon="🏆",
    layout="centered"
)

# Título principal
st.title("🏆 Portal de Rankings - C.A. Vallecas Villa")
st.write("Historial y clasificaciones oficiales del club actualizados mensualmente.")

# Función para cargar y limpiar la base de datos completa
@st.cache_data(ttl=3600)
def cargar_datos_completos():
    try:
        df = pd.read_csv("jugadores_club.csv", sep=";")
        # Asegurar que el Elo sea numérico
        df["Elo_Actual"] = pd.to_numeric(df["Elo_Actual"], errors='coerce').fillna(0).astype(int)
        df["Max_Elo"] = pd.to_numeric(df["Max_Elo"], errors='coerce').fillna(0).astype(int)
        
        df["Nombre"] = df["Nombre"].astype(str).str.strip()
        df["Estado_Club"] = df["Estado_Club"].astype(str).str.strip()
        
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo de datos: {e}")
        return pd.DataFrame()

# FUNCIÓN NUEVA: Aplica color según el estado del jugador
def colorear_por_estado(row):
    estado = str(row["Estado"]).lower().strip()
    if estado == "baja":
        # Texto gris tenue y fondo ligeramente rojizo/oscuro para las bajas
        return ['color: #94a3b8; background-color: #2d1f1f; font-style: italic'] * len(row)
    else:
        # Texto normal (blanco/claro) para activos o altas
        return [''] * len(row)

df_base = cargar_datos_completos()

if not df_base.empty:
    # ---------------------------------------------------------
    # DEFINICIÓN DE LAS 3 PESTAÑAS PRINCIPALES
    # ---------------------------------------------------------
    tab_activos, tab_general, tab_hof = st.tabs([
        "🏃 Jugadores Activos", 
        "👥 Club Completo (Todos)", 
        "👑 Hall of Fame (Top 10)"
    ])

    # =========================================================
    # PESTAÑA 1: JUGADORES ACTIVOS (Aquí todos son activos, no hace falta color extra)
    # =========================================================
    with tab_activos:
        st.subheader("Clasificación de Jugadores en Activo")
        
        df_activos = df_base[df_base["Estado_Club"].str.lower().isin(["activo", "alta"])].copy()
        df_activos = df_activos.sort_values(by="Elo_Actual", ascending=False).reset_index(drop=True)
        df_activos.index = df_activos.index + 1
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Activos", len(df_activos))
        c2.metric("Elo Top Activo", f"{df_activos['Elo_Actual'].max()}")
        c3.metric("Media Elo Activos", int(df_activos["Elo_Actual"].mean()))
        
        buscar_act = st.text_input("🔍 Buscar jugador activo:", placeholder="Escribe un nombre...", key="search_act")
        df_act_filt = df_activos.copy()
        if buscar_act:
            df_act_filt = df_activos[df_activos["Nombre"].str.contains(buscar_act, case=False, na=False)]
            
        df_act_vista = df_act_filt[["Nombre", "ID_FIDE", "Elo_Actual", "Max_Elo", "Fecha_Record"]].copy()
        df_act_vista.columns = ["Nombre del Jugador", "ID FIDE", "Elo Actual", "Máximo Histórico", "Fecha Récord"]
        st.dataframe(df_act_vista, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})
        
        st.markdown("#### 📊 Gráfico: Top 10 Elo Actual")
        top_10_act = df_activos.head(10).sort_values(by="Elo_Actual", ascending=True)
        fig_act = px.bar(top_10_act, x="Elo_Actual", y="Nombre", orientation='h', text="Elo_Actual",
                         color="Elo_Actual", color_continuous_scale=["#334155", "#34d399"])
        fig_act.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#f8fafc",
                              showlegend=False, coloraxis_showscale=False, xaxis=dict(visible=False), yaxis=dict(showgrid=False))
        st.plotly_chart(fig_act, use_container_width=True, config={'displayModeBar': False})


    # =========================================================
    # PESTAÑA 2: CLUB COMPLETO (Muestra colores para las bajas)
    # =========================================================
    with tab_general:
        st.subheader("Escalafón General del Club")
        st.caption("Los jugadores en estado 'Baja' aparecen atenuados en color grisáceo.")
        
        df_general = df_base.sort_values(by="Elo_Actual", ascending=False).reset_index(drop=True)
        df_general.index = df_general.index + 1
        
        cg1, cg2 = st.columns(2)
        cg1.metric("Total Jugadores en Base", len(df_general))
        cg2.metric("Media Elo General", int(df_general["Elo_Actual"].mean()))
        
        buscar_gen = st.text_input("🔍 Buscar en todo el club:", placeholder="Escribe un nombre...", key="search_gen")
        df_gen_filt = df_general.copy()
        if buscar_gen:
            df_gen_filt = df_general[df_general["Nombre"].str.contains(buscar_gen, case=False, na=False)]
            
        df_gen_vista = df_gen_filt[["Nombre", "ID_FIDE", "Estado_Club", "Elo_Actual", "Max_Elo"]].copy()
        df_gen_vista.columns = ["Nombre del Jugador", "ID FIDE", "Estado", "Elo Actual", "Máximo Histórico"]
        
        # MAGIA AQUÍ: Usamos .style.apply para colorear la tabla dinámicamente
        df_gen_estilizado = df_gen_vista.style.apply(colorear_por_estado, axis=1)
        
        st.dataframe(df_gen_estilizado, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})


    # =========================================================
    # PESTAÑA 3: HALL OF FAME (Muestra colores para las bajas si las hay)
    # =========================================================
    with tab_hof:  
        st.subheader("👑 El Salón de la Fama")
        st.write("Los 10 techos de Elo más altos alcanzados por jugadores del club. (Las bajas históricas aparecen atenuadas).")
        
        df_hof = df_base.sort_values(by="Max_Elo", ascending=False).head(10).reset_index(drop=True)
        df_hof.index = df_hof.index + 1
        
        df_hof_vista = df_hof[["Nombre", "ID_FIDE", "Max_Elo", "Fecha_Record", "Elo_Actual", "Estado_Club"]].copy()
        df_hof_vista.columns = ["Leyenda del Club", "ID FIDE", "Récord de Elo", "Fecha del Récord", "Elo Actual", "Estado"]
        
        # MAGIA AQUÍ TAMBIÉN: Coloreamos el Hall of fame por si alguna leyenda ya no está activa
        df_hof_estilizado = df_hof_vista.style.apply(colorear_por_estado, axis=1)
        
        st.dataframe(df_hof_estilizado, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})
        
        st.markdown("#### 📊 Gráfico: Los 10 Techos Históricos del Club")
        top_10_hof = df_hof.sort_values(by="Max_Elo", ascending=True)
        fig_hof = px.bar(
            top_10_hof, 
            x="Max_Elo", 
            y="Nombre", 
            orientation='h', 
            text="Max_Elo",
            color="Max_Elo", 
            color_continuous_scale=["#451a03", "#f59e0b"],
            labels={"Max_Elo": "Récord de Elo"}
        )
        fig_hof.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)', 
            font_color="#f8fafc",
            showlegend=False, 
            coloraxis_showscale=False, 
            xaxis=dict(visible=False), 
            yaxis=dict(showgrid=False)
        )
        st.plotly_chart(fig_hof, use_container_width=True, config={'displayModeBar': False})

else:
    st.warning("Aún no hay datos de jugadores disponibles en el repositorio.")
