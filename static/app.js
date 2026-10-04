const $ = (s, r = document) => r.querySelector(s);
document.querySelectorAll("form.cam").forEach((f) => {
  const fr = $(".frame", f),
    v = $("video", f),
    c = $("canvas", f),
    h = $("[name=foto]", f),
    b = $(".snap", f),
    l = $("span", b);
  let s;
  b.onclick = async () => {
    if (!s) {
      try {
        s = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
        });
      } catch (e) {
        alert(
          "Kamera tidak bisa dibuka. Izinkan akses kamera dan gunakan HTTPS atau localhost.",
        );
        return;
      }
      v.srcObject = s;
      fr.hidden = false;
      v.hidden = false;
      c.hidden = true;
      h.value = "";
      l.textContent = "Jepret foto";
      return;
    }
    c.width = 640;
    c.height = Math.round((640 * v.videoHeight) / v.videoWidth);
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    h.value = c.toDataURL("image/jpeg", 0.7);
    s.getTracks().forEach((t) => t.stop());
    s = null;
    v.hidden = true;
    c.hidden = false;
    l.textContent = "Ulangi foto";
  };
  f.onsubmit = (e) => {
    if (!h.value) {
      e.preventDefault();
      alert("Ambil foto dulu.");
    } else if (!f.lat.value) {
      e.preventDefault();
      alert('Lokasi belum terbaca. Tunggu sampai muncul "Lokasi siap".');
    }
  };
});
document.addEventListener(
  "submit",
  (e) => {
    const m = e.target.dataset.confirm;
    if (m && !confirm(m)) e.preventDefault();
  },
  true,
);
document.addEventListener("submit", (e) => {
  if (e.defaultPrevented) return;
  const b = e.target.querySelector("button:not([type=button])");
  if (b) b.classList.add("loading");
});
addEventListener("pageshow", () =>
  document
    .querySelectorAll(".loading")
    .forEach((b) => b.classList.remove("loading")),
);
document.querySelectorAll(".eye").forEach(
  (b) =>
    (b.onclick = () => {
      const i = b.parentNode.querySelector("input");
      i.type = i.type == "password" ? "text" : "password";
    }),
);
const k = $("#clock");
if (k) {
  const t = () =>
    (k.textContent = new Date()
      .toLocaleTimeString("id-ID", { hour12: false, timeZone: "Asia/Jakarta" })
      .replace(/\./g, ":"));
  t();
  setInterval(t, 1000);
}
setTimeout(
  () => document.querySelectorAll(".toast").forEach((t) => t.remove()),
  4500,
);

document.querySelectorAll("[data-pilih]").forEach(
  (b) =>
    (b.onclick = () => {
      const [a, z] = b.dataset.pilih.split("-").map(Number);
      document
        .querySelectorAll(".days input")
        .forEach((i, n) => (i.checked = n >= a && n <= z));
    }),
);

const gf = [...document.querySelectorAll("form.cam")];
if (gf.length) {
  const st = (t, c) =>
    gf.forEach((f) => {
      const g = f.querySelector(".gps");
      g.textContent = t;
      g.className = "chip gps " + (c || "");
    });
  if (!navigator.geolocation) st("GPS tidak didukung browser", "bad");
  else
    navigator.geolocation.watchPosition(
      (p) => {
        gf.forEach((f) => {
          f.lat.value = p.coords.latitude;
          f.lng.value = p.coords.longitude;
          f.acc.value = p.coords.accuracy;
        });
        st(
          "📍 Lokasi siap · akurasi ±" + Math.round(p.coords.accuracy) + " m",
          "ok",
        );
      },
      () => st("📍 Lokasi tidak terbaca. Izinkan akses lokasi.", "bad"),
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 },
    );
}
document.querySelectorAll(".posku").forEach(
  (b) =>
    (b.onclick = () =>
      navigator.geolocation.getCurrentPosition(
        (p) => {
          const f = b.closest("form");
          f.lat.value = p.coords.latitude.toFixed(6);
          f.lng.value = p.coords.longitude.toFixed(6);
        },
        () => alert("Lokasi tidak bisa dibaca."),
        { enableHighAccuracy: true },
      )),
);
