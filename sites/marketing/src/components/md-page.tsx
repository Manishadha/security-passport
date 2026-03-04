import { readFile } from "node:fs/promises"
import path from "node:path"
import { remark } from "remark"
import html from "remark-html"

type Props = {
  title: string
  mdPathFromRepoRoot: string
}

export default async function MdPage(props: Props) {
  const repoRoot = path.resolve(process.cwd(), "..", "..")
  const filePath = path.join(repoRoot, props.mdPathFromRepoRoot)

  const md = await readFile(filePath, "utf-8")
  const processed = await remark().use(html).process(md)
  const contentHtml = processed.toString()

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-3xl font-bold mb-6">{props.title}</h1>
      <article className="prose max-w-none" dangerouslySetInnerHTML={{ __html: contentHtml }} />
    </main>
  )
}