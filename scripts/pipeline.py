"""
pipeline.py
Lee el Google Sheet de rentabilidad, actualiza el dashboard HTML
y envía un email resumen al correo configurado.

Ejecutado por GitHub Actions el primer lunes de cada mes.
"""

import os
import json
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
SHEET_ID     = "1HGRx4zMbOfU_lnE9SAnqYwUXHw19g5qKwIiRspFlJhs"
HOJA         = "Resumen_y_Calculadora"
HOJA_REBALANCEO = "Control_Rebalanceo"  # NUEVO
HTML_PATH    = "docs/index.html"
EMAIL_DEST   = os.environ.get("EMAIL_DEST", "")      # tu Gmail principal
EMAIL_ORIGEN = os.environ.get("EMAIL_ORIGEN", "")    # el Gmail que envía
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")    # contraseña de app (16 dígitos)
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDENTIALS", "")  # JSON de cuenta de servicio

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

ACTIVOS = [
    {"key": "sp500",    "nombre": "S&P 500",       "color": "#378ADD"},
    {"key": "euro",     "nombre": "Eurostoxx 600",  "color": "#1D9E75"},
    {"key": "em",       "nombre": "Emergentes",     "color": "#7F77DD"},
    {"key": "oro",      "nombre": "Oro",            "color": "#BA7517"},
    {"key": "btc",      "nombre": "Bitcoin",        "color": "#D85A30"},
    {"key": "numantia", "nombre": "Numantia",       "color": "#639922"},
    {"key": "horos",    "nombre": "Horos",          "color": "#A32D2D"},
]

NOMBRES_SHEET = {
    "sp500":    "S&P 500",
    "euro":     "Eurostoxx 600",
    "em":       "Mercados Emergentes",
    "oro":      "Oro",
    "btc":      "Bitcoin",
    "numantia": "Fondo Numantia",
    "horos":    "Horos International",
}

PESOS_OBJ = {
    "sp500": 44, "euro": 8, "em": 16, "oro": 6,
    "btc": 4, "numantia": 8.5, "horos": 8.5, "crowd": 5
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def limpiar_num(txt):
    if not txt or str(txt).strip() in ("", "-", "—"):
        return None
    s = str(txt).strip()
    s = s.replace("€","").replace(" ","").replace("\xa0","")
    s = s.replace(".","").replace(",",".")
    s = s.replace("−","-")
    try:
        return float(s)
    except ValueError:
        return None

def limpiar_pct(txt):
    if not txt or str(txt).strip() in ("", "-", "—"):
        return None
    s = str(txt).strip().replace("%","").replace(" ","").replace(",",".").replace("−","-")
    try:
        return float(s)
    except ValueError:
        return None

def fmt_eur(n):
    if n is None:
        return "—"
    return f"{n:,.0f} €".replace(",",".")

def fmt_pct(n, decimals=2):
    if n is None:
        return "—"
    signo = "+" if n >= 0 else ""
    return f"{signo}{n:.{decimals}f}%".replace(".",",")

def color_pct(n):
    if n is None:
        return "#888"
    return "#4caf7a" if n > 0.05 else "#c95050" if n < -0.05 else "#c9a84c"

# ── LECTURA DEL SHEET ─────────────────────────────────────────────────────────
def conectar_sheet():
    creds_dict = json.loads(GOOGLE_CREDS)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service.spreadsheets()

def leer_filas(sheet, hoja=HOJA):
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{hoja}!A1:Z200"
    ).execute()
    return result.get("values", [])

