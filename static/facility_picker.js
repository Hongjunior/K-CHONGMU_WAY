document.addEventListener("DOMContentLoaded", function () {
    var dataEl = document.getElementById("worksite-map-data");
    var input = document.getElementById("facility_id_input");
    var buildingsEl = document.getElementById("fp-buildings");
    var floorsEl = document.getElementById("fp-floors");
    var canvasEl = document.getElementById("fp-canvas");
    var selectedEl = document.getElementById("fp-selected");
    var clearBtn = document.getElementById("fp-clear");

    if (!dataEl || !input || !buildingsEl || !floorsEl || !canvasEl) {
        return;
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
            var block = document.createElement("button");
            block.type = "button";
            var isSelected = String(fac.id) === String(input.value);
            block.className = "room-block fp-room room-" + fac.facility_type + (isSelected ? " selected" : "");
            block.style.left = fac.pos_x + "%";
            block.style.top = fac.pos_y + "%";
            block.style.width = fac.shape_w + "%";
            block.style.height = fac.shape_h + "%";
            block.textContent = fac.name;
            block.addEventListener("click", function () {
                input.value = fac.id;
                selectedEl.textContent = "선택됨: " + fac.name;
                renderCanvas();
            });
            canvasEl.appendChild(block);
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener("click", function () {
            input.value = "";
            selectedEl.textContent = "선택된 장소 없음";
            renderCanvas();
        });
    }

    var existing = input.value ? findFacility(input.value) : null;
    if (existing) {
        currentBuildingId = existing.building.id;
        currentFloorId = existing.floor.id;
        selectedEl.textContent = "선택됨: " + existing.facility.name;
    } else if (worksiteMap.length) {
        currentBuildingId = worksiteMap[0].id;
        currentFloorId = worksiteMap[0].floors.length ? worksiteMap[0].floors[0].id : null;
    }

    renderBuildings();
    renderFloors();
    renderCanvas();
});
