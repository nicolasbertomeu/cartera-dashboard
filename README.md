# Dashboard Cartera — Nicolás

App de seguimiento patrimonial que se actualiza automáticamente cada mes
leyendo tu Google Sheet de rentabilidad.

---

## Cómo funciona

```
Tú rellenas el Sheet → GitHub lo detecta el día 1 → Script lee los datos → 
Dashboard se regenera → La web se actualiza sola
```

---

## Configuración inicial (una sola vez)

### PASO 1 · Credenciales de Google

1. Ve a https://console.cloud.google.com
2. Haz clic en el selector de proyectos (arriba) → **"Nuevo proyecto"**
   - Nombre: `cartera-dashboard` → Crear
3. En el menú izquierdo: **"APIs y servicios"** → **"Biblioteca"**
4. Busca **"Google Sheets API"** → clic → **"Habilitar"**
5. Busca **"Google Drive API"** → clic → **"Habilitar"**
6. En el menú izquierdo: **"APIs y servicios"** → **"Credenciales"**
7. **"Crear credenciales"** → **"Cuenta de servicio"**
   - Nombre: `cartera-reader` → Crear y continuar → Listo
8. Haz clic en la cuenta de servicio recién creada
9. Pestaña **"Claves"** → **"Agregar clave"** → **"Crear clave nueva"** → JSON → Crear
10. Se descarga un archivo JSON. **Guárdalo bien, es tu llave de acceso.**

### PASO 2 · Compartir el Sheet con la cuenta de servicio

1. Abre el JSON descargado con el Bloc de notas
2. Copia el valor del campo `"client_email"` (algo como `cartera-reader@cartera-dashboard.iam.gserviceaccount.com`)
3. Ve a tu Google Sheet de rentabilidad
4. Clic en **"Compartir"** (botón verde arriba a la derecha)
5. Pega el email copiado → **"Lector"** → Enviar

### PASO 3 · Crear el repositorio en GitHub

1. Ve a https://github.com → inicia sesión (o crea cuenta gratuita)
2. Clic en **"+"** (arriba a la derecha) → **"New repository"**
3. Nombre: `cartera-dashboard`
4. Marca **"Private"** (para que sea privado)
5. Clic **"Create repository"**

### PASO 4 · Subir los archivos al repositorio

**Si usas GitHub Desktop (más fácil):**
1. Descarga GitHub Desktop desde https://desktop.github.com
2. File → Clone repository → elige `cartera-dashboard`
3. Copia todos los archivos de este proyecto a esa carpeta
4. En GitHub Desktop: escribe un mensaje ("Subida inicial") → Commit → Push

**Si usas el terminal:**
```bash
git clone https://github.com/TU_USUARIO/cartera-dashboard
cd cartera-dashboard
# copia aquí todos los archivos
git add .
git commit -m "Subida inicial"
git push
```

### PASO 5 · Configurar las credenciales como Secret en GitHub

1. Ve a tu repositorio en GitHub
2. Pestaña **"Settings"** → en el menú izquierdo: **"Secrets and variables"** → **"Actions"**
3. Clic **"New repository secret"**
4. Nombre: `GOOGLE_CREDENTIALS` (exactamente así, en mayúsculas)
5. Valor: abre el JSON de credenciales con el Bloc de notas → copia TODO el contenido → pégalo
6. Clic **"Add secret"**

### PASO 6 · Activar GitHub Pages

1. En tu repositorio: pestaña **"Settings"**
2. En el menú izquierdo: **"Pages"**
3. En **"Source"**: selecciona **"Deploy from a branch"**
4. En **"Branch"**: selecciona `main` y carpeta `/docs`
5. Clic **"Save"**
6. En 1-2 minutos tu app estará en: `https://TU_USUARIO.github.io/cartera-dashboard`

---

## Uso mensual

**No tienes que hacer nada.** El día 1 de cada mes a las 8:00, GitHub:
1. Lee tu Google Sheet automáticamente
2. Actualiza el dashboard
3. Publica la versión nueva

**Si quieres actualizar manualmente antes del día 1:**
1. Ve a tu repositorio en GitHub
2. Pestaña **"Actions"**
3. Clic en **"Actualizar Dashboard Cartera"**
4. Clic **"Run workflow"** → **"Run workflow"**
5. En 1-2 minutos la app estará actualizada

---

## Estructura del proyecto

```
cartera-dashboard/
├── .github/
│   └── workflows/
│       └── update.yml      ← Automatización (no tocar)
├── scripts/
│   ├── main.py             ← Script principal
│   ├── leer_sheet.py       ← Lee el Google Sheet
│   └── generar_html.py     ← Regenera el HTML
├── docs/
│   └── index.html          ← El dashboard (GitHub Pages lo sirve desde aquí)
├── requirements.txt        ← Librerías Python (no tocar)
└── README.md               ← Este archivo
```
