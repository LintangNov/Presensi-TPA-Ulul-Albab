(() => {
  const channel = new BroadcastChannel("absensi_tpa_channel");
  const idleView = document.querySelector("#tv-idle-view");
  const activeView = document.querySelector("#tv-active-view");
  const badgeEl = document.querySelector("#tv-status-badge");
  const nameEl = document.querySelector("#tv-student-name");
  const noEl = document.querySelector("#tv-student-no");
  const paketEl = document.querySelector("#tv-student-paket");
  const timeEl = document.querySelector("#tv-tap-time");
  const msgEl = document.querySelector("#tv-status-message");
  const dendaBox = document.querySelector("#tv-denda-box");
  const historyList = document.querySelector("#tv-history-list");
  const emptyHistory = document.querySelector("#tv-history-empty");

  let revertTimer = null;
  let buffer = "";
  let bufferTimer = null;

  // Real-time Clock
  function updateClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " WIB";
    const dateStr = now.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    const clockEl = document.querySelector("#tv-time");
    const dateEl = document.querySelector("#tv-date");
    if (clockEl) clockEl.textContent = timeStr;
    if (dateEl) dateEl.textContent = dateStr;
  }
  setInterval(updateClock, 1000);
  updateClock();

  function showTapOnTV(result, uid) {
    if (!result) return;

    if (emptyHistory && emptyHistory.parentNode) {
      emptyHistory.remove();
    }

    const hasil = result.hasil || "berhasil";
    let badgeClass = "tv-badge-masuk";
    let badgeLabel = "ABSEN MASUK";

    if (hasil === "pulang") {
      badgeClass = "tv-badge-pulang";
      badgeLabel = "PENJEMPUTAN (PULANG)";
    } else if (hasil === "denda") {
      badgeClass = "tv-badge-denda";
      badgeLabel = "⚠️ DENDA KETERLAMBATAN PENJEMPUTAN";
    } else if (hasil === "duplikat") {
      badgeClass = "tv-badge-duplikat";
      badgeLabel = "SUDAH TERCATAT HARI INI";
    } else if (hasil === "tidak_dikenal" || hasil === "tidak_aktif") {
      badgeClass = "tv-badge-error";
      badgeLabel = hasil === "tidak_dikenal" ? "KARTU BELUM TERDAFTAR" : "MURID NONAKTIF";
    }

    badgeEl.className = `tv-active-badge ${badgeClass}`;
    badgeEl.textContent = badgeLabel;

    nameEl.textContent = result.nama || `Kartu: ${uid || "-"}`;
    noEl.textContent = result.nomor_urut ? `No. Absen: #${result.nomor_urut}` : "No. Absen: -";
    paketEl.textContent = result.paket_label || (result.paket ? `Paket ${result.paket}` : "Paket TPA");
    timeEl.textContent = `Pukul: ${result.waktu || new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}`;
    msgEl.textContent = result.pesan || "";

    if (result.denda_menit && result.denda_menit > 0) {
      dendaBox.style.display = "block";
      dendaBox.textContent = `Perhatian Orang Tua: Penjemputan terlambat ${result.denda_menit} menit melewati batas toleransi operasional.`;
    } else {
      dendaBox.style.display = "none";
    }

    // Tampilkan Active View
    idleView.style.display = "none";
    activeView.style.display = "block";

    clearTimeout(revertTimer);
    revertTimer = setTimeout(() => {
      activeView.style.display = "none";
      idleView.style.display = "block";
    }, 5500);

    // Tambah ke riwayat list
    addToHistory(result, uid, badgeLabel, badgeClass);
  }

  function addToHistory(result, uid, badgeLabel, badgeClass) {
    const item = document.createElement("li");
    item.className = "tv-history-item";
    const nama = result.nama || uid;
    const no = result.nomor_urut ? `#${result.nomor_urut}` : "-";
    const waktu = result.waktu || new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
    const paket = result.paket ? `(Paket ${result.paket})` : "";

    item.innerHTML = `
      <div style="display: flex; align-items: center; gap: 0.75rem;">
        <span style="font-weight: 700;">${waktu}</span>
        <span style="background: var(--primary-soft); padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.85rem;">${no}</span>
        <strong>${nama}</strong>
        <span style="color: var(--text-muted); font-size: 0.85rem;">${paket}</span>
      </div>
      <div>
        <span class="badge ${badgeClass}" style="font-size: 0.8rem; padding: 0.25rem 0.65rem;">${badgeLabel}</span>
      </div>
    `;

    historyList.prepend(item);
    while (historyList.children.length > 8) {
      historyList.lastElementChild.remove();
    }
  }

  // Terima event dari BroadcastChannel (dari admin tab)
  channel.onmessage = (event) => {
    if (event.data && event.data.type === "tap_result") {
      showTapOnTV(event.data.data, event.data.uid);
    }
  };

  // Cadangan direct keystroke listener jika tab ini kebetulan sedang fokus
  async function sendLocalTap(uid) {
    try {
      const res = await fetch("/api/tap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid }),
      });
      const data = await res.json();
      showTapOnTV(data, uid);
      channel.postMessage({ type: "tap_result", data, uid });
    } catch {
      // Abaikan error jaringan
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      if (buffer.length >= 3) {
        e.preventDefault();
        const scannedUid = buffer;
        buffer = "";
        clearTimeout(bufferTimer);
        sendLocalTap(scannedUid);
        return;
      }
      buffer = "";
      return;
    }

    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      buffer += e.key;
      clearTimeout(bufferTimer);
      bufferTimer = setTimeout(() => { buffer = ""; }, 700);
    }
  });
})();
