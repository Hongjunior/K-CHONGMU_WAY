var FP_ICON_SVG = {
    shuttle_stop:
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="12" rx="2"></rect><circle cx="7.5" cy="18" r="1.5"></circle><circle cx="16.5" cy="18" r="1.5"></circle><line x1="3" y1="11" x2="21" y2="11"></line></svg>',
    entrance_auth:
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"></rect><line x1="3" y1="10" x2="21" y2="10"></line><line x1="7" y1="15" x2="11" y2="15"></line></svg>',
};

document.addEventListener("DOMContentLoaded", function () {
    var dataEl = document.getElementById("worksite-map-data");
    var input = document.getElementById("facility_id_input");
    var buildingsEl = document.getElementById("fp-buildings");
    var floorsEl = document.getElementById("fp-floors");
    var canvasEl = document.getElementById("fp-canvas");
    var selectedEl = document.getElementById("fp-selected");
    var hoursEl = document.getElementById("fp-hours");
    var clearBtn = document.getElementById("fp-clear");

    if (!dataEl || !input || !buildingsEl || !floorsEl || !canvasEl) {
        return;
    }

    function formatHours(fac) {
        if (!fac.operating_hours_open || !fac.operating_hours_close) return "운영시간: 상시";
        return "운영시간: " + fac.operating_hours_open + " ~ " + fac.operating_hours_close;
    }

    var worksiteMap = [];
    try {
        worksiteMap = JSON.parse(dataEl.textContent || "[]");
    } catch (e) {
        worksiteMap = [];
    }

    var currentBuildingId = null;
    var currentFloorId = null;

    function findFacility(id) {
        for (var bi = 0; bi < worksiteMap.length; bi++) {
            var b = worksiteMap[bi];
            for (var fi = 0; fi < b.floors.length; fi++) {
                var f = b.floors[fi];
                for (var ci = 0; ci < f.facilities.length; ci++) {
                    var fac = f.facilities[ci];
                    if (String(fac.id) === String(id)) {
                        return { building: b, floor: f, facility: fac };
                    }
                }
            }
        }
        return null;
    }

    function getBuilding(id) {
        for (var i = 0; i < worksiteMap.length; i++) {
            if (worksiteMap[i].id === id) return worksiteMap[i];
        }
        return null;
    }

    function renderBuildings() {
        buildingsEl.innerHTML = "";
        worksiteMap.forEach(function (b) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "fp-chip" + (b.id === currentBuildingId ? " active" : "");
            btn.textContent = b.name;
            btn.addEventListener("click", function () {
                currentBuildingId = b.id;
                currentFloorId = b.floors.length ? b.floors[0].id : null;
                renderBuildings();
                renderFloors();
                renderCanvas();
            });
            buildingsEl.appendChild(btn);
        });
        if (!worksiteMap.length) {
            buildingsEl.innerHTML = '<span class="field-hint">이 사업장에 등록된 건물이 없습니다.</span>';
        }
    }

    function renderFloors() {
        floorsEl.innerHTML = "";
        var building = getBuilding(currentBuildingId);
        if (!building) return;
        building.floors.forEach(function (f) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "fp-chip" + (f.id === currentFloorId ? " active" : "");
            btn.textContent = f.label;
            btn.addEventListener("click", function () {
                currentFloorId = f.id;
                renderFloors();
                renderCanvas();
            });
            floorsEl.appendChild(btn);
        });
    }

    function renderCanvas() {
        canvasEl.innerHTML = "";
        var building = getBuilding(currentBuildingId);
        if (!building) return;
        var floor = null;
        for (var i = 0; i < building.floors.length; i++) {
            if (building.floors[i].id === currentFloorId) {
                floor = building.floors[i];
                break;
            }
        }
        if (!floor) return;

        if (!floor.facilities.length) {
            var empty = document.createElement("p");
            empty.className = "empty-state";
            empty.textContent = "이 층에 등록된 시설이 없습니다.";
            canvasEl.appendChild(empty);
            return;
        }

        floor.facilities.forEach(function (fac) {
            var isNonSelectable = fac.facility_type === "shuttle_stop" || fac.facility_type === "entrance_auth";
            var block = document.createElement(isNonSelectable ? "div" : "button");
            if (!isNonSelectable) block.type = "button";
            var isSelected = String(fac.id) === String(input.value);

            if (isNonSelectable) {
                block.className = "map-marker marker-facility marker-icon fp-room-info marker-" + fac.facility_type;
                block.style.left = fac.pos_x + "%";
                block.style.top = fac.pos_y + "%";
                block.title = fac.name + " (일정 위치로 선택할 수 없는 안내용 지점입니다)";
                block.innerHTML =
                    '<span class="marker-dot">' + FP_ICON_SVG[fac.facility_type] + "</span>" +
                    '<span class="marker-label">' + fac.name + "</span>";
                canvasEl.appendChild(block);
                return;
            }

            block.className = "room-block fp-room room-" + fac.facility_type + (isSelected ? " selected" : "");
            block.style.left = fac.pos_x + "%";
            block.style.top = fac.pos_y + "%";
            block.style.width = fac.shape_w + "%";
            block.style.height = fac.shape_h + "%";
            block.textContent = fac.name;
            block.addEventListener("click", function () {
                input.value = fac.id;
                selectedEl.textContent = "선택됨: " + fac.name;
                if (hoursEl) hoursEl.textContent = formatHours(fac);
                renderCanvas();
            });
            canvasEl.appendChild(block);
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener("click", function () {
            input.value = "";
            selectedEl.textContent = "선택된 장소 없음";
            if (hoursEl) hoursEl.textContent = "";
            renderCanvas();
        });
    }

    var existing = input.value ? findFacility(input.value) : null;
    if (existing) {
        currentBuildingId = existing.building.id;
        currentFloorId = existing.floor.id;
        selectedEl.textContent = "선택됨: " + existing.facility.name;
        if (hoursEl) hoursEl.textContent = formatHours(existing.facility);
    } else if (worksiteMap.length) {
        currentBuildingId = worksiteMap[0].id;
        currentFloorId = worksiteMap[0].floors.length ? worksiteMap[0].floors[0].id : null;
    }

    renderBuildings();
    renderFloors();
    renderCanvas();
});