def buscar_bloque(filas, nombre_activo):
    """Extrae filas de datos de un activo concreto."""
    datos = []
    dentro = False
    meses = {"Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"}
    for fila in filas:
        txt = " ".join(str(c) for c in fila if c)
        if nombre_activo in txt and "Valor inicial" in txt:
            dentro = True
            continue
        if dentro and any(
            v in txt and "Valor inicial" in txt
            for v in NOMBRES_SHEET.values()
            if v != nombre_activo
        ):
            break
        if not dentro:
            continue
        primera = str(fila[0]).strip() if fila else ""
        if not any(m in primera for m in meses):
            continue
        datos.append({
            "mes":       primera,
            "val_ini":   limpiar_num(fila[1] if len(fila)>1 else ""),
            "aport":     limpiar_num(fila[2] if len(fila)>2 else ""),
            "val_fin":   limpiar_num(fila[3] if len(fila)>3 else ""),
            "rent_pct":  limpiar_pct(fila[5] if len(fila)>5 else ""),
            "rent_acum": limpiar_pct(fila[6] if len(fila)>6 else ""),
        })
    return datos

def buscar_resumen_total(filas):
    datos = []
    dentro = False
    meses = {"Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"}
    for fila in filas:
        txt = " ".join(str(c) for c in fila if c)
        if "RESUMEN PORTAFOLIO TOTAL" in txt:
            dentro = True
            continue
        if not dentro:
            continue
        if "Período" in txt or "Valor Inicial" in txt:
            continue
        primera = str(fila[0]).strip() if fila else ""
        if not any(m in primera for m in meses):
            if datos:
                break
            continue
        datos.append({
            "mes":       primera,
            "val_ini":   limpiar_num(fila[1] if len(fila)>1 else ""),
            "aport":     limpiar_num(fila[2] if len(fila)>2 else ""),
            "val_fin":   limpiar_num(fila[3] if len(fila)>3 else ""),
            "rent_pct":  limpiar_pct(fila[5] if len(fila)>5 else ""),
            "rent_acum": limpiar_pct(fila[6] if len(fila)>6 else ""),
        })
    return datos

def buscar_benchmark(filas):
    datos = []
    dentro = False
    meses = {"Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"}
    for fila in filas:
        txt = " ".join(str(c) for c in fila if c)
        if "COMPARATIVA VS BENCHMARK" in txt:
            dentro = True
            continue
        if not dentro:
            continue
        if "Período" in txt:
            continue
        if "Alpha" in txt and "Positivo" in txt:
            break
        primera = str(fila[0]).strip() if fila else ""
        if not any(m in primera for m in meses):
            continue
        datos.append({
            "mes":       primera,
            "rent_cart": limpiar_pct(fila[1] if len(fila)>1 else ""),
            "rent_sp":   limpiar_pct(fila[2] if len(fila)>2 else ""),
            "alpha":     limpiar_pct(fila[3] if len(fila)>3 else ""),
            "rent_acum_cart": limpiar_pct(fila[4] if len(fila)>4 else ""),
            "rent_acum_sp":   limpiar_pct(fila[5] if len(fila)>5 else ""),
            "alpha_acum":     limpiar_pct(fila[6] if len(fila)>6 else ""),
        })
    return datos

