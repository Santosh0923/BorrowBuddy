import { useEffect, useState } from 'react';
import { RequestTimeline } from './RequestTimeline';
import { api, dateLabel, steps, terminal, timestamp } from './api';
import { Badge, Empty, Field, Icon, Modal } from './ui';

export function Auth({ onLogin }) {
  const [mode, setMode] = useState('login');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(''); setSuccess('');
    const form = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (mode === 'register') {
        if (form.password !== form.confirm_password) throw new Error('Passwords do not match.');
        delete form.confirm_password;
        await api('/auth/register', { method: 'POST', body: form });
        setMode('login'); setSuccess('Your student account is ready. Sign in to continue.');
      } else {
        const response = await fetch(`${import.meta.env.VITE_API_URL || '/api'}/auth/login`, {
          method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ username: form.email, password: form.password }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Unable to sign in. Check your details.');
        onLogin(result.access_token);
      }
    } catch (err) { setError(err.message === 'Failed to fetch' ? 'Cannot reach BorrowBuddy. Check that the server is running.' : err.message); }
    finally { setBusy(false); }
  }
  return <main className="auth-layout"><section className="auth-story"><a className="brand" href="/"><span className="brand-mark"><Icon name="box" size={26} /></span>BorrowBuddy<span className="brand-period">.</span></a>
    <div className="auth-story-copy"><span className="eyebrow light">THE CAMPUS, CONNECTED</span><h1>Good things<br />are better<br /><em>shared.</em></h1><p>From the first request to the final return.<br />Your campus resources, in good hands.</p></div>
    <div className="sharing-card"><div className="sharing-icon"><Icon name="laptop" size={34} /></div><div><strong>One resource. More possibilities.</strong><span>Borrow thoughtfully. Return confidently.</span></div></div>
    <div className="auth-process"><span><b>01</b> Request</span><i /><span><b>02</b> Collect</span><i /><span><b>03</b> Return</span></div><p className="auth-footer">Built for campus life.</p></section>
    <section className="auth-form-panel"><div className="auth-form-wrap"><span className="eyebrow">YOUR CAMPUS WORKSPACE</span><h2>{mode === 'login' ? 'Welcome back.' : 'Create your BorrowBuddy account'}</h2><p className="muted">{mode === 'login' ? 'Sign in to pick up where you left off.' : 'Create an account to start borrowing.'}</p>
      <div className="auth-tabs"><button disabled={busy} className={mode === 'login' ? 'selected' : ''} onClick={() => { setMode('login'); setError(''); }}>Sign in</button><button disabled={busy} className={mode === 'register' ? 'selected' : ''} onClick={() => { setMode('register'); setError(''); }}>Create account</button></div>
      <form onSubmit={submit} className="form-stack">{mode === 'register' && <Field label="Full name"><input name="name" autoComplete="name" maxLength={100} required placeholder="Your full name" /></Field>}
        <Field label="University email"><input name="email" type="email" autoComplete="username" maxLength={150} required placeholder="you@campus.edu" /></Field><Field label="Password"><input name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'register' ? 8 : undefined} maxLength={128} required placeholder={mode === 'login' ? 'Enter your password' : 'At least 8 characters'} /></Field>
        {mode === 'register' && <Field label="Confirm password"><input name="confirm_password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required /></Field>}{error && <div role="alert" className="notice error">{error}</div>}{success && <div role="status" className="notice success">{success}</div>}<button className="button primary full" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}<Icon name="arrow" /></button></form><p className="auth-help"><Icon name="shield" size={18} />Faculty and Admin accounts are managed by your university.</p>
    </div><p className="auth-bottom">BorrowBuddy · Campus resource management</p></section></main>;
}

