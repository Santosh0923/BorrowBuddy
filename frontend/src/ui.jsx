import { useEffect, useRef } from 'react';

const paths = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  box: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="M3 8v9l9 5 9-5V8M12 13v9M7 5.8l9 5" /></>,
  list: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V2h6v2M9 9h6M9 13h6M9 17h4" /></>,
  users: <><circle cx="9" cy="7" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  logout: <><path d="M9 4H4v16h5M10 12h11m-4-4 4 4-4 4" /></>,
  location: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z" /><circle cx="12" cy="10" r="2" /></>,
  shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
  tool: <><path d="m14 6 4 4 3-3a7 7 0 0 1-9 8l-6 6-3-3 6-6a7 7 0 0 1 8-9l-3 3Z" /></>,
  book: <><path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15" /></>,
  laptop: <><rect x="5" y="4" width="14" height="12" rx="1.5" /><path d="m5 16-3 4h20l-3-4" /></>,
  ball: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3v18M5 5c8 3 11 6 14 14M19 5C11 8 8 11 5 19" /></>,
};
export function Icon({ name = 'box', size = 20, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.box}</svg>;
}
export function Badge({ value }) {
  const tone = ['Available', 'Completed', 'Good', 'Active'].includes(value) ? 'green' : ['Rejected', 'Retired', 'Major Damage', 'Overdue'].includes(value) ? 'red' : ['Maintenance', 'Maintenance Required', 'Returned Pending Inspection', 'Due soon'].includes(value) ? 'amber' : ['Cancelled', 'Out of Stock', 'Inactive'].includes(value) ? 'gray' : 'blue';
  return <span className={`badge ${tone}`}>{value}</span>;
}
export function Empty({ title, text, icon = 'box', children }) {
  return <div className="empty"><span className="empty-icon"><Icon name={icon} size={28} /></span><h3>{title}</h3><p>{text}</p>{children}</div>;
}
export function Modal({ title, subtitle, children, onClose, busy = false, wide = false }) {
  const ref = useRef(null);
  useEffect(() => { const dialog = ref.current; dialog.showModal(); return () => dialog.close(); }, []);
  return <dialog ref={ref} className={`modal ${wide ? 'wide' : ''}`} onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="modal-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" aria-label="Close dialog" disabled={busy} onClick={onClose}><Icon name="close" /></button></div>
    {children}
  </dialog>;
}
export function Field({ label, children, ...props }) {
  return <label className="field" {...props}><span>{label}</span>{children}</label>;
}
export function Stat({ label, value, caption, icon, tone = 'blue' }) {
  return <div className="stat"><span className={`stat-icon ${tone}`}><Icon name={icon} /></span><span className="stat-label">{label}</span><strong>{value}</strong><small>{caption}</small></div>;
}
