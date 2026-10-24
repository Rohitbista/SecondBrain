const API = "http://localhost:8000";//window.API_BASE || "";
const $ = (s, r = document) => r.querySelector(s);
const view = $("#view");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = d => new Date(d).toLocaleString();
let token = localStorage.getItem("sb_token"), me = null, tab = "notes";

function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.className = ""), 3500);
}
const guard = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };

async function api(path, { method = "GET", json, form, raw } = {}) {
  const headers = {}; let body = form;
  if (token) headers.Authorization = "Bearer " + token;
  if (json) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  const r = await fetch(API + path, { method, headers, body });
  if (raw && r.ok) return r;
  if (r.status === 401 && token && path !== "/auth/login") { logout(); throw new Error("Session expired. Log in again."); }
  if (!r.ok) {
    let d; try { d = (await r.json()).detail; } catch {}
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(e => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ") : `Request failed (${r.status})`);
  }
  return r.status === 204 ? null : r.json();
}

function logout() { token = null; me = null; localStorage.removeItem("sb_token"); boot(); }
$("#logout").onclick = logout;

/* ---------- voice recording ---------- */
let rec = null;
async function toggleRec(btn, done) {
  if (rec) return rec.stop();
  const s = await navigator.mediaDevices.getUserMedia({ audio: true });
  const chunks = []; rec = new MediaRecorder(s);
  rec.ondataavailable = e => chunks.push(e.data);
  rec.onstop = () => {
    s.getTracks().forEach(t => t.stop());
    const b = new Blob(chunks, { type: rec.mimeType }); rec = null;
    btn.classList.remove("rec"); btn.textContent = btn.dataset.label;
    done(b, "rec." + (b.type.includes("mp4") ? "m4a" : b.type.includes("ogg") ? "ogg" : "webm"));
  };
  btn.dataset.label = btn.textContent; btn.textContent = "Stop recording";
  btn.classList.add("rec"); rec.start();
}
const audioForm = (b, name, extra = {}) => {
  const f = new FormData(); f.append("audio", b, name);
  for (const [k, v] of Object.entries(extra)) if (v) f.append(k, v);
  return f;
};

/* ---------- auth screens ---------- */
const field = (id, label, type = "text", extra = "") => `<label for="${id}">${label}</label><input id="${id}" type="${type}" ${extra}>`;
const v = id => $("#" + id).value;

function authScreen(mode = "login", note = "") {
  const forms = {
    login: `<h2>Log in</h2>${field("u", "Username or email")}${field("p", "Password", "password")}
      <p><button id="go">Log in</button></p>
      <div class="links"><a data-m="register">Create account</a><a data-m="forgot">Forgot password</a><a data-m="resend">Resend verification</a></div>`,
    register: `<h2>Create account</h2>${field("e", "Email", "email")}${field("fn", "First name")}${field("ln", "Last name")}
      ${field("u", "Username (3–30 letters, digits, _)")}${field("p", "Password (8+ characters)", "password")}
      <p><button id="go">Create account</button></p><div class="links"><a data-m="login">Back to log in</a></div>`,
    forgot: `<h2>Reset password</h2>${field("e", "Email", "email")}<p><button id="go">Send reset email</button></p><div class="links"><a data-m="login">Back to log in</a></div>`,
    resend: `<h2>Resend verification</h2>${field("e", "Email", "email")}<p><button id="go">Send verification email</button></p><div class="links"><a data-m="login">Back to log in</a></div>`,
    reset: `<h2>Choose a new password</h2>${field("t", "Reset token")}${field("p", "New password (8+ characters)", "password")}
      <p><button id="go">Update password</button></p><div class="links"><a data-m="login">Back to log in</a></div>`,
  };
  $("#top").hidden = true;
  view.innerHTML = `<div class="card auth">${note ? `<p class="mute">${esc(note)}</p>` : ""}${forms[mode]}</div>`;
  view.querySelectorAll("[data-m]").forEach(a => (a.onclick = () => authScreen(a.dataset.m)));
  if (mode === "reset") { const t = new URLSearchParams(location.search).get("reset"); if (t) $("#t").value = t; }
  const submit = guard(async () => {
    if (mode === "login") {
      const f = new URLSearchParams({ username: v("u"), password: v("p") });
      const r = await api("/auth/login", { method: "POST", form: f });
      token = r.access_token; localStorage.setItem("sb_token", token); boot();
    } else if (mode === "register") {
      await api("/auth/register", { method: "POST", json: { email: v("e"), first_name: v("fn"), last_name: v("ln"), username: v("u"), password: v("p") } });
      authScreen("login", "Account created. Check your email to verify it, then log in.");
    } else if (mode === "reset") {
      const r = await api("/auth/reset-password", { method: "POST", json: { token: v("t"), new_password: v("p") } });
      authScreen("login", r.message);
    } else {
      const r = await api(mode === "forgot" ? "/auth/forgot-password" : "/auth/resend-verification", { method: "POST", json: { email: v("e") } });
      authScreen("login", r.message);
    }
  });
  $("#go").onclick = submit;
  view.querySelectorAll("input").forEach(i => i.addEventListener("keydown", e => e.key === "Enter" && submit()));
}

/* ---------- shell ---------- */
async function boot() {
  const q = new URLSearchParams(location.search);
  if (q.get("verify") || q.get("token")) {   // link from the verification email: ?verify=<token>
    const t = q.get("verify") || q.get("token");
    history.replaceState(null, "", location.pathname);
    try { const r = await api("/auth/verify-email?token=" + encodeURIComponent(t)); return authScreen("login", r.message); }
    catch (e) { return authScreen("login", e.message); }
  }
  if (q.get("reset") && !token) return authScreen("reset");
  if (!token) return authScreen();
  try { me = await api("/auth/me"); } catch { return; }
  const tabs = ["notes", "search", "chat", "account", ...(me.is_admin ? ["admin"] : [])];
  $("#top").hidden = false;
  $("#nav").innerHTML = tabs.map(t => `<button data-t="${t}">${t[0].toUpperCase() + t.slice(1)}</button>`).join("");
  $("#nav").onclick = e => e.target.dataset.t && show(e.target.dataset.t);
  show(tabs.includes(tab) ? tab : "notes");
}
function show(t) {
  tab = t;
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("on", b.dataset.t === t));
  ({ notes: notesView, search: searchView, chat: chatView, account: accountView, admin: adminView })[t]();
}
const pager = (total, limit, offset) => `<div class="pager"><button class="ghost" data-pg="${offset - limit}" ${offset <= 0 ? "disabled" : ""}>Previous</button>
  <span class="mute">${total ? offset + 1 : 0}–${Math.min(offset + limit, total)} of ${total}</span>
  <button class="ghost" data-pg="${offset + limit}" ${offset + limit >= total ? "disabled" : ""}>Next</button></div>`;
