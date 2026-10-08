/**
 * Greenwood Estates Portal - Client Scripts
 */

document.addEventListener("DOMContentLoaded", function () {
  // 1. Auto-dismiss alerts after 5 seconds
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = "opacity 0.4s ease, transform 0.4s ease";
      alert.style.opacity = "0";
      alert.style.transform = "translateY(-8px)";
      setTimeout(function () {
        alert.remove();
      }, 400);
    }, 5500);
  });

  // 2. Notification counter polling every 20 seconds
  function pollNotifications() {
    fetch("/notifications/api/unread-count")
      .then(res => res.json())
      .then(data => {
        const notifBadge = document.getElementById("topbar-notif-badge");
        if (notifBadge) {
          if (data.count > 0) {
            notifBadge.innerText = data.count;
            notifBadge.style.display = "inline-flex";
          } else {
            notifBadge.style.display = "none";
          }
        }
      })
      .catch(() => {});
  }
  setInterval(pollNotifications, 20000);

  // 3. Modal helper functions
  window.openModal = function (modalId) {
    const m = document.getElementById(modalId);
    if (m) {
      m.classList.add("show");
    }
  };

  window.closeModal = function (modalId) {
    const m = document.getElementById(modalId);
    if (m) {
      m.classList.remove("show");
    }
  };

  // Close modals on backdrop click
  document.querySelectorAll(".modal-backdrop").forEach(function (backdrop) {
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) {
        backdrop.classList.remove("show");
      }
    });
  });

  // 4. Interactive 5-star rating selector
  const starContainers = document.querySelectorAll(".star-rating-widget");
  starContainers.forEach(function (widget) {
    const stars = widget.querySelectorAll(".star-icon");
    const input = widget.querySelector("input[name='rating']");
    stars.forEach(function (star, index) {
      star.addEventListener("click", function () {
        const ratingVal = index + 1;
        input.value = ratingVal;
        stars.forEach(function (s, i) {
          if (i < ratingVal) {
            s.classList.add("fas");
            s.classList.remove("far");
            s.style.color = "#f59e0b";
          } else {
            s.classList.add("far");
            s.classList.remove("fas");
            s.style.color = "#cbd5e1";
          }
        });
      });
    });
  });

  // 5. Booking slot conflict previewer in Amenity booking modal/form
  const amenitySelect = document.getElementById("booking_amenity_select");
  const dateInput = document.getElementById("booking_date_input");
  const slotListDiv = document.getElementById("existing_slots_display");

  function refreshReservedSlots() {
    if (!amenitySelect || !dateInput || !slotListDiv) return;
    const amenityId = amenitySelect.value;
    const dateVal = dateInput.value;
    if (!amenityId || !dateVal) return;

    slotListDiv.innerHTML = '<span style="color:#64748b; font-size:0.82rem;"><i class="fas fa-spinner fa-spin"></i> Checking reserved slots...</span>';
    fetch(`/resident/amenities/check-slots?amenity_id=${amenityId}&date=${dateVal}`)
      .then(res => res.json())
      .then(slots => {
        if (slots.length === 0) {
          slotListDiv.innerHTML = '<span style="color:#10b981; font-size:0.82rem; font-weight:600;"><i class="fas fa-circle-check"></i> All slots available for this date!</span>';
        } else {
          let html = '<div style="font-size:0.8rem; font-weight:600; color:#b45309; margin-bottom:6px;"><i class="fas fa-triangle-exclamation"></i> Reserved / Pending Slots:</div><div style="display:flex; flex-wrap:wrap; gap:6px;">';
          slots.forEach(s => {
            const badgeBg = s.status === 'APPROVED' ? '#fee2e2' : '#fef3c7';
            const badgeColor = s.status === 'APPROVED' ? '#991b1b' : '#b45309';
            html += `<span style="background:${badgeBg}; color:${badgeColor}; padding:3px 8px; border-radius:4px; font-size:0.75rem; font-weight:600;">${s.start_time} - ${s.end_time} (${s.status})</span>`;
          });
          html += '</div>';
          slotListDiv.innerHTML = html;
        }
      })
      .catch(() => {
        slotListDiv.innerHTML = '';
      });
  }

  if (amenitySelect && dateInput) {
    amenitySelect.addEventListener("change", refreshReservedSlots);
    dateInput.addEventListener("change", refreshReservedSlots);
  }
});
