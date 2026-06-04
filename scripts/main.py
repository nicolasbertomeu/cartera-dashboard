"""
main.py
Script principal del pipeline. Ejecuta leer_sheet + generar_html.
GitHub Actions llama a este archivo.
"""

import sys
from pathlib import Path

# Añadir el directorio scripts al path
sys.path.insert(0, str(Path(__file__).parent))

from leer_sheet import obtener_datos
from generar_html import generar

def main():
    print("─" * 50)
    print("  Pipeline Cartera · Nicolás")
    print("─" * 50)

    print("\n[1/2] Leyendo Google Sheet...")
    datos = obtener_datos()
    print(f"  ✓ {len(datos['meses'])} meses leídos: {', '.join(datos['meses'])}")

    print("\n[2/2] Generando dashboard HTML...")
    generar(datos)

    print("\n  ✓ Pipeline completado")
    print("─" * 50)

if __name__ == "__main__":
    main()
