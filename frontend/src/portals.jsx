import { dateLabel, terminal, matchesRequest } from './api';
import { Badge, Empty, Icon, Stat } from './ui';
import { RequestTable } from './views';
import { borrowable, inventoryMetrics, overviewData } from './dashboardMetrics';

function InventorySummary({ inventory }) {
  return <p className="results-label">{inventory.total} total units: {inventory.available} available · {inventory.reserved} reserved / ready for pickup · {inventory.issued} issued · {inventory.inspection} awaiting inspection · {inventory.unavailable} maintenance / otherwise unavailable (including restricted listings).</p>;
}

export function FacultyReturns({ requests, user, search, onSearch, status: selectedStatus, onStatus, onOpen }) {
  const groups = [
    ['Collected', 'Currently Issued', 'Open a request to receive the physical return.', 'No items are currently issued.'],
    ['Returned Pending Inspection', 'Awaiting Return Inspection', 'Open a request to inspect its condition and confirm return.', 'No returns are awaiting inspection.'],
    ['Maintenance Required', 'Maintenance Required', 'Open a request to complete maintenance using the existing condition and stock controls.', 'No returned items require maintenance.'],
    ['Completed', 'Recently Completed Returns', 'Read-only return history, most recent inspection first.', 'No completed returns yet.'],
  ];
  const eligible = requests.filter((request) => groups.some(([status]) => status === request.status));
  const visible = eligible.filter((request) => (!selectedStatus || request.status === selectedStatus) && matchesRequest(request, search));
  return <>
    <div className="toolbar"><div className="search-field"><Icon name="search" /><input aria-label="Search returns" placeholder="Search student, email, resource, request ID, or status…" value={search} onChange={(event) => onSearch(event.target.value)} /></div><select aria-label="Filter return status" value={selectedStatus} onChange={(event) => onStatus(event.target.value)}><option value="">All</option>{groups.map(([status]) => <option key={status}>{status}</option>)}</select><span className="count-label" role="status">Showing {visible.length} of {eligible.length} requests</span></div>
    {groups.filter(([status]) => !selectedStatus || selectedStatus === status).map(([status, title, description, empty]) => {
      const records = visible.filter((request) => request.status === status);
      if (status === 'Completed') records.sort((a, b) => new Date(b.inspection_date || b.updated_at || b.created_at) - new Date(a.inspection_date || a.updated_at || a.created_at));
      return <section className="panel portal-section" aria-label={title} key={status}>
        <div className="section-title"><div><h2>{title}</h2><p>{description}</p></div><span className="count-label">{records.length} requests</span></div>
        {records.length ? <RequestTable requests={records} user={user} onOpen={onOpen} /> : <Empty title={search ? 'No matching returns' : empty} text={search ? 'Try another search or clear the filter.' : description} />}
      </section>;
    })}
  </>;
}


export function StudentOverview({ data, navigate, onOpen }) {
  const { user, resources, requests } = overviewData(data);
  const active = requests.filter((r) => !terminal.includes(r.status));
  const due = requests.filter((r) => r.is_due_soon || r.is_overdue);
  return <>
    <section className="stats-grid admin-stats"><Stat label="Available resources" value={resources.filter((r) => borrowable(r) && r.available_quantity > 0).length} caption="Verified and ready to borrow" icon="box" /><Stat label="Active requests" value={active.length} caption="Your requests in progress" icon="list" /><Stat label="Ready for pickup" value={requests.filter((r) => r.status === 'Ready for Pickup').length} caption="Ready for you to collect" icon="check" /><Stat label="Currently borrowed" value={requests.filter((r) => r.status === 'Collected').length} caption="Loans currently with you" icon="box" /><Stat label="Due soon / overdue" value={due.length} caption="Due within two days or overdue" icon="clock" tone="amber" /><Stat label="Completed borrows" value={requests.filter((r) => r.status === 'Completed').length} caption="Returned and confirmed" icon="check" tone="green" /></section>
    <section className="overview-split"><div className="panel"><div className="section-title"><h2>Your return reminders</h2><button className="button text-button" onClick={() => navigate('requests')}>My Requests</button></div>{due.length ? <div className="reminder-list">{due.map((r) => <button key={r.id} onClick={() => onOpen(r)}><span><strong>{r.resource_name}</strong><small>Return by {dateLabel(r.return_date)}</small></span><Badge value={r.is_overdue ? 'Overdue' : 'Due soon'} /></button>)}</div> : <Empty icon="clock" title="You’re all caught up" text="Upcoming returns will appear here." />}</div><div className="campus-note"><span className="eyebrow">STUDENT PORTAL</span><h2>Find what you need.</h2><p>Browse verified campus resources. Tell the Faculty owner what you need, then collect your items when they’re ready.</p><button className="button light-button" onClick={() => navigate('resources')}>Browse Resources<Icon name="arrow" /></button></div></section>
    <section className="panel"><div className="section-title"><h2>My recent requests</h2><button className="button text-button" onClick={() => navigate('history')}>Borrow History</button></div><RequestTable requests={requests.slice(0,5)} user={user} onOpen={onOpen} /></section>
  </>;
}

