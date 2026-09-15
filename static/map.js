var _currentScript = document.currentScript;

document.addEventListener("DOMContentLoaded", function () {
    var markers = document.querySelectorAll(".marker-facility");
    var detail = document.getElementById("facility-detail");
    if (!detail) return;

    var nameEl = document.getElementById("fd-name");
    var typeEl = document.getElementById("fd-type");
    var hoursEl = document.getElementById("fd-hours");
    var descEl = document.getElementById("fd-desc");
    var routesEl = document.getElementById("fd-routes");

    function showDetail(marker) {
        nameEl.textContent = marker.dataset.name;
        typeEl.textContent = marker.dataset.type;
        hoursEl.textContent = marker.dataset.hours;
        descEl.textContent = marker.dataset.desc || "";

        var routes = [];
        try {
            routes = JSON.parse(marker.dataset.routes || "[]");
        } catch (e) {
            routes = [];
        }

        if (routes.length && routesEl) {
            var html = "<h4>여기서 출발하는 셔틀</h4><ul class=\"shuttle-route-list\">";
            routes.forEach(function (r) {
                html +=
                    "<li><strong>" + r.route_name + "</strong> → " + r.arrival +
                    "<br>운행 " + r.operation + " · 배차간격 " + r.interval + "분 · 이동시간 " + r.travel_minutes + "분" +
                    (r.next_departure ? ("<br>다음 셔틀: <strong>" + r.next_departure + "</strong>") : "<br>금일 운행 종료") +
                    "</li>";
            });
            html += "</ul>";
            routesEl.innerHTML = html;
            routesEl.hidden = false;
        } else if (routesEl) {
            routesEl.hidden = true;
            routesEl.innerHTML = "";
        }

        detail.hidden = false;
    }

    markers.forEach(function (marker) {
        marker.addEventListener("click", function () {
            showDetail(marker);
        });
    });

    var highlightId = _currentScript ? _currentScript.dataset.highlight : "";
    if (highlightId) {
        var target = document.querySelector('.marker-facility[data-id="' + highlightId + '"]');
        if (target) {
            showDetail(target);
            target.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }
});
