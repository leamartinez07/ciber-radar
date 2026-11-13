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

La marca es una R de tres líneas paralelas del mismo grosor que recorren el asta, la panza y la pata: en la panza son los anillos de un radar, con la señal detectada en el centro. Acompaña a la palabra CIBERADAR, donde la R compartida va en naranja. El dibujo es `r_mark` en `collector/render.py`. `tools/make_brand.py` genera desde ese mismo dibujo el ícono de la app, el ícono adaptable, el favicon y la imagen para redes. Necesita Playwright con Chromium y solo se corre al cambiar la marca.

## Cambiar qué avisa

En `feeds.toml`, `[rules]` define los términos. Avisa si el título menciona Argentina y un incidente, o si habla de un fallo crítico explotado. `[limits]` fija el máximo: 5 avisos por corrida y 40 por día.

## Configuración en GitHub

- Secreto `NTFY_TOPIC`: el canal de avisos. Quien lo conozca puede leer y mandar avisos, así que nunca va en el código.
- Secreto `VERCEL_DEPLOY_HOOK`: la URL del Deploy Hook. Quien la tenga puede forzar despliegues.
- Variable `SITE_URL`: la dirección final del sitio. Se usa en enlaces canónicos, sitemap y RSS.

## Fuentes tipográficas

Archivo (Omnibus-Type, Buenos Aires) para la marca, los titulares y la interfaz: es variable en peso y ancho, y los titulares usan el corte angosto. Source Serif 4 para los resúmenes y JetBrains Mono solo para los identificadores CVE. Todas con licencia SIL Open Font License 1.1; las licencias están en `site/fonts/`. Archivo viene de `@fontsource-variable/archivo` 5.2.8.

## Diseño

Paleta de colores plenos, sin negro ni blanco puros: azul marino, papel cálido, naranja, amarillo y verde azulado. La cabecera va a sangre sobre azul y cierra con dos filetes, naranja y amarillo, que repiten las líneas de la R. El naranja marca alertas, el amarillo es la barra de última alerta y el verde azulado señala temas y enlaces. Esquinas rectas, sin degradados ni sombras. El tema y la marca de alerta van en la línea de datos, debajo del título. Hay tema claro (el de entrada) y oscuro, que se elige con el botón de la barra superior; no sigue al sistema. `site/theme.js` lo aplica antes de pintar. Los colores son tokens en `site/styles.css` y cada par texto/fondo pasa WCAG AA. El pie lleva la marca LM, el copyright, el correo y el portfolio de Leandro Martinez: se editan en las constantes `OWNER*` de `collector/render.py`.

Referencias consultadas: la lista de patrones genéricos de `pbakaus/impeccable` (qué evitar: violetas y celestes, fondo crema, cursiva con serifa, puntos que laten, etiqueta sobre cada titular) y `docs/STANDARDS/design-references.md` de MASTER-AI. Para la marca se siguió el método de Allan Peters (formas geométricas simples, un mismo grosor de línea, colores plenos y cálidos, filetes derivados de la geometría del logo), sin copiar ninguna de sus piezas.
