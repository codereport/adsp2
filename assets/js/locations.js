(function () {
  "use strict";

  const container = document.getElementById("recording-map");
  const dataElement = document.getElementById("recording-map-data");
  if (!container || !dataElement || !window.L || !window.RecordingMapLayout) return;

  const data = JSON.parse(dataElement.textContent);
  const panel = container.closest(".recording-map-panel");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const logoBase = container.dataset.logoBase;
  const countryBase = container.dataset.countryBase;
  const flagBase = container.dataset.flagBase;
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
  map.createPane("recordingRoutes").style.zIndex = 410;
  map.createPane("recordingLeaders").style.zIndex = 430;

  function episodeLinks(numbers) {
    const links = document.createElement("div");
    links.className = "recording-map-episode-links";
    numbers.forEach(function (number) {
      const episode = data.episodes[number];
      if (!episode) return;
      const link = document.createElement("a");
      link.href = episode.url;
      link.textContent = "Ep. " + number;
      link.title = episode.title;
      link.setAttribute("aria-label", episode.title);
      links.appendChild(link);
    });
    return links;
  }

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
      section.appendChild(episodeLinks(venue.episodes));
      content.appendChild(section);
    });
    return content;
  }

  // Keep neighboring recording countries distinct, especially along the road trip.
  const countryColors = {
    AUS: "#d9894b", AUT: "#9b78c6", CAN: "#dfaa40", HRV: "#ce718c",
    DNK: "#d9894b", ITA: "#dfaa40", NLD: "#9b78c6", NOR: "#48a897",
    POL: "#4f91c4", SVN: "#48a897", ESP: "#ce718c", GBR: "#4f91c4", USA: "#4f91c4"
  };

  function addCountryFlag(layer, code) {
    const element = layer.getElement();
    const svg = element.ownerSVGElement;
    const namespace = "http://www.w3.org/2000/svg";
    let definitions = svg.querySelector("defs");
    if (!definitions) {
      definitions = document.createElementNS(namespace, "defs");
      svg.insertBefore(definitions, svg.firstChild);
    }
    const id = container.id + "-flag-" + code;
    if (!svg.querySelector("#" + id)) {
      const pattern = document.createElementNS(namespace, "pattern");
      pattern.id = id;
      pattern.setAttribute("patternUnits", "objectBoundingBox");
      pattern.setAttribute("patternContentUnits", "objectBoundingBox");
      pattern.setAttribute("width", "1");
      pattern.setAttribute("height", "1");
      const background = document.createElementNS(namespace, "rect");
      background.setAttribute("width", "1");
      background.setAttribute("height", "1");
      background.setAttribute("fill", countryColors[code]);
      pattern.appendChild(background);
      const flag = document.createElementNS(namespace, "image");
      flag.setAttribute("href", flagBase + code + ".svg");
      flag.setAttribute("width", "1");
      flag.setAttribute("height", "1");
      flag.setAttribute("preserveAspectRatio", "none");
      pattern.appendChild(flag);
      definitions.appendChild(pattern);
    }
    element.style.setProperty("--country-flag", 'url("#' + id + '")');
  }

  const countryLayers = new Map();
  const countries = L.geoJSON(data.countries, {
    smoothFactor: 0.3,
    style: function (feature) {
      const color = countryColors[feature.properties.code];
      return {
        className: "recording-country",
        color: color, weight: 1,
        fillColor: color, fillOpacity: 0.42
      };
    },
    onEachFeature: function (feature, layer) {
      const country = feature.properties.country;
      const locations = data.locations.filter(function (location) { return location.country === country; });
      countryLayers.set(feature.properties.code, {
        layer: layer, locations: locations, bounds: layer.getBounds(),
        overview: feature.geometry, detail: null, loading: false
      });
      const content = document.createElement("div");
      locations.forEach(function (location) { content.appendChild(popup(location)); });
      layer.bindTooltip(country, {sticky: true});
      layer.bindPopup(content, {maxWidth: 290, minWidth: 210, maxHeight: 280});
      layer.on("add", function () {
        addCountryFlag(layer, feature.properties.code);
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

  function setCountryGeometry(country, geometry) {
    const depth = geometry.type === "MultiPolygon" ? 2 : 1;
    country.layer.setLatLngs(L.GeoJSON.coordsToLatLngs(geometry.coordinates, depth));
  }

  function updateCountryDetail() {
    const detailed = map.getZoom() >= 5;
    const bounds = map.getBounds();
    countryLayers.forEach(function (country, code) {
      if (!detailed) {
        if (country.showingDetail) {
          setCountryGeometry(country, country.overview);
          country.showingDetail = false;
        }
        return;
      }
      if (!bounds.intersects(country.bounds)) return;
      if (country.detail) {
        if (!country.showingDetail) {
          setCountryGeometry(country, country.detail);
          country.showingDetail = true;
        }
        return;
      }
      if (country.loading) return;
      country.loading = true;
      // Keep the small world outlines until each visible country's detail is ready.
      fetch(countryBase + code + ".geojson")
        .then(function (response) {
          if (!response.ok) throw new Error("Country outline unavailable");
          return response.json();
        })
        .then(function (feature) {
          country.detail = feature.geometry;
          if (feature.properties.attributions) {
            feature.properties.attributions.forEach(function (attribution) {
              map.attributionControl.addAttribution(attribution);
            });
            scheduleConferenceLayout();
          }
          if (map.getZoom() >= 5) {
            setCountryGeometry(country, country.detail);
            country.showingDetail = true;
          }
        })
        .catch(function () { /* The overview remains available if a download fails. */ })
        .finally(function () { country.loading = false; });
    });
  }
  map.on("moveend", updateCountryDetail);

  const travelModes = {
    drive: {label: "Driving", dash: null},
    flight: {label: "Flight", dash: "9 7"},
    train: {label: "Train", dash: "2 6"}
  };
  const routeLayers = new Map();
  function routePopup(route, segment) {
    const content = document.createElement("div");
    content.className = "recording-map-popup recording-route-popup";
    const title = document.createElement("strong");
    title.className = "recording-map-popup-title";
    title.textContent = route.name;
    content.appendChild(title);
    const leg = document.createElement("p");
    leg.className = "recording-route-leg";
    leg.textContent = travelModes[segment.mode].label + " · " +
      route.stops[segment.from].name + " → " + route.stops[segment.to].name;
    content.appendChild(leg);
    const stops = document.createElement("ol");
    route.stops.forEach(function (stop) {
      const item = document.createElement("li");
      item.textContent = stop.name;
      stops.appendChild(item);
    });
    content.appendChild(stops);
    const note = document.createElement("p");
    note.className = "recording-map-popup-note";
    note.textContent = route.note;
    content.appendChild(note);
    content.appendChild(episodeLinks(route.episodes));
    return content;
  }
  (data.routes || []).forEach(function (route) {
    const layer = L.featureGroup().addTo(map);
    route.segments.forEach(function (segment) {
      const mode = travelModes[segment.mode];
      L.polyline(segment.coordinates, {
        pane: "recordingRoutes", color: "#20333d", weight: 7, opacity: 0.5,
        dashArray: mode.dash, interactive: false, className: "recording-route-casing"
      }).addTo(layer);
      const path = L.polyline(segment.coordinates, {
        pane: "recordingRoutes", color: route.color, weight: 3.5, opacity: 1,
        dashArray: mode.dash, className: "recording-route recording-route-" + segment.mode
      }).addTo(layer);
      const label = route.name + ": " + mode.label + " · " +
        route.stops[segment.from].name + " → " + route.stops[segment.to].name;
      path.bindTooltip(label, {sticky: true});
      path.bindPopup(routePopup(route, segment), {maxWidth: 300, minWidth: 230, maxHeight: 310});
      path.on("add", function () {
        const element = path.getElement();
        element.setAttribute("tabindex", "0");
        element.setAttribute("role", "button");
        element.setAttribute("aria-label", label);
        L.DomEvent.on(element, "keydown", function (event) {
          if (event.key === "Enter" || event.key === " ") {
            L.DomEvent.preventDefault(event);
            path.openPopup(L.latLng(segment.coordinates[Math.floor(segment.coordinates.length / 2)]));
          }
        });
      });
    });
    routeLayers.set(route.id, layer);
  });

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
      pane: "recordingLeaders",
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
    const route = routeLayers.get(view);
    const locations = data.locations.filter(function (location) {
      return view === "world" || location.region === view;
    });
    const bounds = route ? route.getBounds() :
      L.latLngBounds(locations.map(function (location) { return location.coordinates; }));
    map.fitBounds(bounds, {
      padding: [32, 32],
      maxZoom: route ? 9 : view === "world" ? 2.5 : 5,
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
  const flagToggle = panel.querySelector("[data-map-flags-toggle]");
  flagToggle.addEventListener("click", function () {
    const enabled = container.classList.toggle("recording-map-show-flags");
    flagToggle.setAttribute("aria-pressed", String(enabled));
  });
  panel.querySelectorAll("[data-map-country]").forEach(function (button) {
    button.addEventListener("click", function () {
      const country = countryLayers.get(button.dataset.mapCountry);
      map.closePopup();
      map.fitBounds(country.bounds, {padding: [32, 32], maxZoom: 5, animate: false});
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
  panel.querySelector(".recording-map-travel-key").hidden = false;
  document.getElementById("recording-map-fallback").hidden = true;
  showView("world");
})();