export function ResourceCard({ resource, user, onEdit, onBorrow, onOpen, onAction, verificationPage = false }) {
  const canBorrow = resource.verification_status === 'Verified' && resource.is_active && resource.status === 'Available' && resource.available_quantity > 0 && resource.custodian_id;
  const review = verificationPage && user.role === 'admin' && resource.verification_status === 'Pending Verification';
  const icon = { Electronics: 'laptop', Academic: 'book', Sports: 'ball' }[resource.category] || 'box';
  return <article className={`resource-card ${!resource.is_active ? 'retired-card' : ''}`}><div className={`resource-art ${resource.category.toLowerCase()}`}><Icon name={icon} size={55} /><span>{resource.category}</span></div><div className="resource-content"><button className="button text-button" onClick={() => onOpen(resource)}>{review ? 'View Details' : 'Open resource'}</button><div className="resource-meta"><span>#{String(resource.id).padStart(3, '0')}</span><Badge value={resource.verification_status === 'Verified' ? resource.status : resource.verification_status} /></div><h3><button className="resource-title" onClick={() => onOpen(resource)}>{resource.name}</button></h3><p className="location"><Icon name="location" size={16} />{resource.location}</p>{resource.description && <p className="resource-description">{resource.description}</p>}<div className="resource-stock"><strong>{resource.available_quantity}<span> / {resource.total_quantity} available</span></strong><div className="stock-track"><i style={{ width: `${resource.total_quantity ? resource.available_quantity / resource.total_quantity * 100 : 0}%` }} /></div></div><p className={`custodian-caption ${!resource.custodian_id ? 'attention-text' : ''}`}><Icon name="users" size={16} />{resource.custodian_name || 'Faculty owner required'}</p>{review ? <div className="form-actions"><button className="button primary" onClick={() => onAction('verify', resource)}>Verify</button><button className="button danger-solid" onClick={() => onAction('reject-listing', resource)}>Reject</button></div> : user.role !== 'student' ? <button className="button secondary full" onClick={() => onEdit(resource)}>Manage resource<Icon name="arrow" size={17} /></button> : user.role === 'student' ? <button className="button secondary full" disabled={!canBorrow} onClick={() => onBorrow(resource)}>{canBorrow ? 'Request resource' : !resource.custodian_id ? 'Awaiting Faculty owner' : 'Currently unavailable'}{canBorrow && <Icon name="arrow" size={17} />}</button> : <div className="custody-label">{resource.custodian_id === user.id ? 'Assigned to you' : 'Managed by another Faculty owner'}</div>}</div></article>;
}

export function RequestTable({ requests, user, onOpen }) {
  if (!requests.length) return <Empty icon="list" title="No requests here yet" text={user.role === 'student' ? 'Choose a resource to start your first request.' : 'Requests will appear here as students submit them.'} />;
  return <div className="table-scroll"><table><thead><tr><th>Request / resource</th>{user.role !== 'student' && <th>Student</th>}<th>Required until</th>{user.role === 'faculty' && <th>Purpose / reason</th>}<th>Status</th><th>Faculty owner</th><th><span className="sr-only">Details</span></th></tr></thead><tbody>{requests.map((r) => <tr key={r.id}><td><button className="table-link" onClick={() => onOpen(r)}>{r.resource_name || `Resource #${r.resource_id}`}</button><small>BB-{String(r.id).padStart(4, '0')} · {r.quantity} {r.quantity === 1 ? 'unit' : 'units'}</small></td>{user.role !== 'student' && <td>{r.student_name}<small>{r.student_email}</small></td>}<td className={r.is_overdue ? 'attention-text' : ''}>{dateLabel(r.return_date)}{r.is_overdue ? <small className="attention-text">Overdue</small> : r.is_due_soon ? <small>Due soon</small> : null}</td>{user.role === 'faculty' && <td>{r.purpose || 'Not recorded'}</td>}<td><Badge value={r.status} /></td><td>{r.custodian_name || <span className="attention-text">Unassigned</span>}</td><td><button className="icon-button" aria-label={`Open request ${r.id}`} onClick={() => onOpen(r)}><Icon name="arrow" size={18} /></button></td></tr>)}</tbody></table></div>;
}

export function RequestDetail({ request, user, token, onClose, onAction }) {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { let active = true; api(`/requests/${request.id}/history`, { token }).then((r) => { if (active) setHistory(r); }).catch((e) => { if (active) setError(e.message); }); return () => { active = false; }; }, [request.id, request.status, token]);
  const assigned = user.role === 'faculty' && request.custodian_id === user.id;
  const actions = assigned ? { Requested: [['approve', 'Approve request'], ['reject', 'Reject']], Approved: [['ready', 'Mark ready for pickup']], 'Ready for Pickup': [['collect', 'Confirm physical handover']], Collected: [['return', 'Receive physical return']], 'Returned Pending Inspection': [['inspect', 'Confirm return']], 'Maintenance Required': [['complete-maintenance', 'Complete maintenance']] }[request.status] || [] : [];
