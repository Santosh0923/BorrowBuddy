const events = {
  Requested: ['Request submitted', 'Awaiting Faculty review.'],
  Approved: ['Request approved', 'Wait for pickup confirmation.'],
  'Ready for Pickup': ['Ready for pickup', 'Your items are ready to collect.'],
  Collected: ['Items collected', ''],
  'Returned Pending Inspection': ['Return received', 'Awaiting inspection.'],
  Completed: ['Return completed', ''],
  Rejected: ['Request rejected', ''],
  Cancelled: ['Request cancelled', ''],
  'Maintenance Required': ['Maintenance needed', 'Returned items require attention.'],
};

// Present lifecycle events only. Audit actions, identifiers and technical
// remarks stay in the backend; expanding history never reveals raw records.
export function presentHistory(history, role) {
  return history.filter((entry) => events[entry.new_status] && entry.old_status !== entry.new_status).map((entry) => {
    const [title, note] = events[entry.new_status];
    const showActor = role === 'faculty' || role === 'admin';
    return {
      title, note, date: entry.created_at,
      ...(showActor && entry.action_by_name ? { actor: entry.action_by_name } : {}),
      ...(showActor && ['Rejected', 'Cancelled'].includes(entry.new_status) && entry.remarks?.trim() ? { reason: entry.remarks.trim() } : {}),
    };
  });
}

export function compactHistory(events) {
  return events.length > 6 ? [events[0], ...events.slice(-5)] : events;
}
