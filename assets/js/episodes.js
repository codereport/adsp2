(function () {
  "use strict";

  const moreGuestsToggle = document.querySelector(".more-guests-toggle");
  const additionalGuests = document.getElementById("additional-guests");

  if (moreGuestsToggle && additionalGuests) {
    moreGuestsToggle.addEventListener("click", function () {
      const isExpanded = moreGuestsToggle.getAttribute("aria-expanded") === "true";
      const willExpand = !isExpanded;

      moreGuestsToggle.setAttribute("aria-expanded", String(willExpand));
      additionalGuests.hidden = !willExpand;
      moreGuestsToggle.textContent = willExpand
        ? moreGuestsToggle.dataset.hideLabel
        : moreGuestsToggle.dataset.showLabel;
    });
  }

  const guestTable = document.querySelector(".frequent-guests-table");

  if (guestTable && guestTable.tBodies.length) {
    const guestButtons = Array.from(guestTable.querySelectorAll(".guest-sort"));
    const primaryGuests = guestTable.tBodies[0];
    const additionalGuestRows = guestTable.tBodies[1] || null;
    const visibleGuestCount = primaryGuests.rows.length;
    let activeGuestKey = "episodes";
    let activeGuestDirection = "descending";

    function updateGuestHeaders() {
      guestButtons.forEach(function (button) {
        const isActive = button.dataset.sortKey === activeGuestKey;
        const nextDirection = isActive
          ? activeGuestDirection === "descending" ? "ascending" : "descending"
          : button.dataset.sortType === "text" ? "ascending" : "descending";
        const header = button.closest("th");

        header.setAttribute(
          "aria-sort",
          isActive ? activeGuestDirection : "none"
        );
        button.setAttribute(
          "aria-label",
          isActive
            ? button.textContent + ", sorted " + activeGuestDirection +
              ". Activate to sort " + nextDirection + "."
            : "Sort by " + button.textContent + ", " + nextDirection + "."
        );
      });
    }

    guestButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        const key = button.dataset.sortKey;
        if (key === activeGuestKey) {
          activeGuestDirection = activeGuestDirection === "ascending"
            ? "descending"
            : "ascending";
        } else {
          activeGuestKey = key;
          activeGuestDirection = button.dataset.sortType === "text"
            ? "ascending"
            : "descending";
        }

        const rows = Array.from(guestTable.querySelectorAll("tbody tr"));
        rows.sort(function (left, right) {
          const leftValue = left.getAttribute("data-" + activeGuestKey);
          const rightValue = right.getAttribute("data-" + activeGuestKey);

          // Keep unavailable total times at the bottom in either direction.
          if (leftValue === "" && rightValue === "") {
            return left.dataset.guest.localeCompare(right.dataset.guest);
          }
          if (leftValue === "") return 1;
          if (rightValue === "") return -1;

          const difference = button.dataset.sortType === "text"
            ? leftValue.localeCompare(rightValue)
            : Number(leftValue) - Number(rightValue);
          if (difference === 0) {
            return left.dataset.guest.localeCompare(right.dataset.guest);
          }
          return activeGuestDirection === "ascending" ? difference : -difference;
        });

        rows.forEach(function (row, index) {
          const destination = additionalGuestRows && index >= visibleGuestCount
            ? additionalGuestRows
            : primaryGuests;
          destination.appendChild(row);
        });
        updateGuestHeaders();
      });
    });

    updateGuestHeaders();
  }

  const bafChart = document.getElementById("baf-chart");
  const bafZoomControls = document.querySelector(".baf-zoom-controls");

  if (bafChart && bafZoomControls) {
    const scroller = bafChart.closest(".conversation-chart-scroll");
    const zoomOut = bafZoomControls.querySelector('[data-baf-zoom="out"]');
    const zoomIn = bafZoomControls.querySelector('[data-baf-zoom="in"]');
    const zoomValue = bafZoomControls.querySelector(".baf-zoom-value");
    const zoomLevels = [0.5, 1, 1.5, 2, 3, 4];
    let zoomIndex = 3;

    function updateZoom(nextIndex) {
      const atStart = scroller.scrollLeft <= 1;
      const atEnd = scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 1;
      const center = scroller.scrollWidth
        ? (scroller.scrollLeft + scroller.clientWidth / 2) / scroller.scrollWidth
        : 0;

      zoomIndex = Math.max(0, Math.min(zoomLevels.length - 1, nextIndex));
      bafChart.style.setProperty("--baf-zoom", zoomLevels[zoomIndex]);
      zoomValue.textContent = Math.round(zoomLevels[zoomIndex] * 100) + "%";
      zoomOut.disabled = zoomIndex === 0;
      zoomIn.disabled = zoomIndex === zoomLevels.length - 1;
      scroller.scrollLeft = atStart ? 0 : atEnd
        ? scroller.scrollWidth - scroller.clientWidth
        : center * scroller.scrollWidth - scroller.clientWidth / 2;
    }

    zoomOut.addEventListener("click", function () { updateZoom(zoomIndex - 1); });
    zoomIn.addEventListener("click", function () { updateZoom(zoomIndex + 1); });
    bafZoomControls.hidden = false;
    updateZoom(zoomIndex);
  }

  const table = document.querySelector(".episodes-table");
  if (!table || !table.tBodies.length) {
    return;
  }

  const buttons = Array.from(table.querySelectorAll(".episodes-sort"));
  let activeKey = "number";
  let activeDirection = "descending";

  function durationInMinutes(value) {
    const text = value.trim();
    if (!/^\d+(?::\d{2})?$/.test(text)) {
      return null;
    }

    const parts = text.split(":").map(Number);
    return parts.length === 2 ? parts[0] * 60 + parts[1] : parts[0];
  }

  function rowValue(row, key) {
    if (key === "number") {
      return Number(row.cells[0].textContent.trim());
    }
    return durationInMinutes(row.cells[2].textContent);
  }

  function updateHeaders() {
    buttons.forEach(function (button) {
      const isActive = button.dataset.sortKey === activeKey;
      const header = button.closest("th");
      const columnLabel = button.dataset.sortKey === "number"
        ? "episode number"
        : "duration";
      const nextDirection = isActive && activeDirection === "descending"
        ? "ascending"
        : "descending";

      header.setAttribute(
        "aria-sort",
        isActive ? activeDirection : "none"
      );
      button.setAttribute(
        "aria-label",
        isActive
          ? columnLabel + ", sorted " + activeDirection +
            ". Activate to sort " + nextDirection + "."
          : "Sort by " + columnLabel + ", descending."
      );
    });
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      const key = button.dataset.sortKey;
      if (key === activeKey) {
        activeDirection = activeDirection === "ascending"
          ? "descending"
          : "ascending";
      } else {
        activeKey = key;
        activeDirection = "descending";
      }

      const rows = Array.from(table.tBodies[0].rows);
      rows.sort(function (left, right) {
        const leftValue = rowValue(left, activeKey);
        const rightValue = rowValue(right, activeKey);

        // Keep unavailable durations at the bottom in either direction.
        if (leftValue === null && rightValue === null) {
          return Number(right.cells[0].textContent) - Number(left.cells[0].textContent);
        }
        if (leftValue === null) return 1;
        if (rightValue === null) return -1;

        const difference = leftValue - rightValue;
        if (difference === 0) {
          return Number(right.cells[0].textContent) - Number(left.cells[0].textContent);
        }
        return activeDirection === "ascending" ? difference : -difference;
      });

      rows.forEach(function (row) {
        table.tBodies[0].appendChild(row);
      });
      updateHeaders();
    });
  });

  updateHeaders();
})();