export function FacultyOverview({ data, navigate, onOpen }) {
  const { user, resources, requests } = overviewData(data);
  const pending = requests.filter((r) => r.status === 'Requested');
  const inventory = inventoryMetrics(resources);
  return <>
    <section className="stats-grid admin-stats"><Stat label="My active resource listings" value={resources.filter((r) => r.is_active).length} caption="Active listings you own" icon="box" /><Stat label="My available resource units" value={inventory.available} caption="Verified and ready to borrow" icon="check" /><Stat label="Pending student requests" value={pending.length} caption="Awaiting your review" icon="list" tone="violet" /><Stat label="Ready for pickup" value={requests.filter((r) => r.status === 'Ready for Pickup').length} caption="Prepared for collection" icon="check" tone="green" /><Stat label="Currently issued" value={requests.filter((r) => r.status === 'Collected').length} caption="With students" icon="users" /><Stat label="Awaiting return confirmation" value={requests.filter((r) => r.status === 'Returned Pending Inspection').length} caption="Returned; awaiting inspection" icon="clock" tone="amber" /></section>
    <InventorySummary inventory={inventory} />
    <div className="setup-banner"><Icon name="box" /><div><strong>Your resources, your student requests.</strong><p>{resources.filter((r) => r.is_active && r.verification_status === 'Pending Verification').length} listings await Admin verification. Students can browse your listings once they are verified and active.</p></div><button className="button secondary" onClick={() => navigate('resources')}>My Resources</button></div>
    <section className="panel portal-section"><div className="section-title"><div><h2>Student requests to review</h2><p>Review purpose, quantity, and required-until date before approving.</p></div><button className="button text-button" onClick={() => navigate('requests')}>Student Requests</button></div><RequestTable requests={pending} user={user} onOpen={onOpen} /></section>
    <button className="button secondary portal-section" onClick={() => navigate('returns')}>Manage issued items and returns<Icon name="arrow" /></button>
  </>;
}

export function AdminOverview({ data, navigate }) {
  const { resources, users, requests } = overviewData(data);
  const inventory = inventoryMetrics(resources);
  const exceptions = resources.filter((r) => r.is_active && (r.status === 'Maintenance' || r.unavailable_quantity > 0 || r.maintenance_quantity > 0 || !r.custodian_id)).length + requests.filter((r) => r.is_overdue).length;
  const pending = resources.filter((r) => r.verification_status === 'Pending Verification' && r.is_active);
  return <>
    <section className="stats-grid admin-stats"><Stat label="Listings awaiting verification" value={pending.length} caption="Faculty listings to review" icon="shield" tone="violet" /><Stat label="Total inventory" value={inventory.total} caption="Units in active listings" icon="box" /><Stat label="Available inventory" value={inventory.available} caption="Verified and ready to borrow" icon="check" tone="green" /><Stat label="Issued / reserved" value={inventory.issued + inventory.reserved} caption="Units with students or held for pickup" icon="list" /><Stat label="Exceptions" value={exceptions} caption="Resource issues and overdue requests" icon="clock" tone="amber" /><Stat label="Active users" value={users.filter((u) => u.is_active).length} caption="Student, Faculty, and Admin" icon="users" /></section>
    <InventorySummary inventory={inventory} />
    <section className="panel"><div className="section-title"><div><h2>Faculty listings awaiting verification</h2><p>Review ownership and details before students can borrow.</p></div><button className="button primary" onClick={() => navigate('verification')}>Review listings<Icon name="arrow" /></button></div>{pending.length ? <div className="reminder-list">{pending.slice(0,5).map((r) => <button key={r.id} onClick={() => navigate('verification')}><span><strong>{r.name}</strong><small>{r.custodian_name || 'Faculty owner required'} · {r.location} · {r.total_quantity} units</small></span><Badge value="Pending Verification" /></button>)}</div> : <Empty icon="shield" title="No listings awaiting review" text="New Faculty submissions will appear here." />}</section>
    <div className="governance-links"><button className="button secondary" onClick={() => navigate('resources')}>Inspect inventory</button><button className="button secondary" onClick={() => navigate('users')}>Manage users</button><button className="button secondary" onClick={() => navigate('exceptions')}>Review exceptions</button></div>
  </>;
}
