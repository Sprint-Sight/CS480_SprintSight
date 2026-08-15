export default function ProfilePage() {
  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-blue-600">Profile</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">Dr. Sarah Chen</h1>
        </div>

        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-2xl font-bold text-blue-700">
          SC
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Account details</h2>
          <div className="mt-4 space-y-4 text-sm text-slate-600">
            <div>
              <span className="font-medium text-slate-500">Role</span>
              <p className="mt-1 text-slate-900">Instructor</p>
            </div>
            <div>
              <span className="font-medium text-slate-500">Email</span>
              <p className="mt-1 text-slate-900">sarah.chen@sprintsight.edu</p>
            </div>
            <div>
              <span className="font-medium text-slate-500">Department</span>
              <p className="mt-1 text-slate-900">Software Engineering</p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Teaching summary</h2>
          <div className="mt-4 space-y-4">
            <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
              <span className="text-slate-600">Active sections</span>
              <span className="font-semibold text-slate-900">3</span>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
              <span className="text-slate-600">Teams monitored</span>
              <span className="font-semibold text-slate-900">12</span>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3">
              <span className="text-slate-600">Reviews pending</span>
              <span className="font-semibold text-slate-900">6</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
