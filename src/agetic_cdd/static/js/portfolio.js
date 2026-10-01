(() => {
  const sidebar = document.getElementById("sidebar");
  const navToggle = document.getElementById("nav-toggle");
  const refreshBtn = document.getElementById("refresh-btn");
  const createBtn = document.getElementById("create-dealroom");
  const modal = document.getElementById("create-modal");
  const modalClose = document.getElementById("modal-close");
  const modalCancel = document.getElementById("modal-cancel");
  const form = document.getElementById("create-deal-form");
  const nameInput = document.getElementById("portfolio-name");
  const slugInput = document.getElementById("portfolio-slug");
  const formError = document.getElementById("form-error");
  const submitBtn = document.getElementById("modal-submit");
  const dealGrid = document.getElementById("deal-grid");

  let slugTouched = false;

  const slugify = (value) =>
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/[\s_-]+/g, "-")
      .replace(/^-+|-+$/g, "");

  const openModal = () => {
    form?.reset();
    slugTouched = false;
    hideError();
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    nameInput?.focus();
  };

  const closeModal = () => {
    modal.hidden = true;
    document.body.style.overflow = "";
    hideError();
  };

  const hideError = () => {
    if (!formError) return;
    formError.hidden = true;
    formError.textContent = "";
  };

  const showError = (message) => {
    if (!formError) return;
    formError.hidden = false;
    formError.textContent = message;
  };

  const statusClass = (status) =>
    `status-badge status-${String(status).toLowerCase().replace(/-/g, "")}`;

  const bindDealCard = (card) => {
    const openDeal = () => {
      const name = card.getAttribute("data-deal");
      window.alert(`Opening workspace for “${name}”.`);
    };
    card.addEventListener("click", openDeal);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDeal();
      }
    });
  };

  const renderDealCard = (deal) => {
    const card = document.createElement("article");
    card.className = "deal-card";
    card.tabIndex = 0;
    card.dataset.deal = deal.name;
    card.dataset.slug = deal.slug;
    card.innerHTML = `
      <div class="deal-card-body">
        <div class="deal-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7">
            <path d="M3 8.5A2.5 2.5 0 0 1 5.5 6H10l2 2h6.5A2.5 2.5 0 0 1 21 10.5v7A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5v-9z" />
          </svg>
        </div>
        <div class="deal-content">
          <div class="deal-title-row">
            <h2></h2>
            <span class="${statusClass(deal.status)}"></span>
          </div>
          <p class="deal-summary"></p>
          <p class="deal-team"></p>
        </div>
        <span class="deal-chevron" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="m9 6 6 6-6 6" />
          </svg>
        </span>
      </div>
    `;
    card.querySelector("h2").textContent = deal.name;
    card.querySelector(".status-badge").textContent = deal.status;
    card.querySelector(".deal-summary").textContent = deal.summary;
    card.querySelector(".deal-team").textContent = deal.team;
    bindDealCard(card);
    return card;
  };

  const updateMetrics = (metrics) => {
    const active = document.getElementById("metric-active-deals");
    const agents = document.getElementById("metric-agents-running");
    const reports = document.getElementById("metric-reports-ready");
    if (active) active.textContent = metrics.active_deals;
    if (agents) agents.textContent = metrics.agents_running_now;
    if (reports) reports.textContent = metrics.reports_ready;
  };

  const prependDeal = (deal) => {
    if (!dealGrid) return;
    dealGrid.prepend(renderDealCard(deal));
  };

  navToggle?.addEventListener("click", () => {
    sidebar?.classList.toggle("is-open");
  });

  refreshBtn?.addEventListener("click", () => {
    window.location.reload();
  });

  createBtn?.addEventListener("click", openModal);
  modalClose?.addEventListener("click", closeModal);
  modalCancel?.addEventListener("click", closeModal);

  modal?.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal && !modal.hidden) {
      closeModal();
    }
  });

  nameInput?.addEventListener("input", () => {
    if (!slugTouched && slugInput) {
      slugInput.value = slugify(nameInput.value);
    }
  });

  slugInput?.addEventListener("input", () => {
    slugTouched = true;
    slugInput.value = slugify(slugInput.value);
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError();

    const payload = {
      name: nameInput.value.trim(),
      slug: slugInput.value.trim() || slugify(nameInput.value),
      description: document.getElementById("portfolio-description").value.trim(),
      tags: document.getElementById("portfolio-tags").value.trim(),
      industry: document.getElementById("portfolio-industry").value,
    };

    if (!payload.name) {
      showError("Portfolio name is required.");
      nameInput.focus();
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Creating...";

    try {
      const response = await fetch("/api/deals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Failed to create workspace");
      }

      prependDeal(data.deal);
      updateMetrics(data.portfolio.metrics);
      closeModal();
    } catch (error) {
      showError(error.message || "Failed to create workspace");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Create workspace";
    }
  });

  document.querySelectorAll(".deal-card").forEach(bindDealCard);
})();
