export default function Security() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-3xl font-bold mb-4">Security</h1>
      <p className="text-gray-700 mb-6">
        SecurityPassport is designed for multi-tenant isolation, operational visibility, and controlled access to evidence.
      </p>

      <div className="space-y-4">
        <section className="rounded border p-6">
          <div className="font-medium">Tenant isolation</div>
          <div className="text-sm text-gray-700 mt-2">
            Tenant context is enforced per request, and data access is scoped by tenant identifiers throughout the system.
          </div>
        </section>

        <section className="rounded border p-6">
          <div className="font-medium">Audit logging</div>
          <div className="text-sm text-gray-700 mt-2">
            System actions and exports are recorded to support traceability and incident investigations.
          </div>
        </section>

        <section className="rounded border p-6">
          <div className="font-medium">Encryption</div>
          <div className="text-sm text-gray-700 mt-2">
            TLS is used in production for data in transit. At-rest controls depend on the chosen infrastructure and storage configuration.
          </div>
        </section>

        <section className="rounded border p-6">
          <div className="font-medium">Responsible disclosure</div>
          <div className="text-sm text-gray-700 mt-2">
            Report security issues to the security contact address on the Contact page.
          </div>
        </section>
      </div>
    </main>
  )
}