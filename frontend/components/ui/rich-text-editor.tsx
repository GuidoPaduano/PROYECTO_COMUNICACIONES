"use client"

import { useEffect, useRef, useState } from "react"
import {
  Bold,
  Italic,
  Strikethrough,
  List,
  ListOrdered,
  Link as LinkIcon,
  Undo,
  Redo,
} from "lucide-react"

interface RichTextEditorProps {
  value: string
  onChange: (html: string) => void
  placeholder?: string
  className?: string
  minHeight?: string
  disabled?: boolean
}

function ToolbarButton({
  onClick,
  active,
  disabled,
  title,
  children,
}: {
  onClick: () => void
  active?: boolean
  disabled?: boolean
  title: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => {
        e.preventDefault()
        onClick()
      }}
      disabled={disabled}
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "4px",
        borderRadius: "4px",
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        background: active ? "#e2e8f0" : "transparent",
        color: active ? "#0f172a" : "#475569",
        opacity: disabled ? 0.4 : 1,
        lineHeight: 1,
      }}
    >
      {children}
    </button>
  )
}

// Llama a document.execCommand de forma segura (deprecated pero universal)
function exec(cmd: string, value?: string) {
  document.execCommand(cmd, false, value)
}

export function RichTextEditor({
  value,
  onChange,
  placeholder = "Escribí tu mensaje...",
  className = "",
  minHeight = "120px",
  disabled = false,
}: RichTextEditorProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [, forceUpdate] = useState(0)
  const isComposing = useRef(false)
  const lastValue = useRef(value)

  // Inicializar contenido
  useEffect(() => {
    if (!ref.current) return
    if (ref.current.innerHTML !== (value || "")) {
      ref.current.innerHTML = value || ""
    }
  }, []) // Solo al montar

  // Sincronizar valor externo (ej: al limpiar form)
  useEffect(() => {
    if (!ref.current) return
    if (value !== lastValue.current && value !== ref.current.innerHTML) {
      ref.current.innerHTML = value || ""
      lastValue.current = value
    }
  }, [value])

  useEffect(() => {
    if (ref.current) {
      ref.current.contentEditable = disabled ? "false" : "true"
    }
  }, [disabled])

  const handleInput = () => {
    if (!ref.current || isComposing.current) return
    const html = ref.current.innerHTML === "<br>" ? "" : ref.current.innerHTML
    lastValue.current = html
    onChange(html)
    forceUpdate((n) => n + 1)
  }

  const queryState = (cmd: string) => {
    if (typeof document === "undefined") return false
    try { return document.queryCommandState(cmd) } catch { return false }
  }

  const queryEnabled = (cmd: string) => {
    if (typeof document === "undefined") return false
    try { return document.queryCommandEnabled(cmd) } catch { return false }
  }

  const handleLink = () => {
    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0) return
    const existingLink = (() => {
      let node: Node | null = selection.anchorNode
      while (node && node !== ref.current) {
        if ((node as Element).tagName === "A") return (node as HTMLAnchorElement).href
        node = node.parentNode
      }
      return null
    })()
    const url = window.prompt("URL del enlace:", existingLink || "https://")
    if (url === null) return
    if (url === "") {
      exec("unlink")
    } else {
      exec("createLink", url)
    }
    handleInput()
  }

  const isActive = (cmd: string) => {
    if (typeof document === "undefined") return false
    try { return document.queryCommandState(cmd) } catch { return false }
  }

  const insertList = (type: "insertUnorderedList" | "insertOrderedList") => {
    ref.current?.focus()
    exec(type)
    handleInput()
  }

  const showPlaceholder = !value && ref.current?.innerHTML === ""

  return (
    <div
      className={`rounded-md bg-white ${className}`}
      style={{ border: "1px solid #cbd5e1" }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "2px",
          padding: "4px 6px",
          borderBottom: "1px solid #e2e8f0",
          backgroundColor: "#f8fafc",
          borderRadius: "6px 6px 0 0",
        }}
      >
        <ToolbarButton onClick={() => { ref.current?.focus(); exec("bold"); forceUpdate(n => n+1) }} active={isActive("bold")} title="Negrita (Ctrl+B)">
          <Bold style={{ width: 15, height: 15 }} />
        </ToolbarButton>
        <ToolbarButton onClick={() => { ref.current?.focus(); exec("italic"); forceUpdate(n => n+1) }} active={isActive("italic")} title="Cursiva (Ctrl+I)">
          <Italic style={{ width: 15, height: 15 }} />
        </ToolbarButton>
        <ToolbarButton onClick={() => { ref.current?.focus(); exec("strikeThrough"); forceUpdate(n => n+1) }} active={isActive("strikeThrough")} title="Tachado">
          <Strikethrough style={{ width: 15, height: 15 }} />
        </ToolbarButton>

        <div style={{ width: 1, height: 14, background: "#cbd5e1", margin: "0 2px" }} />

        <ToolbarButton onClick={() => insertList("insertUnorderedList")} active={isActive("insertUnorderedList")} title="Lista con viñetas">
          <List style={{ width: 15, height: 15 }} />
        </ToolbarButton>
        <ToolbarButton onClick={() => insertList("insertOrderedList")} active={isActive("insertOrderedList")} title="Lista numerada">
          <ListOrdered style={{ width: 15, height: 15 }} />
        </ToolbarButton>

        <div style={{ width: 1, height: 14, background: "#cbd5e1", margin: "0 2px" }} />

        <ToolbarButton onClick={handleLink} title="Insertar enlace">
          <LinkIcon style={{ width: 15, height: 15 }} />
        </ToolbarButton>

        <div style={{ width: 1, height: 14, background: "#cbd5e1", margin: "0 2px" }} />

        <ToolbarButton onClick={() => { ref.current?.focus(); exec("undo"); forceUpdate(n => n+1) }} disabled={!queryEnabled("undo")} title="Deshacer (Ctrl+Z)">
          <Undo style={{ width: 15, height: 15 }} />
        </ToolbarButton>
        <ToolbarButton onClick={() => { ref.current?.focus(); exec("redo"); forceUpdate(n => n+1) }} disabled={!queryEnabled("redo")} title="Rehacer (Ctrl+Y)">
          <Redo style={{ width: 15, height: 15 }} />
        </ToolbarButton>
      </div>

      {/* Área editable */}
      <div style={{ position: "relative" }}>
        <div
          ref={ref}
          contentEditable={!disabled}
          suppressContentEditableWarning
          onInput={handleInput}
          onKeyUp={() => forceUpdate((n) => n + 1)}
          onMouseUp={() => forceUpdate((n) => n + 1)}
          onCompositionStart={() => { isComposing.current = true }}
          onCompositionEnd={() => { isComposing.current = false; handleInput() }}
          className="rich-html"
          style={{
            minHeight,
            padding: "8px 12px",
            fontSize: "0.875rem",
            color: "#0f172a",
            outline: "none",
            overflowY: "auto",
          }}
        />
        {!value && (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              padding: "8px 12px",
              fontSize: "0.875rem",
              color: "#94a3b8",
              pointerEvents: "none",
              userSelect: "none",
            }}
          >
            {placeholder}
          </div>
        )}
      </div>
    </div>
  )
}
