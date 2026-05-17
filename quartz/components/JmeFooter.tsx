import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"
import style from "./styles/footer.scss"
import { version } from "../../package.json"

interface Options {
  links: Record<string, string>
}

export default ((opts?: Options) => {
  const JmeFooter: QuartzComponent = ({ displayClass }: QuartzComponentProps) => {
    const year = new Date().getFullYear()
    const links = opts?.links ?? {}
    return (
      <footer class={`${displayClass ?? ""}`}>
        <p>
          <strong>Archivo público JM Encarnación</strong> — producción ciudadana de{" "}
          <a href="https://github.com/zer0me/jme-encarnacion">Mov. Ciudadanía Activa</a>.
          Material fuente (actas, minutas, resoluciones) es acto público según Ley Orgánica
          Municipal. Curación e interpretaciones (MOCs) bajo licencia{" "}
          <a href="https://creativecommons.org/licenses/by/4.0/deed.es">CC BY 4.0</a>.
        </p>
        <p style="font-size: 0.85em; color: var(--gray); margin-top: 0.5em;">
          No constituye asesoramiento legal. No representa la postura oficial de la Junta
          Municipal de Encarnación. Sitio generado con{" "}
          <a href="https://quartz.jzhao.xyz/">Quartz v{version}</a>. © {year}.
        </p>
        <ul>
          {Object.entries(links).map(([text, link]) => (
            <li>
              <a href={link}>{text}</a>
            </li>
          ))}
        </ul>
      </footer>
    )
  }

  JmeFooter.css = style
  return JmeFooter
}) satisfies QuartzComponentConstructor
