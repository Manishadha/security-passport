export default function Contact() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-3xl font-bold mb-4">Contact</h1>
      <p className="text-gray-700 mb-6">
        Reach out for early access, pricing, or a demo.
      </p>

      <div className="rounded border p-6">
        <div className="text-sm text-gray-700">Email</div>
        <a className="mt-1 block hover:underline" href="mailto:hello@securitypassport.io">
          hello@securitypassport.io
        </a>

        <div className="mt-6 text-sm text-gray-700">Security</div>
        <a className="mt-1 block hover:underline" href="mailto:security@securitypassport.io">
          security@securitypassport.io
        </a>
      </div>
    </main>
  )
}