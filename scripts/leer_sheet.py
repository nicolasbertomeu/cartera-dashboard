"""
leer_sheet.py
Lee la hoja de rentabilidad mensual de Nicolás desde Google Sheets
y devuelve un dict estructurado con todos los datos necesarios para
regenerar el dashboard HTML.
"""

import os
import json
import re
from google.oauth2.service_account import Credentials
import gspread

# ── ID DEL GOOGLE SHEET ───────────────────────────────────────────────────────
# Es la parte de la URL entre /d/ y /edit
SHEET_ID = "1HGRx4zMbOfU_lnE9SAnqYwUXHw19g5qKwIiRspFlJhs"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ── ACTIVOS EN EL ORDEN EN QUE APARECEN EN EL SHEET ──────────────────────────
ACTIVOS_CONFIG = [
    {"key": "sp500",    "nombre": "S&P 500",       "color": "#5090c9"},
    {"key": "euro",     "nombre": "Eurostoxx 600",  "color": "#50b0a0"},
    {"key": "em",       "nombre": "Emergentes",     "color": "#9070c9"},
    {"key": "oro",      "nombre": "Oro",            "color": "#c9a84c"},
    {"key": "btc",      "nombre": "Bitcoin",        "color": "#c98050"},
    {"key": "numantia", "nombre": "Numantia",       "color": "#4caf7a"},
    {"key": "horos",    "nombre": "Horos",          "color": "#c95050"},
]

# Pesos objetivo (cartera total sin crowdfunding)
PESOS_OBJETIVO = {
    "sp500":    44.0,
    "euro":      8.0,
    "em":       16.0,
    "oro":       6.0,
    "btc":       4.0,
    "numantia":  8.5,
    "horos":     8.5,
}

# Aportaciones mensuales estimadas por activo (€/mes)
APORTACIONES_MENSUALES = {
    "sp500":    332.0,
    "euro":      66.0,
    "em":        88.0,
    "oro":       40.0,
    "btc":       16.0,
    "numantia":   0.0,
    "horos":      0.0,
}


def _limpiar_numero(texto):
    """Convierte '1.786,31 €' o '-53,02 €' a float."""
    if not texto or str(texto).strip() == "":
        return None
    s = str(texto).strip()
    s = s.replace("€", "").replace(" ", "").replace("\xa0", "")
    # Formato español: punto=miles, coma=decimales
    s = s.replace(".", "").replace(",", ".")
    s = s.replace("−", "-")
    try:
        return float(s)
    except ValueError:
        return None


def _limpiar_pct(texto):
    """Convierte '3,87%' a 3.87 (float)."""
    if not texto or str(texto).strip() == "":
        return None
    s = str(texto).strip()
    s = s.replace("%", "").replace(" ", "").replace(",", ".")
    s = s.replace("−", "-")
    try:
        return float(s)
    except ValueError:
        return None


