"use strict";
// Se carga antes de pintar para que el tema elegido no parpadee. Claro por defecto; oscuro si se eligió.
let theme = "light";
try {
  if (localStorage.getItem("ciber-radar:theme") === "dark") theme = "dark";
} catch { /* sin almacenamiento, queda el claro */ }
document.documentElement.dataset.theme = theme;
