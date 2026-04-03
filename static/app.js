(() => {
  const form = document.querySelector(".search-form");
  const resultsRegion = document.getElementById("results-region");
  const submitButton = form?.querySelector('button[type="submit"]');

  if (!form || !resultsRegion || !window.fetch) {
    return;
  }

  const loadingTitle =
    resultsRegion.dataset.loadingTitle || "Getting info from indexed documents...";
  const loadingHint =
    resultsRegion.dataset.loadingHint
    || "Matching paths, snippets, and click history.";
  const errorTitle =
    resultsRegion.dataset.errorTitle || "Could not fetch documents right now.";
  const errorHint =
    resultsRegion.dataset.errorHint || "Please try the search again in a moment.";

  let activeController = null;
  const defaultButtonText = submitButton?.textContent ?? "Search";

  const renderState = (title, hint, isLoading = false) => {
    const loadingClass = isLoading ? " message-loading" : "";
    resultsRegion.innerHTML =
      `<div class="message message-state${loadingClass}">`
      + `<strong class="message-title">${title}</strong>`
      + `<span class="message-hint">${hint}</span>`
      + "</div>";
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    activeController?.abort();
    const requestController = new AbortController();
    activeController = requestController;

    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Getting info...";
    }

    renderState(loadingTitle, loadingHint, true);

    try {
      const response = await fetch(form.action || window.location.pathname, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "XMLHttpRequest" },
        signal: requestController.signal,
      });

      if (!response.ok) {
        throw new Error("Search request failed");
      }

      if (activeController === requestController) {
        resultsRegion.innerHTML = await response.text();
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      if (activeController === requestController) {
        renderState(errorTitle, errorHint);
      }
    } finally {
      if (submitButton && activeController === requestController) {
        submitButton.disabled = false;
        submitButton.textContent = defaultButtonText;
      }
      if (activeController === requestController) {
        activeController = null;
      }
    }
  });
})();
