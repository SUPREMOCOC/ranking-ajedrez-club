import streamlit as st
import pandas as pd
import plotly.express as px

# Configuración de la página web
st.set_page_config(
    page_title="Club de Ajedrez Vallecas Villa",
    page_icon="🏆",
    layout="centered"
)

# Título y Subtítulo principal (¡Actualizado!)
st.title("🏆 C.A. Vallecas Villa")
st.subheader("Desde 1968")
st.write("Historial y clasificaciones oficiales del club actualizados mensualmente.")

# Función para cargar y limpiar la base de datos completa
@st.cache_data(ttl=3600)
def cargar_datos_completos():
    try:
        df = pd.read_csv("jugadores_club.csv", sep=";")
        
        # Asegurar que los Elos base sean numéricos
        if "Elo_Actual" in df.columns:
            df["Elo_Actual"] = pd.to_numeric(df["Elo_Actual"], errors='coerce').fillna(0).astype(int)
        if "Max_Elo" in df.columns:
            df["Max_Elo"] = pd.to_numeric(df["Max_Elo"], errors='coerce').fillna(0).astype(int)
        
        # Limpieza de texto básica
        if "Nombre" in df.columns:
            df["Nombre"] = df["Nombre"].astype(str).str.strip()
        if "Estado_Club" in df.columns:
            df["Estado_Club"] = df["Estado_Club"].astype(str).str.strip()
        
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo de datos: {e}")
        return pd.DataFrame()

# Función de estilo robusta: evita KeyError si la columna no existe
def colorear_por_estado(row):
    if "Estado" not in row:
        return [''] * len(row)
    
    estado = str(row["Estado"]).lower().strip()
    if estado == "baja":
        return ['color: #7f1d1d; background-color: #fee2e2; font-style: italic'] * len(row)
    else:
        return ['color: #064e3b; background-color: #d1fae5; font-weight: 500'] * len(row)

df_base = cargar_datos_completos()

