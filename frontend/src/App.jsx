import { useCallback, useEffect, useState } from 'react';
import { api, matchesRequest, dateLabel, roleName, statuses, terminal, today } from './api';
import { Badge, Empty, Icon } from './ui';
import { Editor } from './forms';
import { Auth, RequestDetail, RequestTable, ResourceCard } from './views';
import { AdminOverview, FacultyOverview, FacultyReturns, StudentOverview } from './portals';
import { navigationFor } from './navigation';
import { ResourceDetail } from './views';
import './App.css';

const emptyData = { user: null, resources: [], requests: [], custodians: [], users: [], audit: { items: [], total: 0 } };
const initials = (name) => name?.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase();
async function fetchWorkspace(token) {
  const user = await api('/auth/me', { token });
  const [resources, requests, custodians, users] = await Promise.all([
    api(`/resources?include_retired=${user.role !== 'student'}`, { token }), api('/requests', { token }),
    user.role === 'admin' ? api('/admin/users/faculty', { token }) : [],
    user.role === 'admin' ? api('/admin/users', { token }) : [],
  ]);
  return { user, resources, requests, custodians, users };
}
export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('borrowbuddy_token') || '');
  const [data, setData] = useState(emptyData);
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState(() => location.pathname.split('/')[2] || 'overview');
  const [search, setSearch] = useState('');
  const [exceptionRequestSearch, setExceptionRequestSearch] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [onlyAvailable, setOnlyAvailable] = useState(false);
  const [showRetired, setShowRetired] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editor, setEditor] = useState(null);
  const [detail, setDetail] = useState(null);
  const [resourceDetail, setResourceDetail] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const logout = useCallback(() => { localStorage.removeItem('borrowbuddy_token'); localStorage.removeItem('borrowbuddy_user'); sessionStorage.removeItem('borrowbuddy_user'); setToken(''); setData(emptyData); setView('overview'); setEditor(null); setDetail(null); setResourceDetail(null); setNotice(''); setError(''); setSearch(''); setExceptionRequestSearch(''); setCategory(''); setStatus(''); setOnlyAvailable(false); setShowRetired(false); setRefreshing(false); history.replaceState(null,'','/login'); }, []);
  useEffect(() => {
    if (!token) return;
    let active = true;
    fetchWorkspace(token).then((result) => { if (active) { setData(result); setError(''); setRefreshing(false); if (!navigationFor(result.user.role).some(([key]) => location.pathname === `/${result.user.role}/${key}`)) { history.replaceState(null,'',`/${result.user.role}/overview`); setView('overview'); } } }).catch((err) => {
      if (!active) return;
      setError(err.message); setRefreshing(false);
      if (err.status === 401 || err.status === 403 && /deactivated/.test(err.message)) {
        logout();
      }
    });
    return () => { active = false; };
  }, [token, revision, logout]);
  function login(value) { localStorage.setItem('borrowbuddy_token', value); setToken(value); setError(''); }

  useEffect(() => {
    if (!token || view !== 'overview') return;
    // Re-entering Overview (including browser Back) and returning to the tab
    // must include changes made elsewhere since the workspace was loaded.
    const reloadOverview = () => { setRefreshing(true); setRevision((r) => r + 1); };
    reloadOverview();
    window.addEventListener('focus', reloadOverview);
    return () => window.removeEventListener('focus', reloadOverview);
  }, [token, view]);

  useEffect(() => {
    function guard(event) {
      if (!localStorage.getItem('borrowbuddy_token') || event.type === 'borrowbuddy-session-expired') logout();
      else if (event.type === 'storage' || event.type === 'pageshow' && event.persisted) { setData(emptyData); setToken(localStorage.getItem('borrowbuddy_token')); setRevision((r) => r + 1); }
      else if (event.type === 'popstate' && data.user) {
        const next = location.pathname.split('/')[2];
        if (navigationFor(data.user.role).some(([key]) => key === next) && location.pathname.startsWith('/'+data.user.role+'/')) setView(next);
        else { history.replaceState(null,'','/'+data.user.role+'/overview'); setView('overview'); }
      }
    }
    if (!localStorage.getItem('borrowbuddy_token')) history.replaceState(null,'','/login');
    for (const event of ['popstate','storage','pageshow','borrowbuddy-session-expired']) window.addEventListener(event,guard);
    return () => { for (const event of ['popstate','storage','pageshow','borrowbuddy-session-expired']) window.removeEventListener(event,guard); };
  }, [data.user, logout]);

  function navigate(next) { if (!navigationFor(user.role).some(([key]) => key === next)) return; history.pushState(null,'',`/${user.role}/${next}`); setView(next); setSearch(''); setExceptionRequestSearch(''); setCategory(''); setStatus(''); }
  function refresh() { setRefreshing(true); setRevision((r) => r + 1); }
  function saved(message, updatedRequest) {
    if (localStorage.getItem('borrowbuddy_token') !== token) return;
    setEditor(null); setResourceDetail(null);
    if (updatedRequest) {
      setData((current) => ({ ...current, requests: current.requests.map((request) => request.id === updatedRequest.id ? updatedRequest : request) }));
      setDetail(updatedRequest);
    } else setDetail(null);
    setNotice(message || 'Changes saved.'); refresh();
  }
  function openAction(mode, item) { setDetail(null); setResourceDetail(null); if (mode === 'ownership') { setEditor({ mode: 'resource', item: resources.find((r) => r.id === item.resource_id) }); } else setEditor({ mode, item }); }
  const { user, resources, requests, custodians, users } = data;
  if (!token) return <Auth onLogin={login} />;
  if (!user) return <main className="loading-page"><span className="brand-mark"><Icon name="box" /></span><h2>{error ? 'Workspace unavailable' : 'Opening your workspace…'}</h2>{error && <><p role="alert">{error}</p><button className="button primary" onClick={refresh}>Try again</button><button className="button secondary" onClick={logout}>Back to sign in</button></>}</main>;
  const admin = user.role === 'admin';
  const faculty = user.role === 'faculty';
  const active = requests.filter((r) => !terminal.includes(r.status));
