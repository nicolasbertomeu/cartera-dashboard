"""
generar_html.py
Toma los datos del Sheet y regenera docs/index.html actualizando
el bloque DATA del dashboard con los valores reales.
"""

import json
import re
import sys
from pathlib import Path

# Ruta al HTML template (el dashboard actual)
TEMPLATE_PATH = Path(__file__).parent.parent / "docs" / "index.html"
OUTPUT_PATH   = TEMPLATE_PATH  # Sobreescribimos el mismo archivo


def _js_array(lista):
    """Convierte una lista Python a string de array JavaScript."""
    return "[" + ", ".join(str(v) for v in lista) + "]"


def _js_bench_array(bench_lista):
    """Convierte la lista de benchmark a array JS de objetos."""
    items = []
    for b in bench_lista:
        if b.get("completo"):
            items.append(
                f'{{ mes:"{b["mes"]}", rc:{b["rc"]}, rs:{b["rs"]}, '
                f'am:{b["am"]}, rac:{b["rac"]}, ras:{b["ras"]}, aa:{b["aa"]}, ok:true }}'
            )
        else:
            items.append(f'{{ mes:"{b["mes"]}", ok:false }}')
    return "[\n  " + ",\n  ".join(items) + "\n]"


def _js_pesos_array(activos_config, pesos_obj, pesos_act, vals_ultimo):
    """Genera el array PESOS para la tabla de rebalanceo."""
    items = []
    for a in activos_config:
        k = a["key"]
        obj = pesos_obj.get(k, 0)
        act = pesos_act.get(k, 0)
        val = vals_ultimo.get(k, 0)
        items.append(
            f'  {{ nombre:"{a["nombre"]}", obj:{obj}, act:{act}, val:{val} }}'
        )
    return "[\n" + ",\n".join(items) + "\n]"


def generar(datos):
    """
    Lee el HTML actual, sustituye el bloque DATA con los datos nuevos,
    y guarda el resultado.
    """
    html = TEMPLATE_PATH.read_text(encoding="utf-8")

    # ── Construir el nuevo bloque DATA ────────────────────────────────────────
    meses_str   = json.dumps(datos["meses"], ensure_ascii=False)
    meses_full  = json.dumps(datos["meses_full"], ensure_ascii=False)
    ultimo_mes  = datos.get("ultimo_mes", "")

    # Arrays de valores finales por activo
    data_lines = []
    for a in datos["activos_config"]:
        vals = datos["data"][a["key"]]
        data_lines.append(f'  {a["key"]}:    {_js_array(vals)},')
    data_str = "{\n" + "\n".join(data_lines) + "\n}"

    # Rentabilidades
    rc_str  = _js_array(datos["rent_cartera"])
    ra_str  = _js_array(datos["rent_acum"])
    rs_str  = _js_array(datos["rent_sp500"])
    ras_str = _js_array(datos["rent_acum_sp"])
    aport_str = _js_array(datos["aportaciones"])

    # Pesos
    pesos_str = _js_pesos_array(
        datos["activos_config"],
        datos["pesos_objetivo"],
        datos["pesos_actuales"],
        datos["vals_ultimo"],
    )

    # Benchmark tabla
    bench_str = _js_bench_array(datos["benchmark_tabla"])

    # Total cartera (último mes)
    total_last = datos["total"][-1] if datos["total"] else 0
    total_fmt  = f"{total_last:,.0f}".replace(",", ".")

    # Mes que se muestra en el header
    ultimo_label = datos["meses"][-1] if datos["meses"] else ""

    nuevo_bloque = f"""// ══════════════════════════════════════════════════════════
// ── DATOS ─────────────────────────────────────────────────
// Generado automáticamente por generar_html.py
// Último mes cerrado: {ultimo_mes}
// ══════════════════════════════════════════════════════════

const MESES = {meses_str};
const MESES_FULL = {meses_full};

// Valor final de cada activo al cierre del mes
const DATA = {data_str};

// Total cartera (suma de todos los activos)
const TOTAL = MESES.map((_,i) =>
  DATA.sp500[i]+DATA.euro[i]+DATA.em[i]+DATA.oro[i]+DATA.btc[i]+DATA.numantia[i]+DATA.horos[i]
);

// Rentabilidades mensuales (Modified Dietz, calculadas en Sheet)
const RENT_CARTERA = {rc_str};
const RENT_SP500   = {rs_str};

// Acumuladas
const RENT_ACUM_CARTERA = {ra_str};
const RENT_ACUM_SP500   = {ras_str};

// Aportaciones totales por mes
const APORTACIONES = {aport_str};

// Config activos
const ACTIVOS = [
  {{ key:'sp500',    nombre:'S&P 500',          color:'#5090c9', acento:'--blue'   }},
  {{ key:'euro',     nombre:'Eurostoxx 600',     color:'#50b0a0', acento:'--teal'   }},
  {{ key:'em',       nombre:'Emergentes',        color:'#9070c9', acento:'--purple' }},
  {{ key:'oro',      nombre:'Oro',               color:'#c9a84c', acento:'--gold'   }},
  {{ key:'btc',      nombre:'Bitcoin',           color:'#c98050', acento:'--orange' }},
  {{ key:'numantia', nombre:'Numantia',          color:'#4caf7a', acento:'--green'  }},
  {{ key:'horos',    nombre:'Horos',             color:'#c95050', acento:'--red'    }},
];

// Pesos objetivo y actuales (cartera total sin crowdfunding)
const PESOS = {pesos_str};

const TOTAL_CARTERA = 23509.30; // Con crowdfunding incluido en denominador

// Benchmark data
const BENCH_DATA = {bench_str};"""

    # ── Sustituir el bloque DATA en el HTML ───────────────────────────────────
    # Buscamos desde el marcador de inicio hasta el primer cierre del bloque
    patron = re.compile(
        r"// ══+\n// ── DATOS ──.*?// ── INIT ──",
        re.DOTALL
    )

    if not patron.search(html):
        print("⚠ No se encontró el marcador '// ── DATOS ──' en el HTML.")
        print("  Verifica que el HTML tiene el bloque DATA original intacto.")
        sys.exit(1)

    html_nuevo = patron.sub(nuevo_bloque + "\n\n// ── INIT ──", html)

    # ── Actualizar el header (valor total y último mes) ───────────────────────
    html_nuevo = re.sub(
        r'<div class="total-val" id="hdr-total">.*?</div>',
        f'<div class="total-val" id="hdr-total">{total_fmt} €</div>',
        html_nuevo
    )
    html_nuevo = re.sub(
        r'CARTERA CORE · [A-Z]+-\d+',
        f'CARTERA CORE · {ultimo_label.upper()}',
        html_nuevo
    )

    OUTPUT_PATH.write_text(html_nuevo, encoding="utf-8")
    print(f"✓ Dashboard actualizado: {OUTPUT_PATH}")
    print(f"  Último mes: {ultimo_mes}")
    print(f"  Valor total: {total_fmt} €")
    print(f"  Meses: {', '.join(datos['meses'])}")


if __name__ == "__main__":
    from leer_sheet import obtener_datos
    datos = obtener_datos()
    generar(datos)