def _conectar():
    """Conecta a Google Sheets usando credenciales de variable de entorno."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise EnvironmentError(
            "Variable de entorno GOOGLE_CREDENTIALS no encontrada.\n"
            "En local: export GOOGLE_CREDENTIALS='$(cat credenciales.json)'\n"
            "En GitHub Actions: configura el Secret GOOGLE_CREDENTIALS"
        )
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _buscar_bloque_activo(filas, nombre_activo):
    """
    Encuentra el bloque de datos de un activo en la hoja.
    Devuelve lista de dicts: {mes, val_ini, aportacion, val_fin, rent_pct}
    """
    datos = []
    dentro = False
    meses_validos = {"Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"}

    for fila in filas:
        texto_fila = " ".join(str(c) for c in fila if c)

        # Detectar inicio del bloque de este activo
        if nombre_activo in texto_fila and "Valor inicial" in texto_fila:
            dentro = True
            continue

        # Detectar inicio de otro activo (salir del bloque)
        if dentro and any(
            otro["nombre"] in texto_fila and "Valor inicial" in texto_fila
            for otro in ACTIVOS_CONFIG
            if otro["nombre"] != nombre_activo
        ):
            break

        if not dentro:
            continue

        # Buscar filas de datos (empiezan con un mes como "Feb-2026")
        primera = str(fila[0]).strip() if fila else ""
        if not any(mes in primera for mes in meses_validos):
            continue

        val_ini  = _limpiar_numero(fila[1] if len(fila) > 1 else "")
        aport    = _limpiar_numero(fila[2] if len(fila) > 2 else "")
        val_fin  = _limpiar_numero(fila[3] if len(fila) > 3 else "")
        rent_pct = _limpiar_pct(fila[5] if len(fila) > 5 else "")
        rent_acum= _limpiar_pct(fila[6] if len(fila) > 6 else "")

        datos.append({
            "mes":       primera,
            "val_ini":   val_ini,
            "aportacion":aport,
            "val_fin":   val_fin,
            "rent_pct":  rent_pct,
            "rent_acum": rent_acum,
        })

    return datos


def _buscar_resumen_total(filas):
    """Extrae el bloque RESUMEN PORTAFOLIO TOTAL."""
    datos = []
    dentro = False
    meses_validos = {"Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"}

    for fila in filas:
        texto = " ".join(str(c) for c in fila if c)
        if "RESUMEN PORTAFOLIO TOTAL" in texto:
            dentro = True
            continue
        if not dentro:
            continue
        # Cabecera de columnas — saltar
        if "Período" in texto or "Valor Inicial" in texto:
            continue
        # Fin del bloque (línea en blanco o nuevo bloque)
        if not any(mes in str(fila[0]) for mes in meses_validos):
            if datos:
                break
            continue

        primera = str(fila[0]).strip()
        val_ini  = _limpiar_numero(fila[1] if len(fila) > 1 else "")
        aport    = _limpiar_numero(fila[2] if len(fila) > 2 else "")
        val_fin  = _limpiar_numero(fila[3] if len(fila) > 3 else "")
        rent_pct = _limpiar_pct(fila[5] if len(fila) > 5 else "")
        rent_acum= _limpiar_pct(fila[6] if len(fila) > 6 else "")

        datos.append({
            "mes":       primera,
            "val_ini":   val_ini,
            "aportacion":aport,
            "val_fin":   val_fin,
            "rent_pct":  rent_pct,
            "rent_acum": rent_acum,
        })

    return datos


def _buscar_benchmark(filas):
    """Extrae los datos de comparativa vs S&P 500."""
    datos = []
    dentro = False
    meses_validos = {"Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"}

    for fila in filas:
        texto = " ".join(str(c) for c in fila if c)
        if "COMPARATIVA VS BENCHMARK" in texto:
            dentro = True
            continue
        if not dentro:
            continue
        if "Período" in texto:
            continue
        if "Alpha" in texto and "Positivo" in texto:
            break

        primera = str(fila[0]).strip() if fila else ""
        if not any(mes in primera for mes in meses_validos):
            continue

        rc   = _limpiar_pct(fila[1] if len(fila) > 1 else "")
        rs   = _limpiar_pct(fila[2] if len(fila) > 2 else "")
        am   = _limpiar_pct(fila[3] if len(fila) > 3 else "")
        rac  = _limpiar_pct(fila[4] if len(fila) > 4 else "")
        ras  = _limpiar_pct(fila[5] if len(fila) > 5 else "")
        aa   = _limpiar_pct(fila[6] if len(fila) > 6 else "")

        datos.append({
            "mes": primera,
            "rent_cartera": rc,
            "rent_sp500":   rs,
            "alpha_mensual":am,
            "rent_acum_cartera": rac,
            "rent_acum_sp500":   ras,
            "alpha_acum":   aa,
            "completo": rc is not None and rs is not None,
        })

    return datos


def obtener_datos():
    """
    Punto de entrada principal.
    Devuelve un dict con todos los datos necesarios para el dashboard.
    """
    gc = _conectar()
    sh = gc.open_by_key(SHEET_ID)
    hoja = sh.worksheet("Resumen_y_Calculadora")
    filas = hoja.get_all_values()

    # ── Resumen total
    resumen = _buscar_resumen_total(filas)

    # ── Datos por activo
    activos_data = {}
    for activo in ACTIVOS_CONFIG:
        # Mapeo nombre en sheet → nombre en config
        nombre_sheet = {
            "sp500":    "S&P 500",
            "euro":     "Eurostoxx 600",
            "em":       "Mercados Emergentes",
            "oro":      "Oro",
            "btc":      "Bitcoin",
            "numantia": "Fondo Numantia",
            "horos":    "Horos International",
        }[activo["key"]]
        activos_data[activo["key"]] = _buscar_bloque_activo(filas, nombre_sheet)

    # ── Benchmark
    benchmark = _buscar_benchmark(filas)

    # ── Construir arrays para el dashboard
    # Solo incluimos meses con valor final conocido
    meses_cerrados = [r for r in resumen if r.get("val_fin") is not None]
    meses_labels   = [r["mes"].replace("-2026", "-26") for r in meses_cerrados]
    meses_full     = [r["mes"] for r in meses_cerrados]

    # Valores finales por activo (None → 0 para meses antes de existir el activo)
    def extraer_vals_fin(key):
        bloque = activos_data.get(key, [])
        meses_fin = {r["mes"]: r["val_fin"] for r in bloque if r.get("val_fin") is not None}
        return [meses_fin.get(m, 0) or 0 for m in meses_full]

    data_activos = {a["key"]: extraer_vals_fin(a["key"]) for a in ACTIVOS_CONFIG}

    # Rentabilidades totales
    rent_cartera = [r.get("rent_pct") or 0 for r in meses_cerrados]
    rent_acum    = [r.get("rent_acum") or 0 for r in meses_cerrados]

    # Aportaciones totales por mes
    aportaciones = [r.get("aportacion") or 0 for r in meses_cerrados]

    # Benchmark (solo meses completos)
    bench_completos = [b for b in benchmark if b.get("completo")]
    rent_sp500   = [b.get("rent_sp500") or 0 for b in bench_completos]
    rent_acum_sp = [b.get("rent_acum_sp500") or 0 for b in bench_completos]

    # Pesos actuales (último mes cerrado)
    last_idx = len(meses_cerrados) - 1
    total_last = sum(data_activos[a["key"]][last_idx] for a in ACTIVOS_CONFIG)
    pesos_actuales = {}
    for a in ACTIVOS_CONFIG:
        val = data_activos[a["key"]][last_idx]
        pesos_actuales[a["key"]] = round(val / total_last * 100, 2) if total_last > 0 else 0

    # Último mes con datos de benchmark
    bench_para_tabla = []
    for b in benchmark:
        bench_para_tabla.append({
            "mes":     b["mes"],
            "rc":      b.get("rent_cartera"),
            "rs":      b.get("rent_sp500"),
            "am":      b.get("alpha_mensual"),
            "rac":     b.get("rent_acum_cartera"),
            "ras":     b.get("rent_acum_sp500"),
            "aa":      b.get("alpha_acum"),
            "completo":b.get("completo", False),
        })

    # Datos de cierre (mes siguiente pendiente)
    ultimo_mes = meses_cerrados[-1] if meses_cerrados else {}
    vals_ultimo = {a["key"]: data_activos[a["key"]][last_idx] for a in ACTIVOS_CONFIG}

    return {
        "meses":        meses_labels,
        "meses_full":   meses_full,
        "data":         data_activos,
        "total":        [sum(data_activos[a["key"]][i] for a in ACTIVOS_CONFIG)
                         for i in range(len(meses_labels))],
        "aportaciones": aportaciones,
        "rent_cartera": rent_cartera,
        "rent_acum":    rent_acum,
        "rent_sp500":   rent_sp500,
        "rent_acum_sp": rent_acum_sp,
        "pesos_objetivo":  PESOS_OBJETIVO,
        "pesos_actuales":  pesos_actuales,
        "vals_ultimo":     vals_ultimo,
        "aportaciones_mensuales": APORTACIONES_MENSUALES,
        "benchmark_tabla": bench_para_tabla,
        "activos_config":  ACTIVOS_CONFIG,
        "ultimo_mes":      ultimo_mes.get("mes", ""),
    }


if __name__ == "__main__":
    import json
    datos = obtener_datos()
    print(json.dumps(datos, indent=2, ensure_ascii=False))
