(() => {
  const channel = new BroadcastChannel("absensi_tpa_channel");
  let buffer = "";
  let lastKeyTime = 0;
  let bufferTimer = null;

  function isScannerActive() {
    const val = localStorage.getItem("absensi_scanner_active");
    return val === null ? true : val === "true";
  }

  function setScannerActive(active) {
    localStorage.setItem("absensi_scanner_active", active ? "true" : "false");
    updateScannerUI();
    channel.postMessage({ type: "scanner_status", active: active });
  }

  function showAdminToast(message, type = "info") {
    let toast = document.querySelector("#admin-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "admin-toast";
      toast.className = "admin-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = `admin-toast show ${type}`;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
      toast.className = "admin-toast";
    }, 3200);
  }

  function updateScannerUI() {
    const active = isScannerActive();
    const toggle = document.querySelector("#scanner-toggle");
    const statusTexts = document.querySelectorAll(".scanner-operational-status");
    const indicator = document.querySelector("#scanner-operational-indicator");
    const toggleBox = document.querySelector("#scanner-toggle-container");

    if (toggle) toggle.checked = active;

    if (toggleBox) toggleBox.classList.toggle("is-off", !active);

    statusTexts.forEach((el) => {
      el.textContent = active ? "Aktif" : "Nonaktif";
    });
    if (indicator) {
      indicator.className = `status-dot ${active ? "active" : "inactive"}`;
    }

    if (active) {
      document.body.classList.add("scanner-guard-active");
    } else {
      document.body.classList.remove("scanner-guard-active");
    }
  }

  async function checkHardwareStatus() {
    const hwEl = document.querySelector("#scanner-hardware-status");
    if (!hwEl) return;
    try {
      const res = await fetch("/api/admin/scanner-hardware");
      if (res.ok) {
        const data = await res.json();
        hwEl.textContent = data.details || (data.connected ? "Scanner USB Terhubung" : "Scanner USB Tidak Terdeteksi");
        hwEl.className = `hw-badge ${data.connected ? "connected" : "disconnected"}`;
      }
    } catch {
      hwEl.textContent = "Status Hardware Tidak Tersedia";
    }
  }

  async function sendTap(uid) {
    try {
      const response = await fetch("/api/tap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid }),
      });
      const result = await response.json();

      // Kirim hasil tap ke tab TV LED via BroadcastChannel
      channel.postMessage({
        type: "tap_result",
        uid: uid,
        data: result,
      });

      // Tampilkan toast notifikasi di admin
      const badgeType = result.hasil === "berhasil" || result.hasil === "pulang" ? "success" :
                        result.hasil === "denda" ? "danger" :
                        result.hasil === "duplikat" ? "warning" : "error";
      const infoNama = result.nama ? `[${result.nama}] ` : "";
      showAdminToast(`${infoNama}${result.pesan}`, badgeType);

      // Update feed di dashboard jika ada
      addDashboardFeed(result, uid);
    } catch (err) {
      showAdminToast("Gagal memproses tap kartu. Periksa koneksi aplikasi.", "error");
    }
  }

  function addDashboardFeed(result, uid) {
    const feed = document.querySelector("#recent-tap-feed");
    if (!feed) return;
    const item = document.createElement("li");
    item.className = `feed-item ${result.hasil}`;
    const timeNow = new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const nama = result.nama || uid;
    const statusLabel = result.hasil === "berhasil" ? "Masuk" :
                        result.hasil === "pulang" ? "Pulang" :
                        result.hasil === "denda" ? "Denda" :
                        result.hasil === "duplikat" ? "Sudah Absen" : result.hasil;
    item.innerHTML = `<strong>${timeNow}</strong> <span>${nama}</span> <span class="badge ${result.hasil}">${statusLabel}</span>`;
    feed.prepend(item);
    while (feed.children.length > 5) feed.lastElementChild.remove();
  }

  // Scanner Guard: intercept input clicks if scanner is active
  document.addEventListener("click", (e) => {
    if (!isScannerActive()) return;

    // Kecualikan toggle scanner, sidebar navigasi, dialog daftarkan kartu, dan tombol penting
    if (
      e.target.closest("#scanner-toggle-container") ||
      e.target.closest(".admin-sidebar") ||
      e.target.closest("#register-dialog") ||
      e.target.closest("#delete-confirm-dialog") ||
      e.target.closest("#reset-confirm-dialog")
    ) {
      return;
    }

    const isInput = e.target.matches("input:not([type=checkbox]):not([type=radio]), select, textarea");
    if (isInput) {
      e.preventDefault();
      e.target.blur();
      showAdminToast("Mode Scanner aktif. Matikan toggle scanner jika ingin mengisi data formulir.", "warning");
    }
  });

  // Global Keystroke listener for RFID reader
  document.addEventListener("keydown", (e) => {
    // Jika dialog registrasi kartu sedang aktif, biarkan dialog menangani inputnya sendiri
    const regDialog = document.querySelector("#register-dialog");
    if (regDialog && regDialog.open) return;

    if (!isScannerActive()) return;

    const now = Date.now();
    const interval = now - lastKeyTime;
    lastKeyTime = now;

    if (e.key === "Enter") {
      if (buffer.length >= 3) {
        e.preventDefault();
        const scannedUid = buffer;
        buffer = "";
        clearTimeout(bufferTimer);
        sendTap(scannedUid);
        return;
      }
      buffer = "";
      return;
    }

    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      buffer += e.key;
      clearTimeout(bufferTimer);
      bufferTimer = setTimeout(() => {
        buffer = "";
      }, 700);
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    updateScannerUI();
    checkHardwareStatus();

    const toggle = document.querySelector("#scanner-toggle");
    if (toggle) {
      toggle.addEventListener("change", (e) => {
        setScannerActive(e.target.checked);
        showAdminToast(
          e.target.checked
            ? "Mode Scanner DIAKTIFKAN. Scanner siap menerima tap kartu."
            : "Mode Scanner DINONAKTIFKAN. Formulir dapat diedit.",
          e.target.checked ? "success" : "info"
        );
      });
    }

    // Refresh hardware status periodik setiap 10 detik
    setInterval(checkHardwareStatus, 10000);
  });
})();
