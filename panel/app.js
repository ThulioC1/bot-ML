window.__painelIniciou = true;

const LABELS = {
  channels: "Canais do Telegram",
  sheet: "Planilha",
  scrape: "Raspagem (ML/Shopee)",
  coupons: "Cupons",
  instagram: "Instagram",
  telegram: "Publicação no Telegram"
};

const HINTS = {
  channels: "Repassa as ofertas dos canais parceiros",
  sheet: "Lê os produtos da planilha do Google",
  scrape: "Busca ofertas no Mercado Livre e na Shopee",
  coupons: "Publica os cupons ativos do Mercado Livre",
  instagram: "Monta a fila e publica no Instagram",
  telegram: "Publica as ofertas no canal e no grupo"
};

const SDK_VERSION = "10.12.2";
const SDK = "https://www.gstatic.com/firebasejs/" + SDK_VERSION + "/";

const $ = (id) => document.getElementById(id);

let A = null;
let F = null;
let db = null;
let auth = null;
let flagsAtuais = {};
let salvandoFlags = false;

function msg(texto) {
  $("loginMsg").textContent = texto;
}

function toast(texto) {
  const el = $("toast");
  el.textContent = texto;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 2600);
}

function fmtHora(ts) {
  if (!ts) return "nunca";
  return new Date(ts * 1000).toLocaleString("pt-BR");
}

const proximos = {
  telegram: { ts: 0, ativo: false, rotulo: "próximo em" },
  instagram: { ts: 0, ativo: false, rotulo: "próximo em" },
  channels: { ts: 0, ativo: false, rotulo: "lote em" }
};
let offlineAtual = false;

function pad2(n) {
  return String(n).padStart(2, "0");
}

function fmtContagem(segundos) {
  const total = Math.max(0, Math.ceil(segundos));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return (h ? h + ":" + pad2(m) : String(m)) + ":" + pad2(s);
}

function definirProximo(nome, ts, ativo) {
  proximos[nome].ts = Number(ts) || 0;
  proximos[nome].ativo = !!ativo;
}

function pintarContagem(id, item) {
  const el = $(id);
  if (!item.ativo) {
    el.textContent = "desligado";
    el.classList.add("off");
    return;
  }
  if (offlineAtual) {
    el.textContent = "offline";
    el.classList.add("off");
    return;
  }
  if (!item.ts) {
    el.textContent = "—";
    el.classList.add("off");
    return;
  }
  const seg = item.ts - Date.now() / 1000;
  el.textContent = seg <= 0
    ? "agora"
    : item.rotulo + " " + fmtContagem(seg);
  el.classList.remove("off");
}

function tickContagens() {
  pintarContagem("cTelegram", proximos.telegram);
  pintarContagem("cInstagram", proximos.instagram);
  pintarContagem("cChannels", proximos.channels);
}

function mostrarApp(logado) {
  $("login").classList.toggle("hide", logado);
  $("app").classList.toggle("hide", !logado);
  if (logado && auth.currentUser) {
    $("userEmail").textContent = auth.currentUser.email || "";
  }
}

function pintarFlags() {
  document.querySelectorAll("input[data-flag]").forEach((input) => {
    input.checked = flagsAtuais[input.dataset.flag] !== false;
  });
}

function montarFlags() {
  const box = $("flags");
  box.textContent = "";
  Object.keys(LABELS).forEach((nome) => {
    const row = document.createElement("div");
    row.className = "row";
    const info = document.createElement("div");
    info.className = "flag-info";
    const label = document.createElement("b");
    label.textContent = LABELS[nome];
    const hint = document.createElement("span");
    hint.className = "flag-hint";
    hint.textContent = HINTS[nome] || "";
    info.appendChild(label);
    info.appendChild(hint);
    const sw = document.createElement("label");
    sw.className = "switch";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.flag = nome;
    input.addEventListener("change", () => salvarFlag(nome, input.checked));
    const span = document.createElement("span");
    sw.appendChild(input);
    sw.appendChild(span);
    row.appendChild(info);
    row.appendChild(sw);
    box.appendChild(row);
  });
  pintarFlags();
}

