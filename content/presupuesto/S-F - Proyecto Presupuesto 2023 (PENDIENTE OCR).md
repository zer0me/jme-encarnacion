---
titulo: "Proyecto de Presupuesto 2023 — Municipalidad de Encarnación (PENDIENTE OCR)"
tipo: presupuesto
numero: null
fecha: null
fecha_inferida: "2022 (presupuesto del año fiscal 2023, típicamente presentado por el Ejecutivo a la Junta entre septiembre-noviembre del año previo)"
periodo_cubierto: "2023"
autor: "Municipalidad de Encarnación — Ejecutivo Municipal"
estado_procesamiento: pendiente_ocr
fuente_archivo: "raw/presupuesto/PROYECTO DE PRESUPUESTO 2023_0001.pdf"
paginas: 97
tamano_mb: 386
tipo_contenido: pdf_escaneado_imagen
texto_extraible: false
nota_curacion: "PDF escaneado de 97 páginas y 386 MB, sin texto extraíble (puro imágenes). Requiere OCR especializado (Tesseract, Ollama vision, o Workers AI). Postergado por decisión 2026-05-18 — el presupuesto es contenido mayormente tabular (cuadros, importes, partidas) menos prioritario para /preguntar que los documentos narrativos. Re-evaluar cuando se necesite cubrir consultas sobre presupuesto histórico."
calidad_ocr: pendiente
idioma: es-PY
---

# Proyecto de Presupuesto 2023 — Municipalidad de Encarnación

> **⚠ Stub de trazabilidad — Documento pendiente de OCR**

Este archivo es un placeholder que registra la existencia del PDF original en `raw/presupuesto/`, pero el contenido aún no fue procesado. El PDF es un escaneo de 97 páginas y 386 MB sin texto extraíble.

## Qué sabemos del documento (sin OCR)

- **Filename:** `PROYECTO DE PRESUPUESTO 2023_0001.pdf`
- **Naturaleza:** Proyecto de Presupuesto (proposal/draft), no presupuesto sancionado.
- **Año fiscal cubierto:** 2023.
- **Tipo:** Documento institucional del Ejecutivo Municipal a la Junta Municipal de Encarnación, en el marco del proceso de aprobación del presupuesto anual previsto por la Ley 3966/2010 Orgánica Municipal.
- **Tamaño:** 386 MB (97 páginas escaneadas en alta resolución).

## Por qué está pendiente

OCR de PDF escaneado requiere infraestructura adicional:
- Tesseract local (no instalado al momento de la curación 2026-05-18).
- Ollama con modelo visión local (disponible, pero 1-2hs de proceso para 97 pp).
- Workers AI Cloudflare (gratis pero consume el cupo diario de 10K Neurons en este documento).

Se postergó por decisión del usuario (2026-05-18): el contenido tabular del presupuesto tiene menor prioridad para `/preguntar` que los documentos narrativos (actas, dictámenes, minutas) que ya están procesados.

## Cómo retomar

Cuando se decida procesar:

1. Elegir motor de OCR (Tesseract / Ollama llava / Workers AI).
2. Convertir cada página del PDF a imagen (ej. `pdftoppm` de Poppler, ya instalado).
3. OCR cada imagen, concatenar texto.
4. Generar markdown estructurado siguiendo el template del archivo `2021-12-31 - Presupuesto S-N.md`.
5. Eliminar este stub y reemplazar por el archivo curado real con fecha + nombre canónicos.

## Documentos relacionados ya curados

- `2021-12-31 - Presupuesto S-N.md` — Anexo Balance General + Ejecución Presupuestaria 2021.
