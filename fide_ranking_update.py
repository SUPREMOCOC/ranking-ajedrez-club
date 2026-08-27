#!/usr/bin/env python3
"""
Actualiza el Elo FIDE actual y el récord histórico (Max_Elo) de los
jugadores "Activo"/"Alta" del club, a partir del listado oficial que
publica la FIDE cada mes.

Uso:
    python fide_ranking_update.py [--csv jugadores_club.csv] [--dry-run]

Pensado para ejecutarse automáticamente (p. ej. desde GitHub Actions),
pero funciona igual de bien en local.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

# URL del listado combinado (estándar+rápidas+blitz) de la FIDE en XML.
# Es la URL de descarga directa que la FIDE mantiene estable desde hace
# años para consumo automático (fuera de la web con JavaScript).
# Si algún mes deja de funcionar, entra en https://ratings.fide.com/download_lists.phtml,
# copia el enlace "XML format" de la lista combinada y pégalo aquí (o pásalo
# con --fide-url).
# URL del listado de Elo estándar/clásico de la FIDE en XML. Usamos el
# listado "solo estándar" (no el combinado con rápidas y blitz) porque es
# lo único que necesitamos y pesa mucho menos (~13 MB en vez de ~47 MB):
# más rápido de descargar automáticamente, y más cómodo si algún mes lo
# descargas tú a mano (ver --archivo-local más abajo).
# Si algún mes deja de funcionar, entra en https://ratings.fide.com/download_lists.phtml,
# copia el enlace "XML format" de la fila STANDARD y pégalo aquí (o pásalo
# con --fide-url).
FIDE_XML_URL = "https://ratings.fide.com/download/standard_rating_list_xml.zip"
FIDE_DOWNLOAD_PAGE = "https://ratings.fide.com/download_lists.phtml"

CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"  # conserva el BOM que ya trae el fichero del club

# Columnas fijas que siempre existen, en este orden.
CAMPOS_BASE = ["ID_FIDE", "Nombre", "Estado_Club", "Elo_Actual", "Max_Elo", "Fecha_Record"]

# Además de las fijas, cada mes se añade (o actualiza) una columna con el
# Elo de ese mes, con formato "Elo_AAAA-MM" (p. ej. "Elo_2026-07"), para
# poder consultar la evolución histórica de cada jugador.
PATRON_COL_HISTORICA = re.compile(r"^Elo_(\d{4})-(\d{2})$")

MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def normaliza(texto: str) -> str:
    """minúsculas y sin tildes, para poder comparar estados con seguridad."""
    texto = (texto or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def fecha_formato_club(d: Optional[date] = None) -> str:
    """Devuelve la fecha en el mismo formato que ya usa el CSV: 'jul-26'."""
    d = d or date.today()
    return f"{MESES_ES[d.month - 1]}-{d.strftime('%y')}"


def columna_mes_actual(d: Optional[date] = None) -> str:
    """Nombre de la columna histórica del mes, p. ej. 'Elo_2026-07'."""
    d = d or date.today()
    return f"Elo_{d.strftime('%Y-%m')}"


def ordenar_columnas(fieldnames_existentes: list[str], col_mes_actual: str) -> list[str]:
    """
    Devuelve la lista completa y ordenada de columnas: las fijas primero,
    luego todas las columnas históricas "Elo_AAAA-MM" en orden cronológico
    (incluyendo la del mes actual aunque sea nueva).
    """
    historicas = {c for c in fieldnames_existentes if PATRON_COL_HISTORICA.match(c)}
    historicas.add(col_mes_actual)
    historicas_ordenadas = sorted(historicas, key=lambda c: PATRON_COL_HISTORICA.match(c).groups())
    return CAMPOS_BASE + historicas_ordenadas


# ---------------------------------------------------------------------------
# Descarga y parseo del listado FIDE
# ---------------------------------------------------------------------------

def descargar_xml_fide(url: str = FIDE_XML_URL, intentos: int = 3) -> bytes:
    """Descarga el .zip del listado FIDE y devuelve los bytes del XML interior."""
    import time

    # Cabeceras que imitan un navegador real: la FIDE ha empezado a filtrar
    # peticiones que parecen venir de un script (User-Agent por defecto de
    # requests, sin Accept/Referer, etc.) y devuelve 403 o una página HTML
    # en vez del zip.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/zip,application/octet-stream,*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": FIDE_DOWNLOAD_PAGE,
    }

    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            # Si la FIDE nos devuelve HTML (p. ej. una página de bloqueo o
            # de login) en vez del zip, lo detectamos aquí con un mensaje
            # claro en vez de fallar más adelante con un error críptico de
            # "not a zip file".
            if "html" in content_type.lower() or resp.content[:2] != b"PK":
                snippet = resp.content[:300].decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"La respuesta de {url} no es un .zip válido "
                    f"(Content-Type: {content_type!r}, status: {resp.status_code}).\n"
                    f"Primeros bytes de la respuesta:\n{snippet}"
                )
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                if not xml_names:
                    raise RuntimeError(f"El zip descargado de {url} no contiene ningún .xml")
                return zf.read(xml_names[0])
        except Exception as e:
            ultimo_error = e
            print(f"Intento {intento}/{intentos} fallido: {e}")
            if intento < intentos:
                espera = 45 * intento  # 45s, 90s...
                print(f"Reintentando en {espera}s...")
                time.sleep(espera)

    raise RuntimeError(
        f"No se pudo descargar un listado FIDE válido tras {intentos} intentos. "
        f"Último error: {ultimo_error}"
    )


def leer_xml_local(ruta: Path) -> bytes:
    """
    Lee el XML de la FIDE desde un fichero ya descargado a mano (.zip o
    .xml sueltos), sin contactar con la FIDE. Acepta cualquiera de los
    ficheros que ofrece https://ratings.fide.com/download_lists.phtml
    (combinado, solo estándar, legacy...): busca el primer <player> con
    <fideid> y <rating> dentro.
    """
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el fichero: {ruta}")

    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as zf:
            xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_names:
                raise RuntimeError(f"El zip {ruta} no contiene ningún .xml")
            return zf.read(xml_names[0])
    elif ruta.suffix.lower() == ".xml":
        return ruta.read_bytes()
    else:
        raise ValueError(f"Extensión no soportada en {ruta}: se esperaba .zip o .xml")


def parsear_ratings(xml_bytes: bytes) -> dict[str, int]:
    """
    Parsea el XML de la FIDE y devuelve {fide_id: rating_standard}.

    Solo incluye jugadores con un rating estándar > 0 (0 significa que la
    FIDE no les ha publicado rating estándar vigente ese periodo).
    """
    root = ET.fromstring(xml_bytes)
    ratings: dict[str, int] = {}
    for player in root.iter("player"):
        fide_id = player.findtext("fideid")
        rating_txt = player.findtext("rating")
        if not fide_id or not rating_txt:
            continue
        try:
            rating = int(rating_txt.strip())
        except ValueError:
            continue
        if rating > 0:
            ratings[fide_id.strip()] = rating
    return ratings


# ---------------------------------------------------------------------------
# CSV del club
# ---------------------------------------------------------------------------

def leer_csv(ruta: Path) -> tuple[list[dict[str, str]], list[str]]:
    with ruta.open("r", encoding=CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        fieldnames = list(reader.fieldnames or [])
        faltantes = [c for c in CAMPOS_BASE if c not in fieldnames]
        if faltantes:
            raise ValueError(
                f"Faltan columnas obligatorias en {ruta}: {faltantes} "
                f"(cabecera encontrada: {fieldnames})"
            )
        filas = [dict(fila) for fila in reader if any(fila.values())]
        return filas, fieldnames


def escribir_csv(ruta: Path, filas: list[dict[str, str]], fieldnames: list[str]) -> None:
    with ruta.open("w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=CSV_DELIMITER, restval="")
        writer.writeheader()
        writer.writerows(filas)


# ---------------------------------------------------------------------------
# Lógica de actualización
# ---------------------------------------------------------------------------

def actualizar_filas(
    filas: list[dict[str, str]],
    ratings: dict[str, int],
    col_mes_actual: str,
    hoy: Optional[date] = None,
    actualizar_elo_actual: bool = True,
) -> dict:
    """
    Actualiza el Elo de TODOS los jugadores del CSV que aparezcan en el
    listado de la FIDE, independientemente de su Estado_Club (Activo, Alta
    o Baja incluidos) — hay socios dados de baja del club que siguen
    jugando en otros clubes, y también queremos su Elo al día.
    Estado_Club sigue existiendo como dato informativo de pertenencia al
    club, pero ya no decide a quién se actualiza.

    Si actualizar_elo_actual=False (modo backfill de un mes pasado), se
    rellena la columna histórica de ese mes y se sigue comprobando el
    récord (Max_Elo), pero NO se toca Elo_Actual — ese campo debe reflejar
    siempre el dato más reciente, no uno antiguo que se esté rellenando
    a posteriori.
    """
    fecha_hoy = fecha_formato_club(hoy)

    cambios_elo = []      # (nombre, elo_anterior, elo_nuevo)
    nuevos_records = []   # (nombre, max_anterior, max_nuevo)
    no_encontrados = []   # (fide_id, nombre) -> sin rating en el listado
    jugadores_revisados = 0

    for fila in filas:
        # Asegura que la columna del mes existe en todas las filas, aunque
        # sea la primera vez que se usa.
        fila.setdefault(col_mes_actual, "")

        jugadores_revisados += 1
        fide_id = (fila.get("ID_FIDE") or "").strip()
        nuevo_elo = ratings.get(fide_id)

        if nuevo_elo is None:
            no_encontrados.append((fide_id, fila.get("Nombre", "")))
            continue

        elo_previo = int(fila["Elo_Actual"])
        max_previo = int(fila["Max_Elo"])

        # Registro histórico de este mes: siempre se guarda el rating leído
        # hoy, aunque no haya cambiado respecto al mes anterior.
        fila[col_mes_actual] = str(nuevo_elo)

        if actualizar_elo_actual and nuevo_elo != elo_previo:
            cambios_elo.append((fila["Nombre"], elo_previo, nuevo_elo))
            fila["Elo_Actual"] = str(nuevo_elo)

        if nuevo_elo > max_previo:
            fila["Max_Elo"] = str(nuevo_elo)
            fila["Fecha_Record"] = fecha_hoy
            nuevos_records.append((fila["Nombre"], max_previo, nuevo_elo))

    return {
        "jugadores_revisados": jugadores_revisados,
        "cambios_elo": cambios_elo,
        "nuevos_records": nuevos_records,
        "no_encontrados": no_encontrados,
    }


def tomar_snapshot_actual(filas: list[dict[str, str]], col_mes_actual: str) -> dict:
    """
    Copia el valor que YA HAY en Elo_Actual a la columna histórica del mes,
    para TODOS los jugadores (Alta y Baja incluidos), sin descargar nada
    de la FIDE.

    Útil una única vez para no perder el dato actual justo antes de que la
    siguiente ejecución normal lo sobrescriba con el rating nuevo.
    """
    capturados = []    # (nombre, elo)
    vacios = []         # jugadores sin Elo_Actual con el que hacer snapshot

    for fila in filas:
        fila.setdefault(col_mes_actual, "")

        elo_actual = (fila.get("Elo_Actual") or "").strip()
        if elo_actual:
            fila[col_mes_actual] = elo_actual
            capturados.append((fila["Nombre"], elo_actual))
        else:
            vacios.append(fila.get("Nombre", ""))

    return {
        "capturados": capturados,
        "vacios": vacios,
    }


def generar_resumen_snapshot(r: dict, col_mes_actual: str) -> str:
    L = [f"## Snapshot manual — columna {col_mes_actual}", ""]
    L.append(f"- Jugadores capturados desde Elo_Actual: **{len(r['capturados'])}**")
    if r["vacios"]:
        L.append(f"- Sin Elo_Actual (no se ha podido capturar nada): {len(r['vacios'])}")
    L.append("")
    return "\n".join(L)


def generar_resumen(r: dict, fecha_hoy: str, col_mes_actual: str, actualizar_elo_actual: bool = True) -> str:
    L = [f"## Actualización ranking FIDE — {fecha_hoy}", ""]
    L.append(f"- Columna histórica de este mes: **{col_mes_actual}**")
    if not actualizar_elo_actual:
        L.append("- ⏪ Modo backfill: solo se rellena esta columna histórica (y Max_Elo si aplica). "
                  "Elo_Actual **no** se ha tocado.")
    L.append(f"- Jugadores revisados (Alta y Baja incluidos): **{r['jugadores_revisados']}**")
    L.append(f"- Elo actualizado: **{len(r['cambios_elo'])}**")
    L.append(f"- Nuevos récords históricos (Max_Elo): **{len(r['nuevos_records'])}**")
    L.append(f"- Sin rating encontrado en el listado FIDE: {len(r['no_encontrados'])}")
    L.append("")

    if r["nuevos_records"]:
        L.append("### 🏆 Nuevos récords personales")
        for nombre, antes, ahora in r["nuevos_records"]:
            L.append(f"- **{nombre}**: {antes} → {ahora}")
        L.append("")

    if r["cambios_elo"]:
        L.append("### Variaciones de Elo")
        for nombre, antes, ahora in r["cambios_elo"]:
            signo = "+" if ahora > antes else ""
            L.append(f"- {nombre}: {antes} → {ahora} ({signo}{ahora - antes})")
        L.append("")

    if r["no_encontrados"]:
        L.append("### ⚠️ Sin rating en el listado FIDE (revisar ID_FIDE)")
        for fide_id, nombre in r["no_encontrados"]:
            L.append(f"- {nombre} (ID_FIDE={fide_id})")
        L.append("")

    return "\n".join(L)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="jugadores_club.csv", type=Path,
                         help="Ruta al CSV del club (por defecto: jugadores_club.csv)")
    parser.add_argument("--fide-url", default=FIDE_XML_URL,
                         help="URL del .zip XML de la FIDE a usar")
    parser.add_argument("--summary", default="update_summary.md", type=Path,
                         help="Fichero donde volcar el resumen en Markdown")
    parser.add_argument("--dry-run", action="store_true",
                         help="Calcula los cambios pero no escribe el CSV")
    parser.add_argument("--snapshot-actual", action="store_true",
                         help=(
                             "En vez de descargar el listado FIDE, copia el Elo_Actual "
                             "que ya hay en el CSV a la columna histórica del mes en curso. "
                             "Útil una sola vez para no perder el dato actual antes de la "
                             "primera actualización automática con histórico."
                         ))
    parser.add_argument("--archivo-local", type=Path, default=None,
                         help=(
                             "Ruta a un .zip o .xml de la FIDE ya descargado a mano "
                             "(p. ej. subido por el usuario a fide_data/). Si se indica, "
                             "no se descarga nada de la FIDE."
                         ))
    parser.add_argument("--mes", default=None, metavar="AAAA-MM",
                         help=(
                             "Para rellenar el histórico de un mes PASADO (backfill) con un "
                             "listado archivado de la FIDE, en vez de usar el mes actual. "
                             "Formato AAAA-MM, p. ej. --mes 2024-11. En este modo NO se toca "
                             "Elo_Actual (solo la columna histórica de ese mes y, si aplica, "
                             "Max_Elo/Fecha_Record)."
                         ))
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"ERROR: no se encuentra el CSV: {args.csv}")

    if args.mes:
        try:
            fecha_referencia = datetime.strptime(args.mes, "%Y-%m").date()
        except ValueError:
            sys.exit(f"ERROR: --mes debe tener formato AAAA-MM (ej. 2024-11), recibido: {args.mes!r}")
        modo_backfill = True
    else:
        fecha_referencia = date.today()
        modo_backfill = False

    if args.snapshot_actual:
        filas, fieldnames_existentes = leer_csv(args.csv)
        col_mes_actual = columna_mes_actual()
        fieldnames_finales = ordenar_columnas(fieldnames_existentes, col_mes_actual)

        resultado = tomar_snapshot_actual(filas, col_mes_actual)
        resumen = generar_resumen_snapshot(resultado, col_mes_actual)
        print(resumen)
        args.summary.write_text(resumen, encoding="utf-8")

        if args.dry_run:
            print("[--dry-run] No se ha modificado el CSV.")
        else:
            escribir_csv(args.csv, filas, fieldnames_finales)
            print(f"CSV actualizado: {args.csv}")
        return

    if args.archivo_local:
        print(f"Leyendo listado FIDE desde fichero local: {args.archivo_local}")
        try:
            xml_bytes = leer_xml_local(args.archivo_local)
        except Exception as e:
            sys.exit(f"ERROR leyendo el fichero local {args.archivo_local}: {e}")
    else:
        print(f"Descargando listado FIDE desde: {args.fide_url}")
        try:
            xml_bytes = descargar_xml_fide(args.fide_url)
        except Exception as e:
            sys.exit(
                "ERROR descargando/leyendo el listado FIDE.\n"
                f"Detalle: {e}\n"
                f"Comprueba manualmente en {FIDE_DOWNLOAD_PAGE} si la URL de descarga "
                "ha cambiado y actualiza FIDE_XML_URL en el script si es necesario."
            )

    ratings = parsear_ratings(xml_bytes)
    print(f"Listado FIDE parseado correctamente: {len(ratings)} jugadores con rating estándar vigente.")

    filas, fieldnames_existentes = leer_csv(args.csv)
    col_mes_actual = columna_mes_actual(fecha_referencia)
    fieldnames_finales = ordenar_columnas(fieldnames_existentes, col_mes_actual)

    if modo_backfill:
        print(f"Modo backfill: rellenando {col_mes_actual} sin tocar Elo_Actual.")

    resultado = actualizar_filas(
        filas, ratings, col_mes_actual,
        hoy=fecha_referencia,
        actualizar_elo_actual=not modo_backfill,
    )

    resumen = generar_resumen(
        resultado, fecha_formato_club(fecha_referencia), col_mes_actual,
        actualizar_elo_actual=not modo_backfill,
    )
    print("\n" + resumen)
    args.summary.write_text(resumen, encoding="utf-8")

    if args.dry_run:
        print("\n[--dry-run] No se ha modificado el CSV.")
    else:
        escribir_csv(args.csv, filas, fieldnames_finales)
        print(f"\nCSV actualizado: {args.csv}")


if __name__ == "__main__":
    main()
