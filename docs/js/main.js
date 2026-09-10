/* bodeuro — statische frontend (GitHub Pages) ↔ PythonAnywhere API */

const API = location.hostname.endsWith(".github.io")
  ? "https://V1rprogram.pythonanywhere.com"
  : "";

const $ = (s, c = document) => c.querySelector(s);
const $$ = (s, c = document) => [...c.querySelectorAll(s)];
const fmt = new Intl.NumberFormat("nl-NL", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

/* ---------- toast ---------- */
function toast(msg, type = "success") {
  const box = $("#toasts");
  if (!box) return;
  const t = document.createElement("div");
  t.className = "toast toast-" + type;
  t.innerHTML = msg;
  box.appendChild(t);
  requestAnimationFrame(() => t.classList.add("show"));
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => t.remove(), 350);
  }, 4200);
}

/* ---------- API ---------- */
async function api(path, body) {
  const opts = { method: body ? "POST" : "GET", credentials: "include" };
  if (body) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(API + path, opts);
  let data = {};
  try { data = await r.json(); } catch (e) { /* leeg */ }
  return { status: r.status, data };
}

function openDlg(id) { document.getElementById(id)?.showModal(); }

/* ---------- algemene pagina-elementen ---------- */
function initCommon() {
  // mobiel menu (alleen op index aanwezig)
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
  // reveal-animaties + voortgangsbalken
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
  // dialogs sluiten op backdrop / X
  $$("dialog").forEach((d) => {
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
    $$("[data-close]", d).forEach((b) => b.addEventListener("click", () => d.close()));
  });
}

/* ---------- home ---------- */
function countUp(el, target, dur = 1500) {
  const start = performance.now();
  (function tick(now) {
    const p = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt.format(target * eased);
    if (p < 1) requestAnimationFrame(tick);
  })(start);
}

async function initHome() {
  const card = $("#bankcard");
  if (card) {
    card.addEventListener("mousemove", (e) => {
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform =
        `perspective(900px) rotateY(${x * 9}deg) rotateX(${-y * 9}deg)`;
    });
    card.addEventListener("mouseleave", () => (card.style.transform = ""));
  }

  $("#btnHistory")?.addEventListener("click", () =>
    $("#transacties")?.scrollIntoView({ behavior: "smooth", block: "center" })
  );
  $("#btnSend")?.addEventListener("click", () => openDlg("sendDialog"));
  $("#btnTopup")?.addEventListener("click", () => openDlg("topupDialog"));
  $("#ctaSendBtn")?.addEventListener("click", () => openDlg("sendDialog"));
  $("#btnBlock")?.addEventListener("click", async () => {
    const { data } = await api("/api/card");
    toast(data.ok ? data.message : `❌ ${data.error}`, data.ok ? "success" : "error");
    loadHome();
  });
  $("#heroLogout")?.addEventListener("click", async () => {
    await api("/api/logout");
    toast("👋 Tot de volgende les. Je bodeuro slaapt veilig.");
    loadHome();
  });

  $("#sendForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const { data } = await api("/api/transfer", {
      ontvanger: f.get("ontvanger"),
      bedrag: f.get("bedrag"),
    });
    toast(data.ok ? data.message : `❌ ${data.error}`, data.ok ? "success" : "error");
    if (data.ok) e.target.reset();
    loadHome();
  });

  $("#topupForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const { data } = await api("/api/topup", { bedrag: f.get("bedrag") });
    toast(data.ok ? data.message : `❌ ${data.error}`, data.ok ? "success" : "error");
    if (data.ok) e.target.reset();
    loadHome();
  });

  loadHome();
}

