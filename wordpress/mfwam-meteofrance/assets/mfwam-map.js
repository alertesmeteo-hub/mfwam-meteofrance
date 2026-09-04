(function () {
    "use strict";

    var STALE_THRESHOLD_MS = 8 * 60 * 60 * 1000;
    var ZOOM_MIN = 1;
    var ZOOM_MAX = 4;
    var ZOOM_STEP = 0.25;

    function qs(root, selector) {
        return root.querySelector(selector);
    }

    function formatValidity(isoString, timezone) {
        try {
            var date = new Date(isoString);
            return new Intl.DateTimeFormat("fr-FR", {
                weekday: "short",
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
                timeZone: timezone || undefined,
            }).format(date);
        } catch (error) {
            return isoString;
        }
    }

    function formatRun(isoString, timezone) {
        try {
            var date = new Date(isoString);
            return new Intl.DateTimeFormat("fr-FR", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
                timeZone: timezone || undefined,
            }).format(date) + " UTC".replace("UTC", "");
        } catch (error) {
            return isoString;
        }
    }

    function buildLegend(container, layer) {
        container.innerHTML = "";
        if (!layer || !layer.stops || !layer.stops.length) {
            return;
        }
        var bar = document.createElement("div");
        bar.className = "mfwm-legend-bar";
        var stops = layer.stops;
        var gradientStops = [];
        var minValue = stops[0].value;
        var maxValue = stops[stops.length - 1].value;
        var span = maxValue - minValue || 1;
        stops.forEach(function (stop) {
            var pct = ((stop.value - minValue) / span) * 100;
            gradientStops.push(stop.color + " " + pct.toFixed(1) + "%");
        });
        bar.style.background = "linear-gradient(90deg, " + gradientStops.join(", ") + ")";
        container.appendChild(bar);

        var labels = document.createElement("div");
        labels.className = "mfwm-legend-labels";
        var labelStops = stops.filter(function (_stop, index) {
            return index === 0 || index === stops.length - 1 || index % Math.ceil(stops.length / 5) === 0;
        });
        labelStops.forEach(function (stop) {
            var span = document.createElement("span");
            span.textContent = stop.value + (layer.unit ? " " + layer.unit : "");
            labels.appendChild(span);
        });
        container.appendChild(labels);

        var title = document.createElement("strong");
        title.className = "mfwm-legend-title";
        title.textContent = layer.label + (layer.unit ? " (" + layer.unit + ")" : "");
        container.insertBefore(title, bar);
    }

    function initApp(root) {
        var baseUrl = root.getAttribute("data-base-url");
        var timezone = root.getAttribute("data-timezone");
        var animationEnabled = root.getAttribute("data-animation") === "1";
        var currentLayer = root.getAttribute("data-variable") || null;

        var loading = qs(root, "[data-mfwm-loading]");
        var errorBox = qs(root, "[data-mfwm-error]");
        var background = qs(root, "[data-mfwm-background]");
        var overlay = qs(root, "[data-mfwm-overlay]");
        var layerImage = qs(root, "[data-mfwm-layer-image]");
        var scene = qs(root, "[data-mfwm-scene]");
        var viewport = qs(root, "[data-mfwm-viewport]");
        var slider = qs(root, "[data-mfwm-slider]");
        var runLabel = qs(root, "[data-mfwm-run]");
        var validityLabel = qs(root, "[data-mfwm-validity]");
        var leadLabel = qs(root, "[data-mfwm-lead]");
        var mapRunLabel = qs(root, "[data-mfwm-map-run]");
        var mapDateLabel = qs(root, "[data-mfwm-map-date]");
        var generatedLabel = qs(root, "[data-mfwm-generated]");
        var staleBanner = qs(root, "[data-mfwm-stale]");
        var legend = qs(root, "[data-mfwm-legend]");
        var currentLayerLabel = qs(root, "[data-mfwm-current-layer]");
        var layerMenu = qs(root, "[data-mfwm-layer-menu]");
        var layerGrid = qs(root, "[data-mfwm-layer-grid]");
        var menuToggle = qs(root, "[data-mfwm-menu-toggle]");
        var menuClose = qs(root, "[data-mfwm-menu-close]");
        var playButton = qs(root, "[data-mfwm-play]");
        var previousButton = qs(root, "[data-mfwm-previous]");
        var nextButton = qs(root, "[data-mfwm-next]");
        var zoomInButton = qs(root, "[data-mfwm-zoom-in]");
        var zoomOutButton = qs(root, "[data-mfwm-zoom-out]");
        var resetButton = qs(root, "[data-mfwm-reset]");
        var fullscreenButton = qs(root, "[data-mfwm-fullscreen]");
        var zoomLevelLabel = qs(root, "[data-mfwm-zoom-level]");

        var manifest = null;
        var model = null;
        var stepIndex = 0;
        var playing = false;
        var playTimer = null;
        var zoom = 1;
        var panX = 0;
        var panY = 0;

        function showError(message) {
            loading.hidden = true;
            errorBox.hidden = false;
            errorBox.textContent = message;
        }

        function applyTransform() {
            scene.style.transform = "translate(" + panX + "px, " + panY + "px) scale(" + zoom + ")";
            zoomLevelLabel.textContent = Math.round(zoom * 100) + " %";
        }

        function setZoom(next) {
            zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
            if (zoom === ZOOM_MIN) {
                panX = 0;
                panY = 0;
            }
            applyTransform();
        }

        function updateStep() {
            if (!manifest || !manifest.steps.length) {
                return;
            }
            stepIndex = Math.min(Math.max(stepIndex, 0), manifest.steps.length - 1);
            var step = manifest.steps[stepIndex];
            slider.value = String(stepIndex);
            var files = step.files || {};
            var url = files[currentLayer];
            if (url) {
                layerImage.src = baseUrl + "/" + url;
            }
            var validity = formatValidity(step.valid_time, timezone);
            validityLabel.textContent = validity;
            leadLabel.textContent = "+" + step.lead_hour + " h";
            mapDateLabel.textContent = "Échéance " + validity;
        }

        function selectLayer(key) {
            if (!manifest || !manifest.layers[key]) {
                return;
            }
            currentLayer = key;
            var layer = manifest.layers[key];
            currentLayerLabel.textContent = layer.label;
            buildLegend(legend, layer);
            updateStep();
            var buttons = layerGrid.querySelectorAll("[data-mfwm-layer-option]");
            buttons.forEach(function (button) {
                button.classList.toggle(
                    "is-active",
                    button.getAttribute("data-mfwm-layer-option") === key
                );
            });
        }

        function buildLayerMenu() {
            layerGrid.innerHTML = "";
            var groups = {};
            Object.keys(manifest.layers).forEach(function (key) {
                var layer = manifest.layers[key];
                var group = layer.group || "Autres";
                groups[group] = groups[group] || [];
                groups[group].push(key);
            });
            Object.keys(groups).forEach(function (groupName) {
                var groupTitle = document.createElement("h4");
                groupTitle.className = "mfwm-layer-group-title";
                groupTitle.textContent = groupName;
                layerGrid.appendChild(groupTitle);
                var row = document.createElement("div");
                row.className = "mfwm-layer-group-row";
                groups[groupName].forEach(function (key) {
                    var layer = manifest.layers[key];
                    var button = document.createElement("button");
                    button.type = "button";
                    button.className = "mfwm-layer-option";
                    button.setAttribute("data-mfwm-layer-option", key);
                    button.textContent = layer.label;
                    button.addEventListener("click", function () {
                        selectLayer(key);
                        layerMenu.hidden = true;
                        menuToggle.setAttribute("aria-expanded", "false");
                    });
                    row.appendChild(button);
                });
                layerGrid.appendChild(row);
            });
        }

        function checkStale() {
            if (!model || !model.generated_at) {
                return;
            }
            var age = Date.now() - new Date(model.generated_at).getTime();
            staleBanner.hidden = age <= STALE_THRESHOLD_MS;
            if (staleBanner.hidden) {
                return;
            }
            if (typeof window.MFW_AUTOHEAL !== "undefined" && window.MFW_AUTOHEAL.url) {
                fetch(window.MFW_AUTOHEAL.url, { credentials: "same-origin" }).catch(function () {});
            }
        }

        function stopPlayback() {
            playing = false;
            playButton.textContent = "▶";
            playButton.setAttribute("aria-label", "Lancer l’animation");
            if (playTimer) {
                clearInterval(playTimer);
                playTimer = null;
            }
        }

        function startPlayback() {
            playing = true;
            playButton.textContent = "❚❚";
            playButton.setAttribute("aria-label", "Mettre en pause l’animation");
            playTimer = setInterval(function () {
                stepIndex = (stepIndex + 1) % manifest.steps.length;
                updateStep();
            }, 700);
        }

        function load() {
            Promise.all([
                fetch(baseUrl + "/index.json", { cache: "no-store" }).then(function (response) {
                    return response.json();
                }),
                fetch(baseUrl + "/maps/index.json", { cache: "no-store" }).then(function (response) {
                    return response.json();
                }),
            ])
                .then(function (results) {
                    model = results[0].model || {};
                    manifest = results[1];
                    if (!manifest || manifest.status !== "ok" || !manifest.steps || !manifest.steps.length) {
                        throw new Error("Données MFWAM indisponibles pour le moment.");
                    }

                    background.src = baseUrl + "/" + manifest.background;
                    overlay.src = baseUrl + "/" + manifest.overlay;
                    slider.max = String(manifest.steps.length - 1);
                    slider.value = "0";

                    if (!currentLayer || !manifest.layers[currentLayer]) {
                        currentLayer = Object.keys(manifest.layers)[0];
                    }

                    buildLayerMenu();
                    selectLayer(currentLayer);

                    var runText = formatRun(model.run_time, timezone);
                    runLabel.textContent = "Dernier run MFWAM : " + runText + " UTC";
                    mapRunLabel.textContent = "Run MFWAM " + runText + " UTC";
                    generatedLabel.textContent =
                        "Cartes générées : " + formatRun(results[0].generated_at, timezone) + " UTC";

                    checkStale();
                    loading.hidden = true;
                })
                .catch(function (error) {
                    showError(
                        error && error.message
                            ? error.message
                            : "Impossible de charger les cartes MFWAM."
                    );
                });
        }

        slider.addEventListener("input", function () {
            stopPlayback();
            stepIndex = parseInt(slider.value, 10) || 0;
            updateStep();
        });
        previousButton.addEventListener("click", function () {
            stopPlayback();
            stepIndex = Math.max(0, stepIndex - 1);
            updateStep();
        });
        nextButton.addEventListener("click", function () {
            stopPlayback();
            if (manifest) {
                stepIndex = Math.min(manifest.steps.length - 1, stepIndex + 1);
                updateStep();
            }
        });
        playButton.addEventListener("click", function () {
            if (!animationEnabled || !manifest) {
                return;
            }
            if (playing) {
                stopPlayback();
            } else {
                startPlayback();
            }
        });
        menuToggle.addEventListener("click", function () {
            var expanded = menuToggle.getAttribute("aria-expanded") === "true";
            layerMenu.hidden = expanded;
            menuToggle.setAttribute("aria-expanded", expanded ? "false" : "true");
        });
        menuClose.addEventListener("click", function () {
            layerMenu.hidden = true;
            menuToggle.setAttribute("aria-expanded", "false");
        });
        zoomInButton.addEventListener("click", function () {
            setZoom(zoom + ZOOM_STEP);
        });
        zoomOutButton.addEventListener("click", function () {
            setZoom(zoom - ZOOM_STEP);
        });
        resetButton.addEventListener("click", function () {
            setZoom(1);
        });
        fullscreenButton.addEventListener("click", function () {
            if (viewport.requestFullscreen) {
                viewport.requestFullscreen();
            }
        });

        var dragging = false;
        var dragStartX = 0;
        var dragStartY = 0;
        var panStartX = 0;
        var panStartY = 0;
        viewport.addEventListener("pointerdown", function (event) {
            if (zoom <= 1) {
                return;
            }
            dragging = true;
            dragStartX = event.clientX;
            dragStartY = event.clientY;
            panStartX = panX;
            panStartY = panY;
            viewport.setPointerCapture(event.pointerId);
        });
        viewport.addEventListener("pointermove", function (event) {
            if (!dragging) {
                return;
            }
            panX = panStartX + (event.clientX - dragStartX);
            panY = panStartY + (event.clientY - dragStartY);
            applyTransform();
        });
        viewport.addEventListener("pointerup", function () {
            dragging = false;
        });
        viewport.addEventListener("wheel", function (event) {
            event.preventDefault();
            setZoom(zoom + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP));
        }, { passive: false });

        load();
    }

    function init() {
        var apps = document.querySelectorAll("[data-mfwm-app]");
        apps.forEach(function (root) {
            initApp(root);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
