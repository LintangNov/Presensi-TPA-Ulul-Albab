(() => {
  const channel = new BroadcastChannel("absensi_tpa_channel");
  const RFID_BURST_MAX_INTERVAL_MS = 60; // Batas interval antar-karakter keyboard emulator USB (< 60ms)
  const RFID_MIN_LENGTH = 4;             // Panjang minimal UID kartu
  let buffer = "";
  let lastKeyTime = 0;
  let bufferTimer = null;
  let isBurstSequence = false;

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

  // Dibuat global agar bisa dipakai template admin lain (mis. halaman Simulator RFID)
  window.showAdminToast = showAdminToast;

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

  // Keystroke listener dengan RFID Burst Timing Detection (Solusi 1)
  // Membedakan ketikan manusia (>80ms) dengan kecepatan perangkat keras RFID (<60ms)
  document.addEventListener("keydown", (e) => {
    // 1. Jika dialog registrasi kartu sedang aktif, biarkan dialog menangani inputnya sendiri
    const regDialog = document.querySelector("#register-dialog");
    if (regDialog && regDialog.open) return;

    // 2. Jika scanner dinonaktifkan via toggle admin
    if (!isScannerActive()) return;

    const isInsideInput = e.target.matches("input:not([type=checkbox]):not([type=radio]), select, textarea");
    const now = Date.now();
    const interval = now - lastKeyTime;
    lastKeyTime = now;

    // 3. Tangani tombol Enter (akhir kiriman kartu reader)
    if (e.key === "Enter") {
      if (buffer.length >= RFID_MIN_LENGTH && isBurstSequence) {
        e.preventDefault();
        const scannedUid = buffer;
        buffer = "";
        isBurstSequence = false;
        clearTimeout(bufferTimer);

        // Bersihkan input teks jika kursor sedang berada di dalam form saat kartu di-tap
        if (isInsideInput && typeof e.target.value === "string") {
          if (e.target.value.endsWith(scannedUid)) {
            e.target.value = e.target.value.slice(0, -scannedUid.length);
          }
        }

        sendTap(scannedUid);
        return;
      }

      // Enter ditekan manusia atau buffer belum memenuhi kriteria kartu
      buffer = "";
      isBurstSequence = false;
      return;
    }

    // 4. Tangani karakter biasa
    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      if (buffer.length === 0) {
        buffer = e.key;
        isBurstSequence = true;
      } else {
        if (interval <= RFID_BURST_MAX_INTERVAL_MS) {
          buffer += e.key;
        } else {
          // Jeda lebih lambat dari 60ms: terdeteksi sebagai ketikan manusia
          if (isInsideInput) {
            buffer = "";
            isBurstSequence = false;
            return;
          } else {
            buffer = e.key;
            isBurstSequence = true;
          }
        }
      }

      clearTimeout(bufferTimer);
      bufferTimer = setTimeout(() => {
        buffer = "";
        isBurstSequence = false;
      }, 500);
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
            ? "Mode Scanner DIAKTIFKAN"
            : "Mode Scanner DINONAKTIFKAN",
          e.target.checked ? "success" : "info"
        );
      });
    }

    // Klik area toggle box untuk menyala/matikan scanner
    const toggleBox = document.querySelector("#scanner-toggle-container");
    if (toggleBox) {
      toggleBox.addEventListener("click", (e) => {
        // Hindari trigger duplo jika klik langsung pada checkbox
        if (e.target.closest("input[type=checkbox]")) return;
        const next = !isScannerActive();
        toggle.checked = next;
        setScannerActive(next);
        showAdminToast(
          next
            ? "Mode Scanner DIAKTIFKAN. Scanner siap menerima tap kartu."
            : "Mode Scanner DINONAKTIFKAN. Formulir dapat diedit.",
          next ? "success" : "info"
        );
      });
    }

    // Refresh hardware status periodik setiap 10 detik
    setInterval(checkHardwareStatus, 10000);
  });
})();
