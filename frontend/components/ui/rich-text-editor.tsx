"use client"

import { useEditor, EditorContent } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import Link from "@tiptap/extension-link"
import Placeholder from "@tiptap/extension-placeholder"
import { useEffect, useState } from "react"
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
        cursor: "pointer",
        background: active ? "#e2e8f0" : "transparent",
        color: active ? "#0f172a" : "#64748b",
        opacity: disabled ? 0.4 : 1,
      }}
    >
      {children}
    </button>
  )
}

export function RichTextEditor({
  value,
  onChange,
  placeholder = "Escribí tu mensaje...",
  className = "",
  minHeight = "120px",
  disabled = false,
}: RichTextEditorProps) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        horizontalRule: false,
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: "text-blue-600 underline" },
      }),
      Placeholder.configure({ placeholder }),
    ],
    content: value,
    editable: !disabled,
    onUpdate({ editor }) {
      const html = editor.isEmpty ? "" : editor.getHTML()
      onChange(html)
    },
  })

  useEffect(() => {
    if (!editor) return
    const current = editor.isEmpty ? "" : editor.getHTML()
    if (value !== current) {
      editor.commands.setContent(value || "", { emitUpdate: false })
    }
  }, [value, editor])

  useEffect(() => {
    editor?.setEditable(!disabled)
  }, [disabled, editor])

  const setLink = () => {
    const prev = editor?.getAttributes("link").href || ""
    const url = window.prompt("URL del enlace:", prev)
    if (url === null) return
    if (url === "") {
      editor?.chain().focus().unsetLink().run()
      return
    }
    editor?.chain().focus().setLink({ href: url }).run()
  }

  // Placeholder mientras carga en el cliente
  if (!mounted || !editor) {
    return (
      <div
        className={`rounded-md border border-slate-300 bg-white ${className}`}
        style={{ minHeight }}
      />
    )
  }

  return (
    <div
      className={`rounded-md border border-slate-300 bg-white ${className}`}
      style={{ outline: "none" }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "2px",
          borderBottom: "1px solid #e2e8f0",
          padding: "4px 8px",
          background: "#f8fafc",
          borderRadius: "6px 6px 0 0",
        }}
      >
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBold().run()}
          active={editor.isActive("bold")}
          title="Negrita (Ctrl+B)"
        >
          <Bold style={{ width: 16, height: 16 }} />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleItalic().run()}
          active={editor.isActive("italic")}
          title="Cursiva (Ctrl+I)"
        >
          <Italic style={{ width: 16, height: 16 }} />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleStrike().run()}
          active={editor.isActive("strike")}
          title="Tachado"
        >
          <Strikethrough style={{ width: 16, height: 16 }} />
        </ToolbarButton>

        <div style={{ width: 1, height: 16, background: "#cbd5e1", margin: "0 4px" }} />

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          active={editor.isActive("bulletList")}
          title="Lista con viñetas"
        >
          <List style={{ width: 16, height: 16 }} />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          active={editor.isActive("orderedList")}
          title="Lista numerada"
        >
          <ListOrdered style={{ width: 16, height: 16 }} />
        </ToolbarButton>

        <div style={{ width: 1, height: 16, background: "#cbd5e1", margin: "0 4px" }} />

        <ToolbarButton
          onClick={setLink}
          active={editor.isActive("link")}
          title="Insertar enlace"
        >
          <LinkIcon style={{ width: 16, height: 16 }} />
        </ToolbarButton>

        <div style={{ width: 1, height: 16, background: "#cbd5e1", margin: "0 4px" }} />

        <ToolbarButton
          onClick={() => editor.chain().focus().undo().run()}
          disabled={!editor.can().undo()}
          title="Deshacer (Ctrl+Z)"
        >
          <Undo style={{ width: 16, height: 16 }} />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().redo().run()}
          disabled={!editor.can().redo()}
          title="Rehacer (Ctrl+Y)"
        >
          <Redo style={{ width: 16, height: 16 }} />
        </ToolbarButton>
      </div>

      {/* Área de texto */}
      <EditorContent
        editor={editor}
        className="rich-html px-3 py-2 text-sm text-slate-900 focus:outline-none [&_.ProseMirror]:outline-none [&_.ProseMirror_p.is-editor-empty:first-child::before]:pointer-events-none [&_.ProseMirror_p.is-editor-empty:first-child::before]:float-left [&_.ProseMirror_p.is-editor-empty:first-child::before]:h-0 [&_.ProseMirror_p.is-editor-empty:first-child::before]:text-slate-400 [&_.ProseMirror_p.is-editor-empty:first-child::before]:content-[attr(data-placeholder)]"
        style={{ "--editor-min-h": minHeight, minHeight } as React.CSSProperties}
      />
    </div>
  )
}
