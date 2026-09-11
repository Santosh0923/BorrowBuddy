export function navigationFor(role) {
  return {
    student: [['overview','grid','Overview'],['resources','box','Browse Resources'],['requests','list','My Requests'],['history','clock','Borrow History']],
    faculty: [['overview','grid','Overview'],['resources','box','My Resources'],['requests','list','Student Requests'],['returns','clock','Issued Items / Returns']],
    admin: [['overview','grid','Overview'],['verification','shield','Resource Verification'],['resources','box','Inventory'],['requests','list','Requests'],['users','users','Users'],['exceptions','tool','Exceptions / Maintenance']],
  }[role] || [];
}
