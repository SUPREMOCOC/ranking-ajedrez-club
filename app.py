import streamlit as st
import pandas as pd
import plotly.express as px
import html

# Configuración de la página web
st.set_page_config(
    page_title="Club de Ajedrez Vallecas Villa",
    page_icon="🏆",
    layout="centered"
)

# Título y Subtítulo principal
st.title("🏆 Club de Ajedrez Vallecas Villa")
st.subheader("Desde 1968")
st.write("Historial y clasificaciones oficiales del club actualizados mensualmente.")

# Función para cargar y limpiar la base de datos (VERSIÓN BLINDADA)
@st.cache_data(ttl=3600)
def cargar_datos_completos():
    try:
        df = pd.read_csv("jugadores_club.csv", sep=";")
        
        renombres = {
            "Estado": "Estado_Club", "estado": "Estado_Club", 
            "ID": "ID_FIDE", "id": "ID_FIDE", "FIDE": "ID_FIDE",
            "Elo": "Elo_Actual", "elo": "Elo_Actual", 
            "Max Elo": "Max_Elo", "Max_elo": "Max_Elo",
            "Fecha Record": "Fecha_Record", "Fecha": "Fecha_Record"
        }
        df.rename(columns=renombres, inplace=True)
        
        for col in ["Nombre", "ID_FIDE", "Estado_Club", "Elo_Actual", "Max_Elo", "Fecha_Record"]:
            if col not in df.columns:
                df[col] = ""

        df["Elo_Actual"] = pd.to_numeric(df["Elo_Actual"], errors='coerce').fillna(0).astype(int)
        df["Max_Elo"] = pd.to_numeric(df["Max_Elo"], errors='coerce').fillna(0).astype(int)
        
        df["Nombre"] = df["Nombre"].astype(str).str.strip()
        df["Estado_Club"] = df["Estado_Club"].astype(str).str.strip()
        
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo de datos: {e}")
        return pd.DataFrame()

def colorear_por_estado(row):
    estado = str(row.get("Estado", "")).lower().strip()
    if estado == "baja":
        return ['color: #7f1d1d; background-color: #fee2e2; font-style: italic'] * len(row)
    else:
        return ['color: #064e3b; background-color: #d1fae5; font-weight: 500'] * len(row)

dict_nombres_tablas = {
    "Nombre": "Nombre del Jugador",
    "ID_FIDE": "ID FIDE",
    "Estado_Club": "Estado",
    "Elo_Actual": "Elo Actual",
    "Max_Elo": "Máximo Histórico",
    "Fecha_Record": "Fecha Récord"
}

df_base = cargar_datos_completos()

