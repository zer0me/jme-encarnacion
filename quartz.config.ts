import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

/**
 * Quartz 4 Configuration
 *
 * See https://quartz.jzhao.xyz/configuration for more information.
 */
const config: QuartzConfig = {
  configuration: {
    pageTitle: "Archivo JM Encarnación",
    pageTitleSuffix: "",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "es-ES",
    baseUrl: "zer0me.github.io/jme-encarnacion",
    ignorePatterns: [
      "private",
      "templates",
      ".obsidian",
      "raw",
      "markdown",
      "samples",
      "_tmp",
      "_tmp_compressed",
      "scripts/batches",
    ],
    defaultDateType: "modified",
    theme: {
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {
        header: "Inter",
        body: "Source Serif Pro",
        code: "JetBrains Mono",
      },
      colors: {
        lightMode: {
          light: "#faf5e6",
          lightgray: "#e8e0c8",
          gray: "#8c8266",
          darkgray: "#3d3d3d",
          dark: "#1a1a1a",
          secondary: "#1e3a5f",
          tertiary: "#c9a227",
          highlight: "rgba(201, 162, 39, 0.12)",
          textHighlight: "#c9a22788",
        },
        darkMode: {
          light: "#0f1419",
          lightgray: "#1f2933",
          gray: "#6b7a8a",
          darkgray: "#c8c0a8",
          dark: "#e8e0c8",
          secondary: "#5c8bb0",
          tertiary: "#d4af37",
          highlight: "rgba(212, 175, 55, 0.15)",
          textHighlight: "#d4af3788",
        },
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({
        priority: ["frontmatter", "git", "filesystem"],
      }),
      Plugin.SyntaxHighlighting({
        theme: {
          light: "github-light",
          dark: "github-dark",
        },
        keepBackground: false,
      }),
      Plugin.ObsidianFlavoredMarkdown({ enableInHtmlEmbed: false }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({ markdownLinkResolution: "shortest" }),
      Plugin.Description(),
      Plugin.Latex({ renderEngine: "katex" }),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({
        enableSiteMap: true,
        enableRSS: true,
      }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(),
      Plugin.NotFoundPage(),
      // Comment out CustomOgImages to speed up build time
      // Plugin.CustomOgImages(),
    ],
  },
}

export default config
