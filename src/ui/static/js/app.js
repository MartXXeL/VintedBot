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
});
