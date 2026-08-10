// VintedBot · JS mínimo del panel: nada de frameworks, solo utilidades pequeñas.

document.addEventListener("DOMContentLoaded", () => {
  // El aviso (ok/error) de la última acción se desvanece solo a los pocos segundos.
  document.querySelectorAll(".flash").forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity 400ms ease";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 400);
    }, 4000);
  });

  // Confirmación antes de cualquier acción marcada como irreversible
  // (desconectar una cuenta, descartar una oferta...).
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Vista previa de las fotos elegidas antes de generar el anuncio.
  const photoInput = document.getElementById("photo-input");
  const preview = document.getElementById("photo-preview");
  if (photoInput && preview) {
    photoInput.addEventListener("change", () => {
      preview.innerHTML = "";
      Array.from(photoInput.files || []).forEach((file) => {
        const img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        img.alt = file.name;
        img.style.width = "72px";
        img.style.height = "72px";
        img.style.objectFit = "cover";
        img.style.borderRadius = "8px";
        img.style.border = "1px solid var(--border)";
        preview.appendChild(img);
      });
    });
  }

  // Sello del coche de GitHub: su animación (CSS con `animation-delay` por
  // fila, para el efecto de "se va dibujando") solo se dispara UNA vez al
  // insertarse el elemento en la página — para que quede "todo el rato en
  // bucle" se clona y se reemplaza a sí mismo cada pocos segundos, lo que
  // basta para que el navegador la trate como una animación nueva y la
  // vuelva a reproducir desde el principio. Duración real del dibujo: hasta
  // 1.8s de retraso de la última fila + 0.9s de su propio trazo ≈ 2.7s.
  const CAR_SEAL_LOOP_MS = 4200;
  function loopGithubCarSeal() {
    const svg = document.getElementById("github-car-seal-svg");
    if (!svg || !svg.parentNode) {
      return;
    }
    const clone = svg.cloneNode(true);
    svg.parentNode.replaceChild(clone, svg);
  }
  if (document.getElementById("github-car-seal-svg")) {
    setInterval(loopGithubCarSeal, CAR_SEAL_LOOP_MS);
  }
});
