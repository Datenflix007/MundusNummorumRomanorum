document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-search-form]");
  const status = document.querySelector("[data-search-status]");
  if (form && status) {
    form.addEventListener("submit", () => {
      status.textContent = "Searching the local catalog…";
    });
  }

  const previewRequest = document.querySelector("[data-ocre-image-previews]");
  if (!previewRequest) return;
  const button = previewRequest.querySelector("[data-load-ocre-images]");
  const previewStatus = previewRequest.querySelector("[data-image-status]");
  const results = previewRequest.querySelector("[data-image-results]");
  const coinId = previewRequest.dataset.coinId;
  if (!button || !previewStatus || !results || !coinId) return;

  button.addEventListener("click", async () => {
    button.disabled = true;
    previewStatus.textContent = "Loading attributed external image previews…";
    try {
      const response = await fetch(`/api/coins/${encodeURIComponent(coinId)}/images`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "Image previews are unavailable.");
      results.replaceChildren();
      for (const image of payload.items) {
        const figure = document.createElement("figure");
        const preview = document.createElement("img");
        preview.src = image.thumbnail_url;
        preview.loading = "lazy";
        preview.referrerPolicy = "no-referrer";
        preview.alt = `${image.side || "Coin"} image: ${image.attribution}`;
        figure.append(preview);
        const caption = document.createElement("figcaption");
        if (image.record_url) {
          const link = document.createElement("a");
          link.href = image.record_url;
          link.target = "_blank";
          link.rel = "noreferrer";
          link.textContent = image.attribution;
          caption.append(link);
        } else {
          caption.textContent = image.attribution;
        }
        figure.append(caption);
        results.append(figure);
      }
      previewStatus.textContent = payload.items.length
        ? "Representative images are shown with their OCRE-provided credits."
        : "OCRE did not provide representative images for this type.";
    } catch (error) {
      previewStatus.textContent = error.message;
      button.disabled = false;
    }
  });
});
