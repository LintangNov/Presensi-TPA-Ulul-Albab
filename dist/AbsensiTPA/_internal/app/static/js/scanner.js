(() => {
  const log = document.querySelector("#tap-log");
  const status = document.querySelector("#scanner-status");
  const focusWarning = document.querySelector("#focus-warning");
  const feedback = document.querySelector("#feedback");
  const feedbackTitle = document.querySelector("#feedback-title");
  const feedbackMessage = document.querySelector("#feedback-message");
  const feedbackTypes = {
    berhasil: ["green", "Berhasil", "Absensi sudah dicatat."],
    duplikat: ["yellow", "Sudah absen", "Kartu ini sudah absen hari ini."],
    tidak_dikenal: ["red", "Kartu belum terdaftar", "Silakan laporkan kepada pengurus."],
    tidak_aktif: ["orange", "Data tidak aktif", "Santri ini sedang tidak aktif."],
    registrasi: ["blue", "Kartu terdaftar", "Kartu siap digunakan."],
    uid_terpakai: ["orange", "Kartu sudah dipakai", "Gunakan kartu lain."],
  };
  let buffer = "";
  let bufferTimer;
  let feedbackTimer;

  function showLog(uid, result) {
    const item = document.createElement("li");
    item.textContent = `${result}: ${uid}`;
    log.prepend(item);
    while (log.children.length > 10) log.lastElementChild.remove();
  }

  function showFeedback(result, message) {
    const type = feedbackTypes[result] || ["red", "Gagal", "Tap tidak dapat diproses."];
    feedback.className = `feedback ${type[0]}`;
    feedbackTitle.textContent = type[1];
    feedbackMessage.textContent = message || type[2];
    feedback.hidden = false;
    clearTimeout(feedbackTimer);
    feedbackTimer = setTimeout(() => { feedback.hidden = true; }, 1800);
  }

  function setFocusState(active) {
    status.textContent = active ? "Scanner aktif" : "Scanner tidak aktif";
    status.classList.toggle("connected", active);
    focusWarning.hidden = active;
  }

  async function sendTap(uid) {
    try {
      const response = await fetch("/api/tap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid }),
      });
      if (!response.ok) throw new Error("server menolak tap");
      const result = await response.json();
      showFeedback(result.hasil, result.pesan);
      showLog(uid, result.hasil);
    } catch {
      showFeedback("gagal", "Tap tidak dapat diproses. Periksa aplikasi.");
    }
  }

  function clearBuffer() {
    buffer = "";
    clearTimeout(bufferTimer);
  }

  document.addEventListener("keydown", (event) => {
    if (!document.hasFocus()) {
      setFocusState(false);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const uid = buffer;
      clearBuffer();
      if (uid) sendTap(uid);
      return;
    }
    if (event.key.length !== 1 || event.ctrlKey || event.altKey || event.metaKey) return;
    buffer += event.key;
    clearTimeout(bufferTimer);
    bufferTimer = setTimeout(clearBuffer, 1000);
  });

  window.addEventListener("blur", () => setFocusState(false));
  window.addEventListener("focus", () => setFocusState(true));
  document.addEventListener("click", () => setFocusState(document.hasFocus()));
  setFocusState(document.hasFocus());
})();