if not df_base.empty:
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
        
        total_activos = len(df_activos)
        elo_top = int(df_activos['Elo_Actual'].max()) if total_activos > 0 else 0
        media_activos = int(df_activos["Elo_Actual"].mean()) if total_activos > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Activos", total_activos)
        c2.metric("Elo Top Activo", elo_top)
        c3.metric("Media Elo Activos", media_activos)
        
        buscar_act = st.text_input("🔍 Buscar jugador activo:", placeholder="...", key="search_act")
        df_act_filt = df_activos.copy()
        if buscar_act:
            df_act_filt = df_activos[df_activos["Nombre"].str.contains(buscar_act, case=False, na=False)]
            
        cols_deseadas_act = ["Nombre", "ID_FIDE", "Elo_Actual", "Max_Elo", "Fecha_Record"]
        cols_reales_act = [c for c in cols_deseadas_act if c in df_act_filt.columns]
        
        df_act_vista = df_act_filt[cols_reales_act].copy()
        df_act_vista.rename(columns=dict_nombres_tablas, inplace=True)
        
        st.dataframe(df_act_vista, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})
        
        st.markdown("#### 📊 Top 10 Elo Actual")
        if total_activos > 0:
            top_10_act = df_activos.head(10).sort_values(by="Elo_Actual", ascending=True)
            fig_act = px.bar(top_10_act, x="Elo_Actual", y="Nombre", orientation='h', text="Elo_Actual",
                             color="Elo_Actual", color_continuous_scale=["#a7f3d0", "#047857"])
            fig_act.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#f8fafc",
                                  showlegend=False, coloraxis_showscale=False, xaxis=dict(visible=False), yaxis=dict(showgrid=False))
            st.plotly_chart(fig_act, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("No hay jugadores activos suficientes para generar la gráfica.")

    # =========================================================
    # PESTAÑA 2: CLUB COMPLETO
    # =========================================================
    with tab_general:
        st.subheader("Escalafón General del Club")
        df_general = df_base.sort_values(by="Elo_Actual", ascending=False).reset_index(drop=True)
        df_general.index = df_general.index + 1
        
        media_gen = int(df_general["Elo_Actual"].mean()) if not df_general.empty else 0
        
        cg1, cg2 = st.columns(2)
        cg1.metric("Total Jugadores en Base", len(df_general))
        cg2.metric("Media Elo General", media_gen)
        
        buscar_gen = st.text_input("🔍 Buscar en todo el club:", placeholder="...", key="search_gen")
        df_gen_filt = df_general.copy()
        if buscar_gen:
            df_gen_filt = df_general[df_general["Nombre"].str.contains(buscar_gen, case=False, na=False)]
            
        cols_deseadas_gen = ["Nombre", "ID_FIDE", "Estado_Club", "Elo_Actual", "Max_Elo"]
        cols_reales_gen = [c for c in cols_deseadas_gen if c in df_gen_filt.columns]
        
        df_gen_vista = df_gen_filt[cols_reales_gen].copy()
        df_gen_vista.rename(columns=dict_nombres_tablas, inplace=True)
        
        df_gen_estilizado = df_gen_vista.style.apply(colorear_por_estado, axis=1)
        st.dataframe(df_gen_estilizado, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})

    # =========================================================
    # PESTAÑA 3: HALL OF FAME
    # =========================================================
    with tab_hof:  
        st.subheader("👑 El Salón de la Fama")
        df_hof = df_base.sort_values(by="Max_Elo", ascending=False).head(10).reset_index(drop=True)
        df_hof.index = df_hof.index + 1
                # --- PODIO: Top 3 destacado en tarjetas propias ---
        podio = df_hof.head(3)
        if not podio.empty:
            medallas = ["🥇", "🥈", "🥉"]
            colores_fondo = ["#fff7e6", "#f1f5f9", "#fdf1e7"]
            colores_borde = ["#d97706", "#94a3b8", "#c2703c"]

            cols_podio = st.columns(len(podio))
            for i, (_, fila) in enumerate(podio.iterrows()):
                estado = str(fila.get("Estado_Club", "")).strip().lower()
                etiqueta_estado = "🟢 Activo" if estado in ("activo", "alta") else "⚪ Baja"
                nombre_seguro = html.escape(str(fila.get("Nombre", "")))
                fecha_record = fila.get("Fecha_Record", "") or "—"

                with cols_podio[i]:
                    st.markdown(f"""
                        <div style="background-color:{colores_fondo[i]};border:2px solid {colores_borde[i]};
                                    border-radius:16px;padding:20px 10px;text-align:center;">
                            <div style="font-size:2.4rem;line-height:1;">{medallas[i]}</div>
                            <div style="font-weight:700;font-size:1rem;margin-top:8px;min-height:2.4em;">{nombre_seguro}</div>
                            <div style="font-size:1.9rem;font-weight:800;color:{colores_borde[i]};margin-top:4px;">{int(fila['Max_Elo'])}</div>
                            <div style="font-size:0.78rem;color:#475569;margin-top:6px;">{fecha_record} · {etiqueta_estado}</div>
                        </div>
                    """, unsafe_allow_html=True)
            st.write("")
        
        cols_deseadas_hof = ["Nombre", "ID_FIDE", "Max_Elo", "Fecha_Record", "Elo_Actual", "Estado_Club"]
        cols_reales_hof = [c for c in cols_deseadas_hof if c in df_hof.columns]
        
        df_hof_vista = df_hof[cols_reales_hof].copy()
        
        dict_hof = dict_nombres_tablas.copy()
        dict_hof["Nombre"] = "Leyenda del Club"
        dict_hof["Max_Elo"] = "Récord de Elo"
        dict_hof["Fecha_Record"] = "Fecha del Récord"
        
        df_hof_vista.rename(columns=dict_hof, inplace=True)
        
        df_hof_estilizado = df_hof_vista.style.apply(colorear_por_estado, axis=1)
        st.dataframe(df_hof_estilizado, use_container_width=True, column_config={"ID FIDE": st.column_config.NumberColumn(format="%d")})
        
        st.markdown("#### 📊 Los 10 Techos Históricos")
        if not df_hof.empty:
            top_10_hof = df_hof.sort_values(by="Max_Elo", ascending=True)
            fig_hof = px.bar(top_10_hof, x="Max_Elo", y="Nombre", orientation='h', text="Max_Elo",
                color="Max_Elo", color_continuous_scale=["#64748b", "#059669"]
            )
            fig_hof.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="#f8fafc",
                showlegend=False, coloraxis_showscale=False, xaxis=dict(visible=False), yaxis=dict(showgrid=False))
            st.plotly_chart(fig_hof, use_container_width=True, config={'displayModeBar': False})

    # =========================================================
    # PESTAÑA 4: EVOLUCIÓN ELO Y RENDIMIENTO
    # =========================================================
    with tab_evolucion:
        st.subheader("📈 Evolución Histórica de Elo")
        
        columnas_fijas = ["Nombre", "ID_FIDE", "Estado_Club", "Elo_Actual", "Max_Elo", "Fecha_Record"]
        columnas_meses = [col for col in df_base.columns if col not in columnas_fijas and "Unnamed" not in col]
        
        if len(columnas_meses) == 0:
            st.info("Aún no se han detectado columnas de meses en el archivo.")
        else:
            lista_jugadores = df_base["Nombre"].sort_values().tolist()
            jugadores_activos = df_base[df_base["Estado_Club"].str.lower().isin(["activo", "alta"])]
            
            jugador_default = []
            if not jugadores_activos.empty:
                jugador_default = [jugadores_activos.sort_values(by="Elo_Actual", ascending=False).iloc[0]["Nombre"]]
            elif len(lista_jugadores) > 0:
                jugador_default = [lista_jugadores[0]]
            
            jugadores_elegidos = st.multiselect("♟️ Jugadores a comparar:", options=lista_jugadores, default=jugador_default)
            
            if jugadores_elegidos:
                df_filtrado = df_base[df_base["Nombre"].isin(jugadores_elegidos)]
                df_melted = df_filtrado.melt(id_vars=["Nombre"], value_vars=columnas_meses, var_name="Mes", value_name="Elo")
                
                df_melted["Elo"] = pd.to_numeric(df_melted["Elo"], errors="coerce")
                df_melted = df_melted.dropna(subset=["Elo"])
                df_melted = df_melted[df_melted["Elo"] > 0]
                
                if not df_melted.empty:
                    fig_line = px.line(df_melted, x="Mes", y="Elo", color="Nombre", markers=True)
                    fig_line.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified")
                    st.plotly_chart(fig_line, use_container_width=True)
                
                # -----------------------------------------------------------------
                # ANÁLISIS DE RENDIMIENTO (Último mes, Último año, Rango Personalizado, Pico)
                # -----------------------------------------------------------------
                st.markdown("---")
                st.markdown("### 📊 Análisis de Rendimiento Detallado")
                
                # Selectores para el rango personalizado
                st.write("Selecciona un período de tiempo personalizado:")
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    mes_inicio_sel = st.selectbox("📅 Fecha de Inicio:", options=columnas_meses, index=0, key="ini_custom")
                with col_f2:
                    mes_fin_sel = st.selectbox("📅 Fecha de Fin:", options=columnas_meses, index=len(columnas_meses)-1, key="fin_custom")
                
                for jugador in jugadores_elegidos:
                    df_jug = df_melted[df_melted["Nombre"] == jugador]
                    datos_fijos = df_base[df_base["Nombre"] == jugador].iloc[0]
                    max_historico_fijo = int(datos_fijos["Max_Elo"]) if pd.notna(datos_fijos["Max_Elo"]) else 0
                    
                    st.write(f"**♟️ Estadísticas de {jugador}:**")
                    
                    if not df_jug.empty:
                        elo_actual = int(df_jug["Elo"].iloc[-1])
                        pico_max = max(int(df_jug["Elo"].max()), max_historico_fijo)
                        
                        # 1. Variación del Último Mes
                        if len(df_jug) >= 2:
                            elo_prev_mes = int(df_jug["Elo"].iloc[-2])
                            dif_mes = elo_actual - elo_prev_mes
                            label_mes = f"Mes Ant. ({df_jug['Mes'].iloc[-2]})"
                        else:
                            dif_mes = 0
                            label_mes = "Mes Anterior"
                            
                        # 2. Variación del Último Año (12 meses atrás o inicio)
                        if len(df_jug) >= 13:
                            elo_prev_ano = int(df_jug["Elo"].iloc[-13])
                            label_ano = f"Hace 1 Año ({df_jug['Mes'].iloc[-13]})"
                            dif_ano = elo_actual - elo_prev_ano
                        elif len(df_jug) > 1:
                            elo_prev_ano = int(df_jug["Elo"].iloc[0])
                            label_ano = f"Desde Inicio ({df_jug['Mes'].iloc[0]})"
                            dif_ano = elo_actual - elo_prev_ano
                        else:
                            dif_ano = 0
                            label_ano = "Último Año"

                        # Primera fila de métricas: Último Mes, Último Año, Pico
                        col1, col2, col3 = st.columns(3)
                        col1.metric(label="🗓️ Último Mes", value=elo_actual, delta=f"{dif_mes:+d} pts")
                        col2.metric(label=f"📅 {label_ano}", value=elo_actual, delta=f"{dif_ano:+d} pts")
                        
                        distancia_pico = elo_actual - pico_max
                        col3.metric(label="👑 Pico de Elo", value=pico_max, delta=f"{distancia_pico} al récord" if distancia_pico < 0 else "¡En su Récord!")
                        
                        # Segunda fila: Rango personalizado seleccionado con los desplegables
                        val_inicio = df_jug[df_jug["Mes"] == mes_inicio_sel]["Elo"]
                        val_fin = df_jug[df_jug["Mes"] == mes_fin_sel]["Elo"]
                        
                        if not val_inicio.empty and not val_fin.empty:
                            elo_ini = int(val_inicio.values[0])
                            elo_fin = int(val_fin.values[0])
                            dif_personalizada = elo_fin - elo_ini
                            st.metric(label=f"🎯 Rango Personalizado ({mes_inicio_sel} $\rightarrow$ {mes_fin_sel})", value=elo_fin, delta=f"{dif_personalizada:+d} puntos")
                        
                        st.divider()
                    else:
                        st.info(f"💡 **{jugador}** no tiene registros mensuales suficientes para calcular rendimientos.")
                        st.divider()

else:
    st.warning("Aún no hay datos de jugadores disponibles.")