if not df_base.empty:
    # ---------------------------------------------------------
    # DEFINICIÓN DE LAS 4 PESTAÑAS PRINCIPALES
    # ---------------------------------------------------------
    tab_activos, tab_general, tab_hof, tab_evolucion = st.tabs([
        "🏃 Jugadores Activos", 
        "👥 Club Completo (Todos)", 
        "👑 Hall of Fame",
        "📈 Evolución Elo"
    ])

    # =========================================================
    # PESTAÑA 1: JUGADORES ACTIVOS
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
            
        df_act_vista = df_act_filt[["Nombre", "ID_FIDE", "Elo_Actual", "Max_Elo"]].copy()
        # Añadimos la fecha récord si existe en el CSV
        if "Fecha_Record" in df_act_filt.columns:
            df_act_vista["Fecha_Record"] = df_act_filt["Fecha_Record"]
            df_act_vista.columns = ["Nombre del Jugador", "ID FIDE", "Elo Actual", "Máximo Histórico", "Fecha Récord"]
        else:
            df_act_vista.columns = ["Nombre del Jugador", "ID FIDE", "Elo Actual", "Máximo Histórico"]
        
        st.dataframe(df_act_vista, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})
        
        st.markdown("#### 📊 Top 10 Elo Actual")
        top_10_act = df_activos.head(10).sort_values(by="Elo_Actual", ascending=True)
        
        fig_act = px.bar(top_10_act, x="Elo_Actual", y="Nombre", orientation='h', text="Elo_Actual",
                         color="Elo_Actual", color_continuous_scale=["#a7f3d0", "#047857"])
        fig_act.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#f8fafc",
                              showlegend=False, coloraxis_showscale=False, xaxis=dict(visible=False), yaxis=dict(showgrid=False))
        st.plotly_chart(fig_act, use_container_width=True, config={'displayModeBar': False})


    # =========================================================
    # PESTAÑA 2: CLUB COMPLETO
    # =========================================================
    with tab_general:
        st.subheader("Escalafón General del Club")
        st.caption("Los jugadores en activo aparecen en filas verdes y las bajas en filas rojas.")
        
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
        
        df_gen_estilizado = df_gen_vista.style.apply(colorear_por_estado, axis=1)
        st.dataframe(df_gen_estilizado, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})


    # =========================================================
    # PESTAÑA 3: HALL OF FAME
    # =========================================================
    with tab_hof:  
        st.subheader("👑 El Salón de la Fama")
        st.write("Los 10 techos de Elo más altos alcanzados en la historia del club.")
        
        df_hof = df_base.sort_values(by="Max_Elo", ascending=False).head(10).reset_index(drop=True)
        df_hof.index = df_hof.index + 1
        
        # Preparamos las columnas asegurando que existan
        cols_hof = ["Nombre", "ID_FIDE", "Max_Elo", "Elo_Actual", "Estado_Club"]
        if "Fecha_Record" in df_hof.columns:
            cols_hof.insert(3, "Fecha_Record")
            
        df_hof_vista = df_hof[cols_hof].copy()
        
        if "Fecha_Record" in df_hof_vista.columns:
            df_hof_vista.columns = ["Leyenda del Club", "ID FIDE", "Récord de Elo", "Fecha del Récord", "Elo Actual", "Estado"]
        else:
            df_hof_vista.columns = ["Leyenda del Club", "ID FIDE", "Récord de Elo", "Elo Actual", "Estado"]
        
        df_hof_estilizado = df_hof_vista.style.apply(colorear_por_estado, axis=1)
        st.dataframe(df_hof_estilizado, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})
        
        st.markdown("#### 📊 Los 10 Techos Históricos")
        top_10_hof = df_hof.sort_values(by="Max_Elo", ascending=True)
        
        fig_hof = px.bar(
            top_10_hof, x="Max_Elo", y="Nombre", orientation='h', text="Max_Elo",
            color="Max_Elo", color_continuous_scale=["#64748b", "#059669"]
        )
        fig_hof.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#f8fafc",
            showlegend=False, coloraxis_showscale=False, xaxis=dict(visible=False), yaxis=dict(showgrid=False)
        )
        st.plotly_chart(fig_hof, use_container_width=True, config={'displayModeBar': False})


    # =========================================================
    # PESTAÑA 4: EVOLUCIÓN ELO (¡NUEVA!)
    # =========================================================
    with tab_evolucion:
        st.subheader("📈 Evolución Histórica de Elo")
        st.write("Selecciona uno o varios jugadores para comparar su progreso.")
        
        # 1. Detectar automáticamente las columnas de los meses
        # Asumimos que cualquier columna que no sea de las "fijas", es un mes
        columnas_fijas = ["Nombre", "ID_FIDE", "Estado_Club", "Elo_Actual", "Max_Elo", "Fecha_Record", "Unnamed: 0"]
        columnas_meses = [col for col in df_base.columns if col not in columnas_fijas]
        
        if len(columnas_meses) == 0:
            st.info("Aún no se han detectado columnas de meses. Asegúrate de añadir columnas como 'Ene_2024', 'Feb_2024' en tu archivo Excel/CSV.")
        else:
            # 2. Selector de jugadores
            lista_jugadores = df_base["Nombre"].sort_values().tolist()
            
            # Por defecto, seleccionamos al jugador número 1 en activo para que la gráfica no salga vacía
            jugador_default = []
            if not df_base[df_base["Estado_Club"].str.lower().isin(["activo", "alta"])].empty:
                jugador_default = [df_base[df_base["Estado_Club"].str.lower().isin(["activo", "alta"])].sort_values(by="Elo_Actual", ascending=False).iloc[0]["Nombre"]]
            
            jugadores_elegidos = st.multiselect(
                "♟️ Jugadores a comparar:",
                options=lista_jugadores,
                default=jugador_default
            )
            
            if jugadores_elegidos:
                # 3. Filtrar datos y transformarlos para la gráfica
                df_filtrado = df_base[df_base["Nombre"].isin(jugadores_elegidos)]
                
                # Convertimos el formato "ancho" (muchas columnas) a "largo" (ideal para gráficas)
                df_melted = df_filtrado.melt(
                    id_vars=["Nombre"], 
                    value_vars=columnas_meses, 
                    var_name="Mes", 
                    value_name="Elo"
                )
                
                # 4. Limpiar los Elos (ignorar celdas vacías o con un 0)
                df_melted["Elo"] = pd.to_numeric(df_melted["Elo"], errors="coerce")
                df_melted = df_melted.dropna(subset=["Elo"])  # Quitamos nulos
                df_melted = df_melted[df_melted["Elo"] > 0]   # Quitamos los 0 (si no tenían Elo en ese mes)
                
                if df_melted.empty:
                    st.warning("No hay historial numérico de Elo para los jugadores seleccionados.")
                else:
                    # 5. Dibujar la gráfica
                    fig_line = px.line(
                        df_melted, 
                        x="Mes", 
                        y="Elo", 
                        color="Nombre",
                        markers=True, # Pone un puntito en cada mes
                        title="Progresión del Elo FIDE"
                    )
                    
                    fig_line.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)', 
                        plot_bgcolor='rgba(0,0,0,0)', 
                        hovermode="x unified",
                        xaxis_title="",
                        yaxis_title="Puntos Elo"
                    )
                    
                    st.plotly_chart(fig_line, use_container_width=True)

else:
    st.warning("Aún no hay datos de jugadores disponibles en el repositorio.")
