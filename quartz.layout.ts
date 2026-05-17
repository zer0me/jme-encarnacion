import { PageLayout, SharedLayout } from "./quartz/cfg"
import * as Component from "./quartz/components"

// Las funciones que pasamos a Explorer se serializan con .toString() y se
// evalúan en el browser. Por eso TODAS las constantes que usan tienen que
// estar inline dentro de cada función (no pueden referenciar variables del
// módulo, que no existen en el browser).
const jmeExplorer = Component.Explorer({
  title: "Navegar archivo",
  folderClickBehavior: "collapse",
  folderDefaultState: "collapsed",
  useSavedState: true,
  filterFn: (node) => {
    const HIDDEN_ROOT_FILES = [
      "Escuela Taller",
      "José Ayala",
      "Juan Luis Regis González",
      "Mujeres Programando",
    ]
    if (node.slugSegment === "tags") return false
    if (node.isFolder && node.children.length === 0) return false
    const isRootFile =
      !node.isFolder && node.slug.split("/").filter(Boolean).length === 1
    if (isRootFile && HIDDEN_ROOT_FILES.includes(node.displayName)) return false
    return true
  },
  sortFn: (a, b) => {
    const FOLDER_PRIORITY: Record<string, number> = {
      _MOCs: 0,
      actas: 10,
      minutas: 11,
      resoluciones: 12,
      "informe-gestion": 13,
      "informe-2024": 14,
      presupuesto: 15,
      personas: 20,
      instituciones: 21,
      empresas: 22,
      normativa: 30,
      temas: 31,
    }
    if (a.isFolder && !b.isFolder) return -1
    if (!a.isFolder && b.isFolder) return 1
    if (a.isFolder && b.isFolder) {
      const aPriority = FOLDER_PRIORITY[a.slugSegment ?? ""]
      const bPriority = FOLDER_PRIORITY[b.slugSegment ?? ""]
      const aHas = aPriority !== undefined
      const bHas = bPriority !== undefined
      if (aHas && bHas) return aPriority - bPriority
      if (aHas) return -1
      if (bHas) return 1
    }
    return a.displayName.localeCompare(b.displayName, undefined, {
      numeric: true,
      sensitivity: "base",
    })
  },
  mapFn: (node) => {
    const FOLDER_LABELS: Record<string, string> = {
      _MOCs: "🗺️ Mapas temáticos (MOCs)",
      actas: "📋 Documentos · Actas",
      minutas: "📋 Documentos · Minutas",
      resoluciones: "📋 Documentos · Resoluciones",
      "informe-gestion": "📋 Documentos · Informes",
      "informe-2024": "📋 Documentos · Informe 2024",
      presupuesto: "📋 Documentos · Presupuesto",
      personas: "👥 Actores · Personas",
      instituciones: "👥 Actores · Instituciones",
      empresas: "👥 Actores · Empresas",
      normativa: "📜 Referencias · Normativa",
      temas: "📜 Referencias · Temas",
    }
    if (node.isFolder && node.slugSegment && FOLDER_LABELS[node.slugSegment]) {
      node.displayName = FOLDER_LABELS[node.slugSegment]
    }
  },
  order: ["filter", "sort", "map"],
})

// components shared across all pages
export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [],
  afterBody: [],
  footer: Component.JmeFooter({
    links: {
      "Repo público (GitHub)": "https://github.com/zer0me/jme-encarnacion",
      "Reportar un error": "https://github.com/zer0me/jme-encarnacion/issues/new",
      "Licencia CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/deed.es",
    },
  }),
}

// components for pages that display a single page (e.g. a single note)
export const defaultContentPageLayout: PageLayout = {
  beforeBody: [
    Component.ConditionalRender({
      component: Component.Breadcrumbs(),
      condition: (page) => page.fileData.slug !== "index",
    }),
    Component.ArticleTitle(),
    Component.ContentMeta(),
    Component.TagList(),
  ],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
        { Component: Component.ReaderMode() },
      ],
    }),
    jmeExplorer,
  ],
  right: [
    Component.Graph(),
    Component.DesktopOnly(Component.TableOfContents()),
    Component.Backlinks(),
  ],
}

// components for pages that display lists of pages  (e.g. tags or folders)
export const defaultListPageLayout: PageLayout = {
  beforeBody: [Component.Breadcrumbs(), Component.ArticleTitle(), Component.ContentMeta()],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
      ],
    }),
    jmeExplorer,
  ],
  right: [],
}
