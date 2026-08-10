"""Regenera `src/ui/templates/_github_seal.html` a partir del SVG animado del
perfil de GitHub (el "coche que se dibuja solo").

Se ejecuta desde la raíz del repositorio: `python scripts/build_github_seal.py`.
Hace falta volver a correrlo si alguna vez se actualiza
`docs/assets/github-portrait-source.svg` (p. ej. si GitHub cambia el generador
o se usa un dibujo distinto).

Dos ajustes sobre el SVG original, necesarios porque se incrusta tal cual
dentro de las plantillas del panel (no como `<img>` aparte):

1. Las variables de color viven en `:root` en el original — como el SVG se
   pega directamente en el HTML de la página, eso contaminaría el `:root`
   real del documento. Se mueven a un selector propio con el `id` del SVG.
2. El original alterna claro/oscuro según `prefers-color-scheme` del sistema
   de quien lo mire; aquí se fuerza siempre la variante oscura, para que
   combine con el tema (siempre oscuro) del panel sea cual sea el ajuste del
   sistema de quien lo visite.
"""

import sys
from pathlib import Path

SOURCE = Path("docs/assets/github-portrait-source.svg")
OUTPUT = Path("src/ui/templates/_github_seal.html")

svg = SOURCE.read_text(encoding="utf-8")

svg = svg.replace(
    '<svg xmlns="http://www.w3.org/2000/svg" width="1217" height="409" viewBox="0 0 1217 409" role="img" aria-label="Mercedes-Benz 190E de perfil, dibujado carácter a carácter" font-family="JBM,ui-monospace,monospace">',
    '<svg id="github-car-seal-svg" xmlns="http://www.w3.org/2000/svg" width="1217" height="409" viewBox="0 0 1217 409" role="img" aria-label="Mercedes-Benz 190E, dibujo animado del perfil de GitHub de Martxel Asteinza" font-family="JBM,ui-monospace,monospace">',
)

old_vars = (
    ":root{--ink:#1f2328;--dim:#59636e;--faint:#8c959f;--rule:#d1d9e0;--panel:#f6f8fa;"
    "--accent:#1a7f37;--accent_dim:#aceebb;--heat0:#ebedf0;--heat1:#aceebb;--heat2:#4ac26b;"
    "--heat3:#2da44e;--heat4:#116329;--pt:#2a3038;}"
    "@media(prefers-color-scheme:dark){:root{--ink:#e6edf3;--dim:#8b949e;--faint:#484f58;"
    "--rule:#30363d;--panel:#161b22;--accent:#39d353;--accent_dim:#1f6f3f;--heat0:#21262d;"
    "--heat1:#0e4429;--heat2:#006d32;--heat3:#26a641;--heat4:#39d353;--pt:#c9d1d9;}}"
)
new_vars = (
    "#github-car-seal-svg{--ink:#e6edf3;--dim:#8b949e;--faint:#484f58;--rule:#30363d;"
    "--panel:#161b22;--accent:#39d353;--accent_dim:#1f6f3f;--heat0:#21262d;--heat1:#0e4429;"
    "--heat2:#006d32;--heat3:#26a641;--heat4:#39d353;--pt:#c9d1d9;}"
)
if old_vars not in svg:
    print("ERROR: no se encontró el bloque de variables de color", file=sys.stderr)
    sys.exit(1)
svg = svg.replace(old_vars, new_vars)

old_toggle = ".dk{display:none}@media(prefers-color-scheme:dark){.lt{display:none}.dk{display:inline}}"
new_toggle = ".lt{display:none}.dk{display:inline}"
if old_toggle not in svg:
    print("ERROR: no se encontró el bloque de alternancia claro/oscuro", file=sys.stderr)
    sys.exit(1)
svg = svg.replace(old_toggle, new_toggle)

OUTPUT.write_text(
    "{# Generado por scripts/build_github_seal.py — no editar a mano. #}\n"
    "{# Sello: el coche del perfil de GitHub de Martxel, dibujado y en bucle. #}\n"
    '<a id="github-car-seal" class="github-car-seal" href="https://github.com/MartXXeL" '
    'target="_blank" rel="noopener" aria-label="Perfil de GitHub de MartXXeL">\n'
    + svg + "\n"
    '  <span class="github-car-seal-caption">github.com/MartXXeL</span>\n'
    "</a>\n",
    encoding="utf-8",
)

print(f"escrito {OUTPUT}, tamaño del SVG: {len(svg)} caracteres")
