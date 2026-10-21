import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth, onAuthStateChanged, signInWithEmailAndPassword, signOut
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import {
  getFirestore, doc, onSnapshot, setDoc, addDoc, collection, query, orderBy,
  limit, serverTimestamp
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const LABELS = {
  channels: "Canais do Telegram",
  sheet: "Planilha",
  scrape: "Raspagem (ML/Shopee)",
  coupons: "Cupons",
  instagram: "Instagram",
  telegram: "Publicação no Telegram"
};

const $ = (id) => document.getElementById(id);
const config = window.FIREBASE_CONFIG || {};
let app, db, auth;
let flagsAtuais = {};
let salvandoFlags = false;

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.style.display = "none"; }, 2600);
}

function fmtHora(ts) {
  if (!ts) return "nunca";
  return new Date(ts * 1000).toLocaleString("pt-BR");
}

function iniciarFirebase() {
  if (!config.apiKey || !config.projectId) {
    $("loginMsg").textContent = "Preencha panel/firebase-config.js com os dados do projeto.";
    return false;
  }
  app = initializeApp(config);
  auth = getAuth(app);
  db = getFirestore(app);
  return true;
}

function montarFlags() {
  const box = $("flags");
  box.textContent = "";
  Object.keys(LABELS).forEach((nome) => {
    const row = document.createElement("div");
    row.className = "row";
    const label = document.createElement("span");
    label.textContent = LABELS[nome];
    const sw = document.createElement("label");
    sw.className = "switch";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.flag = nome;
    input.addEventListener("change", () => salvarFlag(nome, input.checked));
    const span = document.createElement("span");
    sw.appendChild(input);
    sw.appendChild(span);
    row.appendChild(label);
    row.appendChild(sw);
    box.appendChild(row);
  });
  pintarFlags();
}

function pintarFlags() {
  document.querySelectorAll("input[data-flag]").forEach((input) => {
    input.checked = flagsAtuais[input.dataset.flag] !== false;
  });
}

async function salvarFlag(nome, valor) {
  flagsAtuais = { ...flagsAtuais, [nome]: valor };
  salvandoFlags = true;
  try {
    await setDoc(doc(db, "panel_control", "state"), {
      flags: flagsAtuais,
      updated_at: serverTimestamp(),
      updated_by: auth.currentUser ? auth.currentUser.email : ""
    }, { merge: true });
    toast(`${LABELS[nome]}: ${valor ? "ligado" : "desligado"}`);
  } catch (e) {
    toast("Falha ao salvar: " + e.message);
    pintarFlags();
  } finally {
    salvandoFlags = false;
  }
}

function montarStatus() {
  onSnapshot(doc(db, "panel_control", "state"), (snap) => {
    const dados = snap.data() || {};
    if (dados.flags && typeof dados.flags === "object") {
      flagsAtuais = dados.flags;
      if (!salvandoFlags) pintarFlags();
    }
  }, (e) => toast("Controle: " + e.message));

  onSnapshot(doc(db, "panel_status", "state"), (snap) => {
    const d = snap.data() || {};
    const online = d.online !== false;
    $("kOnline").innerHTML = "";
    const dot = document.createElement("span");
    dot.className = "dot " + (online ? "on" : "off");
    $("kOnline").appendChild(dot);
    $("kOnline").appendChild(document.createTextNode(online ? " on" : " off"));
    $("kSeen").textContent = d.seen ?? "—";
    $("kQueue").textContent = d.ig_queue ?? "—";
    $("kVitrine").textContent = (d.vitrine || []).length;
    $("tTelegram").textContent = fmtHora(d.last_telegram);
    $("tInstagram").textContent = fmtHora(d.last_instagram);
    $("tListener").textContent = fmtHora(d.last_listener);
    $("tUpdated").textContent = fmtHora(d.updated_at);
    $("logs").textContent = (d.logs || []).join("\n");
    renderVitrine(d.vitrine || []);
  }, (e) => toast("Status: " + e.message));

  const q = query(collection(db, "panel_commands"), orderBy("requested_at", "desc"), limit(6));
  onSnapshot(q, (snap) => {
    const box = $("comandos");
    box.textContent = "";
    if (snap.empty) {
      box.innerHTML = '<div class="cmd">Nenhum comando ainda.</div>';
      return;
    }
    snap.forEach((docSnap) => {
      const d = docSnap.data() || {};
      const div = document.createElement("div");
      div.className = "cmd " + (d.status || "pending");
      const titulo = document.createElement("b");
      titulo.textContent = `${d.type || "?"} — ${d.status || "?"}`;
      div.appendChild(titulo);
      if (d.result) {
        div.appendChild(document.createTextNode(" · " + d.result));
      }
      box.appendChild(div);
    });
  }, (e) => toast("Comandos: " + e.message));
}

