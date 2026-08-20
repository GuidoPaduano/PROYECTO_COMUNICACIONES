/**
 * Sanitiza HTML del lado del cliente antes de pasarlo a dangerouslySetInnerHTML.
 * Conserva solo las etiquetas y atributos seguros que genera el rich-text-editor.
 * El backend ya sanitiza con bleach antes de guardar; esto es una segunda capa defensiva.
 */

const ALLOWED_TAGS = new Set([
  "p", "br", "b", "i", "u", "strong", "em",
  "ul", "ol", "li",
  "a",
  "span", "div",
])

const ALLOWED_ATTRS: Record<string, Set<string>> = {
  a: new Set(["href"]),
}

function isSafeHref(value: string): boolean {
  const lower = value.trim().toLowerCase()
  return lower.startsWith("https://") || lower.startsWith("http://") || lower.startsWith("mailto:")
}

export function sanitizeHtml(html: string): string {
  if (typeof document === "undefined" || !html) return html ?? ""

  const parser = new DOMParser()
  const doc = parser.parseFromString(html, "text/html")

  function clean(node: Node): Node | null {
    if (node.nodeType === Node.TEXT_NODE) return node.cloneNode()

    if (node.nodeType !== Node.ELEMENT_NODE) return null

    const el = node as Element
    const tag = el.tagName.toLowerCase()

    if (!ALLOWED_TAGS.has(tag)) {
      // Reemplazar el nodo por sus hijos (unwrap)
      const frag = document.createDocumentFragment()
      for (const child of Array.from(el.childNodes)) {
        const cleaned = clean(child)
        if (cleaned) frag.appendChild(cleaned)
      }
      return frag
    }

    const newEl = document.createElement(tag)

    const allowedAttrs = ALLOWED_ATTRS[tag]
    if (allowedAttrs) {
      for (const attr of Array.from(el.attributes)) {
        if (allowedAttrs.has(attr.name)) {
          if (attr.name === "href" && !isSafeHref(attr.value)) continue
          newEl.setAttribute(attr.name, attr.value)
        }
      }
    }

    if (tag === "a") {
      newEl.setAttribute("rel", "noopener noreferrer")
      newEl.setAttribute("target", "_blank")
    }

    for (const child of Array.from(el.childNodes)) {
      const cleaned = clean(child)
      if (cleaned) newEl.appendChild(cleaned)
    }

    return newEl
  }

  const result = document.createDocumentFragment()
  for (const child of Array.from(doc.body.childNodes)) {
    const cleaned = clean(child)
    if (cleaned) result.appendChild(cleaned)
  }

  const wrapper = document.createElement("div")
  wrapper.appendChild(result)
  return wrapper.innerHTML
}