async function loadHome() {
  const { data } = await api("/api/me");
  const u = data.user;

  $("#heroPub").hidden = !!u;
  $("#heroUser").hidden = !u;
  $("#ovLocked").hidden = !!u;
  $("#ovUser").hidden = !u;
  $("#ctaPub").hidden = !!u;
  $("#ctaUser").hidden = !u;

  // nav
  $("#navActions").innerHTML = u
    ? `<span class="user-chip" title="Ingelogd als ${esc(u.naam)}">👤 ${esc(u.username)}</span>
       <button class="btn btn-ghost" id="navLogout" type="button">Uitloggen</button>`
    : `<a class="btn btn-ghost" href="login.html">Inloggen</a>
       <a class="btn btn-primary" href="account.html">Open een rekening</a>`;
  $("#navLogout")?.addEventListener("click", async () => {
    await api("/api/logout");
    toast("👋 Tot de volgende les. Je bodeuro slaapt veilig.");
    loadHome();
  });

  if (!u) {
    $("#ovTitle").textContent = "Jouw rekening, privé";
    $("#ovSub").textContent =
      "Niemand toont zomaar een saldo aan toevallige bezoekers. Log in en het overzicht opent zich.";
    $("#cardNumber").textContent = "•••• •••• •••• ••••";
    $("#cardHolder").textContent = "Na inloggen";
    $("#cardDept").textContent = "—";
    $("#cardLocked").hidden = false;
    $("#bankcard").classList.remove("blocked");
    $("#chipPub1").hidden = false; $("#chipPub2").hidden = false;
    $("#chipUser1").hidden = true;  $("#chipUser2").hidden = true;
    return;
  }

  // ingelogd
  $("#ovTitle").textContent = "Jouw rekening, live";
  $("#ovSub").textContent = `Het officiële saldoverzicht van ${u.naam} — zichtbaar voor jou en de leraar.`;
  $("#userChipHero").innerHTML =
    `👤 ${esc(u.naam)} · ${esc(u.klantnr)}${u.is_admin ? " · 👑 admin" : ""}`;
  $("#welcomeH1").innerHTML =
    `Welkom terug, <span class="gold">${esc(u.naam.split(" ")[0])}</span>.`;

  if (u.is_admin) {
    $("#saldoWrap").innerHTML =
      `<span class="gold">∞</span> <span class="saldo-cur">BDE</span>`;
    $("#saldoEquiv").innerHTML =
      "oneindig · <span class='pos'>alleen jij ziet dit cijfer</span>";
  } else {
    $("#saldoWrap").innerHTML =
      `<span id="saldo">0,00</span> <span class="saldo-cur">BDE</span>`;
    $("#saldoEquiv").innerHTML =
      `= € ${fmt.format(u.saldo)} · <span class="pos">je bent miljonair in respect</span>`;
    const el = $("#saldo");
    if (el) countUp(el, u.saldo);
  }

  $("#cardNumber").textContent = u.card_number;
  $("#cardHolder").textContent = u.naam.toUpperCase();
  $("#cardDept").textContent = u.klas || "—";
  $("#cardLocked").hidden = true;
  $("#bankcard").classList.toggle("blocked", u.card_blocked);
  $("#btnBlock").innerHTML = u.card_blocked
    ? '<span class="qa-icon">🔓</span> Kaart opheffen'
    : '<span class="qa-icon">🔒</span> Kaart blokkeren';

  $("#txList").innerHTML = data.txs.map((t) => `
    <li class="tx">
      <span class="tx-icon">${t.icon}</span>
      <span class="tx-info"><b>${esc(t.omschrijving)}</b><small>${esc(t.when)}</small></span>
      <span class="tx-amount ${t.bedrag > 0 ? "pos" : ""}">
        ${t.bedrag > 0 ? "+" : "−"} ${fmt.format(Math.abs(t.bedrag))} BDE
      </span>
    </li>`).join("");

  $("#userDetails").innerHTML = `
    <div class="user-row"><span>Gebruikersnaam</span><span>${esc(u.username)}</span></div>
    <div class="user-row"><span>Email</span><span>${esc(u.email)}</span></div>
    <div class="user-row"><span>Klantnummer</span><span>${esc(u.klantnr)}</span></div>`;

  $("#sendNote").textContent =
    `Saldo: ${u.is_admin ? "∞" : fmt.format(u.saldo)} BDE · overdracht direct na de bel`;
  $("#ctaUserText").textContent =
    `Kaartnummer ${u.card_number} · Klantnummer ${u.klantnr} · 1 BDE = €1,00, altijd.`;

  $("#chipPub1").hidden = true;  $("#chipPub2").hidden = true;
  $("#chipUser1").hidden = false; $("#chipUser2").hidden = false;
}