const bindPager = (fn) => view.querySelectorAll("[data-pg]").forEach(b => (b.onclick = () => fn(+b.dataset.pg)));

/* ---------- notes ---------- */
function notesView(offset = 0, editing = null) {
  const limit = 10;
  view.innerHTML = `<h2>Notes</h2>
  <div class="card"><h3 id="fh">New note</h3>${field("nt", "Title", "text", 'maxlength="255"')}
    <label for="nc">Content</label><textarea id="nc"></textarea>
    <div class="row" style="margin-top:.7rem"><button id="save">Save note</button><button id="cancel" class="ghost" hidden>Cancel edit</button>
    <span class="sp"></span><button id="vn" class="ghost">Record voice note</button><button id="vt" class="ghost">Record and transcribe</button></div></div>
  <div class="row" style="margin-bottom:.7rem"><span class="mute">Your notes, newest first.</span><span class="sp"></span><button id="reidx" class="ghost">Rebuild embeddings</button></div>
  <div id="list"></div>`;
  if (editing) { $("#fh").textContent = "Edit note"; $("#nt").value = editing.title; $("#nc").value = editing.content; $("#cancel").hidden = false; }
  $("#cancel").onclick = () => notesView(offset);
  $("#save").onclick = guard(async () => {
    const json = { title: v("nt"), content: v("nc") };
    if (editing) await api("/notes/" + editing.id, { method: "PATCH", json }); else await api("/notes", { method: "POST", json });
    toast("Note saved."); notesView(editing ? offset : 0);
  });
  $("#vn").onclick = guard(() => toggleRec($("#vn"), guard(async (b, n) => {
    await api("/notes/voice", { method: "POST", form: audioForm(b, n, { title: v("nt") }) });
    toast("Voice note saved."); notesView(0);
  })));
  $("#vt").onclick = guard(() => toggleRec($("#vt"), guard(async (b, n) => {
    const r = await api("/notes/voice/transcribe", { method: "POST", form: audioForm(b, n) });
    $("#nc").value = (v("nc") ? v("nc") + "\n" : "") + r.text; toast("Transcript added. Review it, then save.");
  })));
  $("#reidx").onclick = guard(async () => { const r = await api("/notes/reindex", { method: "POST" }); toast(`Re-indexed ${r.reindexed} notes.`); });
  guard(async () => {
    const d = await api(`/notes?limit=${limit}&offset=${offset}`);
    $("#list").innerHTML = (d.items.length ? d.items.map(n => `<div class="card note"><h3>${esc(n.title)}<span class="mute">${fmt(n.updated_at)}</span></h3>
      <p>${esc(n.content)}</p><div class="row"><button class="ghost" data-e="${n.id}">Edit</button><button class="danger" data-d="${n.id}">Delete</button></div></div>`).join("")
      : `<p class="mute">No notes yet. Write one above or record a voice note.</p>`) + pager(d.total, limit, offset);
    bindPager(o => notesView(o));
    view.querySelectorAll("[data-e]").forEach(b => (b.onclick = guard(async () => notesView(offset, await api("/notes/" + b.dataset.e)))));
    view.querySelectorAll("[data-d]").forEach(b => (b.onclick = guard(async () => {
      if (!confirm("Delete this note?")) return;
      await api("/notes/" + b.dataset.d, { method: "DELETE" }); notesView(offset);
    })));
  })();
}

