"use strict";
// Se carga antes de pintar para que el tema elegido no parpadee. Oscuro por defecto; claro si se eligió.
let theme = "dark";
try {
  if (localStorage.getItem("ciber-radar:theme") === "light") theme = "light";
} catch { /* sin almacenamiento, queda el oscuro */ }
document.documentElement.dataset.theme = theme;
