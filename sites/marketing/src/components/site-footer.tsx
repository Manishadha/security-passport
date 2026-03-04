export default function SiteFooter() {
  return (
    <footer className="border-t mt-16">
      <div className="mx-auto max-w-6xl px-6 py-8 text-sm flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="text-gray-600">
          © {new Date().getFullYear()} SecurityPassport
        </div>

        <nav className="flex gap-4">
          <a href="/legal/privacy" className="hover:underline">Privacy</a>
          <a href="/legal/terms" className="hover:underline">Terms</a>
          <a href="/legal/cookies" className="hover:underline">Cookies</a>
        </nav>
      </div>
    </footer>
  )
}