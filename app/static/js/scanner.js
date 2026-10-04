(() => {
  const input = document.querySelector("#rfid-input");
  const log = document.querySelector("#tap-log");
  const connection = document.querySelector("#connection");
  const pendingCount = document.querySelector("#pending-count");
  const offlineBanner = document.querySelector("#offline-banner");
  const sessionStatus = document.querySelector("#session-status");
  const startButton = document.querySelector("#start-session");
  const feedback = document.querySelector("#feedback");
  const feedbackTitle = document.querySelector("#feedback-title");
  const feedbackMessage = document.querySelector("#feedback-message");
  const queueKey = `absensi-tpa-antrean-${location.host}`;
  const clientId = crypto.randomUUID ? crypto.randomUUID() : `hp-${Date.now()}`;
  const noSleep = new NoSleep();
  let sessionActive = false;
  let lastPingAt = 0;
  let disconnectedSince = 0;
  let lastUid = "";
  let lastUidAt = 0;
  let feedbackTimer;

  const feedbackTypes = {
    berhasil: ["green", "Berhasil", "Absensi sudah dicatat."],
    duplikat: ["yellow", "Sudah absen", "Kartu ini sudah absen hari ini."],
    tidak_dikenal: ["red", "Kartu belum terdaftar", "Silakan laporkan kepada pengurus."],
    tidak_aktif: ["orange", "Data tidak aktif", "Santri ini sedang tidak aktif."],
    registrasi: ["blue", "Kartu terdaftar", "Kartu siap digunakan."],
    uid_terpakai: ["orange", "Kartu sudah dipakai", "Gunakan kartu lain."],
  };

  function getQueue() {
    try {
      return JSON.parse(localStorage.getItem(queueKey) || "[]");
    } catch {
      return [];
    }
  }

  function saveQueue(queue) {
    localStorage.setItem(queueKey, JSON.stringify(queue));
    pendingCount.textContent = `Tap tertunda: ${queue.length}`;
  }

  function keepFocus() {
    if (sessionActive) input.focus({ preventScroll: true });
  }

  function showLog(uid, result, queued = false) {
    const item = document.createElement("li");
    const visible = JSON.stringify(uid);
    const special = [...uid].map((char) => {
      const code = char.codePointAt(0);
      return code < 32 || code === 127 ? `\\u${code.toString(16).padStart(4, "0")}` : char;
    }).join("");
    const title = document.createElement("strong");
    title.textContent = queued ? "Disimpan" : result;
    const details = document.createElement("span");
    details.className = "raw";
    details.textContent = `UID mentah: ${visible}\nPanjang: ${uid.length} karakter\nKarakter terlihat: ${special}`;
    item.append(title, document.createElement("br"), details);
    log.prepend(item);
  }

  function beep(result) {
    try {
      const audio = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audio.createOscillator();
      oscillator.frequency.value = result === "berhasil" ? 880 : 440;
      oscillator.connect(audio.destination);
      oscillator.start();
      oscillator.stop(audio.currentTime + 0.12);
    } catch {
      // Bunyi boleh tidak tersedia di browser atau perangkat.
    }
  }

  function showFeedback(result, message) {
    const type = feedbackTypes[result] || ["red", "Gagal", "Tap tidak dapat diproses."];
    feedback.className = `feedback ${type[0]}`;
    feedbackTitle.textContent = type[1];
    feedbackMessage.textContent = message || type[2];
    feedback.hidden = false;
    if (navigator.vibrate) navigator.vibrate(result === "berhasil" ? 100 : [80, 50, 80]);
    beep(result);
    clearTimeout(feedbackTimer);
    feedbackTimer = setTimeout(() => { feedback.hidden = true; }, 1800);
  }

  async function sendQueue() {
    const queue = getQueue();
    if (!queue.length) return;
    const entry = queue[0];
    const ageMs = Math.max(0, Date.now() - entry.queued_at);
    try {
      const response = await fetch("/api/tap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          uid: entry.uid,
          client_id: entry.client_id,
          client_tap_id: entry.client_tap_id,
          age_ms: ageMs,
        }),
      });
      if (!response.ok) throw new Error("server menolak tap");
      const data = await response.json();
      const current = getQueue();
      if (current[0] && current[0].client_tap_id === entry.client_tap_id) {
        current.shift();
        saveQueue(current);
      }
      showFeedback(data.hasil, data.pesan);
      showLog(entry.uid, data.hasil);
      markConnected();
    } catch {
      markDisconnected();
    }
  }

  function markConnected() {
    lastPingAt = Date.now();
    disconnectedSince = 0;
    connection.textContent = "Koneksi tersambung";
    connection.classList.add("connected");
    offlineBanner.hidden = true;
  }

  function markDisconnected() {
    if (!disconnectedSince) disconnectedSince = Date.now();
    connection.textContent = "Koneksi putus";
    connection.classList.remove("connected");
    if (Date.now() - disconnectedSince > 10000) offlineBanner.hidden = false;
  }

  async function ping() {
    try {
      const response = await fetch("/api/ping", { headers: { "X-Client-ID": clientId } });
      if (!response.ok) throw new Error("ping gagal");
      markConnected();
    } catch {
      markDisconnected();
    }
  }

  function queueTap(uid) {
    const now = Date.now();
    if (uid === lastUid && now - lastUidAt < 1500) return;
    lastUid = uid;
    lastUidAt = now;
    const queue = getQueue();
    queue.push({
      uid,
      client_id: clientId,
      client_tap_id: crypto.randomUUID ? crypto.randomUUID() : `${now}-${Math.random()}`,
      queued_at: now,
    });
    saveQueue(queue);
    showLog(uid, "menunggu", true);
    sendQueue();
  }

  startButton.addEventListener("click", () => {
    sessionActive = !sessionActive;
    if (sessionActive) {
      try {
        Promise.resolve(noSleep.enable()).catch(() => {});
      } catch {
        // Perangkat tertentu tidak mengizinkan NoSleep.
      }
      startButton.textContent = "AKHIRI SESI";
      sessionStatus.textContent = "Sesi aktif. Layar akan dijaga tetap menyala.";
      keepFocus();
    } else {
      try {
        noSleep.disable();
      } catch {
        // Tidak ada tindakan jika NoSleep gagal dilepas.
      }
      startButton.textContent = "MULAI SESI";
      sessionStatus.textContent = "Sesi selesai. Tap tertunda tetap tersimpan.";
    }
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (input.value) queueTap(input.value);
      input.value = "";
      keepFocus();
    }
  });
  document.addEventListener("click", keepFocus);
  saveQueue(getQueue());
  setInterval(() => { ping(); sendQueue(); }, 3000);
  setInterval(() => { if (lastPingAt && Date.now() - lastPingAt > 10000) markDisconnected(); }, 1000);
  ping();
})();