/* ---------- search ---------- */
function searchView() {
  view.innerHTML = `<h2>Search</h2><div class="card"><div class="row"><input id="q" placeholder="Search your notes" maxlength="500">
    <select id="mode" style="width:auto"><option value="">By meaning</option><option value="/keyword">By exact words</option></select>
    <button id="go">Search</button></div></div><div id="res"></div>`;
  const run = guard(async () => {
    if (!v("q").trim()) return;
    const hits = await api(`/search${v("mode")}?q=${encodeURIComponent(v("q"))}&limit=${v("mode") ? 20 : 5}`);
    $("#res").innerHTML = hits.length ? hits.map(h => `<div class="card note"><h3>${esc(h.title)}${h.score != null ? `<span class="mute">match ${(h.score * 100).toFixed(0)}%</span>` : ""}</h3><p>${esc(h.snippet)}</p></div>`).join("")
      : `<p class="mute">No notes matched. Try different words or switch search mode.</p>`;
  });
  $("#go").onclick = run; $("#q").onkeydown = e => e.key === "Enter" && run();
}

/* ---------- chat ---------- */
let sid = null;
function chatView() {
  view.innerHTML = `<h2>Ask your notes</h2><div class="chat"><aside class="card sess"><button id="newc" class="ghost">New chat</button><div id="hist" class="sess"></div>
    <button id="clr" class="danger">Clear all history</button></aside>
    <section class="card"><div id="msgs" class="msgs"></div>
    <div class="row"><input id="ask" maxlength="2000" placeholder="Ask a question about your notes"><button id="send">Ask</button><button id="mic" class="ghost">Ask by voice</button></div></section></div>`;
  const msgs = $("#msgs");
  const add = (role, text, sources) => {
    const d = document.createElement("div"); d.className = "m " + role; d.textContent = text;
    if (sources?.length) { const s = document.createElement("div"); s.className = "src"; s.textContent = "Sources: " + sources.map(x => x.title).join(", "); d.append(s); }
    msgs.append(d); msgs.scrollTop = msgs.scrollHeight; return d;
  };
  const loadHist = guard(async () => {
    const d = await api("/chat/history?limit=50");
    $("#hist").innerHTML = d.items.map(s => `<div class="item"><button class="ghost" data-s="${s.id}" title="${esc(s.title)}">${esc(s.title)}</button><button class="danger" data-x="${s.id}" aria-label="Delete chat">×</button></div>`).join("") || `<p class="mute">No saved chats yet.</p>`;
    view.querySelectorAll("[data-s]").forEach(b => (b.onclick = guard(async () => {
      const s = await api("/chat/history/" + b.dataset.s); sid = s.id; msgs.innerHTML = "";
      s.messages.forEach(m => add(m.role, m.content, m.sources));
    })));
    view.querySelectorAll("[data-x]").forEach(b => (b.onclick = guard(async () => {
      await api("/chat/history/" + b.dataset.x, { method: "DELETE" });
      if (sid == b.dataset.x) { sid = null; msgs.innerHTML = ""; } loadHist();
    })));
  });
  loadHist();
  $("#newc").onclick = () => { sid = null; msgs.innerHTML = ""; };
  $("#clr").onclick = guard(async () => { if (!confirm("Delete all chat history?")) return; await api("/chat/history", { method: "DELETE" }); sid = null; msgs.innerHTML = ""; loadHist(); });

  const send = guard(async () => {
    const q = v("ask").trim(); if (!q) return;
    $("#ask").value = ""; add("user", q); const bubble = add("assistant", "…"); let text = "", src = [];
    $("#send").disabled = true;
    try {
      const r = await api("/chat/ask/stream", { method: "POST", json: { question: q, session_id: sid }, raw: true });
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await rd.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let i; while ((i = buf.indexOf("\n\n")) >= 0) {
          const blk = buf.slice(0, i); buf = buf.slice(i + 2);
          const ev = /^event:\s*(.*)$/m.exec(blk)?.[1]?.trim(), raw = blk.split("\n").filter(l => l.startsWith("data:")).map(l => l.slice(5).trim()).join("");
          if (!raw) continue; const d = JSON.parse(raw);
          if (ev === "token") { text += d.text; bubble.textContent = text; msgs.scrollTop = msgs.scrollHeight; }
          else if (ev === "sources") src = d.sources;
          else if (ev === "done") sid = d.session_id;
          else if (ev === "error") throw new Error(d.message || d.detail || "The answer failed. Try again.");
        }
      }
      bubble.textContent = text || "No answer returned.";
      if (src.length) { const s = document.createElement("div"); s.className = "src"; s.textContent = "Sources: " + src.map(x => x.title).join(", "); bubble.append(s); }
      loadHist();
    } catch (e) { bubble.remove(); throw e; } finally { $("#send").disabled = false; }
  });
  $("#send").onclick = send; $("#ask").onkeydown = e => e.key === "Enter" && send();
  $("#mic").onclick = guard(() => toggleRec($("#mic"), guard(async (b, n) => {
    const r = await api("/chat/voice/ask", { method: "POST", form: audioForm(b, n, { session_id: sid }) });
    sid = r.session_id; add("user", r.transcript); add("assistant", r.answer, r.sources);
    if (r.audio_base64) new Audio(`data:${r.audio_mime};base64,${r.audio_base64}`).play();
    loadHist();
  })));
}