def buscar_pesos_con_crowdfunding(filas):
    """
    Lee la tabla 'PESO REAL SOBRE CARTERA TOTAL' de Control_Rebalanceo.
    Retorna dict con clave 'activo' → {'valor_actual': ..., 'peso_actual': ..., 'peso_objetivo': ...}
    INCLUYE crowdfunding.
    """
    pesos = {}
    dentro = False
    
    for fila in filas:
        txt = " ".join(str(c) for c in fila if c)
        
        # Buscar el inicio de la tabla de pesos reales
        if "PESO REAL SOBRE CARTERA TOTAL" in txt:
            dentro = True
            continue
        
        if not dentro:
            continue
        
        # Headers (Activo, Objetivo, Valor Actual, ...)
        if "Activo" in txt or "Objetivo" in txt:
            continue
        
        # Fin de la tabla (línea de totales o vacía)
        if "TOTAL CARTERA" in txt or (not fila or str(fila[0]).strip() == ""):
            if pesos:
                break
            continue
        
        primera = str(fila[0]).strip() if fila else ""
        if not primera:
            continue
        
        # Mapeamos los nombres del Sheet a nuestras keys
        key_map = {
            "S&P 500": "sp500",
            "Eurostoxx 600": "euro",
            "Mercados Emergentes": "em",
            "Oro": "oro",
            "Bitcoin": "btc",
            "Numantia Patrimonio": "numantia",
            "Horos Internacional": "horos",
            "Crowdfounding": "crowd",
        }
        
        key = key_map.get(primera)
        if not key:
            continue
        
        # Estructura esperada: [Activo, Objetivo, Valor Actual, % s/Cartera Total, ...]
        pesos[key] = {
            "nombre": primera,
            "peso_obj":      limpiar_pct(fila[1] if len(fila)>1 else ""),  # Objetivo
            "valor_actual":  limpiar_num(fila[2] if len(fila)>2 else ""),  # Valor Actual
            "peso_actual":   limpiar_pct(fila[3] if len(fila)>3 else ""),  # % s/Cartera Total
        }
    
    return pesos

# ── EXTRACCIÓN DE DATOS PRINCIPALES ────────────────────────────────────────────
def obtener_datos():
    print("[1/3] Leyendo Google Sheet...")
    sheet = conectar_sheet()
    
    # Leer Resumen_y_Calculadora (sin crowdfunding en rentabilidades)
    filas_resumen = leer_filas(sheet, HOJA)
    
    # Leer Control_Rebalanceo (con crowdfunding en pesos)
    filas_rebalanceo = leer_filas(sheet, HOJA_REBALANCEO)
    
    # Extraer datos de rentabilidad (sin crowdfunding)
    datos_activos = {}
    for a in ACTIVOS:
        datos_activos[a["key"]] = buscar_bloque(filas_resumen, NOMBRES_SHEET[a["key"]])
    
    resumen_total = buscar_resumen_total(filas_resumen)
    benchmark = buscar_benchmark(filas_resumen)
    
    # Extraer pesos CON crowdfunding
    pesos_con_crowd = buscar_pesos_con_crowdfunding(filas_rebalanceo)
    
    # Construir arrays por mes
    meses = [r["mes"] for r in resumen_total]
    
    datos = {
        "meses": meses,
        "ultimo_mes": meses[-1] if meses else "—",
        "rent_cartera": [r.get("rent_pct") for r in resumen_total],
        "rent_acum": [r.get("rent_acum") for r in resumen_total],
        "total": [r.get("val_fin") for r in resumen_total],
        "rent_sp_ult": benchmark[-1].get("rent_sp") if benchmark else None,
        "rent_ult": resumen_total[-1].get("rent_pct") if resumen_total else None,
        "rent_acum_ult": resumen_total[-1].get("rent_acum") if resumen_total else None,
        "alpha_acum": benchmark[-1].get("alpha_acum") if benchmark else None,
        "vals_ultimo": {},
        "pesos_con_crowdfunding": pesos_con_crowd,  # NUEVO: incluye crowdfunding
        "benchmark": benchmark,
        "rent_acum_sp": [b.get("rent_acum_sp") for b in benchmark],
    }
    
    # Valores últimos de cada activo (sin crowdfunding)
    for a in ACTIVOS:
        bloque = datos_activos[a["key"]]
        val = bloque[-1].get("val_fin") if bloque else 0
        datos["vals_ultimo"][a["key"]] = val or 0
    
    # Series por mes de cada activo
    for a in ACTIVOS:
        datos[f"data_{a['key']}"] = [d.get("val_fin") or 0 for d in datos_activos[a["key"]]]
    
    print(f"  ✓ Datos extraídos: {len(meses)} meses, {len(ACTIVOS)} activos")
    print(f"  ✓ Pesos con crowdfunding: {len(pesos_con_crowd)} componentes")
    
    return datos

