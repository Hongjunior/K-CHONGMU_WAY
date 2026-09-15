(function () {
    var script = document.currentScript;
    var upcomingUrl = script ? script.dataset.upcomingUrl : null;
    if (!upcomingUrl) return;

    var ALERT_WINDOW_MINUTES = 10;
    var POLL_MS = 30000;
    var alertedKey = "reminder_alerted_" + new Date().toISOString().slice(0, 10);

    function getAlerted() {
        try {
            return JSON.parse(sessionStorage.getItem(alertedKey) || "[]");
        } catch (e) {
            return [];
        }
    }

    function markAlerted(id) {
        try {
            var list = getAlerted();
            list.push(id);
            sessionStorage.setItem(alertedKey, JSON.stringify(list));
        } catch (e) {
            /* sessionStorage unavailable — reminders just won't dedupe across polls */
        }
    }

    function minutesUntil(startTime) {
        var now = new Date();
        var parts = startTime.split(":");
        var target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parseInt(parts[0], 10), parseInt(parts[1], 10));
        return Math.round((target - now) / 60000);
    }

    function showToast(item, minutesLeft) {
        var root = document.getElementById("reminder-toast-root");
        if (!root) return;

        var toast = document.createElement("div");
        toast.className = "reminder-toast";

        var title = document.createElement("div");
        title.className = "reminder-toast-title";
        title.textContent = "⏰ " + minutesLeft + "분 후 시작: " + item.title;
        toast.appendChild(title);

        var meta = document.createElement("div");
        meta.className = "reminder-toast-meta";
        meta.textContent = item.start_time + (item.location ? " · " + item.location : "");
        toast.appendChild(meta);

        var closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "reminder-toast-close";
        closeBtn.textContent = "닫기";
        closeBtn.addEventListener("click", function () {
            toast.remove();
        });
        toast.appendChild(closeBtn);

        root.appendChild(toast);
        setTimeout(function () {
            if (toast.parentNode) toast.remove();
        }, 25000);

        if (window.Notification && Notification.permission === "granted") {
            try {
                new Notification("K-총무 WAY: " + item.title, {
                    body: minutesLeft + "분 후 시작" + (item.location ? " · " + item.location : ""),
                });
            } catch (e) {
                /* ignore Notification failures, the in-page toast already covers it */
            }
        }
    }

    function poll() {
        fetch(upcomingUrl, { credentials: "same-origin" })
            .then(function (res) {
                return res.ok ? res.json() : [];
            })
            .then(function (items) {
                var alerted = getAlerted();
                items.forEach(function (item) {
                    if (!item.start_time || alerted.indexOf(item.id) !== -1) return;
                    var minutesLeft = minutesUntil(item.start_time);
                    if (minutesLeft > 0 && minutesLeft <= ALERT_WINDOW_MINUTES) {
                        showToast(item, minutesLeft);
                        markAlerted(item.id);
                        alerted.push(item.id);
                    }
                });
            })
            .catch(function () {
                /* network hiccup — just try again next poll */
            });
    }

    if (window.Notification && Notification.permission === "default") {
        Notification.requestPermission();
    }

    poll();
    setInterval(poll, POLL_MS);
})();
