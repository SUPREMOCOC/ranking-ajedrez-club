#!/usr/bin/env python3

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
import cloudscraper

FIDE_XML_URL = "https://ratings.fide.com/download/players_list_xml.zip"
FIDE_DOWNLOAD_PAGE = "https://ratings.fide.com/download_lists.phtml"

CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"
CAMPOS = ["ID_FIDE", "Nombre", "Estado_Club", "Elo_Actual", "Max_Elo", "Fecha_Record"]

ESTADOS_ACTIVOS = {"activo", "alta"}

MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def normaliza(texto: str) -> str:
    texto = (texto or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def fecha_formato_club(d: Optional[date] = None) -> str:
    d = d or date.today()
    return f"{MESES_ES[d.month - 1]}-{d.strftime('%y')}"


def descargar_xml_fide(url: str = FIDE_XML_URL) -> bytes:
    scraper = cloudscraper.create_scraper()
    resp = scraper.get(url, timeout=180)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not xml_names:
            raise RuntimeError(f"El zip descargado de {url} no contiene ningun .xml")
        return zf.read(xml_names[0])


def parsear_ratings(xml_bytes: bytes) -> dict[str, int]:
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


def leer_csv(ruta: Path) -> list[dict[str, str]]:
    with ruta.open("r", encoding=CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        if reader.fieldnames != CAMPOS:
            raise ValueError(f"Cabecera inesperada en {ruta}: {reader.fieldnames}")
        return [dict(fila) for fila in reader if any(fila.values())]


def escribir_csv(ruta: Path, filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=CSV_DELIMITER)
        writer.writeheader()
        writer.writerows(filas)


def actualizar_filas(filas: list[dict[str, str]], ratings: dict[str, int], hoy: Optional[date] = None) -> dict:
    fecha_hoy = fecha_formato_club(hoy)
    fecha_mes_actual = f"{(hoy or date.today()).year}-{(hoy or date.today()).month:02d}"

    cambios_elo = []
    nuevos_records = []
    no_encontrados = []
    historial_filas = []
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

        historial_filas.append({
            "ID_FIDE": fide_id,
            "Fecha": fecha_mes_actual,
            "Elo": str(nuevo_elo)
        })

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
        "historial_filas": historial_filas,
    }


def generar_resumen(r: dict, fecha_hoy: str) -> str:
    L = [f"## Actualizacion ranking FIDE - {fecha_hoy}", ""]
    L.append(f"- Jugadores activos/alta revisados: **{r['activos_revisados']}**")
    L.append(f"- Jugadores no activos (Baja) omitidos: {r['saltados_no_activos']}")
    L.append(f"- Elo actualizado: **{len(r['cambios_elo'])}**")
    L.append(f"- Nuevos records historicos (Max_Elo): **{len(r['nuevos_records'])}**")
    L.append(f"- Activos sin rating encontrado en el listado FIDE: {len(r['no_encontrados'])}")
    L.append("")

    if r["nuevos_records"]:
        L.append("### 🏆 Nuevos records personales")
        for nombre, antes, ahora in r["nuevos_records"]:
            L.append(f"- **{nombre}**: {antes} -> {ahora}")
        L.append("")

    if r["cambios_elo"]:
        L.append("### Variaciones de Elo")
        for nombre, antes, ahora in r["cambios_elo"]:
            signo = "+" if ahora > antes else ""
            L.append(f"- {nombre}: {antes} -> {ahora} ({signo}{ahora - antes})")
        L.append("")

    if r["no_encontrados"]:
        L.append("### ⚠️ Activos sin rating en el listado FIDE (revisar ID_FIDE)")
        for fide_id, nombre in r["no_encontrados"]:
            L.append(f"- {nombre} (ID_FIDE={fide_id})")
        L.append("")

    return "\n".join(L)


def main() -> None:
    parser = argparse.ArgumentParser(description="Actualizar ranking FIDE")
    parser.add_argument("--csv", default="jugadores_club.csv", type=Path)
    parser.add_argument("--fide-url", default=FIDE_XML_URL)
    parser.add_argument("--summary", default="update_summary.md", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"ERROR: no se encuentra el CSV: {args.csv}")

    print(f"Descargando listado FIDE desde: {args.fide_url}")
    try:
        xml_bytes = descargar_xml_fide(args.fide_url)
    except Exception as e:
        sys.exit(f"ERROR descargando/leyendo el listado FIDE: {e}")

    ratings = parsear_ratings(xml_bytes)
    print(f"Listado FIDE parseado correctamente: {len(ratings)} jugadores.")

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
        
        if resultado["historial_filas"]:
            hist_file = Path("historial_elos.csv")
            hist_campos = ["ID_FIDE", "Fecha", "Elo"]
            existe_hist = hist_file.exists()
            
            with hist_file.open("a" if existe_hist else "w", encoding=CSV_ENCODING, newline="") as hf:
                writer = csv.DictWriter(hf, fieldnames=hist_campos, delimiter=CSV_DELIMITER)
                if not existe_hist:
                    writer.writeheader()
                writer.writerows(resultado["historial_filas"])
            print(f"Historial mensual guardado con exito en: {hist_file}")


if __name__ == "__main__":
    main()