/* ---------- account ---------- */
function accountView() {
  view.innerHTML = `<h2>Account</h2>
  <div class="card"><h3>Profile</h3><p class="mute">${esc(me.email)}${me.is_verified ? "" : " (not verified)"} · joined ${fmt(me.created_at)}</p>
    ${field("fn", "First name", "text", `value="${esc(me.first_name)}"`)}${field("ln", "Last name", "text", `value="${esc(me.last_name)}"`)}${field("un", "Username", "text", `value="${esc(me.username)}"`)}
    <p><button id="sp">Save profile</button></p></div>
  <div class="card"><h3>Change password</h3>${field("cp", "Current password", "password")}${field("np", "New password (8+ characters)", "password")}<p><button id="pw">Change password</button></p></div>
  <div class="card"><h3>Delete account</h3><p class="mute">This permanently deletes your account and all your notes.</p>${field("dp", "Confirm with your password", "password")}<p><button id="del" class="danger">Delete my account</button></p></div>`;
  $("#sp").onclick = guard(async () => {
    me = await api("/users/me", { method: "PATCH", json: { first_name: v("fn"), last_name: v("ln"), username: v("un") } }); toast("Profile saved.");
  });
  $("#pw").onclick = guard(async () => {
    const r = await api("/users/me/change-password", { method: "POST", json: { current_password: v("cp"), new_password: v("np") } });
    $("#cp").value = $("#np").value = ""; toast(r.message);
  });
  $("#del").onclick = guard(async () => {
    if (!confirm("Delete your account permanently?")) return;
    await api("/users/me", { method: "DELETE", json: { password: v("dp") } }); logout();
  });
}