const cancel =
  (
    user.role === 'student' &&
    request.student_id === user.id &&
    request.status === 'Requested'
  )
  ||
  (
    assigned &&
    ['Approved', 'Ready for Pickup'].includes(request.status)
  )
  ||
  (
    user.role === 'admin' &&
    ['Requested', 'Approved', 'Ready for Pickup'].includes(request.status)
  );
    const index = steps.indexOf(request.status);
  return <Modal wide title={`Request BB-${String(request.id).padStart(4, '0')}`} subtitle={request.resource_name} onClose={onClose}><div className="detail-body"><div className="detail-top"><Badge value={request.status} /><span className="muted">Submitted {dateLabel(request.created_at)}</span></div>{!['Rejected', 'Cancelled'].includes(request.status) && <ol className="workflow-steps">{steps.map((step, i) => <li aria-current={i === index ? 'step' : undefined} className={i <= index || request.status === 'Maintenance Required' && i < 5 ? 'done' : ''} key={step}><span>{i < index ? <Icon name="check" size={13} /> : i + 1}</span>{step === 'Returned Pending Inspection' ? 'Inspection' : step === 'Ready for Pickup' ? 'Ready' : step}</li>)}</ol>}
    <div className="detail-grid"><div><span>Student</span><strong>{request.student_name}</strong><small>{request.student_email}</small></div><div><span>Quantity</span><strong>{request.quantity} {request.quantity === 1 ? 'unit' : 'units'}</strong></div><div><span>Return by</span><strong>{dateLabel(request.return_date)}</strong></div><div><span>Faculty owner</span><strong>{request.custodian_name || 'Not assigned'}</strong></div></div><div className="detail-note"><span>Purpose / reason</span><p>{request.purpose || 'No purpose provided.'}</p></div>{request.rejection_reason && <div className="notice error">Rejection reason: {request.rejection_reason}</div>}{request.inspection_condition && <div className="detail-note"><span>Inspection · {request.inspection_condition}</span><p>{request.inspection_notes || 'No additional notes.'}</p><small>{request.inspector_name} · {timestamp(request.inspection_date)}</small></div>}
    <div className="detail-actions">{actions.map(([action, label], i) => <button className={`button ${i === 0 ? 'primary' : 'danger'}`} key={action} onClick={() => onAction(action, request)}>{label}</button>)}{cancel && <button className="button danger" onClick={() => onAction('cancel', request)}>Cancel request</button>}{user.role === 'admin' && !terminal.includes(request.status) && <button className="button secondary" onClick={() => onAction('ownership', request)}>Change Faculty ownership</button>}</div>{user.role === 'admin' && !terminal.includes(request.status) && <p className="muted small">The Faculty owner handles routine approval, physical handover, and return confirmation.</p>}
    <h3 className="history-title">Request activity</h3>{error && <p role="alert" className="notice error">Unable to load activity. Close and reopen this request to try again.</p>}{history === null && !error ? <p className="muted">Loading activity…</p> : history && <RequestTimeline key={request.id} history={history} role={user.role} />}</div></Modal>;
}

export function ResourceDetail({ resource, user, onClose, onAction }) {
  const faculty = user.role === 'faculty';
  const borrowable = resource.verification_status === 'Verified' && resource.is_active && resource.status === 'Available' && resource.available_quantity > 0 && resource.custodian_id;
  return <Modal title={resource.name} subtitle={resource.category} onClose={onClose}>
    <div className="detail-body"><div className="detail-top"><Badge value={resource.verification_status} /><Badge value={resource.status} /></div>
      <div className="detail-note"><span>Description</span><p>{resource.description || 'No additional description.'}</p></div>
      <div className="detail-grid"><div><span>Faculty owner</span><strong>{resource.custodian_name || 'Unassigned'}</strong></div><div><span>Location</span><strong>{resource.location}</strong></div><div><span>Available</span><strong>{resource.available_quantity} / {resource.total_quantity} units</strong></div><div><span>Listing</span><strong>{resource.is_active ? 'Active' : 'Inactive'}</strong></div></div>
      {resource.verification_reason && <div className="notice portal-section">Review remarks: {resource.verification_reason}</div>}
      <div className="detail-actions">{user.role === 'student' ? <button className="button primary" disabled={!borrowable} onClick={() => onAction('borrow',resource)}>Request resource</button> : <>
        <button className="button secondary" onClick={() => onAction('resource',resource)}>Manage resource</button>
        {faculty && resource.is_active && <button className="button primary" onClick={() => onAction('replenish',resource)}>Replenish quantity</button>}
        {faculty && resource.is_active && resource.verification_status === 'Rejected' && <button className="button secondary" onClick={() => onAction('resubmit',resource)}>Resubmit for verification</button>}
        {user.role === 'admin' && resource.is_active && resource.verification_status === 'Pending Verification' && <><button className="button primary" onClick={() => onAction('verify',resource)}>Verify listing</button><button className="button danger" onClick={() => onAction('reject-listing',resource)}>Reject listing</button></>}
      </>}</div>
    </div>
  </Modal>;
}