function renderVitrine(itens) {
  const box = $("vitrine");
  box.textContent = "";
  if (!itens.length) {
    box.innerHTML = '<div class="muted">Vitrine vazia.</div>';
    return;
  }
  itens.forEach((item) => {
    const row = document.createElement("div");
    row.className = "item";
    if (item.image) {
      const img = document.createElement("img");
      img.src = item.image;
      img.alt = "";
      img.loading = "lazy";
      row.appendChild(img);
    }
    const info = document.createElement("div");
    info.className = "info";
    const titulo = document.createElement("b");
    titulo.textContent = item.title || "(sem título)";
    const meta = document.createElement("span");
    const preco = typeof item.price === "number"
      ? item.price.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
      : "sem preço";
    meta.textContent = `${preco} · ${item.time || ""} · ${item.id}`;
    info.appendChild(titulo);
    info.appendChild(meta);
    row.appendChild(info);
    const btn = document.createElement("button");
    btn.className = "danger";
    btn.textContent = "Remover";
    btn.addEventListener("click", () => removerItem(item, btn));
    row.appendChild(btn);
    box.appendChild(row);
  });
}

async function removerItem(item, btn) {
  if (!window.confirm(`Remover "${item.title || item.id}" da vitrine?`)) return;
  const repostar = $("repostar").checked;
  btn.disabled = true;
  try {
    await addDoc(collection(db, "panel_commands"), {
      type: "delete_vitrine",
      payload: { id: item.id, remove_from_seen: repostar },
      status: "pending",
      requested_at: serverTimestamp(),
      requested_by: auth.currentUser ? auth.currentUser.email : ""
    });
    toast("Remoção solicitada. O bot confirma em segundos.");
  } catch (e) {
    toast("Falha: " + e.message);
    btn.disabled = false;
  }
}

async function enviarComando(tipo) {
  try {
    await addDoc(collection(db, "panel_commands"), {
      type: tipo,
      payload: {},
      status: "pending",
      requested_at: serverTimestamp(),
      requested_by: auth.currentUser ? auth.currentUser.email : ""
    });
    toast("Comando enviado; o bot executa no próximo ciclo de sincronização.");
  } catch (e) {
    toast("Falha: " + e.message);
  }
}

function ligarEventos() {
  $("btnLogin").addEventListener("click", async () => {
    $("loginMsg").textContent = "";
    try {
      await signInWithEmailAndPassword(auth, $("email").value.trim(), $("password").value);
    } catch (e) {
      $("loginMsg").textContent = e.message;
    }
  });
  $("btnLogout").addEventListener("click", () => signOut(auth));
  document.querySelectorAll("button[data-cmd]").forEach((btn) => {
    btn.addEventListener("click", () => enviarComando(btn.dataset.cmd));
  });
}

function mostrarApp(logado) {
  $("login").classList.toggle("hide", logado);
  $("app").classList.toggle("hide", !logado);
  if (logado) {
    $("userEmail").textContent = auth.currentUser.email || "";
  }
}

if (iniciarFirebase()) {
  onAuthStateChanged(auth, (user) => {
    mostrarApp(!!user);
    if (user) {
      montarFlags();
      montarStatus();
    }
  });
  ligarEventos();
}
