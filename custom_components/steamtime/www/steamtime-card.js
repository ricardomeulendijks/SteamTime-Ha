// SteamTime custom Lovelace card (design §12).
//
// Plain vanilla Web Component — no build step, no framework — served
// directly by the integration (see frontend.py). Reads sensor.steamtime_
// session / next_add / next_done / dish_library reactively via `hass`, and
// drives the same public services the backend already exposes (services.py).
// No card configuration is needed: `setConfig` is a no-op.

(() => {
  const DOMAIN = "steamtime";
  const ENTITY_SESSION = "sensor.steamtime_session";
  const ENTITY_NEXT_ADD = "sensor.steamtime_next_add";
  const ENTITY_NEXT_DONE = "sensor.steamtime_next_done";
  const ENTITY_DISH_LIBRARY = "sensor.steamtime_dish_library";

  const CATEGORIES = [
    ["vegetables", "Vegetables"],
    ["fish", "Fish"],
    ["meat", "Meat"],
    ["other", "Other"],
  ];

  const STATUS_LABELS = {
    pending: "Pending",
    ready_to_add: "Ready to add",
    cooking: "Cooking",
    done: "Done",
  };

  const CONFIRM_TIMEOUT_MS = 4000;
  const ERROR_TIMEOUT_MS = 6000;

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value);
    return div.innerHTML;
  }

  function formatCountdown(stateObj) {
    if (!stateObj || stateObj.state === "unknown" || stateObj.state === "unavailable") {
      return "";
    }
    const target = new Date(stateObj.state).getTime();
    if (Number.isNaN(target)) return "";
    const diffSeconds = Math.round((target - Date.now()) / 1000);
    const abs = Math.abs(diffSeconds);
    const minutes = Math.floor(abs / 60);
    const seconds = abs % 60;
    const text = `${minutes}m ${seconds}s`;
    return diffSeconds >= 0 ? `in ${text}` : `${text} ago`;
  }

  const STYLE = `
    :host { display: block; }
    .card-content { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
    .error-banner {
      background: var(--error-color, #db4437);
      color: var(--text-primary-color, #fff);
      padding: 8px 12px;
      border-radius: 4px;
      font-size: 0.9em;
    }
    h3 { margin: 0 0 8px 0; font-size: 1em; color: var(--primary-text-color); }
    .dish-list { display: flex; flex-direction: column; gap: 4px; }
    .dish-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 0;
      border-bottom: 1px solid var(--divider-color, #e0e0e0);
      flex-wrap: wrap;
    }
    .dish-check { display: flex; align-items: center; gap: 6px; flex: 1 1 auto; min-width: 120px; }
    .dish-meta { color: var(--secondary-text-color); font-size: 0.85em; }
    .dish-minutes { width: 64px; }
    .dish-actions { display: flex; gap: 4px; margin-left: auto; }
    .icon-btn {
      background: none; border: none; cursor: pointer; font-size: 1em;
      color: var(--secondary-text-color); padding: 2px 6px;
    }
    .icon-btn:hover { color: var(--primary-text-color); }
    .empty { color: var(--secondary-text-color); font-style: italic; margin: 0; }
    .dish-form { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
    .dish-form input, .dish-form select {
      padding: 6px 8px; border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 4px; background: var(--card-background-color, #fff);
      color: var(--primary-text-color); font: inherit;
    }
    .dish-form-actions { display: flex; gap: 8px; }
    button.primary {
      background: var(--primary-color); color: var(--text-primary-color, #fff);
      border: none; border-radius: 4px; padding: 8px 16px; cursor: pointer; font: inherit;
    }
    button.danger { background: var(--error-color, #db4437); }
    button.confirming { background: var(--warning-color, #ff9800); }
    button:disabled { opacity: 0.5; cursor: default; }
    .badge {
      padding: 2px 8px; border-radius: 12px; font-size: 0.8em;
      background: var(--divider-color, #e0e0e0); color: var(--primary-text-color);
    }
    .badge-ready_to_add { background: var(--warning-color, #ff9800); color: #000; }
    .badge-cooking { background: var(--info-color, #039be5); color: #fff; }
    .badge-done { background: var(--success-color, #43a047); color: #fff; }
    .countdowns { color: var(--secondary-text-color); font-size: 0.9em; display: flex; flex-direction: column; gap: 4px; }
    #cancel-area { margin-top: 8px; }
  `;

  class SteamtimeCard extends HTMLElement {
    constructor() {
      super();
      this._hass = null;
      this._prevSession = null;
      this._prevLibrary = null;
      this._pendingLibrary = null;
      this._selected = new Map();
      this._editingDishId = null;
      this._confirmable = null;
      this._errorTimeoutId = null;

      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `
        <style>${STYLE}</style>
        <ha-card header="SteamTime">
          <div class="card-content">
            <div id="error-banner" class="error-banner" hidden></div>
            <div id="setup-section">
              <h3>Dishes</h3>
              <div id="dish-list" class="dish-list"></div>
              <div id="dish-form" class="dish-form"></div>
              <button id="start-btn" class="primary">Start session</button>
            </div>
            <div id="live-section" hidden>
              <h3>Cooking now</h3>
              <div id="live-list" class="dish-list"></div>
              <div id="countdowns" class="countdowns"></div>
              <div id="cancel-area"></div>
            </div>
          </div>
        </ha-card>
      `;

      this._errorBanner = root.getElementById("error-banner");
      this._setupSection = root.getElementById("setup-section");
      this._liveSection = root.getElementById("live-section");
      this._dishListEl = root.getElementById("dish-list");
      this._dishFormEl = root.getElementById("dish-form");
      this._startBtn = root.getElementById("start-btn");
      this._liveListEl = root.getElementById("live-list");
      this._countdownsEl = root.getElementById("countdowns");
      this._cancelAreaEl = root.getElementById("cancel-area");

      this._startBtn.addEventListener("click", () => this._startSession());

      this._renderDishForm();
      this._resetDishForm();

      this._cancelBtn = document.createElement("button");
      this._cancelBtn.className = "danger";
      this._cancelBtn.textContent = "Cancel session";
      this._cancelAreaEl.appendChild(this._cancelBtn);
      this._wireConfirmable(this._cancelBtn, "cancel-session", "Confirm cancel?", () =>
        this._cancelSession()
      );

      this._countdownInterval = setInterval(() => this._updateCountdowns(), 1000);
    }

    disconnectedCallback() {
      clearInterval(this._countdownInterval);
    }

    setConfig(_config) {
      // No configuration needed — the card renders from entity state alone.
    }

    getCardSize() {
      return 8;
    }

    set hass(hass) {
      this._hass = hass;
      try {
        this._updateFromHass(hass);
      } catch (err) {
        this._showError(`Render error: ${this._describeError(err)}`);
        // eslint-disable-next-line no-console
        console.error("steamtime-card render error", err);
      }
    }

    _updateFromHass(hass) {
      const session = hass.states[ENTITY_SESSION];
      const library = hass.states[ENTITY_DISH_LIBRARY];

      const running = Boolean(session && session.state === "running");
      this._setupSection.hidden = running;
      this._liveSection.hidden = !running;

      if (library && library !== this._prevLibrary) {
        this._pendingLibrary = library;
      }
      const focusInDishList =
        this.shadowRoot.activeElement && this._dishListEl.contains(this.shadowRoot.activeElement);
      if (this._pendingLibrary && !focusInDishList) {
        this._prevLibrary = this._pendingLibrary;
        this._pendingLibrary = null;
        this._renderDishList(this._prevLibrary.attributes.dishes || []);
      }

      if (session && session !== this._prevSession) {
        this._prevSession = session;
        if (running) this._renderLiveList(session.attributes.dishes || []);
      }

      this._updateCountdowns();
    }

    get hass() {
      return this._hass;
    }

    // ---- dish checklist (start-session picker) ----

    _renderDishList(dishes) {
      const rows = dishes
        .map((dish) => {
          const isCustom = dish.id.startsWith("custom_");
          const checked = this._selected.has(dish.id);
          const overrideValue = checked ? this._selected.get(dish.id) : dish.steam_minutes;
          return `
            <div class="dish-row" data-dish-id="${escapeHtml(dish.id)}">
              <label class="dish-check">
                <input type="checkbox" class="dish-checkbox" ${checked ? "checked" : ""} />
                <span>${escapeHtml(dish.name)}</span>
              </label>
              <span class="dish-meta">${escapeHtml(dish.category)} · ${escapeHtml(dish.temperature)}°C</span>
              <input type="number" class="dish-minutes" min="1" max="600"
                     value="${escapeHtml(overrideValue)}" ${checked ? "" : "disabled"} />
              <span class="dish-actions">
                ${
                  isCustom
                    ? `<button class="icon-btn edit-dish" title="Edit">✎</button>
                       <button class="icon-btn remove-dish" title="Remove">\u{1F5D1}</button>`
                    : ""
                }
              </span>
            </div>
          `;
        })
        .join("");
      this._dishListEl.innerHTML =
        rows || `<p class="empty">No dishes yet — add one below.</p>`;

      this._dishListEl.querySelectorAll(".dish-row").forEach((row) => {
        const dishId = row.dataset.dishId;
        const checkbox = row.querySelector(".dish-checkbox");
        const minutesInput = row.querySelector(".dish-minutes");

        checkbox.addEventListener("change", () => {
          minutesInput.disabled = !checkbox.checked;
          if (checkbox.checked) {
            this._selected.set(dishId, minutesInput.value);
          } else {
            this._selected.delete(dishId);
          }
        });
        minutesInput.addEventListener("input", () => {
          if (checkbox.checked) this._selected.set(dishId, minutesInput.value);
        });

        const editBtn = row.querySelector(".edit-dish");
        if (editBtn) {
          editBtn.addEventListener("click", () => {
            const dish = dishes.find((d) => d.id === dishId);
            if (dish) this._startEditDish(dish);
          });
        }
        const removeBtn = row.querySelector(".remove-dish");
        if (removeBtn) {
          this._wireConfirmable(removeBtn, `remove-${dishId}`, "Sure?", () =>
            this._removeDish(dishId)
          );
        }
      });
    }

    async _startSession() {
      const dishes = Array.from(this._selected.entries()).map(([dishId, minutes]) => {
        const parsed = Number(minutes);
        return Number.isFinite(parsed) && parsed > 0
          ? { dish_id: dishId, minutes: parsed }
          : { dish_id: dishId };
      });
      if (dishes.length === 0) {
        this._showError("Select at least one dish.");
        return;
      }
      try {
        await this._callService("start_session", { dishes });
        this._selected.clear();
        if (this._prevLibrary) {
          this._renderDishList(this._prevLibrary.attributes.dishes || []);
        }
      } catch (err) {
        this._showError(this._describeError(err));
      }
    }

    // ---- add / edit / remove custom dish ----

    _renderDishForm() {
      this._dishFormEl.innerHTML = `
        <h3 id="dish-form-title">Add a custom dish</h3>
        <input id="dish-name" type="text" placeholder="Name" maxlength="100" />
        <input id="dish-minutes" type="number" placeholder="Steam minutes" min="1" max="600" />
        <input id="dish-temperature" type="number" placeholder="Temperature °C" min="1" max="250" />
        <select id="dish-category">
          ${CATEGORIES.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
        </select>
        <div class="dish-form-actions">
          <button id="dish-form-submit" class="primary">Add dish</button>
          <button id="dish-form-cancel" hidden>Cancel edit</button>
        </div>
      `;
      this._dishFormTitle = this._dishFormEl.querySelector("#dish-form-title");
      this._nameInput = this._dishFormEl.querySelector("#dish-name");
      this._minutesInput = this._dishFormEl.querySelector("#dish-minutes");
      this._temperatureInput = this._dishFormEl.querySelector("#dish-temperature");
      this._categorySelect = this._dishFormEl.querySelector("#dish-category");
      this._submitBtn = this._dishFormEl.querySelector("#dish-form-submit");
      this._cancelEditBtn = this._dishFormEl.querySelector("#dish-form-cancel");

      this._submitBtn.addEventListener("click", () => this._submitDishForm());
      this._cancelEditBtn.addEventListener("click", () => this._resetDishForm());
    }

    _startEditDish(dish) {
      this._editingDishId = dish.id;
      this._dishFormTitle.textContent = `Edit ${dish.name}`;
      this._nameInput.value = dish.name;
      this._minutesInput.value = dish.steam_minutes;
      this._temperatureInput.value = dish.temperature;
      this._categorySelect.value = dish.category;
      this._submitBtn.textContent = "Save changes";
      this._cancelEditBtn.hidden = false;
    }

    _resetDishForm() {
      this._editingDishId = null;
      this._dishFormTitle.textContent = "Add a custom dish";
      this._nameInput.value = "";
      this._minutesInput.value = "";
      this._temperatureInput.value = "";
      this._categorySelect.value = CATEGORIES[0][0];
      this._submitBtn.textContent = "Add dish";
      this._cancelEditBtn.hidden = true;
    }

    async _submitDishForm() {
      const payload = {
        name: this._nameInput.value.trim(),
        minutes: Number(this._minutesInput.value),
        temperature: Number(this._temperatureInput.value),
        category: this._categorySelect.value,
      };
      if (!payload.name) {
        this._showError("Name is required.");
        return;
      }
      try {
        if (this._editingDishId) {
          await this._callService("update_dish", { dish_id: this._editingDishId, ...payload });
        } else {
          await this._callService("add_dish", payload);
        }
        this._resetDishForm();
      } catch (err) {
        this._showError(this._describeError(err));
      }
    }

    async _removeDish(dishId) {
      try {
        await this._callService("remove_dish", { dish_id: dishId });
      } catch (err) {
        this._showError(this._describeError(err));
      }
    }

    // ---- live session view ----

    _renderLiveList(dishes) {
      const rows = dishes
        .map((dish) => {
          const canConfirm = dish.status === "ready_to_add";
          return `
            <div class="dish-row" data-dish-id="${escapeHtml(dish.id)}">
              <span>${escapeHtml(dish.name)}</span>
              <span class="badge badge-${escapeHtml(dish.status)}">${escapeHtml(
                STATUS_LABELS[dish.status] || dish.status
              )}</span>
              ${canConfirm ? `<button class="confirm-dish primary">Confirm added</button>` : ""}
            </div>
          `;
        })
        .join("");
      this._liveListEl.innerHTML = rows;
      this._liveListEl.querySelectorAll(".confirm-dish").forEach((btn) => {
        const dishId = btn.closest(".dish-row").dataset.dishId;
        btn.addEventListener("click", () => this._confirmDish(dishId));
      });
    }

    async _confirmDish(dishId) {
      try {
        await this._callService("confirm_dish", { dish_id: dishId });
      } catch (err) {
        this._showError(this._describeError(err));
      }
    }

    async _cancelSession() {
      try {
        await this._callService("cancel_session", {});
        this._selected.clear();
      } catch (err) {
        this._showError(this._describeError(err));
      }
    }

    _updateCountdowns() {
      if (!this._hass) return;
      const nextAdd = this._hass.states[ENTITY_NEXT_ADD];
      const nextDone = this._hass.states[ENTITY_NEXT_DONE];
      const parts = [];
      if (nextAdd && nextAdd.attributes.dish_name) {
        parts.push(
          `Next add: <strong>${escapeHtml(nextAdd.attributes.dish_name)}</strong> ${formatCountdown(nextAdd)}`
        );
      }
      if (nextDone && nextDone.attributes.dish_name) {
        parts.push(
          `Next done: <strong>${escapeHtml(nextDone.attributes.dish_name)}</strong> ${formatCountdown(nextDone)}`
        );
      }
      this._countdownsEl.innerHTML = parts.map((p) => `<div>${p}</div>`).join("");
    }

    // ---- shared helpers ----

    _wireConfirmable(button, key, confirmLabel, onConfirm) {
      const originalLabel = button.textContent;
      button.addEventListener("click", () => {
        if (this._confirmable && this._confirmable.key === key) {
          clearTimeout(this._confirmable.timeoutId);
          this._confirmable = null;
          onConfirm();
          return;
        }
        if (this._confirmable) {
          this._confirmable.revert();
        }
        const timeoutId = setTimeout(() => {
          button.textContent = originalLabel;
          button.classList.remove("confirming");
          this._confirmable = null;
        }, CONFIRM_TIMEOUT_MS);
        button.textContent = confirmLabel;
        button.classList.add("confirming");
        this._confirmable = {
          key,
          timeoutId,
          revert: () => {
            button.textContent = originalLabel;
            button.classList.remove("confirming");
          },
        };
      });
    }

    _callService(service, data) {
      return this._hass.callService(DOMAIN, service, data);
    }

    _showError(message) {
      this._errorBanner.textContent = message;
      this._errorBanner.hidden = false;
      clearTimeout(this._errorTimeoutId);
      this._errorTimeoutId = setTimeout(() => {
        this._errorBanner.hidden = true;
      }, ERROR_TIMEOUT_MS);
    }

    _describeError(err) {
      return (err && err.message) || String(err);
    }
  }

  customElements.define("steamtime-card", SteamtimeCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "steamtime-card",
    name: "SteamTime",
    description: "Start, monitor, and manage SteamTime cooking sessions.",
  });
})();