const visibleResources = resources.filter((r) => {
  const hasException =
    r.status === 'Maintenance' ||
    r.unavailable_quantity > 0 ||
    r.maintenance_quantity > 0 ||
    !r.custodian_id;

  return (
    (
      user.role !== 'student' ||
      (
        r.verification_status === 'Verified' &&
        r.is_active &&
        r.status === 'Available' &&
        r.available_quantity > 0 &&
        r.custodian_id
      )
    ) &&
    (showRetired || r.is_active) &&
    (
      view !== 'verification' ||
      r.verification_status === 'Pending Verification'
    ) &&
    (
      view !== 'exceptions' ||
      hasException
    ) &&
    (
      !category ||
      r.category === category
    ) &&
    (
      !onlyAvailable ||
      (
        r.status === 'Available' &&
        r.available_quantity > 0 &&
        r.custodian_id
      )
    ) &&
    `${r.name} ${r.category} ${r.location} ${r.custodian_name || ''}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );
});
  const scopedRequests = requests.filter((r) => (view !== 'history' || terminal.includes(r.status)) && (user.role !== 'student' || view !== 'requests' || !terminal.includes(r.status)) && (view !== 'exceptions' || r.is_overdue || r.status === 'Maintenance Required'));
  const visibleRequests = scopedRequests.filter((r) => (!status || (status === 'Overdue' ? r.is_overdue : r.status === status)) && matchesRequest(r, view === 'exceptions' ? exceptionRequestSearch : search));
  const requestStatuses = faculty && view === 'requests' ? ['Requested', 'Approved', 'Ready for Pickup', 'Rejected', 'Cancelled'] : [...statuses, 'Overdue'];
  const navigation = navigationFor(user.role);
  const title = view === 'overview' ? {student:'Your Student portal',faculty:'Your Faculty portal',admin:'Admin overview'}[user.role] : navigation.find(([key]) => key === view)?.[2];
  const subtitle = view === 'overview' ? {student:'Browse, request, and track your own borrowing.',faculty:'Provide resources and manage requests from your students.',admin:'Verify listings, govern inventory, and manage platform access.'}[user.role] : {resources:faculty?'Manage the resources you own. New and edited listings require Admin verification.':admin?'Inspect inventory and manage Faculty ownership.':'Browse verified and active campus resources.',verification:'Review Faculty submissions before students can borrow.',requests:'Track requests and open their details for the full activity history.',history:'Your completed, rejected, and cancelled requests.',returns:'Confirm handovers, receive returned items, and complete return checks.',users:'Manage Student, Faculty, and Admin access.',exceptions:'Review overdue requests, missing ownership, and unavailable inventory.'}[view];

  return <div className="workspace"><aside className="sidebar"><a className="brand" href="#overview" onClick={(e) => { e.preventDefault(); navigate('overview'); }}><span className="brand-mark"><Icon name="box" size={23} /></span>BorrowBuddy<span className="brand-period">.</span></a><div className="workspace-label">CAMPUS WORKSPACE</div><nav aria-label="Main navigation">{navigation.map(([key, icon, label]) => <button key={key} className={view === key ? 'active' : ''} aria-current={view === key ? 'page' : undefined} onClick={() => navigate(key)}><Icon name={icon} />{label}{key === 'requests' && active.length > 0 && <span className="nav-count">{active.length}</span>}</button>)}</nav><div className="sidebar-note"><Icon name="shield" size={24} /><strong>Shared with care.</strong><p>Faculty ownership.<br />Accountable borrowing.</p></div><div className="sidebar-account"><span className="avatar">{initials(user.name)}</span><div><strong>{user.name}</strong><small>{roleName(user.role)}</small></div><button onClick={logout} className="icon-button" aria-label="Logout"><Icon name="logout" size={18} /></button></div></aside>
    <div className="workspace-main"><header className="topbar"><div>Workspace <span>/</span> <strong>{navigation.find(([key]) => key === view)?.[2]}</strong></div><div className="topbar-right"><span className="date-chip">{dateLabel(today())}</span><Badge value={roleName(user.role)} /><button className="button text-button" onClick={refresh} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button></div></header>
      <main className="content"><div className="page-heading"><div><span className="eyebrow">BORROWBUDDY / {admin ? 'ADMINISTRATION' : faculty ? 'FACULTY' : 'STUDENT LIFE'}</span><h1>{title}</h1><p>{subtitle}</p></div>{view === 'resources' && faculty ? <button className="button primary" onClick={() => setEditor({ mode: 'resource' })}><Icon name="plus" />Add resource</button> : view === 'users' ? <button className="button primary" onClick={() => setEditor({ mode: 'user' })}><Icon name="plus" />Add user</button> : view === 'overview' && <button className="button primary" onClick={() => navigate(faculty ? 'requests' : admin ? 'verification' : 'resources')}>{faculty ? 'Student Requests' : admin ? 'Review listings' : 'Browse Resources'}<Icon name="arrow" size={18} /></button>}</div>
        {error && <div role="alert" className="notice error">{error}<button onClick={refresh}>Retry</button></div>}{notice && <div role="status" className="notice success">{notice}<button aria-label="Dismiss notification" onClick={() => setNotice('')}><Icon name="close" size={16} /></button></div>}
        {view === 'overview' && (user.role === 'student' ? <StudentOverview data={data} navigate={navigate} onOpen={setDetail} /> : faculty ? <FacultyOverview data={data} navigate={navigate} onOpen={setDetail} /> : <AdminOverview data={data} navigate={navigate} />)}
        {['resources','verification','exceptions'].includes(view) && <>{view === 'exceptions' && <div className="section-title"><div><h2>Resource exceptions</h2><p>Missing Faculty ownership, maintenance, or unavailable inventory.</p></div></div>}<div className="toolbar"><div className="search-field"><Icon name="search" /><input aria-label="Search resources" placeholder="Search resources, locations, Faculty owners…" value={search} onChange={(e) => setSearch(e.target.value)} /></div><select aria-label="Filter category" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All categories</option>{[...new Set(resources.map((r) => r.category))].sort().map((c) => <option key={c}>{c}</option>)}</select><label className="checkbox"><input type="checkbox" checked={onlyAvailable} onChange={(e) => setOnlyAvailable(e.target.checked)} />Available to borrow</label>{admin && <label className="checkbox"><input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} />Include retired</label>}</div><div className="results-label">{visibleResources.length} resource types</div>{visibleResources.length ? <div className="resource-grid">{visibleResources.map((resource) => <ResourceCard key={resource.id} resource={resource} user={user} verificationPage={view === 'verification'} onAction={openAction} onOpen={setResourceDetail} onEdit={(item) => setEditor({ mode: 'resource', item })} onBorrow={(item) => setEditor({ mode: 'borrow', item })} />)}</div> : <div className="panel"><Empty title="No matching resources" text="Try a different search or clear your filters." /></div>}</>}
        {view === 'returns' && faculty && <FacultyReturns requests={requests} user={user} search={search} onSearch={setSearch} status={status} onStatus={setStatus} onOpen={setDetail} />}
        {['requests','history','exceptions'].includes(view) && <section className="panel">{view === 'exceptions' && <div className="section-title"><div><h2>Request exceptions</h2><p>Overdue loans and returns requiring maintenance. Requested borrows appear in Requests.</p></div><button className="button secondary" onClick={() => navigate('requests')}>View all requests</button></div>}<div className="toolbar inset"><div className="search-field"><Icon name="search" /><input aria-label="Search requests" placeholder="Search student, email, resource, request ID, or status…" value={view === 'exceptions' ? exceptionRequestSearch : search} onChange={(e) => view === 'exceptions' ? setExceptionRequestSearch(e.target.value) : setSearch(e.target.value)} /></div><select aria-label="Filter request status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{requestStatuses.map((s) => <option key={s}>{s}</option>)}</select><span className="count-label" role="status">Showing {visibleRequests.length} of {scopedRequests.length} requests</span></div><RequestTable requests={visibleRequests} user={user} onOpen={setDetail} /></section>}
        {view === 'users' && admin && <section className="panel"><div className="toolbar inset"><div className="search-field"><Icon name="search" /><input aria-label="Search people" placeholder="Search names or emails…" value={search} onChange={(e) => setSearch(e.target.value)} /></div><span className="count-label">{users.length} people</span></div><div className="table-scroll"><table><thead><tr><th>Person</th><th>Role</th><th>Account</th><th>Joined</th><th>Manage</th></tr></thead><tbody>{users.filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(search.toLowerCase())).map((u) => <tr key={u.id}><td><div className="person-cell"><span className="avatar pale">{initials(u.name)}</span><div><strong>{u.name}{u.id === user.id && ' (you)'}</strong><small>{u.email}</small></div></div></td><td>{roleName(u.role)}</td><td><Badge value={u.is_active ? 'Active' : 'Inactive'} /></td><td>{dateLabel(u.created_at)}</td><td>{u.id !== user.id && <button className="button secondary compact" onClick={() => setEditor({ mode: 'manage-user', item: u })}>Manage</button>}</td></tr>)}</tbody></table></div></section>}
        <footer className="workspace-footer"><span>BorrowBuddy</span>Shared resources. Clear responsibility.</footer>
      </main></div>
    {editor && <Editor key={`${editor.mode}-${editor.item?.id || 'new'}`} {...editor} user={user} token={token} custodians={custodians} onClose={() => setEditor(null)} onSaved={saved} />}
    {resourceDetail && <ResourceDetail resource={resourceDetail} user={user} onClose={() => setResourceDetail(null)} onAction={openAction} />}
    {detail && <RequestDetail request={requests.find((r) => r.id === detail.id) || detail} user={user} token={token} onClose={() => setDetail(null)} onAction={openAction} />}
  </div>;
}