/* ---------- admin ---------- */
function adminView(offset = 0) {
  const limit = 20;
  view.innerHTML = `<h2>Admin</h2><div id="st" class="stats"></div>
  <div class="card row"><input id="s" placeholder="Search users" maxlength="100"><select id="fv" style="width:auto"><option value="">Any verification</option><option value="true">Verified</option><option value="false">Unverified</option></select>
    <select id="fa" style="width:auto"><option value="">Any role</option><option value="true">Admins</option><option value="false">Non-admins</option></select><button id="go">Filter</button></div>
  <div class="card wrap" id="us"></div>`;
  guard(async () => {
    const s = await api("/admin/stats");
    $("#st").innerHTML = [["Users", s.total_users], ["Verified", s.verified_users], ["Notes", s.total_notes], ["Notes per user", s.avg_notes_per_user.toFixed(1)]].map(([k, x]) => `<div><b>${x}</b>${k}</div>`).join("");
  })();
  const load = guard(async (o = 0) => {
    const p = new URLSearchParams({ limit, offset: o });
    if (v("s").trim()) p.set("search", v("s").trim()); if (v("fv")) p.set("is_verified", v("fv")); if (v("fa")) p.set("is_admin", v("fa"));
    const d = await api("/admin/users?" + p);
    $("#us").innerHTML = `<table><tr><th>User</th><th>Email</th><th>Verified</th><th>Admin</th><th></th></tr>${d.items.map(u => `<tr><td>${esc(u.username)}</td><td>${esc(u.email)}</td>
      <td><button class="ghost" data-v="${u.id}" data-val="${!u.is_verified}">${u.is_verified ? "Yes" : "No"}</button></td>
      <td><button class="ghost" data-a="${u.id}" data-val="${!u.is_admin}">${u.is_admin ? "Yes" : "No"}</button></td>
      <td><button class="ghost" data-i="${u.id}">Notes</button> <button class="danger" data-x="${u.id}">Delete</button></td></tr>`).join("")}</table>` + pager(d.total, limit, o);
    bindPager(load);
    const patch = (sel, key) => view.querySelectorAll(sel).forEach(b => (b.onclick = guard(async () => {
      await api("/admin/users/" + b.dataset[key === "is_verified" ? "v" : "a"], { method: "PATCH", json: { [key]: b.dataset.val === "true" } }); load(o);
    })));
    patch("[data-v]", "is_verified"); patch("[data-a]", "is_admin");
    view.querySelectorAll("[data-i]").forEach(b => (b.onclick = guard(async () => { const u = await api("/admin/users/" + b.dataset.i); toast(`${u.username} has ${u.notes_count} notes.`); })));
    view.querySelectorAll("[data-x]").forEach(b => (b.onclick = guard(async () => {
      if (!confirm("Delete this user and their notes?")) return; await api("/admin/users/" + b.dataset.x, { method: "DELETE" }); load(o);
    })));
  });
  $("#go").onclick = () => load(0); load(0);
}

boot();