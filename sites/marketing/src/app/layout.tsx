import "./globals.css"
import SiteNav from "@/components/site-nav"
import SiteFooter from "@/components/site-footer"

export const metadata = {
  title: "SecurityPassport",
  description: "Compliance evidence organized and export-ready."
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SiteNav />
        {children}
        <SiteFooter />
      </body>
    </html>
  )
}