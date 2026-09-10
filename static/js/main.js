/* bodeuro — interacties */
const $ = (s, c = document) => c.querySelector(s);
const $$ = (s, c = document) => [...c.querySelectorAll(s)];

/* ---------- Mobiel menu ---------- */
const burger = $("#burger");
if (burger) {
  burger.addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    burger.setAttribute("aria-expanded", String(open));
  });
  $$("#mainNav a").forEach((a) =>
    a.addEventListener("click", () => document.body.classList.remove("nav-open"))
  );
}

/* ---------- Reveal-animaties + voortgangsbalken ---------- */
const io = new IntersectionObserver(
  (entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      $$(".bar-fill", e.target).forEach((f) => (f.style.width = f.dataset.w + "%"));
      io.unobserve(e.target);
    });
  },
  { threshold: 0.15 }
);
$$(".reveal, .reveal-goal").forEach((el) => io.observe(el));

/* ---------- Saldo tellen ---------- */
const fmt = new Intl.NumberFormat("nl-NL", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
function countUp(el, target, dur = 1500) {
  const start = performance.now();
  (function tick(now) {
    const p = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt.format(target * eased);
    if (p < 1) requestAnimationFrame(tick);
  })(start);
}
const saldoEl = $("#saldo");
if (saldoEl) {
  const io2 = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) {
        countUp(saldoEl, parseFloat(saldoEl.dataset.value) || 0);
        io2.disconnect();
      }
    },
    { threshold: 0.4 }
  );
  io2.observe(saldoEl);
}

/* ---------- Kaart 3D-tilt ---------- */
const card = $("#bankcard");
if (card) {
  card.addEventListener("mousemove", (e) => {
    const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    card.style.transform = `perspective(900px) rotateY(${x * 9}deg) rotateX(${-y * 9}deg)`;
  });
  card.addEventListener("mouseleave", () => (card.style.transform = ""));
}

/* ---------- Historie ---------- */
$("#btnHistory")?.addEventListener("click", () =>
  $("#transacties")?.scrollIntoView({ behavior: "smooth", block: "center" })
);

/* ---------- Dialogs ---------- */
const openDlg = (id) => document.getElementById(id)?.showModal();
$("#btnSend")?.addEventListener("click", () => openDlg("sendDialog"));
$("#btnTopup")?.addEventListener("click", () => openDlg("topupDialog"));
$("#ctaSendBtn")?.addEventListener("click", () => openDlg("sendDialog"));

$$("dialog").forEach((d) => {
  d.addEventListener("click", (e) => {
    if (e.target === d) d.close();
  });
  $$("[data-close]", d).forEach((b) => b.addEventListener("click", () => d.close()));
});

/* ---------- Flash: zacht verdwijnen ---------- */
setTimeout(() => {
  const f = $("#flashes");
  if (f) {
    f.style.transition = "opacity 0.8s";
    f.style.opacity = "0";
  }
}, 8000);
