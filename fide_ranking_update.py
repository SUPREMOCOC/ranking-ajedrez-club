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
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
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
FIDE_XML_URL = "https://ratings.fide.com/download/players_list_xml.zip"
FIDE_DOWNLOAD_PAGE = "https://ratings.fide.com/download_lists.phtml"

CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"  # conserva el BOM que ya trae el fichero del club
CAMPOS = ["ID_FIDE", "Nombre", "Estado_Club", "Elo_Actual", "Max_Elo", "Fecha_Record"]

# Estados del club que se consideran "jugador activo" (se compara en
# minúsculas y sin tildes, así que "Activo", "ACTIVO" o "Alta" valen igual).
ESTADOS_ACTIVOS = {"activo", "alta"}

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

def leer_csv(ruta: Path) -> list[dict[str, str]]:
    with ruta.open("r", encoding=CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        if reader.fieldnames != CAMPOS:
            raise ValueError(
                f"Cabecera inesperada en {ruta}: {reader.fieldnames} "
                f"(se esperaba {CAMPOS})"
            )
        return [dict(fila) for fila in reader if any(fila.values())]


def escribir_csv(ruta: Path, filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=CSV_DELIMITER)
        writer.writeheader()
        writer.writerows(filas)


# ---------------------------------------------------------------------------
# Lógica de actualización
# ---------------------------------------------------------------------------

def actualizar_filas(
    filas: list[dict[str, str]],
    ratings: dict[str, int],
    hoy: Optional[date] = None,
) -> dict:
    fecha_hoy = fecha_formato_club(hoy)

    cambios_elo = []      # (nombre, elo_anterior, elo_nuevo)
    nuevos_records = []   # (nombre, max_anterior, max_nuevo)
    no_encontrados = []   # (fide_id, nombre) -> activos sin rating en el listado
    activos_revisados = 0
    saltados_no_activos = 0

    for fila in filas:
        estado = normaliza(fila.get("Estado_Club", ""))
        if estado not in ESTADOS_ACTIVOS:
            saltados_no_activos += 1
            continue

        activos_revisados += 1
        fide_id = (fila.get("ID_FIDE") or "").strip()
        nuevo_elo = ratings.get(fide_id)

        if nuevo_elo is None:
            no_encontrados.append((fide_id, fila.get("Nombre", "")))
            continue

        elo_previo = int(fila["Elo_Actual"])
        max_previo = int(fila["Max_Elo"])

        if nuevo_elo != elo_previo:
            cambios_elo.append((fila["Nombre"], elo_previo, nuevo_elo))
            fila["Elo_Actual"] = str(nuevo_elo)

        if nuevo_elo > max_previo:
            fila["Max_Elo"] = str(nuevo_elo)
            fila["Fecha_Record"] = fecha_hoy
            nuevos_records.append((fila["Nombre"], max_previo, nuevo_elo))

    return {
        "activos_revisados": activos_revisados,
        "saltados_no_activos": saltados_no_activos,
        "cambios_elo": cambios_elo,
        "nuevos_records": nuevos_records,
        "no_encontrados": no_encontrados,
    }


def generar_resumen(r: dict, fecha_hoy: str) -> str:
    L = [f"## Actualización ranking FIDE — {fecha_hoy}", ""]
    L.append(f"- Jugadores activos/alta revisados: **{r['activos_revisados']}**")
    L.append(f"- Jugadores no activos (Baja) omitidos: {r['saltados_no_activos']}")
    L.append(f"- Elo actualizado: **{len(r['cambios_elo'])}**")
    L.append(f"- Nuevos récords históricos (Max_Elo): **{len(r['nuevos_records'])}**")
    L.append(f"- Activos sin rating encontrado en el listado FIDE: {len(r['no_encontrados'])}")
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
        L.append("### ⚠️ Activos sin rating en el listado FIDE (revisar ID_FIDE)")
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
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"ERROR: no se encuentra el CSV: {args.csv}")

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

    filas = leer_csv(args.csv)
    resultado = actualizar_filas(filas, ratings)

    resumen = generar_resumen(resultado, fecha_formato_club())
    print("\n" + resumen)
    args.summary.write_text(resumen, encoding="utf-8")

    if args.dry_run:
        print("\n[--dry-run] No se ha modificado el CSV.")
    else:
        escribir_csv(args.csv, filas)
        print(f"\nCSV actualizado: {args.csv}")


if __name__ == "__main__":
    main()
