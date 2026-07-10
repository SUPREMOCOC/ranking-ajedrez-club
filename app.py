import streamlit as st
import pandas as pd

# Configuración de la página web
st.set_page_config(
    page_title="Ranking FIDE | Club de Ajedrez",
    page_icon="🏆",
    layout="centered"
)

# Título principal
st.title("🏆 Ranking FIDE del Club")
st.write("Clasificación actualizada automáticamente a partir de las listas oficiales de la FIDE.")

# Función para cargar y limpiar datos
@st.cache_data(ttl=3600)  # Limpia la caché cada hora para captar actualizaciones
def cargar_datos():
    try:
        df = pd.read_csv("jugadores_club.csv", sep=";")
        # Filtrar solo jugadores activos o de alta
        df = df[df["Estado_Club"].str.lower().isin(["activo", "alta"])]
        # Asegurar que el Elo sea numérico
        df["Elo_Actual"] = pd.to_numeric(df["Elo_Actual"], errors='coerce').fillna(0).astype(int)
        df["Max_Elo"] = pd.to_numeric(df["Max_Elo"], errors='coerce').fillna(0).astype(int)
        # Ordenar de mayor a menor Elo
        df = df.sort_values(by="Elo_Actual", ascending=False).reset_index(drop=True)
        # Crear columna de posición en el ranking (1, 2, 3...)
        df.index = df.index + 1
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo de datos: {e}")
        return pd.DataFrame()

df = cargar_datos()

if not df.empty:
    # 1. Bloque de tarjetas con métricas top
    col1, col2, col3 = st.columns(3)
    col1.metric("Jugadores Activos", len(df))
    col2.metric("Elo Más Alto", f"{df['Elo_Actual'].max()} 👑")
    col3.metric("Media de Elo del Club", int(df["Elo_Actual"].mean()))

    st.markdown("---")

    # 2. Buscador interactivo
    buscador = st.text_input("🔍 Buscar jugador por nombre:", placeholder="Escribe parte del nombre...")
    
    df_filtrado = df.copy()
    if buscador:
        df_filtrado = df[df["Nombre"].str.contains(buscador, case=False, na=False)]

    # 3. Mostrar la tabla de posiciones estilizada
    st.subheader("📋 Lista de Clasificación")
    
    # Renombrar columnas para que queden bonitas en la web
    df_vista = df_filtrado[["Nombre", "ID_FIDE", "Elo_Actual", "Max_Elo", "Fecha_Record"]].copy()
    df_vista.columns = ["Nombre del Jugador", "ID FIDE", "Elo Actual", "Máximo Histórico", "Fecha Récord"]
    
    st.dataframe(
        df_vista, 
        use_container_width=True,
        column_config={
            "ID FIDE": st.column_config.NumberColumn(format="%d"), # Evita comas en el ID FIDE
        }
    )

    st.markdown("---")

    # 4. Gráfico del Top 10 del Club
    st.subheader("📊 Top 10 Jugadores con mayor Elo")
    top_10 = df.head(10)
    st.bar_chart(data=top_10, x="Nombre", y="Elo_Actual", color="#f59e0b")

else:
    st.warning("Aún no hay datos de jugadores disponibles en el repositorio.")
