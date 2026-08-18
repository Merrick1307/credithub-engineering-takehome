// import React, { useCallback, useEffect, useState } from "react";
// import "./styles.css";
// const money = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN" });
// async function read(response) {
//   if (response.ok) return response.json();
//   let detail = `HTTP ${response.status}`;
//   try { detail = (await response.json()).detail || detail; } catch { /* response was not JSON */ }
//   throw new Error(detail);
// }
// function usePage(endpoint, token, active, limit) {
//   const [items, setItems] = useState([]), [cursor, setCursor] = useState(null), [loading, setLoading] = useState(false);
//   const request = useCallback(async (next, reset = false) => { if (!active || loading) return; setLoading(true); try { const sep = endpoint.includes("?") ? "&" : "?"; const data = await read(await fetch(`${endpoint}${sep}limit=${limit}${next ? `&cursor=${encodeURIComponent(next)}` : ""}`, { headers: token ? { "X-Admin-Token": token } : {} })); setItems(old => reset ? data.items : [...old, ...data.items]); setCursor(data.next_cursor); } finally { setLoading(false); } }, [active, endpoint, limit, loading, token]);
//   useEffect(() => { if (active) request(null, true); }, [active, endpoint, limit, token]);
//   return { items, loading, more: () => cursor && request(cursor), refresh: () => request(null, true), hasMore: Boolean(cursor) };
// }
// function Table({ data, columns, page, expanded = false }) { const scroll = e => { const el = e.currentTarget; if (page.hasMore && el.scrollHeight - el.scrollTop - el.clientHeight < 80) page.more(); }; return <div className={`table-scroll ${expanded ? "table-expanded" : ""}`} onScroll={scroll}><table><thead><tr>{columns.map(c => <th key={c[0]}>{c[0]}</th>)}</tr></thead><tbody>{data.map(row => <tr key={row.id}>{columns.map(c => <td key={c[0]}>{c[1](row)}</td>)}</tr>)}</tbody></table>{page.loading && <p className="muted loading">Loading…</p>}</div>; }
// function Card({ label, value, click }) { return <button className="stat" onClick={click}><span className="k">{label}</span><span className="v">{value}</span></button>; }
// export default function App() {
//   const [token, setToken] = useState(sessionStorage.getItem("admin_token") || ""), [entry, setEntry] = useState(""), [tab, setTab] = useState("dashboard"), [menu, setMenu] = useState(true), [summary, setSummary] = useState(null), [expanded, setExpanded] = useState(null), [filters, setFilters] = useState({ provider:"", status:"", reference:"" }), [retryError, setRetryError] = useState(""), [retrying, setRetrying] = useState(null);
//   const auth = Boolean(token); const query = new URLSearchParams(Object.entries(filters).filter(([,v]) => v)).toString();
//   const events = usePage(`/admin/reconciliation/events${query ? `?${query}` : ""}`, token, auth && ["dashboard","events"].includes(tab), tab === "events" ? 10 : expanded === "events" ? 50 : 8);
//   const issues = usePage("/admin/reconciliation/issues", token, auth && tab === "dashboard", expanded === "issues" ? 50 : 3);
//   const loans = usePage("/loans", "", auth && tab === "loans", 10); const overpayments = usePage("/admin/reconciliation/overpayments", token, auth && tab === "overpayments", 10); const retries = usePage("/admin/reconciliation/provider-lookups", token, auth && tab === "receivables", 10);
//   useEffect(() => { if (auth) fetch("/admin/reconciliation/summary", {headers:{"X-Admin-Token":token}}).then(read).then(setSummary); }, [auth, token]);
//   if (!auth) return <main className="login"><section className="login-card"><h1>CreditHub</h1><p>Reconciliation operations</p><input value={entry} type="password" placeholder="Staff token" onChange={e=>setEntry(e.target.value)}/><button className="btn btn-primary" onClick={()=>{sessionStorage.setItem("admin_token",entry);setToken(entry)}}>Sign in</button></section></main>;
//   const nav=[["dashboard","Dashboard"],["events","Events"],["overpayments","Overpayments"],["loans","Loans"],["receivables","Pending receivables"]]; const eventCols=[["Reference",r=>r.reference],["Provider",r=>r.provider],["Kind",r=>r.kind],["Amount",r=>money.format(r.gross_amount)],["Status",r=>r.status]];
//   const retry = async id => { setRetryError(""); setRetrying(id); try { await read(await fetch(`/admin/reconciliation/provider-lookups/${id}/retry`,{method:"POST",headers:{"X-Admin-Token":token}})); await retries.refresh(); } catch (error) { setRetryError(error.message); } finally { setRetrying(null); } };
//   const previewButton = (section, page, previewSize) => {
//     const allShown = !page.loading && !page.hasMore && page.items.length <= previewSize;
//     return <button className="btn" disabled={allShown} onClick={()=>setExpanded(expanded===section?null:section)}>{expanded===section ? "Collapse" : allShown ? "All shown" : "Expand"}</button>;
//   };
//   return <main className={`workspace ${menu ? "" : "collapsed"}`}><aside className="sidebar"><button className="close" aria-label="Collapse navigation" title="Collapse navigation" onClick={()=>setMenu(false)}>‹</button><h1>CreditHub</h1>{nav.map(([id,label])=><button className={tab===id?"side active":"side"} key={id} onClick={()=>setTab(id)}>{label}</button>)}</aside><section className="content"><header className="content-head">{!menu&&<button className="btn menu" aria-label="Expand navigation" title="Expand navigation" onClick={()=>setMenu(true)}>☰</button>}<h2>{nav.find(n=>n[0]===tab)[1]}</h2></header>
//   {tab==="dashboard"&&<><section className="stats"><Card label="Total events" value={summary?.counts.total??"—"} click={()=>setTab("events")}/><Card label="Processed" value={summary?.counts.applied??"—"} click={()=>setTab("events")}/><Card label="Rejected" value={summary?.counts.rejected??"—"} click={()=>setTab("events")}/><Card label="Open issues" value={summary?.counts.open_issues??"—"} click={()=>setExpanded("issues")}/><Card label="Gross received" value={summary?money.format(summary.amounts.gross_received):"—"} click={()=>setExpanded("events")}/><Card label="Processed amount" value={summary?money.format(summary.amounts.applied):"—"} click={()=>setExpanded("events")}/><Card label="Overpaid" value={summary?money.format(summary.amounts.overpaid):"—"} click={()=>setTab("overpayments")}/><Card label="Rejection rate" value={summary?`${summary.rejection_rate}%`:"—"} click={()=>setTab("events")}/></section><div className="preview-head"><h3>Payment feed</h3>{previewButton("events", events, 8)}</div><Table expanded={expanded==="events"} data={expanded==="events"?events.items:events.items.slice(0,8)} columns={eventCols} page={events}/><div className="preview-head"><h3>Needs attention</h3>{previewButton("issues", issues, 3)}</div><Table expanded={expanded==="issues"} data={expanded==="issues"?issues.items:issues.items.slice(0,3)} columns={[["Reason",r=>r.reason],["Loan",r=>r.loan_id||"—"],["Created",r=>new Date(r.created_at).toLocaleString()]]} page={issues}/></>}
//   {tab==="events"&&<><div className="filter-bar"><input placeholder="Reference" value={filters.reference} onChange={e=>setFilters({...filters,reference:e.target.value})}/><select value={filters.provider} onChange={e=>setFilters({...filters,provider:e.target.value})}><option value="">All providers</option><option value="paystack">Paystack</option><option value="mock">Mock</option><option value="core_banking">Core banking</option></select><select value={filters.status} onChange={e=>setFilters({...filters,status:e.target.value})}><option value="">All statuses</option><option value="applied">Processed</option><option value="rejected">Rejected</option></select></div><Table data={events.items} columns={eventCols} page={events}/></>}
//   {tab==="loans"&&<Table data={loans.items} columns={[["Borrower",r=>r.borrower_name],["Outstanding",r=>money.format(r.outstanding)],["Status",r=>r.status]]} page={loans}/>} {tab==="overpayments"&&<Table data={overpayments.items} columns={[["Loan",r=>r.loan_id],["Remaining",r=>money.format(r.remaining_amount)],["Status",r=>r.status]]} page={overpayments}/>} {tab==="receivables"&&<>{retryError&&<p className="banner">Retry failed: {retryError}</p>}<Table data={retries.items} columns={[["Provider",r=>r.provider],["Attempts",r=>r.attempts],["Status",r=>r.status],["",r=><button className="btn" disabled={retrying===r.id} onClick={()=>retry(r.id)}>{retrying===r.id?"Retrying…":"Retry"}</button>]]} page={retries}/></>}</section></main>;
// }


