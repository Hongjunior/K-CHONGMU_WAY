document.addEventListener("DOMContentLoaded", function () {
    var MIN_SCALE = 1;
    var MAX_SCALE = 3;
    var DRAG_THRESHOLD = 4;

    // .fp-canvas (the compact in-form facility picker) redraws its own contents
    // via facility_picker.js's own innerHTML resets, which would wipe out and
    // desync the zoom wrapper below — it doesn't need pan/zoom anyway, so skip it.
    document.querySelectorAll(".map-canvas:not(.fp-canvas)").forEach(setupZoom);

    function setupZoom(canvas) {
        if (canvas.dataset.zoomReady) return;
        canvas.dataset.zoomReady = "1";

        var computed = window.getComputedStyle(canvas);
        var bgImage = computed.backgroundImage;
        var bgSize = computed.backgroundSize;
        var bgPosition = computed.backgroundPosition;

        var inner = document.createElement("div");
        inner.className = "map-zoom-inner";
        inner.style.backgroundImage = bgImage;
        inner.style.backgroundSize = bgSize;
        inner.style.backgroundPosition = bgPosition;
        canvas.style.backgroundImage = "none";

        while (canvas.firstChild) {
            inner.appendChild(canvas.firstChild);
        }
        canvas.appendChild(inner);

        var controls = document.createElement("div");
        controls.className = "map-zoom-controls";
        controls.innerHTML =
            '<button type="button" class="map-zoom-btn" data-action="in">+</button>' +
            '<button type="button" class="map-zoom-btn" data-action="out">−</button>' +
            '<button type="button" class="map-zoom-btn" data-action="reset">⟲</button>';
        canvas.appendChild(controls);

        var state = { scale: 1, x: 0, y: 0 };

        function clamp() {
            var rect = canvas.getBoundingClientRect();
            var maxX = (rect.width * (state.scale - 1)) / 2;
            var maxY = (rect.height * (state.scale - 1)) / 2;
            state.x = Math.max(-maxX, Math.min(maxX, state.x));
            state.y = Math.max(-maxY, Math.min(maxY, state.y));
        }

        function apply() {
            clamp();
            inner.style.transform =
                "translate(" + state.x + "px, " + state.y + "px) scale(" + state.scale + ")";
        }

        function setScale(newScale) {
            state.scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
            apply();
        }

        controls.addEventListener("click", function (e) {
            var action = e.target.dataset.action;
            if (!action) return;
            if (action === "in") setScale(state.scale + 0.4);
            if (action === "out") setScale(state.scale - 0.4);
            if (action === "reset") {
                state.scale = 1;
                state.x = 0;
                state.y = 0;
                apply();
            }
        });

        canvas.addEventListener(
            "wheel",
            function (e) {
                e.preventDefault();
                setScale(state.scale + (e.deltaY < 0 ? 0.2 : -0.2));
            },
            { passive: false }
        );

        var dragging = false;
        var dragged = false;
        var startX, startY, startStateX, startStateY;

        canvas.addEventListener("mousedown", function (e) {
            if (e.target.closest(".map-zoom-controls")) return;
            dragging = true;
            dragged = false;
            startX = e.clientX;
            startY = e.clientY;
            startStateX = state.x;
            startStateY = state.y;
        });

        window.addEventListener("mousemove", function (e) {
            if (!dragging) return;
            var dx = e.clientX - startX;
            var dy = e.clientY - startY;
            if (!dragged && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
                dragged = true;
            }
            if (dragged) {
                state.x = startStateX + dx;
                state.y = startStateY + dy;
                apply();
            }
        });

        window.addEventListener("mouseup", function () {
            if (!dragging) return;
            dragging = false;
            if (dragged) {
                var suppressClick = function (e) {
                    e.stopPropagation();
                    e.preventDefault();
                    document.removeEventListener("click", suppressClick, true);
                };
                document.addEventListener("click", suppressClick, true);
            }
        });
    }
});