async function salvarFlag(nome, valor) {
  flagsAtuais = { ...flagsAtuais, [nome]: valor };
  if (proximos[nome]) {
    proximos[nome].ativo = valor;
    tickContagens();
  }
  salvandoFlags = true;
  try {
    await F.setDoc(F.doc(db, "panel_control", "state"), {
      flags: flagsAtuais,
      updated_at: F.serverTimestamp(),
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
    const meta = document.createElement("div");
    meta.className = "meta";
    if (typeof item.price === "number") {
      const preco = document.createElement("span");
      preco.className = "price";
      preco.textContent = item.price.toLocaleString("pt-BR", {
        style: "currency", currency: "BRL"
      });
      meta.appendChild(preco);
    }
    const detalhe = document.createElement("span");
    detalhe.className = "muted";
    detalhe.textContent = [item.time, item.id].filter(Boolean).join(" · ");
    meta.appendChild(detalhe);
    if (item.link && /^https?:\/\//i.test(item.link)) {
      const abrir = document.createElement("a");
      abrir.className = "open";
      abrir.textContent = "Abrir";
      abrir.href = item.link;
      abrir.target = "_blank";
      abrir.rel = "noopener noreferrer";
      meta.appendChild(abrir);
    }
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

function renderFilaIg(itens) {
  const box = $("filaIg");
  const contador = $("qCount");
  box.textContent = "";
  contador.textContent = itens.length
    ? itens.length + (itens.length === 1 ? " item na fila" : " itens na fila")
    : "fila vazia";
  if (!itens.length) {
    box.innerHTML = '<div class="muted">Nenhum post aguardando.</div>';
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
    const meta = document.createElement("div");
    meta.className = "meta";
    if (typeof item.price === "number") {
      const preco = document.createElement("span");
      preco.className = "price";
      preco.textContent = item.price.toLocaleString("pt-BR", {
        style: "currency", currency: "BRL"
      });
      meta.appendChild(preco);
    }
    const detalhe = document.createElement("span");
    detalhe.className = "muted";
    detalhe.textContent = item.id || "sem id";
    meta.appendChild(detalhe);
    if (item.link && /^https?:\/\//i.test(item.link)) {
      const abrir = document.createElement("a");
      abrir.className = "open";
      abrir.textContent = "Abrir";
      abrir.href = item.link;
      abrir.target = "_blank";
      abrir.rel = "noopener noreferrer";
      meta.appendChild(abrir);
    }
    info.appendChild(titulo);
    info.appendChild(meta);
    row.appendChild(info);
    const btn = document.createElement("button");
    btn.className = "danger";
    btn.textContent = "Excluir";
    btn.title = "Remove só da fila do Instagram; a vitrine não muda.";
    btn.addEventListener("click", () => removerFila(item, btn));
    row.appendChild(btn);
    box.appendChild(row);
  });
}

async function removerFila(item, btn) {
  if (!window.confirm(`Excluir "${item.title || item.qid}" da fila do Instagram?`)) return;
  btn.disabled = true;
  try {
    await F.addDoc(F.collection(db, "panel_commands"), {
      type: "delete_ig_queue",
      payload: { qid: item.qid },
      status: "pending",
      requested_at: F.serverTimestamp(),
      requested_by: auth.currentUser ? auth.currentUser.email : ""
    });
    toast("Exclusão solicitada. O bot confirma em segundos.");
  } catch (e) {
    toast("Falha: " + e.message);
    btn.disabled = false;
  }
}

async function removerItem(item, btn) {
  if (!window.confirm(`Remover "${item.title || item.id}" da vitrine?`)) return;
  const repostar = $("repostar").checked;
  btn.disabled = true;
  try {
    await F.addDoc(F.collection(db, "panel_commands"), {
      type: "delete_vitrine",
      payload: { id: item.id, remove_from_seen: repostar },
      status: "pending",
      requested_at: F.serverTimestamp(),
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
    await F.addDoc(F.collection(db, "panel_commands"), {
      type: tipo,
      payload: {},
      status: "pending",
      requested_at: F.serverTimestamp(),
      requested_by: auth.currentUser ? auth.currentUser.email : ""
    });
    toast("Comando enviado; o bot executa no próximo ciclo de sincronização.");
  } catch (e) {
    toast("Falha: " + e.message);
  }
}

function renderLogs(linhas) {
  const box = $("logs");
  box.textContent = "";
  if (!linhas.length) {
    box.innerHTML = '<span class="muted">Nenhum log recebido ainda.</span>';
    return;
  }
  linhas.forEach((linha) => {
    const div = document.createElement("div");
    div.className = "log-line";
    if (linha.includes("❌")) div.classList.add("err");
    else if (linha.includes("⚠️")) div.classList.add("warn");
    else if (linha.includes("✅")) div.classList.add("ok");
    div.textContent = linha;
    box.appendChild(div);
  });
  box.scrollTop = box.scrollHeight;
}

function montarStatus() {
  F.onSnapshot(F.doc(db, "panel_control", "state"), (snap) => {
    const dados = snap.data() || {};
    if (dados.flags && typeof dados.flags === "object") {
      flagsAtuais = dados.flags;
      if (!salvandoFlags) pintarFlags();
    }
  }, (e) => toast("Controle: " + e.message));

  F.onSnapshot(F.doc(db, "panel_status", "state"), (snap) => {
    const d = snap.data() || {};
    const online = d.online !== false;
    offlineAtual = !online;
    const kOnline = $("kOnline");
    kOnline.textContent = "";
    const dot = document.createElement("span");
    dot.className = "dot " + (online ? "on" : "off");
    kOnline.appendChild(dot);
    kOnline.appendChild(document.createTextNode(online ? " online" : " offline"));
    const fila = Array.isArray(d.ig_queue_items) ? d.ig_queue_items : [];
    $("kSeen").textContent = d.seen ?? "—";
    $("kQueue").textContent = d.ig_queue ?? fila.length;
    $("kVitrine").textContent = (d.vitrine || []).length;
    $("tTelegram").textContent = fmtHora(d.last_telegram);
    $("tInstagram").textContent = fmtHora(d.last_instagram);
    $("tListener").textContent = fmtHora(d.last_listener);
    $("tUpdated").textContent = fmtHora(d.updated_at);
    const flags = (d.flags && typeof d.flags === "object") ? d.flags : flagsAtuais;
    definirProximo("telegram", d.next_telegram, flags.telegram !== false);
    definirProximo("instagram", d.next_instagram, flags.instagram !== false);
    definirProximo("channels", d.next_channels, flags.channels !== false);
    tickContagens();
    renderLogs(d.logs || []);
    renderFilaIg(fila);
    renderVitrine(d.vitrine || []);
  }, (e) => toast("Status: " + e.message));

  const q = F.query(F.collection(db, "panel_commands"),
                    F.orderBy("requested_at", "desc"), F.limit(6));
  F.onSnapshot(q, (snap) => {
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

function ligarEventos() {
  $("btnLogin").addEventListener("click", async () => {
    msg("");
    if (!auth) {
      msg("Firebase não inicializado. Veja o erro acima e o console (F12).");
      return;
    }
    const email = $("email").value.trim();
    const senha = $("password").value;
    if (!email || !senha) {
      msg("Preencha e-mail e senha.");
      return;
    }
    $("btnLogin").disabled = true;
    try {
      await A.signInWithEmailAndPassword(auth, email, senha);
    } catch (e) {
      msg("Login falhou: " + e.code + " — " + e.message);
    } finally {
      $("btnLogin").disabled = false;
    }
  });

  $("password").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") $("btnLogin").click();
  });

  $("btnLogout").addEventListener("click", () => A.signOut(auth));

  document.querySelectorAll("button[data-cmd]").forEach((btn) => {
    btn.addEventListener("click", () => enviarComando(btn.dataset.cmd));
  });
}

async function iniciar() {
  ligarEventos();
  const config = window.FIREBASE_CONFIG || {};
  const faltando = ["apiKey", "authDomain", "projectId", "appId"]
    .filter((chave) => !config[chave]);
  if (faltando.length) {
    msg("Config incompleta em panel/firebase-config.js. Falta: " + faltando.join(", "));
    return;
  }
  try {
    const [appMod, authMod, dbMod] = await Promise.all([
      import(SDK + "firebase-app.js"),
      import(SDK + "firebase-auth.js"),
      import(SDK + "firebase-firestore.js")
    ]);
    A = authMod;
    F = dbMod;
    const app = appMod.initializeApp(config);
    auth = A.getAuth(app);
    db = F.getFirestore(app);
  } catch (e) {
    msg("Falha ao carregar o SDK do Firebase: " + e.message +
        " (verifique a conexão; gstatic.com precisa estar acessível)");
    return;
  }
  A.onAuthStateChanged(auth, (user) => {
    mostrarApp(!!user);
    if (user) {
      msg("");
      montarFlags();
      montarStatus();
    }
  });
}

setInterval(tickContagens, 1000);
iniciar();