// import React, { useCallback, useEffect, useState } from "react";
// import "./styles.css";
//
// const money = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN" });
//
// const providerName = {
//   paystack: "Paystack",
//   mock: "Mock",
//   core_banking: "Core banking",
// };
//
// const eventKind = {
//   "transaction.credit": "Credit received",
// };
//
// const pageDescriptions = {
//   dashboard: "Reconciliation activity, payment outcomes and exceptions at a glance.",
//   events: "All reconciliation events received from payment and banking rails.",
//   overpayments: "Amounts received beyond the outstanding balance on a loan.",
//   loans: "Current borrower balances and loan servicing state.",
//   receivables: "Provider lookups awaiting reconciliation or retry.",
// };
//
// async function read(response) {
//   if (response.ok) return response.json();
//   let detail = `HTTP ${response.status}`;
//   try {
//     detail = (await response.json()).detail || detail;
//   } catch {
//     /* response was not JSON */
//   }
//   throw new Error(detail);
// }
//
// function usePage(endpoint, token, active, limit) {
//   const [items, setItems] = useState([]);
//   const [cursor, setCursor] = useState(null);
//   const [loading, setLoading] = useState(false);
//
//   const request = useCallback(
//     async (next, reset = false) => {
//       if (!active || loading) return;
//       setLoading(true);
//       try {
//         const sep = endpoint.includes("?") ? "&" : "?";
//         const data = await read(
//           await fetch(
//             `${endpoint}${sep}limit=${limit}${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
//             { headers: token ? { "X-Admin-Token": token } : {} },
//           ),
//         );
//         setItems((old) => (reset ? data.items : [...old, ...data.items]));
//         setCursor(data.next_cursor);
//       } finally {
//         setLoading(false);
//       }
//     },
//     [active, endpoint, limit, loading, token],
//   );
//
//   useEffect(() => {
//     if (active) request(null, true);
//   }, [active, endpoint, limit, token]);
//
//   return {
//     items,
//     loading,
//     more: () => cursor && request(cursor),
//     refresh: () => request(null, true),
//     hasMore: Boolean(cursor),
//   };
// }
//
// function Table({ data, columns, page, expanded = false, emptyMessage = "Nothing to show." }) {
//   const scroll = (event) => {
//     const el = event.currentTarget;
//     if (page.hasMore && el.scrollHeight - el.scrollTop - el.clientHeight < 80) page.more();
//   };
//
//   if (!page.loading && data.length === 0) {
//     return (
//       <div className="empty-state">
//         <span className="empty-icon" aria-hidden="true">✓</span>
//         <span>{emptyMessage}</span>
//       </div>
//     );
//   }
//
//   return (
//     <div className={`table-scroll ${expanded ? "table-expanded" : ""}`} onScroll={scroll}>
//       <table>
//         <thead>
//           <tr>{columns.map((column) => <th key={column[0]}>{column[0]}</th>)}</tr>
//         </thead>
//         <tbody>
//           {data.map((row) => (
//             <tr key={row.id}>
//               {columns.map((column) => <td key={column[0]}>{column[1](row)}</td>)}
//             </tr>
//           ))}
//         </tbody>
//       </table>
//       {page.loading && <p className="muted loading">Loading…</p>}
//     </div>
//   );
// }
//
// function Card({ label, value, meta, click }) {
//   return (
//     <button className="stat" onClick={click}>
//       <span className="k">{label}</span>
//       <span className="v">{value}</span>
//       {meta && <span className="meta">{meta}</span>}
//     </button>
//   );
// }
//
// function StatusBadge({ status }) {
//   const label = status === "applied" ? "Processed" : status
//     ? status.charAt(0).toUpperCase() + status.slice(1).replaceAll("_", " ")
//     : "Unknown";
//   return <span className={`pbadge ${status || "pending"}`}>{label}</span>;
// }
//
// export default function App() {
//   const [token, setToken] = useState(sessionStorage.getItem("admin_token") || "");
//   const [entry, setEntry] = useState("");
//   const [tab, setTab] = useState("dashboard");
//   const [menu, setMenu] = useState(true);
//   const [summary, setSummary] = useState(null);
//   const [expanded, setExpanded] = useState(null);
//   const [filters, setFilters] = useState({ provider: "", status: "", reference: "" });
//   const [retryError, setRetryError] = useState("");
//   const [retrying, setRetrying] = useState(null);
//
//   const auth = Boolean(token);
//   const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();
//   const events = usePage(
//     `/admin/reconciliation/events${query ? `?${query}` : ""}`,
//     token,
//     auth && ["dashboard", "events"].includes(tab),
//     tab === "events" ? 10 : expanded === "events" ? 50 : 8,
//   );
//   const issues = usePage(
//     "/admin/reconciliation/issues",
//     token,
//     auth && tab === "dashboard",
//     expanded === "issues" ? 50 : 3,
//   );
//   const loans = usePage("/loans", "", auth && tab === "loans", 10);
//   const overpayments = usePage("/admin/reconciliation/overpayments", token, auth && tab === "overpayments", 10);
//   const retries = usePage("/admin/reconciliation/provider-lookups", token, auth && tab === "receivables", 10);
//
//   useEffect(() => {
//     if (auth) {
//       fetch("/admin/reconciliation/summary", { headers: { "X-Admin-Token": token } })
//         .then(read)
//         .then(setSummary);
//     }
//   }, [auth, token]);
//
//   if (!auth) {
//     return (
//       <main className="login">
//         <section className="login-card">
//           <h1>CreditHub</h1>
//           <p>Reconciliation operations</p>
//           <input
//             value={entry}
//             type="password"
//             placeholder="Staff token"
//             onChange={(event) => setEntry(event.target.value)}
//           />
//           <button
//             className="btn btn-primary"
//             onClick={() => {
//               sessionStorage.setItem("admin_token", entry);
//               setToken(entry);
//             }}
//           >
//             Sign in
//           </button>
//         </section>
//       </main>
//     );
//   }
//
//   const nav = [
//     ["dashboard", "Dashboard"],
//     ["events", "Events"],
//     ["overpayments", "Overpayments"],
//     ["loans", "Loans"],
//     ["receivables", "Pending receivables"],
//   ];
//
//   const eventCols = [
//     ["Reference", (row) => <span className="mono-ref">{row.reference}</span>],
//     ["Provider", (row) => providerName[row.provider] || row.provider],
//     ["Kind", (row) => eventKind[row.kind] || row.kind],
//     ["Amount", (row) => <span className="amount-cell">{money.format(row.gross_amount)}</span>],
//     ["Status", (row) => <StatusBadge status={row.status} />],
//   ];
//
//   const retry = async (id) => {
//     setRetryError("");
//     setRetrying(id);
//     try {
//       await read(
//         await fetch(`/admin/reconciliation/provider-lookups/${id}/retry`, {
//           method: "POST",
//           headers: { "X-Admin-Token": token },
//         }),
//       );
//       await retries.refresh();
//     } catch (error) {
//       setRetryError(error.message);
//     } finally {
//       setRetrying(null);
//     }
//   };
//
//   const previewButton = (section, page, previewSize) => {
//     const allShown = !page.loading && !page.hasMore && page.items.length <= previewSize;
//     if (allShown) return null;
//     return (
//       <button
//         className="link-btn preview-action"
//         onClick={() => setExpanded(expanded === section ? null : section)}
//       >
//         {expanded === section ? "Show less" : "View all →"}
//       </button>
//     );
//   };
//
//   const currentTitle = nav.find((item) => item[0] === tab)?.[1] || "Dashboard";
//
//   return (
//     <main className={`workspace ${menu ? "" : "collapsed"}`}>
//       <aside className="sidebar">
//         <button
//           className="close"
//           aria-label="Collapse navigation"
//           title="Collapse navigation"
//           onClick={() => setMenu(false)}
//         >
//           ‹
//         </button>
//         <h1>CreditHub</h1>
//         {nav.map(([id, label]) => (
//           <button
//             className={tab === id ? "side active" : "side"}
//             key={id}
//             onClick={() => setTab(id)}
//           >
//             {label}
//           </button>
//         ))}
//       </aside>
//
//       <section className="content">
//         <header className="content-head">
//           {!menu && (
//             <button
//               className="menu-toggle"
//               aria-label="Expand navigation"
//               title="Expand navigation"
//               onClick={() => setMenu(true)}
//             >
//               ☰
//             </button>
//           )}
//           <div className="page-heading">
//             <h2>{currentTitle}</h2>
//             <p>{pageDescriptions[tab]}</p>
//           </div>
//         </header>
//
//         {tab === "dashboard" && (
//           <>
//             <section className="stats">
//               <Card
//                 label="Gross received"
//                 value={summary ? money.format(summary.amounts.gross_received) : "—"}
//                 meta={`${summary?.counts.total ?? "—"} payment events`}
//                 click={() => setExpanded("events")}
//               />
//               <Card
//                 label="Processed"
//                 value={summary ? money.format(summary.amounts.applied) : "—"}
//                 meta={`${summary?.counts.applied ?? "—"} applied events`}
//                 click={() => setTab("events")}
//               />
//               <Card
//                 label="Rejected"
//                 value={summary?.counts.rejected ?? "—"}
//                 meta={summary ? `${summary.rejection_rate}% rejection rate` : "—"}
//                 click={() => setTab("events")}
//               />
//               <Card
//                 label="Exceptions"
//                 value={summary?.counts.open_issues ?? "—"}
//                 meta={summary ? `${money.format(summary.amounts.overpaid)} overpaid` : "—"}
//                 click={() => setExpanded("issues")}
//               />
//             </section>
//
//             <div className="preview-head">
//               <h3>Recent payments</h3>
//               {previewButton("events", events, 8)}
//             </div>
//             <Table
//               expanded={expanded === "events"}
//               data={expanded === "events" ? events.items : events.items.slice(0, 8)}
//               columns={eventCols}
//               page={events}
//               emptyMessage="No payment events have been received yet."
//             />
//
//             <div className="preview-head">
//               <h3>Needs attention</h3>
//               {previewButton("issues", issues, 3)}
//             </div>
//             <Table
//               expanded={expanded === "issues"}
//               data={expanded === "issues" ? issues.items : issues.items.slice(0, 3)}
//               columns={[
//                 ["Reason", (row) => row.reason],
//                 ["Loan", (row) => row.loan_id || "—"],
//                 ["Created", (row) => new Date(row.created_at).toLocaleString()],
//               ]}
//               page={issues}
//               emptyMessage="No reconciliation issues require attention."
//             />
//           </>
//         )}
//
//         {tab === "events" && (
//           <>
//             <div className="filter-bar">
//               <input
//                 placeholder="Search reference"
//                 value={filters.reference}
//                 onChange={(event) => setFilters({ ...filters, reference: event.target.value })}
//               />
//               <select
//                 value={filters.provider}
//                 onChange={(event) => setFilters({ ...filters, provider: event.target.value })}
//               >
//                 <option value="">All providers</option>
//                 <option value="paystack">Paystack</option>
//                 <option value="mock">Mock</option>
//                 <option value="core_banking">Core banking</option>
//               </select>
//               <select
//                 value={filters.status}
//                 onChange={(event) => setFilters({ ...filters, status: event.target.value })}
//               >
//                 <option value="">All statuses</option>
//                 <option value="applied">Processed</option>
//                 <option value="rejected">Rejected</option>
//               </select>
//             </div>
//             <Table data={events.items} columns={eventCols} page={events} emptyMessage="No events match these filters." />
//           </>
//         )}
//
//         {tab === "loans" && (
//           <Table
//             data={loans.items}
//             columns={[
//               ["Borrower", (row) => row.borrower_name],
//               ["Outstanding", (row) => <span className="amount-cell">{money.format(row.outstanding)}</span>],
//               ["Status", (row) => <StatusBadge status={row.status} />],
//             ]}
//             page={loans}
//             emptyMessage="No loans to show."
//           />
//         )}
//
//         {tab === "overpayments" && (
//           <Table
//             data={overpayments.items}
//             columns={[
//               ["Loan", (row) => row.loan_id],
//               ["Remaining", (row) => <span className="amount-cell">{money.format(row.remaining_amount)}</span>],
//               ["Status", (row) => <StatusBadge status={row.status} />],
//             ]}
//             page={overpayments}
//             emptyMessage="No overpayments to show."
//           />
//         )}
//
//         {tab === "receivables" && (
//           <>
//             {retryError && <p className="banner">Retry failed: {retryError}</p>}
//             <Table
//               data={retries.items}
//               columns={[
//                 ["Provider", (row) => providerName[row.provider] || row.provider],
//                 ["Attempts", (row) => row.attempts],
//                 ["Status", (row) => <StatusBadge status={row.status} />],
//                 ["", (row) => (
//                   <button className="btn" disabled={retrying === row.id} onClick={() => retry(row.id)}>
//                     {retrying === row.id ? "Retrying…" : "Retry"}
//                   </button>
//                 )],
//               ]}
//               page={retries}
//               emptyMessage="No provider lookups are waiting for action."
//             />
//           </>
//         )}
//       </section>
//     </main>
//   );
// }

