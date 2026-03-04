export default function Pricing() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-3xl font-bold mb-4">Pricing</h1>
      <p className="text-gray-700 mb-8">
        Early access pilots are available for teams who want a fast path to audit-ready evidence exports.
      </p>

      <div className="rounded border p-6">
        <div className="flex items-baseline justify-between">
          <div className="font-medium">Early Access</div>
          <div className="text-sm text-gray-700">Contact for pricing</div>
        </div>

        <ul className="mt-4 list-disc pl-6 text-sm text-gray-700">
          <li>Multi-tenant organization setup</li>
          <li>Evidence vault and audit logs</li>
          <li>Export package generation</li>
          <li>Onboarding support</li>
        </ul>

        <div className="mt-6">
          <a href="/contact" className="px-4 py-2 rounded border hover:bg-gray-50">
            Contact
          </a>
        </div>
      </div>
    </main>
  )
}