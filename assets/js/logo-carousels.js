(function () {
  "use strict";

  function initialize(viewport, index) {
    const heading = viewport.previousElementSibling;
    const root = document.createElement("div");
    root.className = "logo-carousel";
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", heading ? heading.textContent.trim() : "Episode logos");
    viewport.before(root);
    root.append(viewport);
    viewport.classList.add("logo-carousel-viewport");
    viewport.id = viewport.id || "logo-carousel-" + index;

    const track = document.createElement("div");
    track.className = "logo-carousel-track";
    const group = document.createElement("div");
    group.className = "logo-carousel-group";
    group.append(...viewport.children);
    track.append(group);
    viewport.append(track);

    const copy = group.cloneNode(true);
    copy.setAttribute("aria-hidden", "true");
    copy.querySelectorAll("[id]").forEach(element => element.removeAttribute("id"));
    copy.querySelectorAll("a").forEach(link => link.tabIndex = -1);
    track.append(copy);

    const button = document.createElement("button");
    button.className = "logo-carousel-toggle";
    button.type = "button";
    button.setAttribute("aria-controls", viewport.id);
    root.append(button);

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const pixelsPerSecond = viewport.classList.contains("topic-logos") ? 42 : 28;
    let overflowing = false;
    let loopWidth = 0;
    let userPaused = false;
    let hovered = false;
    let focused = false;
    let interacting = false;
    let inView = true;
    let frame = 0;
    let lastTime = null;
    let offset = 0;
    let interactionTimer = 0;

    function animate(time) {
      if (lastTime !== null) {
        offset = (offset + Math.min(time - lastTime, 64) * pixelsPerSecond / 1000) % loopWidth;
        viewport.scrollLeft = offset;
      }
      lastTime = time;
      frame = window.requestAnimationFrame(animate);
    }

    function synchronize() {
      const running = overflowing && !reducedMotion.matches && !userPaused &&
        !hovered && !focused && !interacting && inView && !document.hidden;
      if (running && !frame) {
        offset = viewport.scrollLeft % loopWidth;
        lastTime = null;
        frame = window.requestAnimationFrame(animate);
      } else if (!running && frame) {
        window.cancelAnimationFrame(frame);
        frame = 0;
        lastTime = null;
      }
      if (button.getAttribute("aria-pressed") !== String(userPaused)) {
        const label = userPaused ? "Resume logo scrolling" : "Pause logo scrolling";
        button.setAttribute("aria-label", label);
        button.setAttribute("aria-pressed", String(userPaused));
        button.title = label;
        button.innerHTML = userPaused
          ? '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1v10l8-5z"/></svg>'
          : '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 1h3v10H2zm5 0h3v10H7z"/></svg>';
      }
    }

    function measure() {
      const style = window.getComputedStyle(viewport);
      const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      const width = group.getBoundingClientRect().width;
      overflowing = width > root.clientWidth - padding + 1;
      loopWidth = width + parseFloat(window.getComputedStyle(track).columnGap);
      root.classList.toggle("is-overflowing", overflowing);
      root.classList.toggle("is-reduced-motion", reducedMotion.matches);
      copy.hidden = !overflowing || reducedMotion.matches;
      button.hidden = !overflowing || reducedMotion.matches;
      if (overflowing) viewport.tabIndex = 0;
      else {
        viewport.removeAttribute("tabindex");
        viewport.scrollLeft = 0;
      }
      offset = viewport.scrollLeft;
      synchronize();
    }

    function hold() {
      window.clearTimeout(interactionTimer);
      interacting = true;
      synchronize();
    }

    function release() {
      window.clearTimeout(interactionTimer);
      interactionTimer = window.setTimeout(function () {
        interacting = false;
        synchronize();
      }, 1200);
    }

    button.addEventListener("click", function () {
      userPaused = !userPaused;
      // An explicit resume should work while the control still has focus.
      if (!userPaused) {
        hovered = false;
        focused = false;
      }
      synchronize();
    });
    root.addEventListener("pointerenter", function (event) {
      if (event.pointerType === "touch") return;
      hovered = true;
      synchronize();
    });
    root.addEventListener("pointerleave", function () {
      hovered = false;
      synchronize();
    });
    root.addEventListener("focusin", function () {
      focused = true;
      synchronize();
    });
    root.addEventListener("focusout", function (event) {
      focused = root.contains(event.relatedTarget);
      synchronize();
    });
    viewport.addEventListener("pointerdown", hold);
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
    viewport.addEventListener("wheel", function () {
      hold();
      release();
    }, { passive: true });
    document.addEventListener("visibilitychange", synchronize);
    reducedMotion.addEventListener("change", measure);

    const resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(root);
    resizeObserver.observe(group);
    if ("IntersectionObserver" in window) {
      const intersectionObserver = new IntersectionObserver(function (entries) {
        inView = entries[0].isIntersecting;
        synchronize();
      });
      intersectionObserver.observe(root);
    }
    measure();
  }

  function start() {
    document.querySelectorAll(".topic-logos, .company-logos").forEach(initialize);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
