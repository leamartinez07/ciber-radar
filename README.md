# Ciber Radar

Diario de ciberseguridad que se actualiza solo y avisa al celular.

- `collector/collect.py` lee las fuentes de `feeds.toml`, deduplica, clasifica y manda avisos.
- `collector/vulns.py` trae las vulnerabilidades explotadas (CISA KEV), los CVE críticos nuevos (NVD) y la probabilidad de explotación (FIRST EPSS). Las tres APIs son gratis y sin clave. Avisa cada alta nueva en KEV.
- `collector/render.py` genera en `public/` un sitio estático completo en español (`/`) y en inglés (`/en`): portada, secciones, vulnerabilidades, archivo, RSS, sitemap con hreflang y `security.txt`.
- `.github/workflows/collect.yml` corre ambos cada 30 minutos y publica solo si hay noticias nuevas. Cada edición dispara un Deploy Hook de Vercel: como máximo 48 despliegues por día, dentro de los 100 del plan gratis.

Solo usa la biblioteca estándar de Python.

## Probar en la computadora

```bash
python3 -m unittest discover -s tests
python3 collector/collect.py
python3 collector/vulns.py
python3 collector/render.py
python3 tools/serve.py 8000
```

`tools/serve.py` sirve `public/` como Vercel, con las cabeceras de `vercel.json`.

## Fuentes confiables

Las fuentes directas son medios especializados, CERT oficiales (CISA, INCIBE-CERT, NCSC) e investigación primaria (Talos, Unit 42, Project Zero). De Google Noticias solo entran notas de los medios de `[trusted]` en `feeds.toml`: diarios con redacción propia, agencias y prensa tecnológica reconocida. Para sumar un medio, agregá su dominio a esa lista.

## Marca

La marca es tipográfica, como la cabecera de un diario: el nombre en Archivo angosta entre filetes, sin emblema. Los íconos llevan las iniciales CR. `tools/make_brand.py` genera el ícono de la app, el ícono adaptable, el favicon y la imagen para redes. Necesita Playwright con Chromium y solo se corre al cambiar la marca.

## El radar en datos

La portada lleva un bloque con datos propios, calculados en cada edición sobre las notas más recientes:

- **Mapa:** un círculo por país nombrado en titulares y resúmenes. Los países y sus términos están en `COUNTRIES` de `collector/render.py`; se buscan como palabras enteras. El contorno es de Natural Earth (dominio público) y lo regenera `tools/make_map.py`.
- **Temas y notas por día:** conteos por categoría y por fecha.
- **Tipo de fuente:** cada fuente de `feeds.toml` declara `kind` (oficial, investigacion, especializado); lo que llega por Google Noticias cuenta como prensa general verificada.

No hay imágenes de terceros: la política de seguridad solo admite recursos propios.

## Cambiar qué avisa

En `feeds.toml`, `[rules]` define los términos. Avisa si el título menciona Argentina y un incidente, o si habla de un fallo crítico explotado. `[limits]` fija el máximo: 5 avisos por corrida y 40 por día.

## Configuración en GitHub

- Secreto `NTFY_TOPIC`: el canal de avisos. Quien lo conozca puede leer y mandar avisos, así que nunca va en el código.
- Secreto `VERCEL_DEPLOY_HOOK`: la URL del Deploy Hook. Quien la tenga puede forzar despliegues.
- Variable `SITE_URL`: la dirección final del sitio. Se usa en enlaces canónicos, sitemap y RSS.

## Fuentes tipográficas

Archivo (Omnibus-Type, Buenos Aires) en su corte angosto para la cabecera, los títulos de sección y los titulares. Source Serif 4 para el texto, los resúmenes y las líneas de datos en versalitas. JetBrains Mono solo para los identificadores CVE. Todas con licencia SIL Open Font License 1.1; las licencias están en `site/fonts/`. Archivo viene de `@fontsource-variable/archivo` 5.2.8.

## Diseño

Diario clásico: tinta sobre papel blanco, filetes finos, tres columnas en la tapa y bloques por región con el título grande y centrado. El rojo se reserva para las alertas. El tema y la ficha de alerta van en la línea de datos, debajo del título. Hay tema claro (el de entrada) y oscuro, que se elige con el botón de la barra superior; no sigue al sistema. `site/theme.js` lo aplica antes de pintar. Los colores son tokens en `site/styles.css` y cada par texto/fondo pasa WCAG AA. El pie lleva la marca LM, el copyright, el correo y el portfolio de Leandro Martinez: se editan en las constantes `OWNER*` de `collector/render.py`.

Referencias consultadas: la lista de patrones genéricos de `pbakaus/impeccable` (qué evitar: violetas y celestes, fondo crema, cursiva con serifa, puntos que laten, etiqueta sobre cada titular) y `docs/STANDARDS/design-references.md` de MASTER-AI.
