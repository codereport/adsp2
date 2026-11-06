(function () {
  "use strict";

  function addMonthsUTC(date, months) {
    const result = new Date(date.getTime());
    const day = result.getUTCDate();
    result.setUTCDate(1);
    result.setUTCMonth(result.getUTCMonth() + months);
    const lastDay = new Date(Date.UTC(
      result.getUTCFullYear(), result.getUTCMonth() + 1, 0
    )).getUTCDate();
    result.setUTCDate(Math.min(day, lastDay));
    return result;
  }

  function elapsedSince(published, now) {
    const current = new Date(Math.max(published.getTime(), now.getTime()));
    let months = (current.getUTCFullYear() - published.getUTCFullYear()) * 12 +
      current.getUTCMonth() - published.getUTCMonth();
    if (addMonthsUTC(published, months) > current) months -= 1;

    let remaining = Math.floor((current - addMonthsUTC(published, months)) / 1000);
    const weeks = Math.floor(remaining / 604800);
    remaining %= 604800;
    const days = Math.floor(remaining / 86400);
    remaining %= 86400;
    const hours = Math.floor(remaining / 3600);
    remaining %= 3600;

    return {
      months: months, weeks: weeks, days: days, hours: hours,
      minutes: Math.floor(remaining / 60), seconds: remaining % 60,
      state: current > addMonthsUTC(published, 12) ? "danger" :
        current > addMonthsUTC(published, 10) ? "warning" : "normal"
    };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {addMonthsUTC: addMonthsUTC, elapsedSince: elapsedSince};
  }
  if (typeof document === "undefined") return;

  const container = document.querySelector("[data-tssp-published]");
  if (!container) return;
  const published = new Date(container.dataset.tsspPublished);
  if (!Number.isFinite(published.getTime())) return;

  const clock = container.querySelector(".tssp-clock");
  const status = container.querySelector(".tssp-status");
  const units = Array.from(container.querySelectorAll("[data-tssp-unit]"));
  const messages = {normal: "", warning: "Over 10 months", danger: "Over 1 year"};

  function updateClock() {
    const values = elapsedSince(published, new Date());
    const description = [];
    units.forEach(function (unit) {
      const name = unit.dataset.tsspUnit;
      const value = values[name];
      const text = String(value).padStart(2, "0");
      if (unit.textContent !== text) unit.textContent = text;
      description.push(value + " " + (value === 1 ? name.slice(0, -1) : name));
    });
    clock.setAttribute("aria-label", description.join(", ") + " since Sean Parent's last episode");
    clock.hidden = false;
    container.dataset.state = values.state;
    const message = messages[values.state];
    if (status.textContent !== message) status.textContent = message;
    status.hidden = !message;
  }

  updateClock();
  setInterval(updateClock, 1000);
  document.addEventListener("visibilitychange", updateClock);
})();
