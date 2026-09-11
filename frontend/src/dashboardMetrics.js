export const borrowable = (resource) => resource.is_active && resource.verification_status === 'Verified' && resource.status === 'Available' && !!resource.custodian_id;

export function overviewData(data) {
  const { user } = data;
  return {
    ...data,
    resources: user.role === 'faculty' ? data.resources.filter((r) => r.custodian_id === user.id) : data.resources,
    requests: data.requests.filter((r) => user.role === 'admin' || (user.role === 'faculty' ? r.custodian_id : r.student_id) === user.id),
  };
}

export function inventoryMetrics(resources) {
  return resources.filter((r) => r.is_active).reduce((totals, r) => {
    const available = borrowable(r) ? r.available_quantity : 0;
    totals.total += r.total_quantity;
    totals.available += available;
    totals.reserved += r.reserved_quantity;
    totals.issued += r.issued_quantity;
    totals.inspection += r.inspection_quantity;
    // Available stock in an unverified, unowned, or maintenance listing cannot be borrowed.
    totals.unavailable += r.maintenance_quantity + r.unavailable_quantity + r.available_quantity - available;
    return totals;
  }, { total: 0, available: 0, reserved: 0, issued: 0, inspection: 0, unavailable: 0 });
}