import React, { useCallback, useEffect, useRef, useState } from "react";
import "./styles.css";

const WEBHOOK_TOKEN = "dev-webhook-secret";

const money = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN" });

const providerName = {
  paystack: "Paystack",
  mock: "Mock",
  core_banking: "Core banking",
};

const eventKind = {
  "transaction.credit": "Credit received",
};

const pageDescriptions = {
  dashboard: "Reconciliation activity, payment outcomes and exceptions at a glance.",
  events: "All reconciliation events received from payment and banking rails.",
  overpayments: "Amounts received beyond the outstanding balance on a loan.",
  loans: "Current borrower balances and loan servicing state.",
  receivables: "Provider lookups awaiting reconciliation or retry.",
};

async function read(response) {
  if (response.ok) return response.json();
  let detail = `HTTP ${response.status}`;
  try {
    detail = (await response.json()).detail || detail;
  } catch {
    /* response was not JSON */
  }
  throw new Error(detail);
}

function usePage(endpoint, token, active, limit) {
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const loadingMore = useRef(false);
  const generation = useRef(0);
  const requestedCursors = useRef(new Set());

  const request = useCallback(
    async (next, reset = false) => {
      if (!active) return false;
      if (!reset && (!next || loadingMore.current || requestedCursors.current.has(next))) return false;

      const requestGeneration = reset ? ++generation.current : generation.current;

      if (reset) {
        requestedCursors.current.clear();
      } else {
        loadingMore.current = true;
        requestedCursors.current.add(next);
      }
      setLoading(true);

      try {
        const sep = endpoint.includes("?") ? "&" : "?";
        const data = await read(
          await fetch(
            `${endpoint}${sep}limit=${limit}${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
            { headers: token ? { "X-Admin-Token": token } : {} },
          ),
        );

        // Ignore a response from a request that became stale because the
        // endpoint/filter was reset while it was in flight.
        if (requestGeneration !== generation.current) return false;

        const received = Array.isArray(data.items) ? data.items : [];
        setItems((old) => (reset ? received : [...old, ...received]));

        // Treat an empty page, a repeated cursor, or a missing next cursor as
        // terminal. Infinite scrolling therefore stops permanently at the end
        // instead of repeatedly polling an exhausted endpoint.
        const nextCursor =
          received.length > 0 && data.next_cursor && data.next_cursor !== next
            ? data.next_cursor
            : null;
        setCursor(nextCursor);
        return true;
      } catch (error) {
        if (!reset && next) requestedCursors.current.delete(next);
        throw error;
      } finally {
        if (!reset) loadingMore.current = false;
        if (requestGeneration === generation.current) setLoading(false);
      }
    },
    [active, endpoint, limit, token],
  );

  useEffect(() => {
    if (active) request(null, true).catch(() => {});
  }, [active, request]);

  return {
    items,
    loading,
    more: () => {
      if (!cursor || loadingMore.current) return Promise.resolve(false);
      return request(cursor);
    },
    refresh: () => request(null, true),
    hasMore: Boolean(cursor),
  };
}

function Table({ data, columns, page, expanded = false, tall = false, emptyMessage = "Nothing to show.", loadOnScroll = true, onRowClick = null }) {
  const scrollRef = useRef(null);
  const sentinelRef = useRef(null);

  const maybeLoadMore = useCallback(() => {
    if (!loadOnScroll || page.loading || !page.hasMore) return;
    page.more();
  }, [loadOnScroll, page]);

  const scroll = (event) => {
    if (!loadOnScroll) return;
    const el = event.currentTarget;
    if (page.hasMore && !page.loading && el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
      maybeLoadMore();
    }
  };

  // If a cursor page is shorter than the visible container there may be no
  // scrollbar yet. The sentinel fills that gap by requesting one page at a
  // time until there is actually something to scroll. Once the sentinel leaves
  // view, further requests happen only as the user reaches the bottom.
  useEffect(() => {
    if (!loadOnScroll || !page.hasMore || page.loading) return undefined;
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) maybeLoadMore();
      },
      { root, rootMargin: "0px 0px 140px 0px", threshold: 0.01 },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [data.length, loadOnScroll, maybeLoadMore, page.hasMore, page.loading]);

  if (!page.loading && data.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon" aria-hidden="true">✓</span>
        <span>{emptyMessage}</span>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className={`table-scroll ${expanded ? "table-expanded" : ""} ${tall ? "table-tall" : ""}`} onScroll={scroll}>
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column[0]}>{column[0]}</th>)}</tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const clickable = typeof onRowClick === "function";
            return (
              <tr
                key={row.id}
                className={clickable ? "table-row-clickable" : undefined}
                onClick={clickable ? () => onRowClick(row) : undefined}
                onKeyDown={clickable ? (event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onRowClick(row);
                  }
                } : undefined}
                tabIndex={clickable ? 0 : undefined}
                aria-label={clickable ? "Open event details" : undefined}
              >
                {columns.map((column) => <td key={column[0]}>{column[1](row)}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
      {loadOnScroll && page.hasMore && <div ref={sentinelRef} className="scroll-sentinel" aria-hidden="true" />}
      {page.loading && <p className="muted loading">Loading…</p>}
      {loadOnScroll && !page.loading && !page.hasMore && data.length > 0 && (
        <p className="muted end-of-results">End of results</p>
      )}
    </div>
  );
}

function Card({ label, value, meta, click }) {
  return (
    <button className="stat" onClick={click}>
      <span className="k">{label}</span>
      <span className="v">{value}</span>
      {meta && <span className="meta">{meta}</span>}
    </button>
  );
}

function StatusBadge({ status }) {
  const label = status === "applied" ? "Processed" : status
    ? status.charAt(0).toUpperCase() + status.slice(1).replaceAll("_", " ")
    : "Unknown";
  return <span className={`pbadge ${status || "pending"}`}>{label}</span>;
}

function detailLabel(key) {
  return key
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function renderDetailValue(key, value) {
  if (value === null || value === undefined || value === "") return "—";

  if (typeof value === "object") {
    return <pre className="detail-json">{JSON.stringify(value, null, 2)}</pre>;
  }

  if (typeof value === "boolean") return value ? "Yes" : "No";

  if (key.endsWith("_at")) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) return date.toLocaleString();
  }

  if (["principal", "total_repayable", "total_paid", "outstanding"].includes(key) || /(^|_)(amount|delta)$/.test(key) || key.includes("_amount") || key.includes("balance_delta")) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return <span className="amount-cell">{money.format(numeric)}</span>;
  }

  return String(value);
}

function DetailGrid({ data, onLoanClick }) {
  if (!data || Object.keys(data).length === 0) {
    return <p className="detail-empty">No details recorded.</p>;
  }

  return (
    <dl className="detail-grid">
      {Object.entries(data).map(([key, value]) => (
        <div className="detail-field" key={key}>
          <dt>{detailLabel(key)}</dt>
          <dd>
            {key === "loan_id" && value !== null && value !== undefined && onLoanClick ? (
              <button
                type="button"
                className="loan-detail-link mono-ref"
                onClick={() => onLoanClick(value)}
                title="View loan details"
              >
                Loan #{value}
              </button>
            ) : renderDetailValue(key, value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function EventDetailOverlay({ eventId, data, loading, error, onClose, onRetry, onOpenLoan }) {
  const event = data?.event || null;
  const ledger = data?.ledger || [];
  const deliveries = data?.deliveries || [];
  const issues = data?.issues || [];
  const audit = data?.audit || [];
  const reference = event?.reference || event?.external_ref || event?.id || eventId;
  const provider = event?.provider ? (providerName[event.provider] || event.provider) : null;

  return (
    <div
      className="event-detail-overlay"
      onMouseDown={(mouseEvent) => {
        if (mouseEvent.target === mouseEvent.currentTarget) onClose();
      }}
    >
      <section className="event-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="event-detail-title">
        <header className="event-detail-head">
          <div className="event-detail-heading">
            <span className="event-detail-eyebrow">Payment event</span>
            <h3 id="event-detail-title" className="mono-ref">{reference}</h3>
            <p>
              {provider || "Reconciliation event"}
              {event?.kind ? ` · ${eventKind[event.kind] || event.kind}` : ""}
            </p>
          </div>
          <div className="event-detail-head-actions">
            {event?.status && <StatusBadge status={event.status} />}
            <button className="inspect-close" onClick={onClose} aria-label="Close event details" title="Close">×</button>
          </div>
        </header>

        <div className="event-detail-body">
          {loading && (
            <div className="event-detail-loading" aria-label="Loading event details">
              <div className="skeleton" />
              <div className="skeleton" />
              <div className="skeleton" />
              <div className="skeleton" />
            </div>
          )}

          {!loading && error && (
            <div className="detail-error">
              <div>
                <strong>Couldn’t load this event.</strong>
                <p>{error}</p>
              </div>
              <button className="btn" onClick={onRetry}>Retry</button>
            </div>
          )}

          {!loading && !error && data && (
            <>
              <section className="detail-section">
                <div className="detail-section-head">
                  <h4>Event</h4>
                </div>
                <DetailGrid data={event} onLoanClick={onOpenLoan} />
              </section>

              <section className="detail-section">
                <div className="detail-section-head">
                  <h4>Ledger</h4>
                  <span>{ledger.length}</span>
                </div>
                {ledger.length ? (
                  <div className="detail-table-wrap">
                    <table className="detail-table">
                      <thead><tr><th>ID</th><th>Type</th><th>Amount</th><th>Loan balance Δ</th><th>Overpayment Δ</th><th>Created</th></tr></thead>
                      <tbody>
                        {ledger.map((row) => (
                          <tr key={row.id}>
                            <td className="mono-ref">{row.id}</td>
                            <td>{row.type}</td>
                            <td>{renderDetailValue("amount", row.amount)}</td>
                            <td>{renderDetailValue("loan_balance_delta", row.loan_balance_delta)}</td>
                            <td>{renderDetailValue("overpayment_balance_delta", row.overpayment_balance_delta)}</td>
                            <td>{renderDetailValue("created_at", row.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="detail-empty">No ledger entries were recorded for this event.</p>}
              </section>

              <section className="detail-section">
                <div className="detail-section-head">
                  <h4>Overpayment</h4>
                  <span>{data.overpayment ? "Recorded" : "None"}</span>
                </div>
                {data.overpayment
                  ? <DetailGrid data={data.overpayment} />
                  : <p className="detail-empty">No overpayment is associated with this payment event.</p>}
              </section>

              <section className="detail-section">
                <div className="detail-section-head">
                  <h4>Webhook deliveries</h4>
                  <span>{deliveries.length}</span>
                </div>
                {deliveries.length ? (
                  <div className="detail-table-wrap">
                    <table className="detail-table">
                      <thead><tr><th>ID</th><th>Status</th><th>Received</th></tr></thead>
                      <tbody>
                        {deliveries.map((item) => (
                          <tr key={item.id}>
                            <td className="mono-ref">{item.id}</td>
                            <td><StatusBadge status={item.status} /></td>
                            <td>{renderDetailValue("received_at", item.received_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="detail-empty">No webhook delivery records were found.</p>}
              </section>

              <section className="detail-section">
                <div className="detail-section-head">
                  <h4>Issues</h4>
                  <span>{issues.length}</span>
                </div>
                {issues.length ? (
                  <div className="detail-table-wrap">
                    <table className="detail-table">
                      <thead><tr><th>ID</th><th>Status</th><th>Reason</th></tr></thead>
                      <tbody>
                        {issues.map((item) => (
                          <tr key={item.id}>
                            <td className="mono-ref">{item.id}</td>
                            <td><StatusBadge status={item.status} /></td>
                            <td>{item.reason || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="detail-empty">No reconciliation issues are linked to this event.</p>}
              </section>

              <section className="detail-section">
                <div className="detail-section-head">
                  <h4>Audit trail</h4>
                  <span>{audit.length}</span>
                </div>
                {audit.length ? (
                  <div className="detail-table-wrap">
                    <table className="detail-table detail-audit-table">
                      <thead><tr><th>Action</th><th>Actor</th><th>Detail</th><th>Created</th></tr></thead>
                      <tbody>
                        {audit.map((item) => (
                          <tr key={item.id}>
                            <td>{item.action}</td>
                            <td>{item.actor || "—"}</td>
                            <td>{renderDetailValue("detail", item.detail)}</td>
                            <td>{renderDetailValue("created_at", item.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <p className="detail-empty">No audit entries are linked to this event.</p>}
              </section>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function LoanDetailOverlay({ loanId, data, loading, error, onClose, onRetry }) {
  const totalRepayable = Number(data?.total_repayable || 0);
  const totalPaid = Number(data?.total_paid || 0);
  const progress = totalRepayable > 0
    ? Math.min(100, Math.max(0, (totalPaid / totalRepayable) * 100))
    : 0;

  return (
    <div
      className="event-detail-overlay loan-detail-overlay"
      onMouseDown={(mouseEvent) => {
        if (mouseEvent.target === mouseEvent.currentTarget) onClose();
      }}
    >
      <section
        className="event-detail-dialog loan-detail-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="loan-detail-title"
      >
        <header className="event-detail-head">
          <div className="event-detail-heading">
            <span className="event-detail-eyebrow">Loan</span>
            <h3 id="loan-detail-title">{data?.borrower_name || `Loan #${loanId}`}</h3>
            <p className="mono-ref">Loan #{data?.id ?? loanId}</p>
          </div>
          <div className="event-detail-head-actions">
            {data?.status && <StatusBadge status={data.status} />}
            <button className="inspect-close" onClick={onClose} aria-label="Close loan details" title="Close">×</button>
          </div>
        </header>

        <div className="event-detail-body">
          {loading && (
            <div className="event-detail-loading" aria-label="Loading loan details">
              <div className="skeleton" />
              <div className="skeleton" />
              <div className="skeleton" />
              <div className="skeleton" />
            </div>
          )}

          {!loading && error && (
            <div className="detail-error">
              <div>
                <strong>Couldn’t load this loan.</strong>
                <p>{error}</p>
              </div>
              <button className="btn" onClick={onRetry}>Retry</button>
            </div>
          )}

          {!loading && !error && data && (
            <>
              <section className="detail-section">
                <div className="detail-section-head">
                  <h4>Loan summary</h4>
                </div>
                <DetailGrid data={data} />
              </section>

              <section className="detail-section loan-repayment-section">
                <div className="detail-section-head">
                  <h4>Repayment progress</h4>
                  <span>{progress.toFixed(1)}%</span>
                </div>
                <div className="loan-progress-track" aria-label={`${progress.toFixed(1)}% repaid`}>
                  <span className="loan-progress-value" style={{ width: `${progress}%` }} />
                </div>
                <div className="loan-progress-meta">
                  <span>{money.format(totalPaid)} paid</span>
                  <span>{money.format(totalRepayable)} total repayable</span>
                </div>
              </section>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState(sessionStorage.getItem("admin_token") || "");
  const [entry, setEntry] = useState("");
  const [tab, setTab] = useState("dashboard");
  const [menu, setMenu] = useState(true);
  const [summary, setSummary] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [filters, setFilters] = useState({ provider: "", status: "", reference: "" });
  const [retryError, setRetryError] = useState("");
  const [retrying, setRetrying] = useState(null);
  const [simulationMode, setSimulationMode] = useState("random");
  const [simulating, setSimulating] = useState(false);
  const [simulationNote, setSimulationNote] = useState("");
  const [redelivering, setRedelivering] = useState(null);
  const [eventDetailId, setEventDetailId] = useState(null);
  const [eventDetail, setEventDetail] = useState(null);
  const [eventDetailLoading, setEventDetailLoading] = useState(false);
  const [eventDetailError, setEventDetailError] = useState("");
  const eventDetailRequest = useRef(0);
  const [loanDetailId, setLoanDetailId] = useState(null);
  const [loanDetail, setLoanDetail] = useState(null);
  const [loanDetailLoading, setLoanDetailLoading] = useState(false);
  const [loanDetailError, setLoanDetailError] = useState("");
  const loanDetailRequest = useRef(0);

  const auth = Boolean(token);
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();


  const closeEventDetail = useCallback(() => {
    eventDetailRequest.current += 1;
    setEventDetailId(null);
    setEventDetail(null);
    setEventDetailLoading(false);
    setEventDetailError("");
  }, []);

  const openEventDetail = useCallback(async (eventId) => {
    if (!eventId) return;
    const requestId = ++eventDetailRequest.current;
    setEventDetailId(eventId);
    setEventDetail(null);
    setEventDetailError("");
    setEventDetailLoading(true);

    try {
      const data = await read(
        await fetch(`/admin/reconciliation/events/${encodeURIComponent(eventId)}`, {
          headers: { "X-Admin-Token": token },
        }),
      );
      if (requestId === eventDetailRequest.current) setEventDetail(data);
    } catch (error) {
      if (requestId === eventDetailRequest.current) setEventDetailError(error.message || String(error));
    } finally {
      if (requestId === eventDetailRequest.current) setEventDetailLoading(false);
    }
  }, [token]);

  const closeLoanDetail = useCallback(() => {
    loanDetailRequest.current += 1;
    setLoanDetailId(null);
    setLoanDetail(null);
    setLoanDetailLoading(false);
    setLoanDetailError("");
  }, []);

  const openLoanDetail = useCallback(async (loanId) => {
    if (loanId === null || loanId === undefined || loanId === "") return;
    const requestId = ++loanDetailRequest.current;
    setLoanDetailId(loanId);
    setLoanDetail(null);
    setLoanDetailError("");
    setLoanDetailLoading(true);

    try {
      const data = await read(
        await fetch(`/loans/${encodeURIComponent(loanId)}`),
      );
      if (requestId === loanDetailRequest.current) setLoanDetail(data);
    } catch (error) {
      if (requestId === loanDetailRequest.current) setLoanDetailError(error.message || String(error));
    } finally {
      if (requestId === loanDetailRequest.current) setLoanDetailLoading(false);
    }
  }, []);

  const events = usePage(
    `/admin/reconciliation/events${query ? `?${query}` : ""}`,
    token,
    auth && ["dashboard", "events"].includes(tab),
    10,
  );
  const issues = usePage(
    "/admin/reconciliation/issues",
    token,
    auth && tab === "dashboard",
    10,
  );
  const loans = usePage(
    "/loans",
    "",
    auth && ["dashboard", "loans"].includes(tab),
    tab === "dashboard" ? 50 : 10,
  );
  const overpayments = usePage("/admin/reconciliation/overpayments", token, auth && tab === "overpayments", 10);
  const retries = usePage("/admin/reconciliation/provider-lookups", token, auth && tab === "receivables", 10);

  const loadSummary = useCallback(async () => {
    if (!auth) return;
    const data = await read(
      await fetch("/admin/reconciliation/summary", { headers: { "X-Admin-Token": token } }),
    );
    setSummary(data);
  }, [auth, token]);

  useEffect(() => {
    loadSummary().catch(() => {});
  }, [loadSummary]);

  // Keep transient operation feedback useful without leaving stale banners on screen.
  useEffect(() => {
    if (!simulationNote) return undefined;
    const timer = window.setTimeout(() => setSimulationNote(""), 4500);
    return () => window.clearTimeout(timer);
  }, [simulationNote]);

  useEffect(() => {
    if (!retryError) return undefined;
    const timer = window.setTimeout(() => setRetryError(""), 5000);
    return () => window.clearTimeout(timer);
  }, [retryError]);

  // Keep scrollbar tracks invisible. Show only the thumb while a scrollable
  // container is actively moving, then fade it back out shortly afterwards.
  useEffect(() => {
    const selector = ".table-scroll, .drawer, .event-detail-body, .detail-json, .detail-table-wrap, .card";
    const hideTimers = new Map();

    const markScrolling = (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || !target.matches(selector)) return;

      target.classList.add("is-scrolling");
      const existing = hideTimers.get(target);
      if (existing) window.clearTimeout(existing);

      const timer = window.setTimeout(() => {
        target.classList.remove("is-scrolling");
        hideTimers.delete(target);
      }, 700);
      hideTimers.set(target, timer);
    };

    window.addEventListener("scroll", markScrolling, true);
    return () => {
      window.removeEventListener("scroll", markScrolling, true);
      hideTimers.forEach((timer, element) => {
        window.clearTimeout(timer);
        element.classList.remove("is-scrolling");
      });
      hideTimers.clear();
    };
  }, []);

  // Escape closes the top-most overlay first. Event details can be opened
  // from inside the dashboard View all overlay without closing the list below.
  useEffect(() => {
    if (!expanded && !eventDetailId && !loanDetailId) return undefined;
    const closeOnEscape = (event) => {
      if (event.key !== "Escape") return;
      if (loanDetailId) closeLoanDetail();
      else if (eventDetailId) closeEventDetail();
      else setExpanded(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [closeEventDetail, closeLoanDetail, eventDetailId, expanded, loanDetailId]);

  useEffect(() => {
    if (!expanded && !eventDetailId && !loanDetailId) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [eventDetailId, expanded, loanDetailId]);

  if (!auth) {
    return (
      <main className="login">
        <section className="login-card">
          <h1>CreditHub</h1>
          <p>Reconciliation operations</p>
          <input
            value={entry}
            type="password"
            placeholder="Staff token"
            onChange={(event) => setEntry(event.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={() => {
              sessionStorage.setItem("admin_token", entry);
              setToken(entry);
            }}
          >
            Sign in
          </button>
        </section>
      </main>
    );
  }

  const nav = [
    ["dashboard", "Dashboard"],
    ["events", "Events"],
    ["overpayments", "Overpayments"],
    ["loans", "Loans"],
    ["receivables", "Pending receivables"],
  ];

  const eventCols = [
    ["Reference", (row) => (
      <button
        type="button"
        className="event-detail-link mono-ref"
        onClick={(event) => {
          event.stopPropagation();
          openEventDetail(row.id);
        }}
        title="View reconciliation event details"
      >
        {row.reference || row.external_ref || row.id}
      </button>
    )],
    ["Provider", (row) => providerName[row.provider] || row.provider],
    ["Kind", (row) => eventKind[row.kind] || row.kind],
    ["Amount", (row) => <span className="amount-cell">{money.format(row.gross_amount)}</span>],
    ["Status", (row) => <StatusBadge status={row.status} />],
  ];

  const issueCols = [
    ["Reason", (row) => row.reason],
    ["Loan", (row) => row.loan_id ? (
      <button type="button" className="loan-detail-link mono-ref" onClick={() => openLoanDetail(row.loan_id)}>
        Loan #{row.loan_id}
      </button>
    ) : "—"],
    ["Created", (row) => new Date(row.created_at).toLocaleString()],
  ];

  const refreshReconciliation = async () => {
    await Promise.allSettled([
      events.refresh(),
      issues.refresh(),
      loans.refresh(),
      loadSummary(),
    ]);
  };

  const postSyntheticPayment = async (payload, successMessage) => {
    const response = await fetch("/webhooks/payments", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Webhook-Token": WEBHOOK_TOKEN,
      },
      body: JSON.stringify(payload),
    });

    if (response.status === 501) {
      throw new Error("The payments webhook is not implemented yet (POST /webhooks/payments).");
    }
    if (!response.ok) {
      let detail = `Webhook returned ${response.status}`;
      try {
        const data = await response.json();
        detail = data.detail || data.message || detail;
      } catch {
        /* response was not JSON */
      }
      throw new Error(detail);
    }

    setSimulationNote(successMessage);
    await refreshReconciliation();
  };

  const simulate = async () => {
    const loanList = loans.items || [];
    if (!loanList.length) {
      setSimulationNote("No loans are available to simulate a payment against.");
      return;
    }

    const activeLoans = loanList.filter((loan) => loan.status === "active" && Number(loan.outstanding) > 0);
    const closedLoans = loanList.filter((loan) => loan.status !== "active");
    const choose = (list) => list[Math.floor(Math.random() * list.length)];

    let loan;
    let amount;

    if (simulationMode === "active") {
      loan = choose(activeLoans);
      if (!loan) {
        setSimulationNote("There is no active loan available for this scenario.");
        return;
      }
      const candidate = [5000, 10000, 20000][Math.floor(Math.random() * 3)];
      amount = Math.min(candidate, Number(loan.outstanding));
    } else if (simulationMode === "full") {
      loan = choose(activeLoans);
      if (!loan) {
        setSimulationNote("There is no active loan available for a full repayment.");
        return;
      }
      amount = Number(loan.outstanding);
    } else if (simulationMode === "overpayment") {
      loan = choose(activeLoans);
      if (!loan) {
        setSimulationNote("There is no active loan available for an overpayment.");
        return;
      }
      amount = Number(loan.outstanding) + 5000;
    } else if (simulationMode === "closed") {
      loan = choose(closedLoans);
      if (!loan) {
        setSimulationNote("There is no closed loan available for this scenario.");
        return;
      }
      amount = 5000;
    } else {
      loan = choose(loanList);
      const choices = [5000, 10000, 20000, Number(loan.outstanding) || 5000];
      amount = choices[Math.floor(Math.random() * choices.length)];
    }

    setSimulationNote("");
    setSimulating(true);
    try {
      await postSyntheticPayment(
        {
          external_ref: `SIM-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
          loan_id: loan.id,
          amount,
          channel: "paystack",
        },
        `Synthetic ${money.format(amount)} payment sent for loan ${loan.id}.`,
      );
    } catch (error) {
      setSimulationNote(`Simulation failed: ${error.message}`);
    } finally {
      setSimulating(false);
    }
  };

  const redeliver = async (row) => {
    if (!row.loan_id || row.gross_amount == null || !row.reference) {
      setSimulationNote("This event does not contain enough source payment data to redeliver it.");
      return;
    }

    setSimulationNote("");
    setRedelivering(row.id);
    try {
      await postSyntheticPayment(
        {
          external_ref: row.reference,
          loan_id: row.loan_id,
          amount: row.gross_amount,
          channel: row.provider || "paystack",
        },
        `Redelivered ${row.reference}. It should be treated as the same payment, not applied twice.`,
      );
    } catch (error) {
      setSimulationNote(`Redelivery failed: ${error.message}`);
    } finally {
      setRedelivering(null);
    }
  };

  const eventColsWithActions = [
    ...eventCols,
    ["", (row) => (
      <button
        className="btn btn-compact"
        onClick={(event) => {
          event.stopPropagation();
          redeliver(row);
        }}
        disabled={redelivering === row.id || simulating || !row.loan_id}
        title={row.loan_id ? "Redeliver this payment with the same reference" : "Loan data unavailable for redelivery"}
      >
        {redelivering === row.id ? "Sending…" : "Redeliver ↻"}
      </button>
    )],
  ];

  const retry = async (id) => {
    setRetryError("");
    setRetrying(id);
    try {
      await read(
        await fetch(`/admin/reconciliation/provider-lookups/${id}/retry`, {
          method: "POST",
          headers: { "X-Admin-Token": token },
        }),
      );
      await retries.refresh();
    } catch (error) {
      setRetryError(error.message);
    } finally {
      setRetrying(null);
    }
  };

  const previewButton = (section, page, previewSize) => {
    const allShown = !page.loading && !page.hasMore && page.items.length <= previewSize;
    if (allShown) return null;
    return (
      <button
        className="link-btn preview-action"
        onClick={() => setExpanded(section)}
      >
        View all →
      </button>
    );
  };

  const signOut = () => {
    sessionStorage.removeItem("admin_token");
    setToken("");
    setEntry("");
    setSummary(null);
    setExpanded(null);
    closeLoanDetail();
    closeEventDetail();
    setSimulationNote("");
    setRetryError("");
  };

  const currentTitle = nav.find((item) => item[0] === tab)?.[1] || "Dashboard";

  // Dashboard inspection uses the same cursor pagination as the main tabs.
  // Only the first server batch exists initially; each additional batch is
  // requested when the overlay reaches the bottom.
  const inspectSource = expanded === "events" ? events : issues;
  const inspectColumns = expanded === "events" ? eventCols : issueCols;

  return (
    <main className={`workspace ${menu ? "" : "collapsed"}`}>
      <aside className="sidebar">
        <button
          className="close"
          aria-label="Collapse navigation"
          title="Collapse navigation"
          onClick={() => setMenu(false)}
        >
          ‹
        </button>
        <h1>CreditHub</h1>
        {nav.map(([id, label]) => (
          <button
            className={tab === id ? "side active" : "side"}
            key={id}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
        <button className="side signout" onClick={signOut}>
          Sign out
        </button>
      </aside>

      <section className="content">
        <header className="content-head">
          {!menu && (
            <button
              className="menu-toggle"
              aria-label="Expand navigation"
              title="Expand navigation"
              onClick={() => setMenu(true)}
            >
              ☰
            </button>
          )}
          <div className="page-heading">
            <h2>{currentTitle}</h2>
            <p>{pageDescriptions[tab]}</p>
          </div>
        </header>

        {simulationNote && (
          <div className="banner note simulation-note">
            {simulationNote}
            <button className="banner-dismiss" onClick={() => setSimulationNote("")} aria-label="Dismiss">×</button>
          </div>
        )}

        {tab === "dashboard" && (
          <>
            <section className="stats">
              <Card
                label="Gross received"
                value={summary ? money.format(summary.amounts.gross_received) : "—"}
                meta={`${summary?.counts.total ?? "—"} payment events`}
                click={() => setExpanded("events")}
              />
              <Card
                label="Processed"
                value={summary ? money.format(summary.amounts.applied) : "—"}
                meta={`${summary?.counts.applied ?? "—"} applied events`}
                click={() => setTab("events")}
              />
              <Card
                label="Rejected"
                value={summary?.counts.rejected ?? "—"}
                meta={summary ? `${summary.rejection_rate}% rejection rate` : "—"}
                click={() => setTab("events")}
              />
              <Card
                label="Exceptions"
                value={summary?.counts.open_issues ?? "—"}
                meta={summary ? `${money.format(summary.amounts.overpaid)} overpaid` : "—"}
                click={() => setExpanded("issues")}
              />
            </section>

            <div className="preview-head">
              <div>
                <h3>Recent payments</h3>
                <span className="preview-sub">Synthetic payments use the same webhook as incoming rail events. Click any payment row to inspect its details.</span>
              </div>
              <div className="preview-actions">
                <select
                  className="scenario-select"
                  value={simulationMode}
                  onChange={(event) => setSimulationMode(event.target.value)}
                  aria-label="Simulation scenario"
                >
                  <option value="random">Random payment</option>
                  <option value="active">Active-loan payment</option>
                  <option value="full">Full repayment</option>
                  <option value="overpayment">Overpayment</option>
                  <option value="closed">Payment to closed loan</option>
                </select>
                <button
                  className="btn btn-primary simulate-btn"
                  onClick={simulate}
                  disabled={simulating}
                  title="Generate a synthetic incoming payment for testing"
                >
                  {simulating ? "Sending…" : "Simulate incoming payment"}
                </button>
                {previewButton("events", events, 8)}
              </div>
            </div>
            <Table
              data={events.items.slice(0, 8)}
              columns={eventCols}
              page={events}
              loadOnScroll={false}
              onRowClick={(row) => openEventDetail(row.id)}
              emptyMessage="No payment events have been received yet."
            />

            <div className="preview-head">
              <h3>Needs attention</h3>
              {previewButton("issues", issues, 3)}
            </div>
            <Table
              data={issues.items.slice(0, 3)}
              columns={issueCols}
              page={issues}
              loadOnScroll={false}
              emptyMessage="No reconciliation issues require attention."
            />
          </>
        )}

        {tab === "events" && (
          <>
            <div className="filter-bar">
              <input
                placeholder="Search reference"
                value={filters.reference}
                onChange={(event) => setFilters({ ...filters, reference: event.target.value })}
              />
              <select
                value={filters.provider}
                onChange={(event) => setFilters({ ...filters, provider: event.target.value })}
              >
                <option value="">All providers</option>
                <option value="paystack">Paystack</option>
                <option value="mock">Mock</option>
                <option value="core_banking">Core banking</option>
              </select>
              <select
                value={filters.status}
                onChange={(event) => setFilters({ ...filters, status: event.target.value })}
              >
                <option value="">All statuses</option>
                <option value="applied">Processed</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
            <Table
              tall
              data={events.items}
              columns={eventColsWithActions}
              page={events}
              onRowClick={(row) => openEventDetail(row.id)}
              emptyMessage="No events match these filters."
            />
          </>
        )}

        {tab === "loans" && (
          <Table
            tall
            data={loans.items}
            columns={[
              ["Borrower", (row) => (
                <button
                  type="button"
                  className="loan-detail-link loan-borrower-link"
                  onClick={() => openLoanDetail(row.id)}
                  title="View loan details"
                >
                  <span className="name">{row.borrower_name}</span>
                  <span className="sub-id">Loan #{row.id}</span>
                </button>
              )],
              ["Outstanding", (row) => <span className="amount-cell">{money.format(row.outstanding)}</span>],
              ["Status", (row) => <StatusBadge status={row.status} />],
            ]}
            page={loans}
            emptyMessage="No loans to show."
          />
        )}

        {tab === "overpayments" && (
          <Table
            tall
            data={overpayments.items}
            columns={[
              ["Loan", (row) => (
                <button type="button" className="loan-detail-link mono-ref" onClick={() => openLoanDetail(row.loan_id)}>
                  Loan #{row.loan_id}
                </button>
              )],
              ["Remaining", (row) => <span className="amount-cell">{money.format(row.remaining_amount)}</span>],
              ["Status", (row) => <StatusBadge status={row.status} />],
            ]}
            page={overpayments}
            emptyMessage="No overpayments to show."
          />
        )}

        {tab === "receivables" && (
          <>
            {retryError && <p className="banner">Retry failed: {retryError}</p>}
            <Table
              tall
              data={retries.items}
              columns={[
                ["Provider", (row) => providerName[row.provider] || row.provider],
                ["Attempts", (row) => row.attempts],
                ["Status", (row) => <StatusBadge status={row.status} />],
                ["", (row) => (
                  <button className="btn" disabled={retrying === row.id} onClick={() => retry(row.id)}>
                    {retrying === row.id ? "Retrying…" : "Retry"}
                  </button>
                )],
              ]}
              page={retries}
              emptyMessage="No provider lookups are waiting for action."
            />
          </>
        )}

        {tab === "dashboard" && expanded && (
          <div
            className="inspect-overlay"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setExpanded(null);
            }}
          >
            <section
              className="inspect-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="inspect-title"
            >
              <header className="inspect-head">
                <div>
                  <h3 id="inspect-title">{expanded === "events" ? "All payment events" : "All issues needing attention"}</h3>
                  <p>{expanded === "events" ? "Scroll through the reconciliation feed without leaving the dashboard." : "Inspect reconciliation exceptions, then close this view when finished."}</p>
                </div>
                <button
                  className="inspect-close"
                  onClick={() => setExpanded(null)}
                  aria-label="Close inspection view"
                  title="Close"
                >
                  ×
                </button>
              </header>
              <div className="inspect-body">
                <Table
                  expanded
                  data={inspectSource.items}
                  columns={inspectColumns}
                  page={inspectSource}
                  loadOnScroll
                  onRowClick={expanded === "events" ? (row) => openEventDetail(row.id) : null}
                  emptyMessage={expanded === "events" ? "No payment events have been received yet." : "No reconciliation issues require attention."}
                />
              </div>
              <footer className="inspect-pagination">
                <span className="inspect-page-status">
                  {inspectSource.loading
                    ? `Loaded ${inspectSource.items.length} · fetching next batch…`
                    : inspectSource.hasMore
                      ? `Loaded ${inspectSource.items.length} · scroll for more`
                      : `${inspectSource.items.length} loaded · end of results`}
                </span>
              </footer>
            </section>
          </div>
        )}

        {eventDetailId && (
          <EventDetailOverlay
            eventId={eventDetailId}
            data={eventDetail}
            loading={eventDetailLoading}
            error={eventDetailError}
            onClose={closeEventDetail}
            onRetry={() => openEventDetail(eventDetailId)}
            onOpenLoan={openLoanDetail}
          />
        )}

        {loanDetailId !== null && loanDetailId !== undefined && (
          <LoanDetailOverlay
            loanId={loanDetailId}
            data={loanDetail}
            loading={loanDetailLoading}
            error={loanDetailError}
            onClose={closeLoanDetail}
            onRetry={() => openLoanDetail(loanDetailId)}
          />
        )}
      </section>
    </main>
  );
}