# ── CONSTRUCCIÓN DE JAVASCRIPT PARA HTML ──────────────────────────────────────
def js_array(arr):
    """Convierte array Python a JavaScript."""
    return "[" + ",".join(f"{v}" if v is not None else "null" for v in arr) + "]"

def js_bench(bench):
    """Convierte datos de benchmark a objeto JavaScript."""
    if not bench:
        return "{}"
    obj = {
        "meses": [b["mes"] for b in bench],
        "rent_cart": [b.get("rent_cart") for b in bench],
        "rent_sp": [b.get("rent_sp") for b in bench],
        "alpha": [b.get("alpha") for b in bench],
        "rent_acum_cart": [b.get("rent_acum_cart") for b in bench],
        "rent_acum_sp": [b.get("rent_acum_sp") for b in bench],
        "alpha_acum": [b.get("alpha_acum") for b in bench],
    }
    js_str = "{"
    for k, v in obj.items():
        js_str += f"{k}: {js_array(v)}, "
    js_str = js_str.rstrip(", ") + "}"
    return js_str

def js_pesos(pesos_dict):
    """Convierte dict de pesos a array JavaScript."""
    # pesos_dict = {"sp500": {"nombre": ..., "peso_obj": ..., "valor_actual": ..., "peso_actual": ...}, ...}
    arr = []
    for key in ["sp500", "euro", "em", "oro", "btc", "numantia", "horos", "crowd"]:
        if key in pesos_dict:
            p = pesos_dict[key]
            arr.append(f"""{{
  nombre: "{p.get('nombre', '')}",
  obj: {p.get('peso_obj') or 0},
  actual: {p.get('peso_actual') or 0},
  valor: {p.get('valor_actual') or 0}
}}""")
    return "[" + ", ".join(arr) + "]"

def actualizar_html(datos):
    print("[2/3] Actualizando HTML...")
    
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    
# Construir bloque de datos
    bench_json = js_bench(datos.get('benchmark', []))
    pesos_json = js_pesos(datos.get('pesos_con_crowdfunding', {}))
    
    data_parts = []
    for a in ACTIVOS:
        key = a['key']
        arr = js_array(datos.get(f'data_{key}', []))
        data_parts.append(f"  {key}: {arr},")
    data_str = "\n".join(data_parts).rstrip(",")
    
    nuevo_bloque = f"""// AUTO-GENERADO por pipeline.py
const MESES = {js_array(datos['meses'])};
const DATA = {{
{data_str}
}};
const PESOS = {pesos_json};
const RENT_ACUM_SP = {js_array(datos.get('rent_acum_sp', []))};
const BENCH_DATA = {bench_json};"""

    patron = re.compile(
        r"// AUTO-GENERADO.*?(?=const ACT\s*=)",
        re.DOTALL
    )
    if patron.search(html):
        html_nuevo = patron.sub(nuevo_bloque + "\n", html)
    else:
        # Primera vez: insertar antes de const ACT
        html_nuevo = html.replace(
            "const ACT=[",
            nuevo_bloque + "\nconst ACT=["
        )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_nuevo)

    print(f"  ✓ HTML actualizado → {HTML_PATH}")

