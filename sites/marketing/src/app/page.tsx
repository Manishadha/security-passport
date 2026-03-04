const appUrl = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"

export default function Home() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <section className="py-10">
        <h1 className="text-5xl font-bold tracking-tight">
          Compliance evidence, organized and export-ready.
        </h1>
        <p className="mt-4 text-lg text-gray-700 max-w-2xl">
          SecurityPassport helps organizations collect evidence, keep it current, and generate audit-ready exports with a complete activity trail.
        </p>

        <div className="mt-8 flex gap-4">
          <a href={`${appUrl}/signup`} className="px-4 py-2 rounded border hover:bg-gray-50">
            Sign up
          </a>
          <a href={`${appUrl}/login`} className="px-4 py-2 rounded hover:underline">
            Log in
          </a>
        </div>
      </section>

      <section className="py-10 border-t">
        <h2 className="text-2xl font-semibold">What problem it solves</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="rounded border p-5">
            <div className="font-medium">Evidence sprawl</div>
            <div className="mt-2 text-gray-700 text-sm">
              Files and screenshots live across drives, tickets, and inboxes.
            </div>
          </div>
          <div className="rounded border p-5">
            <div className="font-medium">Slow exports</div>
            <div className="mt-2 text-gray-700 text-sm">
              Audit requests trigger manual collection and formatting work.
            </div>
          </div>
          <div className="rounded border p-5">
            <div className="font-medium">Missing traceability</div>
            <div className="mt-2 text-gray-700 text-sm">
              Hard to prove who changed what and when.
            </div>
          </div>
        </div>
      </section>

      <section className="py-10 border-t">
        <h2 className="text-2xl font-semibold">Features</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="rounded border p-5">
            <div className="font-medium">Evidence vault</div>
            <div className="mt-2 text-gray-700 text-sm">
              Upload evidence with metadata and keep it organized by tenant.
            </div>
          </div>
          <div className="rounded border p-5">
            <div className="font-medium">Audit logs</div>
            <div className="mt-2 text-gray-700 text-sm">
              Immutable activity trail for actions and exports.
            </div>
          </div>
          <div className="rounded border p-5">
            <div className="font-medium">Export packages</div>
            <div className="mt-2 text-gray-700 text-sm">
              Generate ZIP/DOCX exports via background jobs.
            </div>
          </div>
          <div className="rounded border p-5">
            <div className="font-medium">Freshness scans</div>
            <div className="mt-2 text-gray-700 text-sm">
              Periodic checks to keep evidence current and audit-ready.
            </div>
          </div>
        </div>
      </section>

      <section className="py-10 border-t">
        <h2 className="text-2xl font-semibold">Pricing</h2>
        <div className="mt-4 rounded border p-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="font-medium">Early Access</div>
            <div className="text-sm text-gray-700 mt-1">
              Pilot with your team. We’ll help you onboard and configure.
            </div>
          </div>
          <a href="/contact" className="px-4 py-2 rounded border hover:bg-gray-50">
            Contact for pricing
          </a>
        </div>
      </section>
    </main>
  )
}