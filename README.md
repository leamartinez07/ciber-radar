# Ciber Radar

Diario de ciberseguridad que se actualiza solo y avisa al celular.

- `collector/collect.py` lee las fuentes de `feeds.toml`, deduplica, clasifica y manda avisos.
- `collector/render.py` genera en `public/` un sitio estático completo: portada, secciones, archivo, RSS, sitemap y `security.txt`.
- `.github/workflows/collect.yml` corre ambos cada 30 minutos y publica solo si hay noticias nuevas. Cada edición dispara un Deploy Hook de Vercel: como máximo 48 despliegues por día, dentro de los 100 del plan gratis.

Solo usa la biblioteca estándar de Python.

## Probar en la computadora

```bash
python3 -m unittest discover -s tests
python3 collector/collect.py
python3 collector/render.py
python3 tools/serve.py 8000
```

`tools/serve.py` sirve `public/` como Vercel, con las cabeceras de `vercel.json`.

## Cambiar qué avisa

En `feeds.toml`, `[rules]` define los términos. Avisa si el título menciona Argentina y un incidente, o si habla de un fallo crítico explotado. `[limits]` fija el máximo: 5 avisos por corrida y 40 por día.

## Configuración en GitHub

- Secreto `NTFY_TOPIC`: el canal de avisos. Quien lo conozca puede leer y mandar avisos, así que nunca va en el código.
- Secreto `VERCEL_DEPLOY_HOOK`: la URL del Deploy Hook. Quien la tenga puede forzar despliegues.
- Variable `SITE_URL`: la dirección final del sitio. Se usa en enlaces canónicos, sitemap y RSS.

## Fuentes tipográficas

Playfair Display, Source Serif 4 y JetBrains Mono, con licencia SIL Open Font License 1.1. Las licencias están en `site/fonts/`.