/* ---------- inloggen (2 stappen) ---------- */
async function initLogin() {
  const step1 = $("#loginStep1");
  const step2 = $("#loginStep2");

  $("#loginForm1").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const { data } = await api("/api/login", {
      username: f.get("username"),
      password: f.get("password"),
    });
    if (!data.ok) {
      if (data.code === "unverified") {
        sessionStorage.setItem("bodeuro_verify_email", (f.get("username") || "").toString());
        toast(data.error, "error");
        location.assign("verify.html");
      } else {
        toast(`❌ ${data.error}`, "error");
      }
      return;
    }
    if (data.step === "done") {
      toast(data.message);
      location.assign("index.html");
      return;
    }
    step1.hidden = true;
    step2.hidden = false;
    toast(data.message);
    if (data.demo_code) {
      $("#loginDemo").hidden = false;
      $("#loginDemoCode").textContent = data.demo_code;
    }
  });

  $("#loginForm2").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const { data } = await api("/api/login/code", { code: f.get("code") });
    if (data.ok) {
      toast(data.message);
      location.assign("index.html");
      return;
    }
    toast(`❌ ${data.error}`, "error");
    step2.hidden = true;
    step1.hidden = false;
    $("#loginDemo").hidden = true;
  });

  $("#loginRestart").addEventListener("click", (e) => {
    e.preventDefault();
    step2.hidden = true;
    step1.hidden = false;
    $("#loginDemo").hidden = true;
  });
}

/* ---------- rekening openen ---------- */
async function initSignup() {
  $("#signupForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const payload = {
      naam: f.get("naam"),
      username: f.get("username"),
      email: f.get("email"),
      password: f.get("password"),
      klas: f.get("klas"),
      motivatie: f.get("motivatie"),
    };
    const { data } = await api("/api/signup", payload);
    if (!data.ok) {
      toast(`❌ ${data.error}`, "error");
      return;
    }
    if (data.demo_code) {
      sessionStorage.setItem("bodeuro_demo_verify", data.demo_code);
    }
    sessionStorage.setItem("bodeuro_verify_email", (f.get("email") || "").toString());
    toast(data.message);
    location.assign("verify.html");
  });
}

/* ---------- email verifiëren ---------- */
function initVerify() {
  const storedEmail = sessionStorage.getItem("bodeuro_verify_email") || "";
  $("#verifyEmail").value = storedEmail;
  $("#resendEmail").value = storedEmail;

  const storedCode = sessionStorage.getItem("bodeuro_demo_verify");
  if (storedCode) {
    $("#verifyDemo").hidden = false;
    $("#verifyDemoCode").textContent = storedCode;
  }

  const showDemo = (code) => {
    if (!code) return;
    sessionStorage.setItem("bodeuro_demo_verify", code);
    $("#verifyDemo").hidden = false;
    $("#verifyDemoCode").textContent = code;
  };

  $("#verifyForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const { data } = await api("/api/verify", {
      email: f.get("email"),
      code: f.get("code"),
    });
    if (data.ok) {
      sessionStorage.removeItem("bodeuro_demo_verify");
      sessionStorage.removeItem("bodeuro_verify_email");
      toast(data.message);
      location.assign("index.html");
      return;
    }
    toast(`❌ ${data.error}`, "error");
  });

  $("#resendForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const { data } = await api("/api/verify/resend", { email: f.get("email") });
    if (data.ok) {
      toast(data.message);
      showDemo(data.demo_code);
    } else {
      toast(`❌ ${data.error}`, "error");
    }
  });
}

/* ---------- start ---------- */
document.addEventListener("DOMContentLoaded", () => {
  initCommon();
  if ($("#heroPub")) initHome();
  if ($("#loginForm1")) initLogin();
  if ($("#signupForm")) initSignup();
  if ($("#verifyForm")) initVerify();
});
