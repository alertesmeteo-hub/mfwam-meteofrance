(function () {
    "use strict";

    var STALE_THRESHOLD_MS = 8 * 60 * 60 * 1000;
    var ZOOM_MIN = 1;
    var ZOOM_MAX = 8;
    var ZOOM_STEP = 0.25;

    function hexToRgb(hex) {
        var clean = hex.replace("#", "");
        return [
            parseInt(clean.substring(0, 2), 16),
            parseInt(clean.substring(2, 4), 16),
            parseInt(clean.substring(4, 6), 16),
        ];
    }

    // Reconstruit une valeur approximative à partir de la couleur du pixel
    // survolé et des points de la légende (aucune grille numérique publiée
    // par le pipeline : on inverse le dégradé déjà envoyé dans le manifeste).
    function valueFromColor(rgb, stops) {
        var best = null;
        for (var i = 0; i < stops.length - 1; i += 1) {
            var a = hexToRgb(stops[i].color);
            var b = hexToRgb(stops[i + 1].color);
            var abx = b[0] - a[0];
            var aby = b[1] - a[1];
            var abz = b[2] - a[2];
            var lengthSquared = abx * abx + aby * aby + abz * abz;
            var t = 0;
            if (lengthSquared > 0) {
                t =
                    ((rgb[0] - a[0]) * abx + (rgb[1] - a[1]) * aby + (rgb[2] - a[2]) * abz) /
                    lengthSquared;
                t = Math.min(1, Math.max(0, t));
            }
            var projected = [a[0] + abx * t, a[1] + aby * t, a[2] + abz * t];
            var dx = rgb[0] - projected[0];
            var dy = rgb[1] - projected[1];
            var dz = rgb[2] - projected[2];
            var distance = dx * dx + dy * dy + dz * dz;
            if (best === null || distance < best.distance) {
                best = {
                    distance: distance,
                    value: stops[i].value + (stops[i + 1].value - stops[i].value) * t,
                };
            }
        }
        return best ? best.value : null;
    }

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
        var probe = qs(root, "[data-mfwm-probe]");

        var manifest = null;
        var model = null;
        var stepIndex = 0;
        var playing = false;
        var playTimer = null;
        var zoom = 1;
        var panX = 0;
        var panY = 0;
        var probeCanvas = document.createElement("canvas");
        var probeContext = probeCanvas.getContext("2d", { willReadFrequently: true });
        var probeReady = false;

        layerImage.crossOrigin = "anonymous";
        layerImage.addEventListener("load", function () {
            try {
                probeCanvas.width = layerImage.naturalWidth;
                probeCanvas.height = layerImage.naturalHeight;
                probeContext.drawImage(layerImage, 0, 0);
                probeReady = true;
            } catch (error) {
                probeReady = false;
            }
        });
        layerImage.addEventListener("error", function () {
            probeReady = false;
        });

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

        viewport.addEventListener("mousemove", function (event) {
            if (!manifest || !probeReady || !currentLayer) {
                probe.hidden = true;
                return;
            }
            var rect = layerImage.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) {
                probe.hidden = true;
                return;
            }
            var px = event.clientX - rect.left;
            var py = event.clientY - rect.top;
            if (px < 0 || py < 0 || px > rect.width || py > rect.height) {
                probe.hidden = true;
                return;
            }
            var naturalWidth = probeCanvas.width;
            var naturalHeight = probeCanvas.height;
            var coverScale = Math.max(rect.width / naturalWidth, rect.height / naturalHeight);
            var displayedWidth = naturalWidth * coverScale;
            var displayedHeight = naturalHeight * coverScale;
            var offsetX = (displayedWidth - rect.width) / 2;
            var offsetY = (displayedHeight - rect.height) / 2;
            var sourceX = Math.round((px + offsetX) / coverScale);
            var sourceY = Math.round((py + offsetY) / coverScale);
            if (sourceX < 0 || sourceY < 0 || sourceX >= naturalWidth || sourceY >= naturalHeight) {
                probe.hidden = true;
                return;
            }

            var pixel;
            try {
                pixel = probeContext.getImageData(sourceX, sourceY, 1, 1).data;
            } catch (error) {
                probe.hidden = true;
                return;
            }
            if (pixel[3] < 40) {
                probe.hidden = false;
                probe.style.left = px + "px";
                probe.style.top = py + "px";
                probe.textContent = "Hors zone / pas de données";
                return;
            }

            var layer = manifest.layers[currentLayer];
            var value = valueFromColor([pixel[0], pixel[1], pixel[2]], layer.stops);
            if (value === null) {
                probe.hidden = true;
                return;
            }
            probe.hidden = false;
            probe.style.left = px + "px";
            probe.style.top = py + "px";
            probe.textContent =
                value.toFixed(layer.decimals || 1) + (layer.unit ? " " + layer.unit : "") +
                " · " + layer.label;
        });
        viewport.addEventListener("mouseleave", function () {
            probe.hidden = true;
        });

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
