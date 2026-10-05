<script>
  let session = null;
  let page = "desk"; // desk 报测缝 | gate 放行专页
  let logs = [];
  let zones = [];
  let events = [];
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let zoneCode = "";
  let chainage = "";
  let deltaMm = "";
  let error = "";
  let notice = "";
  let loading = false;
  let timer;

  $: isWriter = session?.role === "writer";
  $: canForeman = session?.role === "foreman" || (session?.perms || []).includes("foreman");
  $: zoneMap = Object.fromEntries(zones.map((z) => [z.code, z]));
  $: waitingZones = zones.filter((z) => z.status === "waiting" || z.status === "rejected" || z.status === "closed");
  $: openZones = zones.filter((z) => z.status === "open");
  $: selectedZone = zoneMap[zoneCode] || null;
  $: writeOpen = selectedZone?.status === "open";

  const ACTION_TEXT = {
    request: "提交开放申请",
    approve: "值班长点头放行",
    reject: "值班长驳回申请",
  };

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refresh() {
    if (!session) return;
    const zres = await fetch("/api/zones", { headers: headers() });
    if (zres.status === 401) return logout();
    if (zres.ok) zones = await zres.json();
    if (page === "desk") {
      const res = await fetch("/api/logs", { headers: headers() });
      if (res.ok) logs = await res.json();
    } else {
      const res = await fetch("/api/gate-events", { headers: headers() });
      if (res.ok) events = await res.json();
    }
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = {
        token: data.access_token,
        username: data.username,
        role: data.role,
        perms: data.perms || [],
      };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function fillAccount(u, p) {
    loginUser = u;
    loginPass = p;
    error = "";
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    zones = [];
    events = [];
    localStorage.removeItem("tunnel_session");
  }

  function flashError(msg) {
    error = msg;
    setTimeout(() => (error = ""), 4000);
  }

  function flashNotice(msg) {
    notice = msg;
    setTimeout(() => (notice = ""), 4000);
  }

  async function apiPost(path, okMsg) {
    error = "";
    notice = "";
    try {
      const res = await fetch(path, { method: "POST", headers: headers() });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "操作失败";
        return false;
      }
      if (okMsg) flashNotice(okMsg);
      await refresh();
      return true;
    } catch {
      error = "网络异常";
      return false;
    }
  }

  async function submit() {
    error = "";
    notice = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ zone_code: zoneCode, chainage, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 后端写口门禁退回：界面再漂亮也以后端判定为准
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      flashNotice("送单成功，已进入待认领");
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  async function switchPage(p) {
    page = p;
    error = "";
    notice = "";
    await refresh();
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", { hour12: false });
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  header {
    background: #0c0a09;
    border-bottom: 1px solid #44403c;
    padding: 0.75rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
  }
  header .brand {
    color: #fbbf24; margin: 0; font-size: 1.15rem; cursor: pointer;
    background: none; border: none; padding: 0; font-weight: 700;
  }
  header nav { display: flex; gap: 0.5rem; }
  header .spacer { flex: 1; }
  header .who { color: #a8a29e; font-size: 0.85rem; }
  .navbtn {
    background: transparent; border: 1px solid #57534e; color: #d6d3d1;
    padding: 0.3rem 0.8rem; border-radius: 6px; font-weight: 500;
  }
  .navbtn.active { background: #d97706; border-color: #d97706; color: #fff; }
  main { max-width: 1080px; margin: 0 auto; padding: 1.5rem; }
  .sub { color: #a8a29e; margin-bottom: 1rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button:disabled { cursor: not-allowed; opacity: 0.45; }
  button.secondary { background: #57534e; }
  button.ok { background: #15803d; }
  button.bad { background: #b91c1c; }
  button.mini { padding: 0.25rem 0.6rem; font-size: 0.8rem; }
  .err { color: #fb7185; }
  .note { color: #86efac; }
  .lock-note {
    background: #450a0a; border: 1px solid #b91c1c; color: #fecaca;
    border-radius: 6px; padding: 0.6rem 0.8rem; font-size: 0.88rem; margin-bottom: 0.75rem;
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok-tag { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .closed { background: #44403c; color: #d6d3d1; }
  .gate-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  @media (max-width: 760px) { .gate-grid { grid-template-columns: 1fr; } }
  .zone-card {
    border: 1px solid #44403c; border-radius: 6px; padding: 0.7rem 0.85rem;
    margin-bottom: 0.6rem; background: #0c0a09;
  }
  .zone-card .zc-top { display: flex; justify-content: space-between; align-items: center; }
  .zone-card .zc-meta { color: #a8a29e; font-size: 0.8rem; margin: 0.3rem 0; }
  .zone-card .zc-actions { display: flex; gap: 0.5rem; margin-top: 0.4rem; }
  .col-title { font-weight: 600; margin: 0 0 0.75rem; }
  .col-title .cnt { color: #a8a29e; font-weight: 400; font-size: 0.85rem; }
  .empty { color: #78716c; font-size: 0.88rem; }
  /* 底部滚动流水 */
  .ticker-wrap {
    margin-top: 0.5rem; border-top: 1px solid #44403c; padding-top: 0.75rem;
    overflow: hidden; white-space: nowrap;
  }
  .ticker {
    display: inline-block; padding-left: 100%;
    animation: ticker-scroll 40s linear infinite;
  }
  .ticker-wrap:hover .ticker { animation-play-state: paused; }
  .ticker-item { margin-right: 3rem; font-size: 0.88rem; color: #d6d3d1; }
  .ticker-item b { color: #fbbf24; font-weight: 600; }
  .ticker-item .ev-request { color: #93c5fd; }
  .ticker-item .ev-approve { color: #86efac; }
  .ticker-item .ev-reject { color: #fca5a5; }
  @keyframes ticker-scroll {
    0% { transform: translateX(0); }
    100% { transform: translateX(-100%); }
  }
  .chips { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.5rem; }
  .chip {
    background: #44403c; color: #d6d3d1; border-radius: 999px; padding: 0.2rem 0.7rem;
    font-size: 0.78rem; border: none;
  }
</style>

<header>
  <button class="brand" on:click={() => switchPage("desk")}>隧道收敛测缝台</button>
  {#if session}
    <nav>
      <button class="navbtn {page === 'desk' ? 'active' : ''}" on:click={() => switchPage("desk")}>报测缝</button>
      <button class="navbtn {page === 'gate' ? 'active' : ''}" on:click={() => switchPage("gate")}>放行专页</button>
    </nav>
    <div class="spacer"></div>
    <span class="who">
      {session.username}（{session.role}{#each session.perms as p}／{p === "foreman" ? "值班长权限" : p}{/each}）
    </span>
    <button class="secondary mini" on:click={logout}>退出</button>
  {/if}
</header>

<main>
  {#if !session}
    <p class="sub">工区没经值班长点头不能报测缝：测量员先在「放行专页」提交开放申请，值班长点头后写口才开。</p>
    <section>
      <label for="loginUser">用户名</label>
      <input id="loginUser" bind:value={loginUser} autocomplete="off" />
      <label for="loginPass">密码</label>
      <input id="loginPass" type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      <div class="chips">
        <button class="chip" on:click={() => fillAccount("surveyor", "surv123456")}>surveyor 测量员（一号/三号）</button>
        <button class="chip" on:click={() => fillAccount("surveyor2", "surv234567")}>surveyor2 测量员（二号）</button>
        <button class="chip" on:click={() => fillAccount("lead", "lead123456")}>lead 带班测量员＋点头权（四号）</button>
        <button class="chip" on:click={() => fillAccount("inspector", "insp123456")}>inspector 巡检员＋点头权</button>
        <button class="chip" on:click={() => fillAccount("chief", "chief12345")}>chief 值班长</button>
      </div>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else if page === "desk"}
    <p class="sub">报测缝：所选工区未经值班长点头放行时，送单会被后端退回。</p>
    {#if isWriter}
      <section>
        <label for="zoneCode">工区</label>
        <select id="zoneCode" bind:value={zoneCode}>
          <option value="" disabled>请选择工区</option>
          {#each zones as z}
            <option value={z.code}>
              {z.name}（{z.code}）— {z.status === "open" ? "已放开" : z.status === "waiting" ? "等候点头" : z.status === "rejected" ? "已驳回" : "未申请"}
            </option>
          {/each}
        </select>
        {#if selectedZone && !writeOpen}
          <p class="lock-note">
            🔒 {selectedZone.name} 写口未开（{selectedZone.status === "waiting" ? "已申请，正等候值班长点头" : selectedZone.status === "rejected" ? "申请被驳回，请重新申请" : "尚未提交开放申请"}），现在送单会被退回。
            可到
            <button class="mini secondary" on:click={() => switchPage("gate")}>放行专页</button>
            申请。
          </p>
        {/if}
        <label for="chainage">里程桩号</label>
        <input id="chainage" placeholder="例如 K20+050" bind:value={chainage} />
        <label for="deltaMm">收敛（毫米，可正可负）</label>
        <input id="deltaMm" type="number" step="0.1" bind:value={deltaMm} />
        <button disabled={loading || !writeOpen || !chainage || deltaMm === ""} on:click={submit}>
          {writeOpen ? "提交（进入待认领）" : "写口未放行"}
        </button>
        {#if error}<p class="err">{error}</p>{/if}
        {#if notice}<p class="note">{notice}</p>{/if}
      </section>
    {:else}
      <section><p class="empty">当前账号不是测量员，只读。巡检员即使带值班长权限，也不能报送测缝。</p></section>
    {/if}
    <section>
      <table>
        <thead>
          <tr><th>编号</th><th>工区</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th></tr>
        </thead>
        <tbody>
          {#each logs as row}
            <tr>
              <td>{row.id}</td>
              <td>{row.zone_code}</td>
              <td>{row.chainage}</td>
              <td>{row.delta_mm}</td>
              <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok-tag'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
              <td>
                {#if row.verdict}
                  <span class="tag {row.verdict === '合格' ? 'ok-tag' : 'bad'}">{row.verdict}</span>
                {:else}—{/if}
              </td>
              <td>{row.reason ?? "—"}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {:else}
    <p class="sub">
      放行专页：左边是等候工区（未申请／已驳回可提交申请，等候中由值班长点头或驳回），右边是已放开清单，底下是滚动流水。
    </p>
    {#if error}<p class="err">{error}</p>{/if}
    {#if notice}<p class="note">{notice}</p>{/if}
    <div class="gate-grid">
      <section>
        <p class="col-title">⏳ 等候工区 <span class="cnt">（{waitingZones.length}）</span></p>
        {#each waitingZones as z}
          <div class="zone-card">
            <div class="zc-top">
              <strong>{z.name}</strong>
              {#if z.status === "waiting"}
                <span class="tag pending">等候点头</span>
              {:else if z.status === "rejected"}
                <span class="tag bad">已驳回</span>
              {:else}
                <span class="tag closed">未申请</span>
              {/if}
            </div>
            <p class="zc-meta">
              {z.code} · 负责人 {z.owner_username}
              {#if z.status === "waiting"}· 申请人 {z.requested_by} · {fmtTime(z.requested_at)}{/if}
            </p>
            <div class="zc-actions">
              {#if isWriter && z.owner_username === session.username && z.status !== "waiting"}
                <button class="mini" disabled={loading}
                  on:click={() => apiPost(`/api/zones/${z.code}/request`, `已为 ${z.name} 提交开放申请，等候值班长点头`)}>
                  提交开放申请
                </button>
              {/if}
              {#if z.status === "waiting"}
                {#if canForeman}
                  <button class="mini ok" disabled={loading || z.owner_username === session.username}
                    title={z.owner_username === session.username ? "不能给自己负责的工区点头" : ""}
                    on:click={() => apiPost(`/api/zones/${z.code}/approve`, `${z.name} 已点头放行，写口打开`)}>
                    点头放行
                  </button>
                  <button class="mini bad" disabled={loading || z.owner_username === session.username}
                    title={z.owner_username === session.username ? "不能给自己负责的工区点头" : ""}
                    on:click={() => apiPost(`/api/zones/${z.code}/reject`, `${z.name} 申请已驳回`)}>
                    驳回
                  </button>
                  {#if z.owner_username === session.username}
                    <span class="empty">自己不能给自己负责的工区点头</span>
                  {/if}
                {:else}
                  <span class="empty">等候值班长点头…</span>
                {/if}
              {/if}
            </div>
          </div>
        {/each}
        {#if waitingZones.length === 0}<p class="empty">暂无等候工区。</p>{/if}
      </section>

      <section>
        <p class="col-title">✅ 已放开清单 <span class="cnt">（{openZones.length}）</span></p>
        {#each openZones as z}
          <div class="zone-card">
            <div class="zc-top">
              <strong>{z.name}</strong>
              <span class="tag ok-tag">已放开</span>
            </div>
            <p class="zc-meta">
              {z.code} · 申请人 {z.requested_by} · {z.owner_username} 负责
            </p>
            <p class="zc-meta">点头人 {z.decided_by} · {fmtTime(z.decided_at)}</p>
          </div>
        {/each}
        {#if openZones.length === 0}<p class="empty">还没有工区被放行。</p>{/if}
      </section>
    </div>

    <section>
      <p class="col-title">📜 放行流水 <span class="cnt">（每 2 秒刷新，悬停可暂停滚动）</span></p>
      <div class="ticker-wrap">
        <div class="ticker">
          {#each events as ev (ev.id)}
            <span class="ticker-item">
              <b>[{ev.zone_code}]</b>
              <span class="ev-{ev.action}">{ACTION_TEXT[ev.action] || ev.action}</span>
              · {ev.actor} · {fmtTime(ev.created_at)}
            </span>
          {/each}
          {#each events as ev ("dup-" + ev.id)}
            <span class="ticker-item" aria-hidden="true">
              <b>[{ev.zone_code}]</b>
              <span class="ev-{ev.action}">{ACTION_TEXT[ev.action] || ev.action}</span>
              · {ev.actor} · {fmtTime(ev.created_at)}
            </span>
          {/each}
        </div>
      </div>
    </section>
  {/if}
</main>
