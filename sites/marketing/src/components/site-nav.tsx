const appUrl = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"

export default function SiteNav() {
  return (
    <header className="border-b">
      <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
        <a href="/" className="font-semibold">
          SecurityPassport
        </a>

        <nav className="flex items-center gap-5 text-sm">
          <a href="/pricing" className="hover:underline">Pricing</a>
          <a href="/security" className="hover:underline">Security</a>
          <a href="/contact" className="hover:underline">Contact</a>
          <a href={`${appUrl}/login`} className="hover:underline">Log in</a>
          <a href={`${appUrl}/signup`} className="px-3 py-1 rounded border hover:bg-gray-50">
            Sign up
          </a>
        </nav>
      </div>
    </header>
  )
}