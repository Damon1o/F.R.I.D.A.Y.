document.addEventListener("DOMContentLoaded", async () => {
  const cal = document.getElementById("calendar");
  if (cal) {
    await loadCalendar(cal);
  }

  const fab = document.getElementById("calendar-fab");
  const panel = document.getElementById("fab-chat-panel");
  if (fab && panel) {
    let widget = null;
    fab.addEventListener("click", () => {
      panel.classList.toggle("open");
      if (panel.classList.contains("open") && !widget) {
        widget = createChatWidget(panel, { compact: true });
      }
    });
  }
});

async function loadCalendar(cal) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const start = new Date(year, month, 1).toISOString();
  const end = new Date(year, month + 1, 0, 23, 59, 59).toISOString();

  try {
    const res = await fetch(
      `/calendar/api/events?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    );
    const events = await res.json();
    renderCalendar(cal, events, year, month);
  } catch (e) {
    cal.textContent = "Error loading events: " + e.message;
  }
}

function renderCalendar(cal, events, year, month) {
  const now = new Date();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const monthName = now.toLocaleString("default", { month: "long" });

  let html = `<div class="calendar-header-row"><span class="calendar-title">${monthName} ${year}</span></div>`;
  html += '<table class="cal-grid"><thead><tr>';
  ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].forEach((d) => {
    html += `<th>${d}</th>`;
  });
  html += "</tr></thead><tbody><tr>";

  let day = 1;
  for (let i = 0; i < 6; i++) {
    for (let j = 0; j < 7; j++) {
      if (i === 0 && j < firstDay) {
        html += "<td></td>";
      } else if (day > daysInMonth) {
        html += "<td></td>";
      } else {
        const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const dayEvents = events.filter((e) => e.start.startsWith(dateStr));
        html += `<td class="cal-day"><span class="day-num">${day}</span>`;
        if (dayEvents.length) {
          html += '<ul class="day-events">';
          dayEvents.forEach((e) => {
            html += `<li>${escapeHtml(e.title)}</li>`;
          });
          html += "</ul>";
        }
        html += "</td>";
        day++;
      }
    }
    if (day > daysInMonth) break;
    html += "</tr><tr>";
  }
  html += "</tr></tbody></table>";
  cal.innerHTML = html;
}
