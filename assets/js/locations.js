(function () {
  "use strict";

  const container = document.getElementById("recording-map");
  const dataElement = document.getElementById("recording-map-data");
  if (!container || !dataElement || !window.L || !window.RecordingMapLayout) return;

  const data = JSON.parse(dataElement.textContent);
  const panel = container.closest(".recording-map-panel");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const logoBase = container.dataset.logoBase;
  container.hidden = false;

  const map = L.map(container, {
    scrollWheelZoom: false,
    minZoom: 0,
    maxZoom: 16,
    zoomSnap: 0.5,
    worldCopyJump: true,
    zoomAnimation: !reducedMotion,
    fadeAnimation: !reducedMotion
  });

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  map.attributionControl.setPrefix(false);
  map.attributionControl.addAttribution('<a href="https://www.naturalearthdata.com/">Natural Earth</a>');

  function badge(location) {
    const element = document.createElement("span");
    element.className = "recording-marker-badge";
    if (location.logo) {
      const logo = document.createElement("img");
      logo.src = logoBase + location.logo;
      logo.alt = location.logo_name;
      element.appendChild(logo);
    } else if (location.mark) {
      element.classList.add("recording-marker-wordmark");
      element.textContent = location.mark;
    }
    return element;
  }

  function popup(location) {
    const content = document.createElement("div");
    content.className = "recording-map-popup";
    const heading = document.createElement("strong");
    heading.className = "recording-map-popup-title";
    heading.textContent = location.place;
    content.appendChild(heading);

    if (location.approximate) {
      const note = document.createElement("p");
      note.textContent = "Approximate road-trip location";
      note.className = "recording-map-popup-note";
      content.appendChild(note);
    }

    location.venues.forEach(function (venue) {
      const section = document.createElement("div");
      section.className = "recording-map-venue";
      const name = document.createElement("span");
      name.textContent = venue.name;
      section.appendChild(name);
      const links = document.createElement("div");
      links.className = "recording-map-episode-links";
      venue.episodes.forEach(function (number) {
        const episode = data.episodes[number];
        if (!episode) return;
        const link = document.createElement("a");
        link.href = episode.url;
        link.textContent = "Ep. " + number;
        link.title = episode.title;
        link.setAttribute("aria-label", episode.title);
        links.appendChild(link);
      });
      section.appendChild(links);
      content.appendChild(section);
    });
    return content;
  }

  const countryLayers = new Map();
  const countries = L.geoJSON(data.countries, {
    style: {
      className: "recording-country",
      color: "#9f354b", weight: 1,
      fillColor: "#b94b62", fillOpacity: 0.32
    },
    onEachFeature: function (feature, layer) {
      const country = feature.properties.country;
      const locations = data.locations.filter(function (location) { return location.country === country; });
      countryLayers.set(feature.properties.code, {layer: layer, locations: locations});
      const content = document.createElement("div");
      locations.forEach(function (location) { content.appendChild(popup(location)); });
      layer.bindTooltip(country, {sticky: true});
      layer.bindPopup(content, {maxWidth: 290, minWidth: 210, maxHeight: 280});
      layer.on("add", function () {
        const element = layer.getElement();
        element.setAttribute("tabindex", "0");
        element.setAttribute("role", "button");
        element.setAttribute("aria-label", country + ": recording locations and episodes");
        L.DomEvent.on(element, "keydown", function (event) {
          if (event.key === "Enter" || event.key === " ") {
            L.DomEvent.preventDefault(event);
            layer.openPopup(L.latLng(locations[0].coordinates));
          }
        });
      });
    }
  }).addTo(map);

  let conferenceRadius = container.clientWidth < 600 ? 23 : 27;
  container.style.setProperty("--conference-size", conferenceRadius * 2 + "px");
  function conferenceIcon(location, radius = conferenceRadius) {
    const icon = badge(location);
    icon.classList.add("recording-conference-badge");
    icon.style.setProperty("--conference-size", radius * 2 + "px");
    return L.divIcon({
      html: icon,
      className: "recording-marker recording-conference-marker" +
        (location.callout === false ? " recording-conference-fixed" : ""),
      iconSize: [radius * 2, radius * 2],
      iconAnchor: [radius, radius]
    });
  }

  const conferences = [];
  data.locations.forEach(function (location) {
    if (!location.logo && !location.mark) return;
    const marker = L.marker(location.coordinates, {
      location: location,
      title: location.place + (location.logo_name ? " · " + location.logo_name : ""),
      alt: location.place,
      icon: conferenceIcon(location)
    });
    marker.bindTooltip(marker.options.title, {direction: "top", offset: [0, -28]});
    if (location.callout === false) {
      marker.bindPopup(popup(location), {maxWidth: 290, minWidth: 210, maxHeight: 280});
      conferences.push({location: location, marker: marker, layers: L.layerGroup([marker])});
      return;
    }
    const leader = L.polyline([], {
      className: "recording-conference-leader",
      color: "#56798b", weight: 1.5, opacity: 0.9, interactive: false,
      smoothFactor: 0
    });
    marker.on("click", function () {
      // Popups stay attached to the real location, independently of the logo.
      L.popup({maxWidth: 290, minWidth: 210, maxHeight: 280})
        .setLatLng(location.coordinates).setContent(popup(location)).openOn(map);
    });
    conferences.push({location: location, marker: marker, leader: leader,
      layers: L.layerGroup([leader, marker])});
  });

  function layoutConferenceLogos(radiusOverride) {
    const size = map.getSize();
    const radius = radiusOverride || (size.x < 600 ? 23 : 27);
    if (radius !== conferenceRadius) {
      conferenceRadius = radius;
      container.style.setProperty("--conference-size", radius * 2 + "px");
      conferences.forEach(function (conference) {
        conference.marker.setIcon(conferenceIcon(conference.location));
      });
    }

    const fixed = conferences.filter(function (conference) { return conference.location.callout === false; })
      .map(function (conference) {
        return {conference: conference, point: map.latLngToContainerPoint(conference.location.coordinates)};
      }).filter(function (entry) {
        return entry.point.x >= 0 && entry.point.x <= size.x && entry.point.y >= 0 && entry.point.y <= size.y;
      });
    const fixedRadii = new Map();
    fixed.forEach(function (entry) {
      let fittedRadius = radius;
      fixed.forEach(function (other) {
        if (entry === other) return;
        fittedRadius = Math.min(fittedRadius, Math.max(8, Math.floor((entry.point.distanceTo(other.point) - 9) / 2)));
      });
      fixedRadii.set(entry.conference, fittedRadius);
    });

    const visible = [], obstacles = [];
    conferences.forEach(function (conference, index) {
      const anchor = map.latLngToContainerPoint(conference.location.coordinates);
      if (anchor.x < 0 || anchor.x > size.x || anchor.y < 0 || anchor.y > size.y) {
        map.removeLayer(conference.layers);
        return;
      }
      if (conference.location.callout === false) {
        const fixedRadius = fixedRadii.get(conference);
        if (conference.marker.options.icon.options.iconSize[0] !== fixedRadius * 2) {
          conference.marker.setIcon(conferenceIcon(conference.location, fixedRadius));
        }
        if (!map.hasLayer(conference.layers)) conference.layers.addTo(map);
        obstacles.push({x: anchor.x, y: anchor.y, radius: fixedRadius});
        return;
      }
      const offset = conference.location.callout_offset || [105, -45];
      visible.push({id: index, anchor: anchor,
        target: {x: anchor.x + offset[0], y: anchor.y + offset[1]}});
    });

    const mapRect = container.getBoundingClientRect();
    container.querySelectorAll(".leaflet-control").forEach(function (element) {
      const rect = element.getBoundingClientRect();
      obstacles.push({left: rect.left - mapRect.left, right: rect.right - mapRect.left,
        top: rect.top - mapRect.top, bottom: rect.bottom - mapRect.top});
    });
    const placement = RecordingMapLayout.place(visible, obstacles, size.x, size.y, radius);
    if (!placement && radius > 19) {
      layoutConferenceLogos(radius - 4);
      return;
    }
    if (!placement) return;
    placement.forEach(function (entry) {
      const conference = conferences[entry.id];
      conference.leader.setLatLngs([
        conference.location.coordinates,
        map.containerPointToLatLng(entry.elbow),
        map.containerPointToLatLng(entry.end)
      ]);
      conference.marker.setLatLng(map.containerPointToLatLng(entry.point));
      if (!map.hasLayer(conference.layers)) conference.layers.addTo(map);
    });
  }

  let layoutFrame;
  function scheduleConferenceLayout() {
    if (layoutFrame) cancelAnimationFrame(layoutFrame);
    layoutFrame = requestAnimationFrame(function () {
      layoutFrame = null;
      layoutConferenceLogos();
    });
  }
  map.on("moveend resize", scheduleConferenceLayout);

  function showView(view) {
    map.closePopup();
    const locations = data.locations.filter(function (location) {
      return view === "world" || location.region === view;
    });
    const bounds = L.latLngBounds(locations.map(function (location) { return location.coordinates; }));
    map.fitBounds(bounds, {
      padding: [32, 32],
      maxZoom: view === "australia" ? 5 : view === "world" ? 2.5 : 5,
      animate: false
    });
    panel.querySelectorAll("[data-map-view]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.mapView === view));
    });
    panel.querySelectorAll("[data-map-country]").forEach(function (button) {
      button.setAttribute("aria-pressed", "false");
    });
  }

  panel.querySelectorAll("[data-map-view]").forEach(function (button) {
    button.addEventListener("click", function () { showView(button.dataset.mapView); });
  });
  panel.querySelectorAll("[data-map-country]").forEach(function (button) {
    button.addEventListener("click", function () {
      const country = countryLayers.get(button.dataset.mapCountry);
      map.closePopup();
      map.fitBounds(country.layer.getBounds(), {padding: [32, 32], maxZoom: 5, animate: false});
      country.layer.openPopup(L.latLng(country.locations[0].coordinates));
      panel.querySelectorAll("[data-map-view]").forEach(function (view) {
        view.setAttribute("aria-pressed", "false");
      });
      panel.querySelectorAll("[data-map-country]").forEach(function (flag) {
        flag.setAttribute("aria-pressed", String(flag === button));
      });
    });
  });
  panel.querySelector(".recording-map-views").hidden = false;
  panel.querySelector(".recording-map-caption").hidden = false;
  panel.querySelector(".recording-map-flags").hidden = false;
  document.getElementById("recording-map-fallback").hidden = true;
  showView("world");
})();
