const API_URL = import.meta.env.VITE_API_URL || '/api';

export async function api(path, { token, body, ...options } = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (token && (response.status === 401 || response.status === 403 && data.detail === 'Account is deactivated')) {
      window.dispatchEvent(new Event('borrowbuddy-session-expired'));
    }
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => `${item.loc?.at(-1) || 'Input'}: ${item.msg}`).join('. ')
      : data.detail;
    const error = new Error(detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const roleName = (role) => ({ student: 'Student', faculty: 'Faculty', staff: 'Faculty', admin: 'Admin' }[role] || role);
export const terminal = ['Completed', 'Rejected', 'Cancelled'];
export const steps = ['Requested', 'Approved', 'Ready for Pickup', 'Collected', 'Returned Pending Inspection', 'Completed'];
export const statuses = [...steps, 'Maintenance Required', 'Rejected', 'Cancelled'];
export const matchesRequest = (request, search) => [request.student_name, request.student_email, request.resource_name, request.id, `BB-${String(request.id).padStart(4, '0')}`, request.status, request.custodian_name].join(' ').toLowerCase().includes(search.trim().toLowerCase());
export const dateLabel = (value) => value ? new Date(value.length === 10 ? `${value}T12:00:00` : value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Not recorded';
export const timestamp = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'Not recorded';
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
