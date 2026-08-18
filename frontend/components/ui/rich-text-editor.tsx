"use client"

import { useEffect, useRef, useState } from "react"

interface RichTextEditorProps {
  value: string
  onChange: (html: string) => void
  placeholder?: string
  className?: string
  minHeight?: string
  disabled?: boolean
}

function exec(cmd: string, value?: string) {
  if (typeof document !== "undefined") {
    document.execCommand(cmd, false, value)
  }
}

function isActive(cmd: string): boolean {
  if (typeof document === "undefined") return false
  try { return document.queryCommandState(cmd) } catch { return false }
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
  const [tick, setTick] = useState(0)
  const lastValue = useRef(value)

  useEffect(() => {
    if (ref.current && ref.current.innerHTML !== (value || "")) {
      ref.current.innerHTML = value || ""
    }
  }, [])

  useEffect(() => {
    if (!ref.current) return
    if (value !== lastValue.current && value !== ref.current.innerHTML) {
      ref.current.innerHTML = value || ""
      lastValue.current = value
    }
  }, [value])

  const handleInput = () => {
    if (!ref.current) return
    const html = ref.current.innerHTML === "<br>" || ref.current.innerHTML === "" ? "" : ref.current.innerHTML
    lastValue.current = html
    onChange(html)
    setTick((t) => t + 1)
  }

  const btn = (label: string, cmd: string, cmdValue?: string) => {
    const active = isActive(cmd)
    return (
      <button
        key={cmd}
        type="button"
        title={label}
        onMouseDown={(e) => {
          e.preventDefault()
          ref.current?.focus()
          exec(cmd, cmdValue)
          setTick((t) => t + 1)
        }}
        style={{
          fontFamily: "inherit",
          fontSize: "13px",
          fontWeight: active ? "700" : "400",
          color: active ? "#1e293b" : "#475569",
          background: active ? "#e2e8f0" : "transparent",
          border: "none",
          borderRadius: "4px",
          padding: "3px 7px",
          cursor: "pointer",
          lineHeight: "1.4",
          minWidth: "24px",
        }}
      >
        {label}
      </button>
    )
  }

  return (
    <div style={{ border: "1px solid #cbd5e1", borderRadius: "6px", background: "white" }} className={className}>
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "1px",
          padding: "4px 6px",
          borderBottom: "1px solid #e2e8f0",
          background: "#f1f5f9",
          borderRadius: "6px 6px 0 0",
          minHeight: "32px",
        }}
      >
        {btn("B", "bold")}
        {btn("I", "italic")}
        {btn("S̶", "strikeThrough")}
        <div style={{ width: "1px", height: "14px", background: "#cbd5e1", margin: "0 3px" }} />
        {btn("• Lista", "insertUnorderedList")}
        {btn("1. Lista", "insertOrderedList")}
        <div style={{ width: "1px", height: "14px", background: "#cbd5e1", margin: "0 3px" }} />
        <button
          type="button"
          title="Enlace"
          onMouseDown={(e) => {
            e.preventDefault()
            const url = window.prompt("URL del enlace:", "https://")
            if (!url) return
            ref.current?.focus()
            exec("createLink", url)
            setTick((t) => t + 1)
          }}
          style={{
            fontFamily: "inherit",
            fontSize: "13px",
            color: "#475569",
            background: "transparent",
            border: "none",
            borderRadius: "4px",
            padding: "3px 7px",
            cursor: "pointer",
          }}
        >
          🔗
        </button>
        <div style={{ width: "1px", height: "14px", background: "#cbd5e1", margin: "0 3px" }} />
        {btn("↩", "undo")}
        {btn("↪", "redo")}
      </div>

      {/* Área editable */}
      <div style={{ position: "relative" }}>
        <div
          ref={ref}
          contentEditable={!disabled}
          suppressContentEditableWarning
          onInput={handleInput}
          onKeyUp={() => setTick((t) => t + 1)}
          onMouseUp={() => setTick((t) => t + 1)}
          className="rich-html"
          style={{
            minHeight,
            padding: "8px 12px",
            fontSize: "0.875rem",
            color: "#0f172a",
            outline: "none",
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
