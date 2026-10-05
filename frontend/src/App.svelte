<script>
  let session = null;
  let view = "desk";
  let logs = [];
  let zones = [];
  let flow = [];
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let zoneId = "";
  let error = "";
  let gateError = "";
  let loading = false;
  let timer;
  let flowBox;

  $: canSubmit = !!session && session.perms.includes("submit");
  $: canApprove = !!session && session.perms.includes("approve");
  $: waitingZones = zones.filter((z) => z.status !== "open");
  $: openZones = zones.filter((z) => z.status === "open");
  $: openZoneOptions = zones.filter((z) => z.status === "open");

  const ACCOUNTS = [
    { u: "surveyor", p: "surv123456", label: "测量员·一号" },
    { u: "surveyor2", p: "surv234567", label: "测量员·二号" },
    { u: "boss", p: "boss123456", label: "值班长(兼三号)" },
    { u: "inspector", p: "insp123456", label: "巡检员(带点头权)" },
  ];

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function getJson(path) {
    const res = await fetch(path, { headers: headers() });
    if (res.status === 401) {
      logout();
      return null;
    }
    return res.ok ? await res.json() : null;
  }

  async function refresh() {
    if (!session) return;
    const [logsData, zonesData, flowData] = await Promise.all([
      getJson("/api/logs"),
      getJson("/api/zones"),
      getJson("/api/release-flow"),
    ]);
    if (logsData) logs = logsData;
    if (zonesData) zones = zonesData;
    if (flowData) {
      const grew = flowData.length > flow.length;
      flow = flowData;
      if (grew) tick(scrollFlow);
    }
  }

  function tick(fn) {
    requestAnimationFrame(() => requestAnimationFrame(fn));
  }

  function scrollFlow() {
    if (flowBox) flowBox.scrollTop = flowBox.scrollHeight;
  }

  function fillAccount(a) {
    loginUser = a.u;
    loginPass = a.p;
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
      session = { token: data.access_token, username: data.username, perms: data.perms || [] };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      view = "desk";
      await refresh();
      tick(scrollFlow);
      clearInterval(timer);
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    zones = [];
    flow = [];
    localStorage.removeItem("tunnel_session");
  }

  async function callJson(path, method, onError) {
    const res = await fetch(path, { method, headers: headers() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401) logout();
      else if (onError) onError(data.detail || "操作失败");
      return null;
    }
    await refresh();
    return data;
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, delta_mm: Number(deltaMm), zone_id: Number(zoneId) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  async function applyZone(z) {
    gateError = "";
    await callJson(`/api/zones/${z.id}/apply`, "POST", (m) => (gateError = m));
  }

  async function approveZone(z) {
    gateError = "";
    await callJson(`/api/zones/${z.id}/approve`, "POST", (m) => (gateError = m));
  }

  function fmtTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", { hour12: false });
  }

  function roleText() {
    const t = [];
    if (canSubmit) t.push("可报送");
    if (canApprove) t.push("值班长点头权");
    return t.length ? t.join("·") : "只读";
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      const s = JSON.parse(raw);
      session = s;
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
  main { max-width: 1000px; margin: 0 auto; padding: 1.5rem; }
  header {
    display: flex; align-items: center; gap: 1rem;
    border-bottom: 1px solid #44403c; padding-bottom: 0.75rem; margin-bottom: 1.25rem;
  }
  h1 { color: #fbbf24; margin: 0; font-size: 1.35rem; cursor: pointer; }
  nav { display: flex; gap: 0.5rem; }
  .spacer { flex: 1; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
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
    cursor: pointer; padding: 0.45rem 0.9rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600; font-size: 0.85rem;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.secondary { background: #57534e; }
  button.approve { background: #15803d; }
  button.ghost { background: transparent; border: 1px solid #57534e; }
  button.active { background: #b45309; }
  .err { color: #fb7185; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .closed { background: #44403c; color: #d6d3d1; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
  .chips button { font-weight: 400; font-size: 0.78rem; }
  .gate-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  @media (max-width: 720px) { .gate-grid { grid-template-columns: 1fr; } }
  .zone-card {
    border: 1px solid #44403c; border-radius: 6px; padding: 0.7rem 0.85rem; margin-bottom: 0.6rem;
    background: #0c0a09;
  }
  .zone-card .top { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
  .zone-name { font-weight: 600; }
  .zone-meta { font-size: 0.78rem; color: #a8a29e; margin-top: 0.25rem; }
  .zone-actions { margin-top: 0.55rem; display: flex; gap: 0.4rem; }
  .flow-box {
    height: 180px; overflow-y: auto; background: #0c0a09; border: 1px solid #44403c;
    border-radius: 6px; padding: 0.6rem 0.8rem; font-size: 0.83rem; line-height: 1.7;
    scroll-behavior: smooth;
  }
  .flow-line { color: #d6d3d1; border-bottom: 1px dashed #292524; }
  .flow-line .t { color: #78716c; margin-right: 0.5rem; font-variant-numeric: tabular-nums; }
  .flow-line .a-apply { color: #fbbf24; }
  .flow-line .a-approve { color: #4ade80; }
</style>

<main>
  {#if !session}
    <h1 style="cursor:default">隧道收敛测缝台</h1>
    <p class="sub">工区未经值班长点头不得报测。下方快捷填充测试账号。</p>
    <section>
      <div class="chips">
        {#each ACCOUNTS as a}
          <button class="ghost" on:click={() => fillAccount(a)}>{a.label}</button>
        {/each}
      </div>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <header>
      <h1 on:click={() => (view = "gate")} title="进入放行专页">隧道收敛测缝台</h1>
      <nav>
        <button class="secondary {view === 'desk' ? 'active' : ''}" on:click={() => (view = "desk")}>报测台</button>
        <button class="secondary {view === 'gate' ? 'active' : ''}" on:click={() => { view = "gate"; tick(scrollFlow); }}>放行专页</button>
      </nav>
      <div class="spacer"></div>
      <span class="sub" style="margin:0">{session.username}（{roleText()}）</span>
      <button class="ghost" on:click={logout}>退出</button>
    </header>

    {#if view === "desk"}
      {#if canSubmit}
        <section>
          <label>工区（仅已点头放行的工区可报测）</label>
          <select bind:value={zoneId}>
            <option value="">— 选择已放开工区 —</option>
            {#each zones as z}
              <option value={z.id} disabled={z.status !== "open"}>
                {z.name}{z.status === "open" ? "（已放开）" : z.status === "pending" ? "（候点头，禁报）" : "（未申请，禁报）"}
              </option>
            {/each}
          </select>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading || !zoneId} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">{error}</p>{/if}
        </section>
      {:else}
        <p class="sub">当前账号无报送权限：巡检员即使带值班长点头权，也只能放行、不能报测。</p>
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
                <td>{row.zone_name ?? "—"}</td>
                <td>{row.chainage}</td>
                <td>{row.delta_mm}</td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待认领' : '已完成'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.reason ?? "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <section>
        <div class="gate-grid">
          <div>
            <strong>等候工区（未放行）</strong>
            {#each waitingZones as z}
              <div class="zone-card">
                <div class="top">
                  <span class="zone-name">{z.name}</span>
                  {#if z.status === "pending"}
                    <span class="tag pending">候值班长点头</span>
                  {:else}
                    <span class="tag closed">未申请</span>
                  {/if}
                </div>
                <div class="zone-meta">
                  负责人：{z.owner}
                  {#if z.applied_by} · 申请人 {z.applied_by} · {fmtTime(z.applied_at)}{/if}
                </div>
                <div class="zone-actions">
                  {#if canSubmit}
                    {#if z.status === "closed"}
                      <button on:click={() => applyZone(z)}>提交开放申请</button>
                    {:else}
                      <button class="secondary" disabled>已申请，候点头</button>
                    {/if}
                  {/if}
                  {#if canApprove}
                    <button
                      class="approve"
                      disabled={z.status !== "pending" || z.owner === session.username}
                      title={z.owner === session.username ? "自己负责的工区不能自己点头" : ""}
                      on:click={() => approveZone(z)}
                    >
                      {z.owner === session.username ? "本人负责·禁点头" : "值班长点头"}
                    </button>
                  {/if}
                </div>
              </div>
            {:else}
              <p class="sub" style="margin-top:0.6rem">全部工区均已放开。</p>
            {/each}
          </div>

          <div>
            <strong>已放开清单</strong>
            {#each openZones as z}
              <div class="zone-card">
                <div class="top">
                  <span class="zone-name">{z.name}</span>
                  <span class="tag ok">已放开</span>
                </div>
                <div class="zone-meta">
                  负责人：{z.owner} · 点头人 {z.opened_by ?? "—"} · {fmtTime(z.opened_at)}
                </div>
              </div>
            {:else}
              <p class="sub" style="margin-top:0.6rem">还没有工区通过点头。</p>
            {/each}
          </div>
        </div>
        {#if gateError}<p class="err">{gateError}</p>{/if}
      </section>

      <section>
        <strong>放行流水</strong>
        <div class="flow-box" bind:this={flowBox}>
          {#each flow as line}
            <div class="flow-line">
              <span class="t">{fmtTime(line.created_at)}</span>
              <span class="a-{line.action}">{line.action === "approve" ? "点头" : "申请"}</span>
              &nbsp;{line.detail}
            </div>
          {:else}
            <div class="sub">暂无流水。</div>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</main>