# ── EMAIL RESUMEN ─────────────────────────────────────────────────────────────
def generar_email_html(datos):
    mes    = datos["ultimo_mes"]
    total  = sum(datos["vals_ultimo"].values())
    rc     = datos["rent_ult"]
    rac    = datos["rent_acum_ult"]
    rs     = datos["rent_sp_ult"]
    alpha  = datos["alpha_acum"]

    def fila_activo(a):
        v     = datos["vals_ultimo"][a["key"]]
        pct   = v / total * 100 if total else 0
        obj   = PESOS_OBJ.get(a["key"], 0)
        dev   = pct - obj
        dc    = "#4caf7a" if abs(dev)<1 else "#c9a84c" if abs(dev)<3 else "#c95050"
        return f"""
        <tr>
          <td style="padding:10px 14px;color:#9a8e7a;border-bottom:1px solid #1a2430">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{a['color']};margin-right:8px;vertical-align:middle"></span>
            {a['nombre']}
          </td>
          <td style="padding:10px 14px;text-align:right;border-bottom:1px solid #1a2430;font-family:'Courier New',monospace">{fmt_eur(v)}</td>
          <td style="padding:10px 14px;text-align:right;border-bottom:1px solid #1a2430;color:{dc};font-family:'Courier New',monospace">{pct:.1f}% <span style="color:#555">({obj}%)</span></td>
          <td style="padding:10px 14px;text-align:right;border-bottom:1px solid #1a2430;color:{dc};font-family:'Courier New',monospace">{dev:+.2f}%</td>
        </tr>"""

    filas_activos = "".join(fila_activo(a) for a in ACTIVOS)

    # Historial últimos meses
    n = min(4, len(datos["meses"]))
    filas_hist = ""
    for i in range(len(datos["meses"])-n, len(datos["meses"])):
        m   = datos["meses"][i]
        rc2 = datos["rent_cartera"][i]
        ra2 = datos["rent_acum"][i]
        t2  = datos["total"][i]
        filas_hist += f"""
        <tr>
          <td style="padding:9px 14px;color:#9a8e7a;border-bottom:1px solid #1a2430">{m}</td>
          <td style="padding:9px 14px;text-align:right;border-bottom:1px solid #1a2430;color:{color_pct(rc2)};font-family:'Courier New',monospace">{fmt_pct(rc2)}</td>
          <td style="padding:9px 14px;text-align:right;border-bottom:1px solid #1a2430;color:{color_pct(ra2)};font-family:'Courier New',monospace">{fmt_pct(ra2)}</td>
          <td style="padding:9px 14px;text-align:right;border-bottom:1px solid #1a2430;font-family:'Courier New',monospace">{fmt_eur(t2)}</td>
        </tr>"""

    alpha_str = fmt_pct(alpha) if alpha is not None else "—"
    alpha_col = color_pct(alpha) if alpha is not None else "#888"
    rs_str    = fmt_pct(rs) if rs is not None else "pendiente"

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#080c10;font-family:'Helvetica Neue',Arial,sans-serif;color:#e2ddd4;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#080c10;padding:40px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

  <!-- CABECERA -->
  <tr><td style="background:#0e1419;border:1px solid rgba(201,168,76,0.15);border-radius:4px 4px 0 0;padding:28px 32px;border-bottom:2px solid #c9a84c">
    <p style="margin:0 0 6px;font-size:10px;letter-spacing:4px;text-transform:uppercase;color:#c9a84c">Resumen Patrimonial</p>
    <h1 style="margin:0;font-size:28px;font-weight:300;color:#e8c97a">{mes}</h1>
    <p style="margin:8px 0 0;font-size:12px;color:#7a7060">Generado automáticamente · {date.today().strftime("%-d de %B de %Y")}</p>
  </td></tr>

  <!-- KPIs -->
  <tr><td style="background:#0e1419;border:1px solid rgba(201,168,76,0.15);border-top:none;padding:24px 32px">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="25%" style="padding:0 8px 0 0;text-align:center">
          <p style="margin:0 0 4px;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7a7060">Valor total</p>
          <p style="margin:0;font-size:22px;font-weight:300;color:#e8c97a;font-family:Georgia,serif">{fmt_eur(total)}</p>
        </td>
        <td width="25%" style="padding:0 8px;text-align:center;border-left:1px solid #1a2430">
          <p style="margin:0 0 4px;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7a7060">Rent. {mes}</p>
          <p style="margin:0;font-size:22px;font-weight:300;color:{color_pct(rc)};font-family:Georgia,serif">{fmt_pct(rc)}</p>
        </td>
        <td width="25%" style="padding:0 8px;text-align:center;border-left:1px solid #1a2430">
          <p style="margin:0 0 4px;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7a7060">Rent. acum.</p>
          <p style="margin:0;font-size:22px;font-weight:300;color:{color_pct(rac)};font-family:Georgia,serif">{fmt_pct(rac)}</p>
        </td>
        <td width="25%" style="padding:0 0 0 8px;text-align:center;border-left:1px solid #1a2430">
          <p style="margin:0 0 4px;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7a7060">Alpha acum.</p>
          <p style="margin:0;font-size:22px;font-weight:300;color:{alpha_col};font-family:Georgia,serif">{alpha_str}</p>
        </td>
      </tr>
    </table>
    <p style="margin:16px 0 0;font-size:11px;color:#7a7060;text-align:center">S&P 500 EUR este mes: <span style="color:{color_pct(rs) if rs else '#888'}">{rs_str}</span></p>
  </td></tr>

  <!-- ACTIVOS -->
  <tr><td style="background:#0e1419;border:1px solid rgba(201,168,76,0.15);border-top:none;padding:0 32px 8px">
    <p style="margin:0;padding:16px 0 10px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#c9a84c;border-bottom:1px solid #1a2430">Desglose por activo (sin crowdfunding)</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px">
      <tr style="background:#141c24">
        <th style="padding:8px 14px;text-align:left;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Activo</th>
        <th style="padding:8px 14px;text-align:right;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Valor</th>
        <th style="padding:8px 14px;text-align:right;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Peso (obj.)</th>
        <th style="padding:8px 14px;text-align:right;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Desv.</th>
      </tr>
      {filas_activos}
    </table>
  </td></tr>

  <!-- HISTORIAL -->
  <tr><td style="background:#0e1419;border:1px solid rgba(201,168,76,0.15);border-top:none;padding:0 32px 8px">
    <p style="margin:0;padding:16px 0 10px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#c9a84c;border-bottom:1px solid #1a2430">Últimos {n} meses</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px">
      <tr style="background:#141c24">
        <th style="padding:8px 14px;text-align:left;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Mes</th>
        <th style="padding:8px 14px;text-align:right;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Rent. mes</th>
        <th style="padding:8px 14px;text-align:right;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Rent. acum.</th>
        <th style="padding:8px 14px;text-align:right;font-size:10px;letter-spacing:2px;color:#7a7060;font-weight:400">Valor total</th>
      </tr>
      {filas_hist}
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#0e1419;border:1px solid rgba(201,168,76,0.15);border-top:none;border-radius:0 0 4px 4px;padding:16px 32px;text-align:center">
    <p style="margin:0;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7a7060">Solo orientativo · Datos privados · Generado automáticamente</p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""

def enviar_email(datos):
    print("[3/3] Enviando email resumen...")
    if not all([EMAIL_DEST, EMAIL_ORIGEN, APP_PASSWORD]):
        print("  ⚠ Variables de email no configuradas — saltando envío")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Cartera · {datos['ultimo_mes']} · {fmt_eur(sum(datos['vals_ultimo'].values()))}"
    msg["From"]    = EMAIL_ORIGEN
    msg["To"]      = EMAIL_DEST

    html_content = generar_email_html(datos)
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ORIGEN, APP_PASSWORD)
            server.sendmail(EMAIL_ORIGEN, EMAIL_DEST, msg.as_string())
        print(f"  ✓ Email enviado a {EMAIL_DEST}")
    except Exception as e:
        print(f"  ✗ Error al enviar email: {e}")
        sys.exit(1)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("─" * 52)
    print("  Pipeline Cartera · Nicolás")
    print(f"  {date.today().isoformat()}")
    print("─" * 52)

    datos = obtener_datos()
    actualizar_html(datos)
    enviar_email(datos)

    print("\n  ✓ Pipeline completado")
    print("─" * 52)
