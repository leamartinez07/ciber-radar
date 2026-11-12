"use strict";
// Se carga antes de pintar para que el tema elegido no parpadee.
try {
  const theme = localStorage.getItem("ciber-radar:theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch { /* sin almacenamiento, sigue el tema del sistema */ }
