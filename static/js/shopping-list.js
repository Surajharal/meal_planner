/**
 * Shopping list checkboxes persisted in localStorage per week.
 */
(function () {
    function storageKey(weekStart) {
        return "mealplanner-shopping-" + (weekStart || "default");
    }

    function itemKey(name, unit) {
        return (name || "").trim().toLowerCase() + "|" + (unit || "").trim().toLowerCase();
    }

    document.addEventListener("DOMContentLoaded", function () {
        var root = document.getElementById("shopping-list-root");
        if (!root) return;

        var week = root.getAttribute("data-week-start") || "";
        var key = storageKey(week);
        var checked = {};
        try {
            checked = JSON.parse(localStorage.getItem(key) || "{}") || {};
        } catch (e) {
            checked = {};
        }

        var items = root.querySelectorAll(".shopping-item[data-item-key]");
        var countEl = document.getElementById("shopping-checked-count");

        function updateCount() {
            if (!countEl) return;
            var total = items.length;
            var done = root.querySelectorAll(".shopping-item.is-checked").length;
            countEl.textContent = done + " of " + total + " checked";
        }

        items.forEach(function (li) {
            var id = li.getAttribute("data-item-key");
            var box = li.querySelector(".shopping-item-check");
            if (!box) return;
            if (checked[id]) {
                box.checked = true;
                li.classList.add("is-checked");
            }
            box.addEventListener("change", function () {
                if (box.checked) {
                    checked[id] = true;
                    li.classList.add("is-checked");
                } else {
                    delete checked[id];
                    li.classList.remove("is-checked");
                }
                try {
                    localStorage.setItem(key, JSON.stringify(checked));
                } catch (e) { /* ignore */ }
                updateCount();
            });
        });

        var clearBtn = document.getElementById("shopping-clear-checked");
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                checked = {};
                try {
                    localStorage.removeItem(key);
                } catch (e) { /* ignore */ }
                items.forEach(function (li) {
                    var box = li.querySelector(".shopping-item-check");
                    if (box) box.checked = false;
                    li.classList.remove("is-checked");
                });
                updateCount();
            });
        }

        updateCount();
    });
})();
